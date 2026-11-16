import numpy as np
import pytest
from pathlib import Path
import cv2

from boaz.config import Settings
from boaz.recognition import (OCR, Profile, Rect, RecognitionError, Recognizer,
                              Slot, load_profile, record_asset, save_profile)


class FakeOCR:
    def count(self, crop):
        return self.number(crop)
    def check(self):
        pass

    def number(self, crop):
        return int(crop[0, 0, 0])

    def text(self, crop):
        return "Wall"


@pytest.mark.parametrize('capture,heroes,skipped',[
    ('queen-card-preview',1,{'hero.1'}),('king-card-preview',1,{'hero.1'}),
    ('three-hero-preview',3,{'hero.2','hero.3'}),
    ('two-hero-preview',2,{'hero.2'}),('four-slot-base-second',0,set())])
def test_card_library_survives_hero_changes(capture,heroes,skipped):
    root = Path(__file__).parent/'fixtures'
    profile = load_profile(root,'historic-hero-cards')
    profile.inventory_profiles = ['queen-away','heroes-unavailable','king-card','three-hero-geometry']
    rec = Recognizer(root,profile,OCR('',root/'numeric-font'))
    rec._ready_profiles = rec._inventory_profiles[1:3]
    frame = cv2.imread(str(root/(capture+'.png')))
    rec.select_inventory(frame)
    assert rec.skipped_heroes == skipped
    assert sum(s.kind=='hero' for s in rec.profile.slots) == heroes
    counts = {s.key:rec.slot_state('base',s,frame)[1] for s in rec.profile.slots}
    assert [counts[k] for k in ('troop.1','troop.2','spell.1','spell.2')] == [35,1,5,1]
    if capture == 'king-card-preview':
        frame[600:690,308:398] = 0
        with pytest.raises(RecognitionError):
            rec.select_inventory(frame)
    assert rec.ocr.count(cv2.imread(str(root/'king-selected-34.png'))) == 34


def test_resource_ocr_with_buildings_behind_the_labels():
    root = Path(__file__).parent/'fixtures'
    rec = Recognizer(root,load_profile(root,'queen-away'),OCR('',root/'numeric-font'))
    frame = cv2.imread(str(root/'king-base-loot.png'))
    assert [rec.read('base.'+key,frame) for key in ('gold','elixir','dark_elixir')] == [238706,211099,7283]
    other = cv2.imread(str(root/'scenery-elixir-loot.png'))
    assert rec.read('base.elixir',other) == 587828
    wall = cv2.imread(str(root/'selected-wall-yellow-level.png'))
    rec.profile.assets['wall.level'] = rec.asset('base.elixir').model_copy(
        update={'rect':Rect(x=720,y=465,width=31,height=27)})
    assert rec.read('wall.level',wall) == 12


def test_selected_warden_remains_ready_without_matching_deployed_state():
    root = Path(__file__).parent/'fixtures'
    profile = load_profile(root,'historic-hero-cards')
    profile.inventory_profiles = ['queen-away','heroes-unavailable','king-card','three-hero-geometry']
    rec = Recognizer(root,profile,OCR('',root/'numeric-font'))
    rec._ready_profiles = rec._inventory_profiles[1:3]
    rec.select_inventory(cv2.imread(str(root/'three-hero-preview.png')))
    frame = cv2.imread(str(root/'warden-selected-three-heroes.png'))
    hero = next(s for s in rec.profile.slots if s.key == 'hero.1')
    assert rec.slot_state('battle',hero,frame) == ('ready',1)
    assert not rec.matches('battle.hero.1.deployed',frame)
    for name in ('warden-selected-deployed.png','warden-selected-deployed-second.png'):
        deployed = cv2.imread(str(root/name))
        assert rec.slot_state('battle',hero,deployed) == ('deployed',0)
        assert not rec.matches('battle.hero.1.ready',deployed)
    shifted = cv2.imread(str(root/'shifted-freeze-count.png'))
    freeze = next(s for s in rec.profile.slots if s.key == 'spell.2')
    assert rec.slot_state('battle',freeze,shifted) == ('ready',1)


