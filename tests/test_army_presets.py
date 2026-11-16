import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError

from boaz.config import Settings, load_settings, save_settings, town_hall_army
from boaz.dashboard import apply_farming_mode, apply_town_hall
from boaz.recognition import Profile, Slot, initial_slots


@pytest.mark.parametrize("level", range(7, 19))
@pytest.mark.parametrize("wall_breakers", [False, True])
def test_town_hall_suggestions(level, wall_breakers):
    army = town_hall_army(level, wall_breakers)
    assert army.troops == (2 if level >= 8 and wall_breakers else 1)
    assert army.wall_breakers == (level >= 8 and wall_breakers)
    assert army.heroes == (1 if level < 9 else 2 if level < 11 else 3 if level < 13 else 4)
    assert army.spells == (1 if level < 9 else 2)
    assert army.siege == int(level >= 10)


@pytest.mark.parametrize("level", [6, 19])
def test_invalid_town_hall(level):
    with pytest.raises(ValidationError):
        town_hall_army(level)


def test_army_application_preserves_other_settings_and_round_trips(tmp_path):
    draft = Settings().model_dump()
    draft["device"]["address"] = "127.0.0.1:6610"
    draft["live"]["profile"] = "my-village"
    draft["farming"]["min_gold"] = 345678
    draft["farming"]["deployment"][0]["delay"] = 0.1
    before = deepcopy(draft)
    apply_town_hall(draft, 13, True)
    expected = deepcopy(before)
    expected["farming"]["army"] = town_hall_army(13, True).model_dump()
    expected["farming"]["deployment"][0]["delay"] = 0.5
    assert draft == expected
    draft["farming"]["army"].update(heroes=0, spells=3, siege=0)
    settings = Settings.model_validate(draft)
    save_settings(tmp_path / "preset.json", settings)
    assert load_settings(tmp_path / "preset.json") == settings
    assert [s.key for s in initial_slots(settings)] == ["troop.1", "troop.2", "spell.1", "spell.2", "spell.3"]


def test_new_slots_include_single_siege_and_leave_existing_profile_unchanged():
    cfg = Settings()
    cfg.farming.army = town_hall_army(13, True)
    existing = Profile(width=1280, height=720, slots=[Slot(kind="troop", slot=1)])
    before = existing.model_dump()
    slots = initial_slots(cfg)
    assert [s.key for s in slots] == ["troop.1", "troop.2", "troop.3", "hero.1", "hero.2", "hero.3", "hero.4", "spell.1", "spell.2"]
    assert [s.key for s in slots if s.single] == ["troop.3"]
    assert existing.model_dump() == before


def test_legacy_preset_keeps_saved_delay_and_slots():
    cfg = Settings.model_validate({"farming": {"deployment": [dict(x=10, y=20, kind="spell", slot=2, count="all", delay=0.1)]}})
    assert cfg.farming.army is None
    assert cfg.farming.deployment[0].delay == 0.1
    assert initial_slots(cfg) == [Slot(kind="spell", slot=2)]


def test_modes_keep_budget_and_support_advanced_tasks():
    draft = Settings().model_dump()
    draft["farming"]["attack"] = False
    before = deepcopy(draft)
    apply_farming_mode(draft, True)
    cfg = Settings.model_validate(draft)
    assert cfg.farming.attack and cfg.walls.enabled and cfg.walls.build_menu
    assert cfg.walls.reserve_gold == before["walls"]["reserve_gold"]
    assert cfg.walls.upgrade_limit == before["walls"]["upgrade_limit"]
    apply_farming_mode(draft, False)
    assert not Settings.model_validate(draft).walls.enabled
    draft["farming"].update(attack=False, collect=True)
    assert not Settings.model_validate(draft).farming.attack


def test_safe_default_and_dump_plan_delay(tmp_path):
    from test_live import setup
    cfg = Settings()
    assert not cfg.farming.collect and not cfg.walls.enabled
    assert cfg.farming.attack and cfg.farming.dump_all and cfg.farming.auto_corner
    assert cfg.session.attack_limit == 1 and cfg.session.duration_minutes == 15
    assert cfg.live.profile == ""
    assert cfg.farming.deployment[0].delay == 0.5
    async def scenario():
        game, runner, _ = setup(tmp_path)
        runner.settings = cfg
        plan = runner._deployment_plan({"troop.1": ("ready", 35), "hero.1": ("ready", 1), "spell.1": ("ready", 5)})
        assert all(s.delay == 0.5 for s in plan)
    asyncio.run(scenario())
