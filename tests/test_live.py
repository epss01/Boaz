import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from boaz.config import Settings
from boaz.live import LiveRunner, UncertainAction
from boaz.recognition import RecognitionError, Slot


class FakeGame:
    connected = True

    def __init__(self):
        self.screen = "home"
        self.counts = {"troop.1": 2, "hero.1": 1, "spell.1": 2}
        self.commands = []
        self.selected = None
        self.fail_deploy = False
        self.balance = 1000000
        self.level = 10
        self.cost = 100000
        self.currency_ok = True
        self.wall_ok = True
        self.fail_upgrade = False
        self.battle_empty_frames = 0
        self.collect_gain = 0

    def capture(self):
        # Snapshot the game rather than share its mutable live fields with readers.
        if self.screen == "battle" and not any(self.counts.values()):
            self.battle_empty_frames += 1
            if self.battle_empty_frames >= 18:
                self.screen = "results"
        return SimpleNamespace(screen=self.screen, counts=self.counts.copy(), balance=self.balance, level=self.level)

    def tap(self, x, y, *, allowed=None):
        if allowed is not None and not allowed.is_set():
            raise InterruptedError
        self.commands.append((x, y))
        actions = {1: "home.army", 2: "army.close", 3: "home.attack", 4: "matchmaking.find", 5: "base.next", 6: "base.home", 7: "results.home", 8: "wall.upgrade_gold", 9: "confirm.accept", 10: "confirm.cancel", 11: "wall.close"}
        key = actions.get(x)
        transitions = {"home.army": "army", "army.close": "home", "home.attack": "matchmaking", "matchmaking.find": "base", "base.home": "home", "results.home": "home", "wall.upgrade_gold": "confirm", "confirm.accept": "wall", "confirm.cancel": "wall", "wall.close": "home"}
        if key:
            self.screen = transitions.get(key, self.screen)
            if key == "confirm.accept" and not self.fail_upgrade:
                self.level += 1
                self.balance -= self.cost
            return
        slots = {20: "troop.1", 21: "hero.1", 22: "spell.1"}
        if x in slots:
            self.selected = slots[x]
        elif x == 100:
            self.screen = "battle"
            if not self.fail_deploy:
                self.counts[self.selected] -= 1
            if not any(self.counts.values()):
                self.finish_next = True
        elif x == 200:
            self.screen = "wall"
        elif x == 300:
            self.balance += self.collect_gain


class FakeRecognizer:
    def __init__(self, game):
        self.game = game
        self.profile = SimpleNamespace(slots=[Slot(kind=k, slot=1) for k in ("troop", "hero", "spell")])
        self.screen = "unknown"
        self.confidence = 1.0

    def ready(self, cfg):
        pass

    def expect(self, screen, frame):
        if frame.screen != screen:
            raise RecognitionError(f"Expected {screen}, got {frame.screen}")
        self.screen = screen

    def matches(self, name, frame):
        if "currency" in name:
            return self.game.currency_ok
        return True

    def asset(self, name):
        codes = {"home.army": 1, "army.close": 2, "home.attack": 3, "matchmaking.find": 4, "base.next": 5, "base.home": 6, "results.home": 7, "wall.upgrade_gold": 8, "confirm.accept": 9, "confirm.cancel": 10, "wall.close": 11}
        if ".troop." in name:
            x = 20
        elif ".hero." in name:
            x = 21
        elif ".spell." in name:
            x = 22
        else:
            x = codes[name]
        return SimpleNamespace(rect=SimpleNamespace(center=(x, 0)))

    def read(self, name, frame):
        if name == "wall.name":
            return "Wall" if self.game.wall_ok else "Cannon"
        if name == "wall.level":
            return frame.level
        if name == "confirm.cost":
            return self.game.cost
        if ".wallet" in name:
            return frame.balance
        return 200000 if name.endswith("gold") or name.endswith("elixir") else 2000

    def slot_state(self, screen, slot, frame):
        count = frame.counts[slot.key]
        return ("ready", count) if count else ("deployed" if slot.kind == "hero" else "depleted", 0)


def setup(tmp_path, **tasks):
    game = FakeGame()
    recognizer = FakeRecognizer(game)
    runner = LiveRunner(game, recognizer, asyncio.Lock(), tmp_path)
    data = Settings().model_dump()
    data["farming"].update(collect=False, **tasks)
    if not data["farming"]["attack"]:
        data["walls"]["enabled"] = True
        data["calibration"]["walls"] = [{"x": 200, "y": 100}]
    data["farming"]["deployment"] = [
        dict(kind="troop", slot=1, x=100, y=100, count=1, delay=0.0),
        dict(kind="hero", slot=1, x=100, y=100, count=1, delay=0.0),
        dict(kind="spell", slot=1, x=100, y=100, count="all", delay=0.0),
        dict(kind="troop", slot=1, x=100, y=100, count="all", delay=0.0),
    ]
    data["session"]["attack_limit"] = 1
    cfg = Settings.model_validate(data)
    runner.settings = cfg
    runner._gate.set()
    runner.input_allowed.set()
    async def instant(seconds):
        await asyncio.sleep(0)
    runner._delay = instant
    return game, runner, cfg