def test_real_two_and_three_row_results_require_positive_layout():
    root = Path(__file__).parent / 'fixtures'
    p = load_profile(root, 'result-layouts')
    rec = Recognizer(root, p, OCR('', root / 'numeric-font'))
    two = cv2.imread(str(root/'result-two.png'))
    three = cv2.imread(str(root/'result-three.png'))
    assert rec.result_loot(two) == dict(gold=414174,elixir=215507,dark_elixir=0)
    assert rec.result_loot(three) == dict(gold=89145,elixir=83289,dark_elixir=203)
    missing = two.copy()
    missing[280:460] = 0
    with pytest.raises(RecognitionError, match='exactly one'):
        rec.result_loot(missing)
    p.assets['results.three.anchor'] = p.assets['results.two.anchor'].model_copy(deep=True)
    rec._images.clear()
    with pytest.raises(RecognitionError, match='exactly one'):
        rec.result_loot(two)


def test_observed_boundary_requires_clear_ground(scene):
    root = Path(__file__).parent / 'fixtures'
    profile = load_profile(root,'queen-away')
    rec = Recognizer(root,profile,FakeOCR())
    frame = cv2.imread(str(root/'placement-boundary.png'))
    x,y = rec.deployment_corner(frame)
    assert 503 <= x <= 512 and 420 <= y <= 430
    blocked = frame.copy()
    blocked[y-9:y+10,x-9:x+10] = 0
    with pytest.raises(RecognitionError,match='clear ground'):
        rec.deployment_corner(blocked)
    with pytest.raises(RecognitionError,match='boundary'):
        rec.deployment_corner(np.zeros_like(frame))
    inner_wall = cv2.imread(str(root/'placement-inner-wall.png'))
    with pytest.raises(RecognitionError, match='boundary'):
        rec.deployment_corner(inner_wall)
    minimum = cv2.imread(str(root/'placement-minimum-zoom.png'))
    x,y = rec.deployment_corner(minimum)
    assert 168 <= x <= 180 and 345 <= y <= 365


def test_real_hidden_boundary_is_rejected_before_deployment():
    from boaz.recognition import PlacementUnavailable
    root = Path(__file__).parent / 'fixtures'
    rec = Recognizer(root, load_profile(root, 'queen-away'), FakeOCR())
    frame = cv2.imread(str(root / 'placement-hidden-boundary.png'))
    with pytest.raises(PlacementUnavailable, match='boundary'):
        rec.deployment_corner(frame)


