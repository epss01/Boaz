import json

import pytest
from pydantic import ValidationError

from boaz import config
from boaz.config import Settings, load_settings, preset_path, save_settings


def test_round_trip(tmp_path):
    settings = Settings()
    settings.farming.min_gold = 999000
    path = preset_path(tmp_path, "harvest-1")
    save_settings(path, settings)
    assert load_settings(path) == settings


@pytest.mark.parametrize("name", ["../escape", "bad/name", "", "CON", "LPT1", "a" * 49])
def test_preset_name_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        preset_path(tmp_path, name)


@pytest.mark.parametrize("change", [
    {"farming": {"min_gold": -1}},
    {"farming": {"search_limit": 0}},
    {"farming": {"attack": "false"}},
    {"farming": {"deployment": []}},
    {"session": {"duration_minutes": float("nan")}},
    {"session": {"attack_limit": 2.5}},
    {"walls": {"enabled": True}},
    {"walls": {"currency": "gems"}},
    {"calibration": {"width": 320, "height": 720}},
    {"calibration": {"walls": [{"x": 99999, "y": 0}]}},
    {"farming": {"collect": False, "attack": False}},
    {"unexpected": True},
])
def test_invalid_configuration(change):
    data = Settings().model_dump()
    for key, value in change.items():
        if isinstance(value, dict):
            data[key].update(value)
        else:
            data[key] = value
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_failed_save_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "farm.json"
    save_settings(path, Settings())
    original = path.read_bytes()
    changed = Settings()
    changed.farming.min_gold = 300000
    def fail(*args):
        raise OSError("Disk unavailable")
    monkeypatch.setattr(config.os, "replace", fail)
    with pytest.raises(OSError):
        save_settings(path, changed)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_settings_do_not_replace_existing_file(tmp_path):
    path = tmp_path / "farm.json"
    save_settings(path, Settings())
    bad = Settings()
    bad.farming.min_gold = -100
    with pytest.raises(ValidationError):
        save_settings(path, bad)
    assert load_settings(path) == Settings()


def test_default_json_matches_model():
    from pathlib import Path
    default = Path(__file__).parents[1] / "config" / "default.json"
    assert json.loads(default.read_text()) == Settings().model_dump()
