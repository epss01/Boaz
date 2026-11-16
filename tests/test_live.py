import asyncio
import time
from types import SimpleNamespace

import numpy as np
import pytest

from boaz.config import Settings
from boaz.live import LiveRunner, UncertainAction, BattleFinished
from boaz.recognition import RecognitionError, PlacementUnavailable, Slot


def test_placement_interval_includes_existing_check_time(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = 'battle'
        game.selected = 'troop.1'
        waits = []
        async def delay(seconds):
            waits.append(seconds)
        runner._delay = delay
        runner._last_placement_at = time.monotonic() - .35
        await runner._tap('battle', point=(100,100), interval=.5)
        assert 0 <= waits[-1] <= .150001
        runner._last_placement_at = time.monotonic() - .8
        await runner._tap('battle', point=(100,100), interval=.5)
        assert waits[-1] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('state', ['paused', 'uncertain', 'running', 'failed'])
def test_reconnect_uses_session_emulator_without_input_or_automatic_resume(tmp_path, state):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        runner.status = 'running' if state == 'running' else 'paused'
        runner.input_allowed.clear()
        runner.resumable = state != 'uncertain'
        connections = []
        def connect(path, address):
            connections.append((path, address))
            if state == 'failed':
                raise RuntimeError('Still offline')
        game.connect = connect
        if state in {'uncertain', 'running'}:
            with pytest.raises(RecognitionError):
                await runner.reconnect()
            assert connections == []
        elif state == 'failed':
            with pytest.raises(RuntimeError, match='Still offline'):
                await runner.reconnect()
        else:
            await runner.reconnect()
            assert connections == [(cfg.device.adb_path, cfg.device.address)]
        assert game.commands == []
        assert not runner.input_allowed.is_set()
        assert runner.status == ('running' if state == 'running' else 'paused')
    asyncio.run(scenario())


def test_selected_hero_guard_observes_settling_before_one_placement(tmp_path):
    async def scenario():
        game,runner,cfg=setup(tmp_path)
        game.screen='battle'
        game.selected='hero.1'
        checks=0
        original=runner.recognizer.matches
        def matches(name,frame):
            nonlocal checks
            if name=='battle.hero.1.ready':
                checks+=1
                return checks>1
            return original(name,frame)
        runner.recognizer.matches=matches
        await runner._tap('battle',point=(100,100),checks={'battle.hero.1.ready':True})
        assert checks==2
        assert game.commands==[(100,100)]
    asyncio.run(scenario())


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
        actions = {1: "matchmaking.army", 2: "army.close", 3: "home.attack", 4: "matchmaking.find_regular", 5: "base.next", 6: "base.home", 7: "results.home", 8: "wall.upgrade_gold", 9: "confirm.accept", 10: "confirm.cancel", 11: "wall.close", 12: "army.attack"}
        key = actions.get(x)
        transitions = {"matchmaking.army": "army", "army.close": "matchmaking", "home.attack": "matchmaking", "matchmaking.find_regular": "army", "army.attack": "base", "base.home": "home", "results.home": "home", "wall.upgrade_gold": "confirm", "confirm.accept": "wall", "confirm.cancel": "wall", "wall.close": "home"}
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
    def result_loot(self, frame):
        self.expect('results', frame)
        return {key:self.read(f'results.{key}',frame) for key in ('gold','elixir','dark_elixir')}
    def select_inventory(self, frame):
        pass

    def __init__(self, game):
        self.game = game
        self.profile = SimpleNamespace(slots=[Slot(kind=k, slot=1) for k in ("troop", "hero", "spell")], assets={})
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
        codes = {"matchmaking.army": 1, "army.close": 2, "home.attack": 3, "matchmaking.find_regular": 4, "base.next": 5, "base.home": 6, "results.home": 7, "wall.upgrade_gold": 8, "confirm.accept": 9, "confirm.cancel": 10, "wall.close": 11, "army.attack": 12}
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
        if name.endswith('.count'):
            return frame.counts['.'.join(name.split('.')[1:3])]
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
    data["farming"].update(collect=False, dump_all=False, auto_corner=False, **tasks)
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


@pytest.mark.parametrize("hero_available", [True, False])
def test_dump_all_uses_one_corner_and_skips_unavailable_heroes(tmp_path, hero_available):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.farming.dump_all = True
        cfg.farming.deployment = [cfg.farming.deployment[0]]
        game.counts["troop.1"] = 35
        if not hero_available:
            game.counts["hero.1"] = 0
        before = cfg.model_dump()
        game.screen = "base"
        inventory = await runner._inventory("base")
        runner._check_plan(inventory)
        await runner._begin_and_deploy(inventory)
        assert not any(game.counts.values())
        assert game.commands.count((100, 100)) == 37 + int(hero_available)
        assert game.commands.count((21, 0)) == int(hero_available)
        assert cfg.model_dump() == before
    asyncio.run(scenario())


def test_dump_all_requires_a_troop_or_hero(tmp_path):
    game, runner, cfg = setup(tmp_path)
    cfg.farming.dump_all = True
    with pytest.raises(RecognitionError, match="No available troops or heroes"):
        runner._deployment_plan({"troop.1": ("unavailable", 0),
                                 "hero.1": ("unavailable", 0), "spell.1": ("ready", 2)})


def test_dump_covers_other_slots_before_emptying_large_first_stack(tmp_path):
    game, runner, cfg = setup(tmp_path)
    cfg.farming.dump_all = True
    plan = runner._deployment_plan({'troop.1':('ready',35),'hero.1':('ready',1),'spell.1':('ready',5)})
    assert [(s.kind,s.count) for s in plan] == [('troop',1),('hero',1),('spell','all'),('troop','all')]
    assert len({(s.x,s.y) for s in plan}) == 1


def test_regular_battle_guard_blocks_matchmaking_input(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = "matchmaking"
        original = runner.recognizer.matches
        runner.recognizer.matches = lambda name, frame: False if name == "matchmaking.regular" else original(name, frame)
        async def fail(exc):
            raise exc
        runner._recover = fail
        with pytest.raises(RecognitionError, match="matchmaking.regular"):
            await runner._transition("matchmaking", "matchmaking.find_regular", "base",
                                     checks={"matchmaking.regular": True})
        assert game.commands == []
    asyncio.run(scenario())


@pytest.mark.parametrize('recognize', [True, False])
def test_boundary_preparation_is_bounded_and_checks_screen_before_swiping(tmp_path, recognize):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        frame = SimpleNamespace(screen='base', shape=(720,1280,3))
        async def screen(*args, **kwargs): return frame
        runner._screen = screen
        game.capture = lambda: frame
        calls = []
        def swipe(*args, allowed):
            assert allowed.is_set()
            calls.append(args)
        game.swipe = swipe
        def corner(frame):
            if recognize and calls: return (200,350)
            raise PlacementUnavailable('No visible boundary')
        runner.recognizer.deployment_corner = corner
        if recognize:
            assert await runner._prepare_corner() == (200,350)
            assert len(calls) == 1
        else:
            with pytest.raises(RecognitionError, match='No visible boundary'):
                await runner._prepare_corner()
            assert len(calls) == 3
        frame.screen = 'unknown'
        calls.clear()
        with pytest.raises(RecognitionError):
            await runner._prepare_corner()
        assert calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['boundary', 'all_boundaries', 'unknown', 'uncertain'])
def test_search_skips_only_unavailable_placement_before_deployment(tmp_path, failure):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.farming.auto_corner = True
        cfg.farming.search_limit = 2
        runner.recognizer.supports_deployment_scenery = lambda frame: True
        attempts = 0
        async def corner():
            nonlocal attempts
            attempts += 1
            if failure == 'unknown':
                raise RecognitionError('Unknown screen')
            if failure == 'uncertain':
                raise UncertainAction('Swipe outcome uncertain')
            if attempts == 1 or failure == 'all_boundaries':
                raise PlacementUnavailable('No visible boundary')
            return 100, 100
        runner._prepare_corner = corner
        if failure in {'unknown', 'uncertain'}:
            with pytest.raises(UncertainAction if failure == 'uncertain' else RecognitionError):
                await runner._cycle()
            assert (5, 0) not in game.commands
        else:
            await runner._cycle()
            assert game.commands.count((5, 0)) == 1
            assert attempts == 2 and game.screen == 'home'
            assert runner.attacks == (1 if failure == 'boundary' else 0)
        if failure != 'boundary':
            assert (100, 100) not in game.commands
            assert game.counts == {'troop.1': 2, 'hero.1': 1, 'spell.1': 2}
        assert runner.upgrades == 0
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


def test_count_change_before_next_placement_blocks_input(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = 'battle'
        original = runner._tap
        async def tap(screen, **kwargs):
            if kwargs.get('point'):
                game.counts['troop.1'] -= 1
            await original(screen, **kwargs)
        runner._tap = tap
        async def fail(exc): raise exc
        runner._recover = fail
        with pytest.raises(RecognitionError, match='changed before input'):
            await runner._deploy({'troop.1':('ready',2),'hero.1':('ready',1),'spell.1':('ready',2)})
        assert game.commands == [(20,0)]
    asyncio.run(scenario())


def test_failed_burst_consumption_blocks_the_following_stack(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = 'battle'
        game.fail_deploy = True
        cfg.farming.deployment[0].count = 'all'
        async def fail(exc): raise exc
        runner._recover = fail
        with pytest.raises(UncertainAction, match='consumption is uncertain'):
            await runner._deploy({'troop.1':('ready',2),'hero.1':('ready',1),'spell.1':('ready',2)})
        assert game.commands == [(20,0),(100,100),(100,100)]
        assert game.counts['troop.1'] == 2
    asyncio.run(scenario())


def test_burst_honors_cancel_before_next_tap(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.selected = 'troop.1'
        original = game.tap
        def tap(x,y,**kwargs):
            original(x,y,**kwargs)
            runner.input_allowed.clear()
        game.tap = tap
        with pytest.raises(UncertainAction, match='cancelled'):
            await runner._burst(cfg.farming.deployment[0],3)
        assert game.commands == [(100,100)]
    asyncio.run(scenario())


def test_burst_dispatches_at_half_second_cadence(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        step = cfg.farming.deployment[0]
        step.delay = .5
        times = []
        def tap(*args,**kwargs):
            times.append(time.monotonic())
            time.sleep(.2)
        game.tap = tap
        runner._delay = asyncio.sleep
        await runner._burst(step,3)
        assert len(times) == 3
        assert all(.48 <= b-a < .68 for a,b in zip(times,times[1:]))
    asyncio.run(scenario())


def test_natural_battle_end_during_consumption_check_is_not_retried(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = 'battle'
        calls = 0
        async def inventory(screen, key=None):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise BattleFinished('Natural battle end')
            return {'troop.1':('ready',2)}
        runner._inventory = inventory
        with pytest.raises(BattleFinished):
            await runner._deploy({'troop.1':('ready',2)})
        assert game.commands == [(20,0),(100,100)]
    asyncio.run(scenario())


def test_unreadable_first_deployment_is_uncertain_and_never_retried(tmp_path):
    async def scenario():
        game,runner,cfg=setup(tmp_path)
        game.screen='base'
        inventory=await runner._inventory('base')
        original=runner.recognizer.slot_state
        def state(screen,slot,frame):
            if screen=='battle': raise RecognitionError('Unreadable portrait')
            return original(screen,slot,frame)
        runner.recognizer.slot_state=state
        with pytest.raises(UncertainAction,match='First deployment reading'):
            await runner._begin_and_deploy(inventory)
        assert game.commands==[(20,0),(100,100)]
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


def test_wall_does_not_read_obscured_confirmation_wallet(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        original = runner.recognizer.read
        def read(name, frame):
            assert not name.startswith('confirm.wallet')
            return original(name, frame)
        runner.recognizer.read = read
        await runner._walls()
        assert runner.upgrades == 1
        assert game.balance == 900000
    asyncio.run(scenario())


def test_combined_ceiling_checked_before_accept(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        cfg.walls.spend_limit = 750000
        game.balance = 2000000
        game.cost = 750001
        await runner._walls()
        assert game.screen == 'home' and (9,0) not in game.commands
        game.cost = 750000
        await runner._walls()
        await runner._walls()
        assert runner.wall_spent == 750000 and game.commands.count((9,0)) == 1
    asyncio.run(scenario())


def test_continuous_completion_precedes_any_attack_or_purchase(tmp_path):
    from boaz.village import WallProgress
    from collections import Counter
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.walls.until_max = cfg.walls.enabled = cfg.walls.build_menu = True
        async def export():
            return WallProgress('#PY2',100,13,14,300,Counter({14:300}))
        runner._export = export
        assert 'maximum' in await runner._cycle()
        assert game.commands == []
    asyncio.run(scenario())


@pytest.mark.parametrize('confirmed', [False, True])
def test_continuous_rechecks_wall_distribution_after_purchase(tmp_path, confirmed):
    from boaz.village import WallProgress
    from collections import Counter
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.walls.until_max = cfg.walls.enabled = cfg.walls.build_menu = True
        exports = iter([Counter({13:1}), Counter({14:1}) if confirmed else Counter({13:1})])
        async def export():
            return WallProgress('#PY2',100,13,14,1,next(exports))
        async def walls(progress):
            return 13
        runner._export, runner._walls = export, walls
        if confirmed:
            assert 'maximum' in await runner._cycle()
        else:
            with pytest.raises(UncertainAction, match='Export did not confirm'):
                await runner._cycle()
        assert game.commands == []
    asyncio.run(scenario())


@pytest.mark.parametrize('balances,costs,expected', [
    ({'gold':2000000,'elixir':1500000},{'gold':100000,'elixir':100000},'gold'),
    ({'gold':1500000,'elixir':2000000},{'gold':100000,'elixir':100000},'elixir'),
    ({'gold':1500000,'elixir':1500000},{'gold':100000,'elixir':100000},'gold'),
    ({'gold':550000,'elixir':600000},{'gold':100000,'elixir':100000},'elixir'),
    ({'gold':550000,'elixir':550000},{'gold':100000,'elixir':100000},None),
])
def test_continuous_currency_selection_and_reserves(tmp_path, balances, costs, expected):
    from boaz.village import WallProgress
    from collections import Counter
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        cfg.walls.build_menu = True
        cfg.walls.spend_limit = 750000
        progress = WallProgress('#PY2',100,13,14,1,Counter({10:1}))
        chosen = []
        async def number(screen, name):
            if name == 'home.builders_free':
                return 1
            if '.wallet_' in name:
                currency = name.rsplit('_',1)[1]
                return balances[currency] - (costs[currency] if chosen and currency == chosen[0] and game.level == 11 else 0)
            if name.startswith('wall.cost_'):
                return costs[name.rsplit('_',1)[1]]
            if name == 'wall.name':
                return 'Wall'
            if name == 'wall.level':
                return game.level
            if name == 'confirm.cost':
                return costs[chosen[0]]
            raise AssertionError(name)
        async def transition(before, target, after, **kwargs):
            assert game.screen == before
            if target.startswith('wall.upgrade_'):
                chosen.append(target.rsplit('_',1)[1])
            if target == 'confirm.accept':
                game.level += 1
            game.screen = after
        runner._number = number
        runner._transition = transition
        result = await runner._walls(progress)
        assert chosen == ([expected] if expected else [])
        assert result == (10 if expected else None)
        assert game.screen == 'home'
        assert runner.wall_spent == (costs[expected] if expected else 0)
    asyncio.run(scenario())


def test_build_menu_selects_wall_without_coordinates_or_camera_alignment(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path, attack=False)
        cfg.walls.build_menu = True
        cfg.walls.upgrade_limit = 1
        cfg.calibration.walls = []
        transitions = []
        original = runner._transition
        async def transition(before, target, after, **kwargs):
            transitions.append(target)
            if target in {'home.build', 'build.wall', 'build_wall.close'}:
                assert game.screen == before
                game.screen = after
            else:
                await original(before, target, after, **kwargs)
        runner._transition = transition
        matches = runner.recognizer.matches
        runner.recognizer.matches = lambda name, frame: False if name == 'home.camera' else matches(name, frame)
        await runner._walls()
        assert transitions[:3] == ['home.build', 'build.wall', 'build_wall.close']
        assert runner.upgrades == 1
        assert game.balance == 900000
        assert game.screen == 'home'
    asyncio.run(scenario())


def test_pausing_wall_workflow_requires_fresh_session(tmp_path):
    game, runner, cfg = setup(tmp_path, attack=False)
    runner._wall_in_progress = True
    runner.pause()
    with pytest.raises(RecognitionError, match='uncertain'):
        runner.resume()


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
        assert game.commands[:3] == [(3, 0), (4, 0), (12, 0)]
    asyncio.run(scenario())


def test_disabled_dark_filter_does_not_require_candidate_ocr(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        read = runner.recognizer.read
        def checked(name, frame):
            assert name != 'base.dark_elixir'
            return read(name,frame)
        runner.recognizer.read = checked
        runner.start(cfg)
        await asyncio.wait_for(runner._task,5)
        assert runner.attacks == 1 and game.screen == 'home'
        assert runner.loot['dark_elixir'] == 200000
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


def test_next_waits_through_search_clouds_without_another_tap(tmp_path):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        cfg.farming.min_gold = 999999
        cfg.farming.search_limit = 2
        original_tap, original_capture = game.tap, game.capture
        clouds = 0
        def tap(x, y, **kwargs):
            nonlocal clouds
            original_tap(x, y, **kwargs)
            if x == 5:
                clouds = 4
        def capture():
            nonlocal clouds
            frame = original_capture()
            if clouds:
                clouds -= 1
                if clouds < 3:
                    frame.screen = 'unknown'
            return frame
        game.tap, game.capture = tap, capture
        runner.start(cfg)
        await asyncio.wait_for(runner._task, timeout=3)
        assert runner.status == 'completed'
        assert runner.searches == 2 and runner.attacks == 0
        assert game.commands == [(3,0),(4,0),(12,0),(5,0),(6,0)]
    asyncio.run(scenario())


@pytest.mark.parametrize('target,started,allowed', [('base.home',False,True),('base.home',True,False),('base.next',False,False)])
def test_scouting_expiry_only_allows_exit_before_deployment(tmp_path, target, started, allowed):
    async def scenario():
        game, runner, cfg = setup(tmp_path)
        game.screen = 'battle'
        runner._deployment_started = started
        if allowed:
            await runner._transition('base',target,'home')
            assert game.commands == [(6,0)] and game.screen == 'home'
        else:
            with pytest.raises(UncertainAction):
                await runner._tap('base',target=target)
            assert game.commands == []
    asyncio.run(scenario())


def test_battle_end_animation_is_observed_without_input(tmp_path):
    async def scenario():
        game,runner,cfg=setup(tmp_path)
        frames=iter([SimpleNamespace(screen='battle'),SimpleNamespace(screen='unknown'),SimpleNamespace(screen='results')])
        game.capture=lambda: next(frames)
        result=await runner._await_results()
        assert result.screen=='results'
        assert game.commands==[]
    asyncio.run(scenario())


def test_return_home_dismisses_only_known_bonus(tmp_path):
    async def scenario():
        game,runner,cfg=setup(tmp_path)
        game.screen='results'
        runner.recognizer.profile.assets={'bonus':object()}
        original=game.tap
        def tap(x,y,**kwargs):
            if x==7:
                game.commands.append((x,y)); game.screen='bonus'
            elif x==13:
                game.commands.append((x,y)); game.screen='home'
            else: original(x,y,**kwargs)
        game.tap=tap
        original_asset=runner.recognizer.asset
        runner.recognizer.asset=lambda name: SimpleNamespace(rect=SimpleNamespace(center=(13,0))) if name=='bonus.close' else original_asset(name)
        runner.recognizer.matches=lambda name,frame: frame.screen=='bonus' if name=='bonus' else True
        await runner._transition('results','results.home','home')
        assert game.commands==[(7,0),(13,0)]
        assert game.screen=='home'
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