def test_shifted_portrait_matches_but_unavailable_grey_portrait_does_not():
    root = Path(__file__).parent/'fixtures'
    rec = Recognizer(root,load_profile(root,'queen-away'),FakeOCR())
    frame = cv2.imread(str(root/'four-slot-ready.png'))
    assert rec.matches('base.troop.1.ready',frame)
    grey = cv2.cvtColor(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    assert not rec.matches('base.troop.1.ready',grey)


def test_calibrated_font_reads_real_wallets_counts_and_discounted_price():
    root = Path(__file__).parent / 'fixtures'
    ocr = OCR('', root / 'numeric-font')
    for path in root.glob('number-*.png'):
        expected = int(path.stem.rsplit('-', 1)[1])
        assert ocr.number(cv2.imread(str(path))) == expected
    for text in ('10K', '1.2M', '-10', 'unknown'):
        crop = np.zeros((40, 180, 3), dtype=np.uint8)
        cv2.putText(crop, text, (2, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        with pytest.raises(RecognitionError):
            ocr.number(crop)


def test_full_multiplier_label_never_turns_clipped_x_into_a_leading_one():
    root=Path(__file__).parent/'fixtures'
    ocr=OCR('',root/'numeric-font')
    for index,expected in enumerate((35,34,31,35)):
        crop=cv2.imread(str(root/f'count-label-{index}.png'))
        assert ocr.count(crop)==expected
        with pytest.raises(RecognitionError): ocr.number(crop)
    with pytest.raises(RecognitionError):
        ocr.count(cv2.imread(str(root/'count-clipped-31.png')))
    with pytest.raises(RecognitionError):
        ocr.count(cv2.imread(str(root/'count-clipped-34.png')))
    assert ocr.count(cv2.imread(str(root/'count-label-30.png')))==30
    for name in ('count-label-29.png','count-label-29-second.png'):
        assert ocr.count(cv2.imread(str(root/name)))==29
    assert ocr.count(cv2.imread(str(root/'count-rage-4.png')))==4
    for count in (4,3,2,1):
        assert ocr.count(cv2.imread(str(root/f'count-rage-production-{count}.png')))==count
    for name in ('count-freeze-1.png','count-freeze-1-second.png'):
        assert ocr.count(cv2.imread(str(root/name)))==1


def test_numeric_font_must_be_complete_and_unambiguous(tmp_path):
    with pytest.raises(RecognitionError, match='missing or invalid'):
        OCR('', tmp_path)
    root = Path(__file__).parent / 'fixtures'
    ocr = OCR('', root / 'numeric-font')
    ocr.digits['8'] = ocr.digits['3']
    with pytest.raises(RecognitionError):
        ocr.number(cv2.imread(str(root / 'number-0-1993262.png')))


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


def test_readiness_reports_all_configuration_and_calibration_blockers(scene):
    _, _, rec = scene
    cfg = Settings()
    cfg.farming.collect = True
    cfg.calibration.width = 1280
    with pytest.raises(RecognitionError) as caught:
        rec.ready(cfg)
    message = str(caught.value)
    assert 'Calibration incomplete' in message
    assert 'resolution differs' in message
    assert 'Mark at least one collector' in message
    assert 'Deployment steps must cover' in message


def test_inventory_profile_selection_is_unique_and_updates_slot_coordinates(scene, tmp_path, monkeypatch):
    _, primary, _ = scene
    primary.slots = [Slot(kind='hero', slot=1), Slot(kind='hero', slot=2)]
    alternative = primary.model_copy(deep=True)
    alternative.slots.pop()
    alternative.assets['base.hero.1.ready'] = alternative.assets['home'].model_copy(deep=True)
    alternative.assets['base.hero.1.ready'].rect.x = 100
    save_profile(tmp_path, 'queen-unavailable', alternative)
    primary.inventory_profiles = ['queen-unavailable']
    rec = Recognizer(tmp_path, primary, FakeOCR())
    monkeypatch.setattr(Recognizer, 'expect', lambda *args: None)
    monkeypatch.setattr(Recognizer, 'matches', lambda self, name, frame: len(self.profile.slots) == frame)
    monkeypatch.setattr(Recognizer, 'slot_state', lambda *args: ('ready', 1))
    rec.select_inventory(1)
    assert len(rec.profile.slots) == 1
    assert rec.asset('base.hero.1.ready', validated=False).rect.x == 100
    rec.select_inventory(2)
    assert len(rec.profile.slots) == 2
    with pytest.raises(RecognitionError, match='found 0'):
        rec.select_inventory(3)
    monkeypatch.setattr(Recognizer, 'matches', lambda *args: True)
    with pytest.raises(RecognitionError, match='found 2'):
        rec.select_inventory(1)


def test_inventory_profile_references_cannot_recurse(scene, tmp_path):
    _, profile, _ = scene
    profile.inventory_profiles = ['nested']
    save_profile(tmp_path, 'nested', profile)
    with pytest.raises(RecognitionError, match='cannot reference'):
        Recognizer(tmp_path, profile, FakeOCR())


def test_readiness_initializes_from_complete_alternative(scene, tmp_path, monkeypatch):
    _, primary, _ = scene
    primary.slots = [Slot(kind='hero', slot=1), Slot(kind='hero', slot=2)]
    alternative = primary.model_copy(deep=True)
    alternative.slots.pop()
    save_profile(tmp_path, 'queen-unavailable', alternative)
    primary.inventory_profiles = ['queen-unavailable']
    rec = Recognizer(tmp_path, primary, FakeOCR())
    def check(candidate, settings):
        if len(candidate.profile.slots) == 2:
            raise RecognitionError('Missing deployed state')
    monkeypatch.setattr(Recognizer, '_ready_current', check)
    rec.ready(Settings())
    assert [name for name, _ in rec._ready_profiles] == ['queen-unavailable']
    assert len(rec.profile.slots) == 1


def test_real_five_slot_layout_ready_and_consumed_states():
    root = Path(__file__).parent / 'fixtures'
    profile = load_profile(root, 'queen-away')
    rec = Recognizer(root, profile, OCR('', root / 'numeric-font'))
    ready = cv2.imread(str(root / 'queen-away-base-second.png'))
    expected = {'troop.1': 35, 'troop.2': 1, 'hero.1': 1, 'spell.1': 5, 'spell.2': 1}
    assert {s.key: rec.slot_state('base', s, ready)[1] for s in profile.slots} == expected
    for name in ('depleted', 'depleted-second'):
        consumed = cv2.imread(str(root / f'queen-away-{name}.png'))
        for slot in profile.slots:
            assert rec.slot_state('battle', slot, consumed) == ('deployed' if slot.kind == 'hero' or slot.single else 'depleted', 0)


def test_real_four_slot_no_heroes_layout_and_consumed_states():
    root=Path(__file__).parent/'fixtures'
    p=load_profile(root,'heroes-unavailable')
    rec=Recognizer(root,p,OCR('',root/'numeric-font'))
    ready=cv2.imread(str(root/'four-slot-base-second.png'))
    assert {s.key:rec.slot_state('base',s,ready)[1] for s in p.slots} == {'troop.1':35,'troop.2':1,'spell.1':5,'spell.2':1}
    selected=cv2.imread(str(root/'four-slot-selected.png'))
    assert rec.slot_state('battle',p.slots[0],selected)==('ready',34)
    for tag in ('depleted','depleted-second'):
        used=cv2.imread(str(root/f'four-slot-{tag}.png'))
        assert all(rec.slot_state('battle',s,used)==('deployed' if s.single else 'depleted',0) for s in p.slots)


def test_bright_enemy_background_keeps_roster_but_extra_slot_is_rejected():
    root=Path(__file__).parent/'fixtures'
    rec=Recognizer(root,load_profile(root,'heroes-unavailable'),OCR('',root/'numeric-font'))
    frame=cv2.imread(str(root/'bright-enemy-roster.png'))
    assert rec.matches('base.roster',frame)
    cv2.rectangle(frame,(510,595),(595,708),(255,255,255),3)
    assert not rec.matches('base.roster',frame)


@pytest.mark.parametrize('profile',['heroes-unavailable','queen-away'])
def test_live_siege_release_marker_is_consumed_and_distinct_from_ready(profile):
    root=Path(__file__).parent/'fixtures'
    p=load_profile(root,profile)
    rec=Recognizer(root,p,OCR('',root/'numeric-font'))
    siege=next(s for s in p.slots if s.key=='troop.2')
    assert siege.single
    for name in ('siege-deployed-four.png','siege-deployed-six.png','siege-release-pulse.png'):
        assert rec.slot_state('battle',siege,cv2.imread(str(root/name)))==('deployed',0)
    depleted = 'four-slot-depleted.png' if profile == 'heroes-unavailable' else 'queen-away-depleted.png'
    assert rec.slot_state('battle',siege,cv2.imread(str(root/depleted)))==('deployed',0)
    ready = 'four-slot-base-second.png' if profile == 'heroes-unavailable' else 'queen-away-base-second.png'
    assert rec.slot_state('battle',siege,cv2.imread(str(root/ready)))==('ready',1)


def test_attack_only_requirements_do_not_need_village_camera():
    from boaz.recognition import requirements
    cfg=Settings()
    cfg.farming.collect=False
    assert 'home.camera' not in requirements(cfg,Profile(width=1280,height=720))


def test_slot_area_requires_recognized_state_and_contains_portrait(scene, tmp_path):
    frame, profile, rec = scene
    record_asset(tmp_path, profile, 'base.hero.1.ready', frame, Rect(x=100,y=100,width=30,height=30))
    record_asset(tmp_path, profile, 'base.hero.1.area', frame, Rect(x=90,y=90,width=50,height=50))
    rec.validate_asset('base.hero.1.area', frame.copy())
    with pytest.raises(RecognitionError, match='No recognized slot state'):
        rec.validate_asset('base.hero.1.area', np.zeros_like(frame))
    profile.assets['base.hero.1.area'].rect.width = 20
    with pytest.raises(RecognitionError, match='must contain'):
        rec.validate_asset('base.hero.1.area', frame)


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