def test_interleaved_full_deployment_single_hero_and_no_abilities(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = "base"
        before = cfg.model_dump()
        await runner._begin_and_deploy(await runner._inventory("base"))
        assert game.counts == {"troop.1": 0, "hero.1": 0, "spell.1": 0}
        assert [x for x, y in game.commands if x < 100] == [20, 21, 22, 20]
        assert game.commands.count((21, 0)) == 1
        assert cfg.model_dump() == before
    asyncio.run(scenario())


def test_prepared_army_and_plan_coverage(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = "army"
        inventory = await runner._inventory("army")
        runner._check_plan(inventory)
        cfg.farming.deployment.pop()
        with pytest.raises(RecognitionError, match="every available"):
            runner._check_plan(inventory)
        assert game.commands == []
    asyncio.run(scenario())


def test_uncertain_deployment_is_not_repeated(tmp_path):
    async def scenario():
        game, runner, _ = setup(tmp_path)
        game.screen = "base"
        game.fail_deploy = True
        with pytest.raises(UncertainAction):
            await runner._begin_and_deploy(await runner._inventory("base"))
        assert game.commands == [(20, 0), (100, 100)]
    asyncio.run(scenario())


@pytest.mark.parametrize("reserve,expected", [(500000, 1), (950000, 0)])
def test_verified_wall_cost_and_reserve(tmp_path, reserve, expected):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        cfg.walls.enabled = True
        cfg.walls.reserve_gold = reserve
        from boaz.config import Point
        cfg.calibration.walls = [Point(x=200, y=100)]
        await runner._walls()
        assert runner.upgrades == expected
        assert game.commands.count((9, 0)) == expected
        assert game.balance >= reserve
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["currency", "object", "outcome"])
def test_wall_failure_never_repeats_spending(tmp_path, failure):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        from boaz.config import Point
        cfg.calibration.walls = [Point(x=200, y=100)]
        if failure == "currency":
            game.currency_ok = False
        if failure == "object":
            game.wall_ok = False
        if failure == "outcome":
            game.fail_upgrade = True
        with pytest.raises(RecognitionError):
            await runner._walls()
        assert game.commands.count((9, 0)) == (1 if failure == "outcome" else 0)
    asyncio.run(scenario())


def test_paused_stop_cancels_pending_input(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        runner.start(cfg)
        runner.pause()
        await asyncio.sleep(0.02)
        assert game.commands == []
        await runner.stop()
        before = list(game.commands)
        await asyncio.sleep(0.02)
        assert game.commands == before
        assert runner.status == "stopped"
    asyncio.run(scenario())


def test_full_live_cycle_observes_loot_and_returns_home(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        runner.start(cfg)
        await asyncio.wait_for(runner._task, timeout=5)
        assert runner.status == "completed"
        assert runner.attacks == 1
        assert runner.searches == 1
        assert runner.loot == dict(gold=200000, elixir=200000, dark_elixir=200000)
        assert game.screen == "home"
        assert game.commands.count((21, 0)) == 1
        assert not runner.input_allowed.is_set()
    asyncio.run(scenario())


def test_search_limit_returns_home_without_deployment(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.farming.min_gold = 999999
        cfg.farming.search_limit = 2
        runner.start(cfg)
        await asyncio.wait_for(runner._task, timeout=3)
        assert runner.status == "completed"
        assert runner.searches == 2
        assert runner.attacks == 0
        assert game.screen == "home"
        assert not any(x in {20, 21, 22, 100} for x, y in game.commands)
    asyncio.run(scenario())


def test_hero_can_be_first_without_ability_or_repeat(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        steps = cfg.farming.deployment
        cfg.farming.deployment = [steps[1], steps[0], steps[2], steps[3]]
        game.screen = "base"
        await runner._begin_and_deploy(await runner._inventory("base"))
        assert game.commands[0] == (21, 0)
        assert game.commands.count((21, 0)) == 1
        assert game.counts["hero.1"] == 0
    asyncio.run(scenario())


def test_uncertain_action_locks_resume_until_stop(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.fail_deploy = True
        runner.start(cfg)
        async def paused():
            while runner.status != "paused":
                await asyncio.sleep(0.01)
        await asyncio.wait_for(paused(), 3)
        assert not runner.resumable
        with pytest.raises(RecognitionError, match="uncertain"):
            runner.resume()
        commands = game.commands.copy()
        await runner.stop()
        assert commands == game.commands
        assert runner.status == "stopped"
    asyncio.run(scenario())


@pytest.mark.parametrize("gain,expected", [(100, 1), (0, 0)])
def test_collection_requires_observed_gain(tmp_path, gain, expected):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        from boaz.config import Point
        cfg.walls.enabled = False
        cfg.farming.collect = True
        cfg.calibration.collectors = [Point(x=300, y=100)]
        game.collect_gain = gain
        runner.start(cfg)
        if gain:
            await asyncio.wait_for(runner._task, 3)
            assert runner.status == "completed"
        else:
            async def paused():
                while runner.status != "paused":
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(paused(), 3)
            assert not runner.resumable
        assert runner.collections == expected
        assert game.commands == [(300, 100)]
        await runner.stop()
    asyncio.run(scenario())
