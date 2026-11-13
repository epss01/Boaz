import numpy as np
import pytest

from boaz.config import Settings
from boaz.recognition import (OCR, Profile, Rect, RecognitionError, Recognizer,
                              Slot, load_profile, record_asset, save_profile)


class FakeOCR:
    def check(self):
        pass

    def number(self, crop):
        return int(crop[0, 0, 0])

    def text(self, crop):
        return "Wall"


@pytest.fixture
def scene(tmp_path):
    frame = np.random.default_rng(7).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    profile = Profile(width=320, height=240)
    record_asset(tmp_path, profile, "home", frame, Rect(x=0, y=0, width=40, height=40))
    rec = Recognizer(tmp_path, profile, FakeOCR())
    return frame, profile, rec


def test_profile_and_second_capture_validation(scene, tmp_path):
    frame, profile, rec = scene
    with pytest.raises(RecognitionError, match="second capture"):
        rec.expect("home", frame)
    assert "Match" in rec.validate_asset("home", frame.copy())
    rec.expect("home", frame)
    assert rec.confidence > 0.99
    changed = frame.copy()
    changed[:40, :40] = 0
    with pytest.raises(RecognitionError):
        rec.expect("home", changed)
    save_profile(tmp_path, "village", profile)
    assert load_profile(tmp_path, "village") == profile
    with pytest.raises(ValueError):
        save_profile(tmp_path, "../escape", profile)


def test_unknown_overlay_resolution_and_camera(scene, tmp_path):
    frame, profile, rec = scene
    rec.validate_asset("home", frame)
    record_asset(tmp_path, profile, "home.camera", frame, Rect(x=50, y=50, width=30, height=30))
    rec.validate_asset("home.camera", frame)
    changed = frame.copy()
    changed[50:80, 50:80] = 0
    assert not rec.matches("home.camera", changed)
    with pytest.raises(RecognitionError, match="dimensions"):
        rec.expect("home", frame[:200])
    with pytest.raises(RecognitionError):
        rec.expect("home", np.zeros_like(frame))


@pytest.mark.parametrize("text,expected", [("0", 0), ("100000", 100000), ("1 234 567", 1234567), ("1,234", 1234)])
def test_number_parser(text, expected):
    assert OCR.parse_number(text) == expected


@pytest.mark.parametrize("text", ["", "10K", "1.2M", "-10", "12 34", "123O", "1,23", "100 gold", "×10"])
def test_number_parser_rejects_ambiguous_values(text):
    with pytest.raises(RecognitionError):
        OCR.parse_number(text)


def test_inconsistent_ocr_validation(scene, tmp_path):
    frame, profile, rec = scene
    frame[100, 100] = 12
    record_asset(tmp_path, profile, "base.gold", frame, Rect(x=100, y=100, width=10, height=10), "number")
    changed = frame.copy()
    changed[100, 100] = 13
    with pytest.raises(RecognitionError, match="disagree"):
        rec.validate_asset("base.gold", changed)
    assert not profile.assets["base.gold"].validated


def test_missing_calibration_blocks_live(scene):
    _, _, rec = scene
    with pytest.raises(RecognitionError, match="incomplete"):
        rec.ready(Settings())


def test_roster_guard_detects_new_unconfigured_slot(scene, tmp_path):
    frame, profile, rec = scene
    record_asset(tmp_path, profile, "base.roster", frame, Rect(x=0, y=100, width=300, height=100))
    record_asset(tmp_path, profile, "base.troop.1.ready", frame, Rect(x=10, y=110, width=40, height=40))
    record_asset(tmp_path, profile, "base.troop.1.area", frame, Rect(x=10, y=110, width=40, height=40))
    rec.validate_asset("base.roster", frame)
    changed = frame.copy()
    changed[110:150, 10:50] = 0
    assert rec.matches("base.roster", changed)
    changed[100:200, 150:300] = 0
    assert not rec.matches("base.roster", changed)


def test_hero_deployed_and_spell_depleted_are_distinct(scene, tmp_path):
    frame, profile, rec = scene
    region = Rect(x=100, y=100, width=30, height=30)
    for state in ("ready", "unavailable", "deployed"):
        sample = np.random.default_rng(len(state)).integers(0, 255, frame.shape, dtype=np.uint8)
        record_asset(tmp_path, profile, f"battle.hero.1.{state}", sample, region)
        rec.validate_asset(f"battle.hero.1.{state}", sample)
        if state == "deployed":
            deployed = sample
    assert rec.slot_state("battle", Slot(kind="hero", slot=1), deployed) == ("deployed", 0)
    with pytest.raises(RecognitionError):
        rec.slot_state("battle", Slot(kind="hero", slot=1), np.zeros_like(frame))
    for index, state in enumerate(("ready", "unavailable", "depleted")):
        sample = np.random.default_rng(100 + index).integers(0, 255, frame.shape, dtype=np.uint8)
        record_asset(tmp_path, profile, f"battle.spell.1.{state}", sample, region)
        rec.validate_asset(f"battle.spell.1.{state}", sample)
    assert rec.slot_state("battle", Slot(kind="spell", slot=1), sample) == ("depleted", 0)
