import asyncio

import pytest

from boaz.config import Settings
from boaz.runner import Runner


def quick_settings():
    cfg = Settings()
    cfg.farming.deployment[0].delay = 0.0
    cfg.session.attack_limit = 2
    return cfg


async def finish(runner):
    await asyncio.wait_for(runner._task, timeout=3)


def test_deterministic_cycle_and_snapshot():
    async def scenario():
        runner = Runner(step_seconds=0.001)
        cfg = quick_settings()
        runner.start(cfg)
        cfg.farming.min_gold = 99999999
        await finish(runner)
        assert runner.status == "completed"
        assert runner.attacks == 2
        assert runner.searches == 4
        assert runner.loot == dict(gold=400000, elixir=320000, dark_elixir=2800)
        assert runner.settings.farming.min_gold == 200000
        assert Runner().status == "idle"
    asyncio.run(scenario())


def test_pause_resume_stop_and_duplicate_start():
    async def scenario():
        runner = Runner(step_seconds=0.1)
        runner.start(quick_settings())
        with pytest.raises(ValueError, match="already running"):
            runner.start(quick_settings())
        await asyncio.sleep(0.02)
        runner.pause()
        before = (list(runner.events), runner.attacks, runner.elapsed)
        await asyncio.sleep(0.15)
        assert (list(runner.events), runner.attacks, runner.elapsed) == before
        runner.resume()
        assert runner.status == "running"
        await runner.stop()
        assert runner.status == "stopped"
        before = (list(runner.events), runner.attacks)
        await asyncio.sleep(0.15)
        assert (list(runner.events), runner.attacks) == before
        runner.start(quick_settings())
        runner.pause()
        await runner.stop()
        assert not runner.active
    asyncio.run(scenario())


def test_search_limit_and_all_thresholds():
    async def scenario():
        cfg = quick_settings()
        cfg.farming.min_dark_elixir = 999999
        cfg.farming.search_limit = 2
        runner = Runner(step_seconds=0.001)
        runner.start(cfg)
        await finish(runner)
        assert runner.attacks == 0
        assert runner.searches == 2
        assert "Search limit" in runner.reason
    asyncio.run(scenario())


def test_duration_limit():
    async def scenario():
        cfg = quick_settings()
        cfg.session.duration_minutes = 0.001
        runner = Runner(step_seconds=0.1)
        runner.start(cfg)
        await finish(runner)
        assert runner.status == "completed"
        assert "duration" in runner.reason
        assert runner.attacks == 0
    asyncio.run(scenario())


def test_error_transition(monkeypatch):
    async def fail(*args):
        raise RuntimeError("fixture failure")
    async def scenario():
        runner = Runner()
        monkeypatch.setattr(runner, "_stage", fail)
        runner.start(quick_settings())
        await finish(runner)
        assert runner.status == "error"
        assert "fixture failure" in runner.reason
        assert not runner.active
    asyncio.run(scenario())


@pytest.mark.parametrize("reserve,limit,expected", [(950000, 5, 0), (500000, 1, 1), (850000, 5, 1)])
def test_wall_reserves_and_limits(reserve, limit, expected):
    async def scenario():
        data = quick_settings().model_dump()
        data["farming"].update(attack=False, collect=False)
        data["walls"].update(enabled=True, reserve_gold=reserve, upgrade_limit=limit)
        data["calibration"]["walls"] = [{"x": 100, "y": 100}, {"x": 200, "y": 100}]
        runner = Runner(step_seconds=0.001)
        runner.start(Settings.model_validate(data))
        await finish(runner)
        assert runner.upgrades == expected
        assert runner.wallet["gold"] >= reserve
    asyncio.run(scenario())


def test_simulation_sends_zero_input(monkeypatch):
    from airtest.core.android.adb import ADB
    from boaz.device import Device
    calls = []
    def forbid(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Simulation must never access an emulator")
    monkeypatch.setattr(ADB, "cmd", forbid)
    monkeypatch.setattr(Device, "connect", forbid)
    monkeypatch.setattr(Device, "capture", forbid)
    async def scenario():
        runner = Runner(step_seconds=0.001)
        runner.start(quick_settings())
        await finish(runner)
        assert runner.status == "completed"
        assert calls == []
    asyncio.run(scenario())
