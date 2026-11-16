"""Verified live workflow. Uncertain inputs require a stop and manual inspection."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
import re
import threading
import time

import cv2

from .recognition import RecognitionError, PlacementUnavailable, RESOURCE_KEYS
from .runner import Runner
from .config import DeploymentStep
from .village import clipboard_export, read_village
from .army import UNITS, recommend


class UncertainAction(RecognitionError):
    pass


class BattleFinished(RecognitionError):
    pass


class LiveRunner(Runner):
    mode = "Live"

    def __init__(self, device, recognizer, device_lock, diagnostics: Path):
        super().__init__()
        self.device, self.recognizer, self.device_lock = device, recognizer, device_lock
        self.diagnostics = diagnostics
        self.input_allowed = threading.Event()
        self.resumable = True
        self._in_battle = False
        self._deployment_started = False
        self._last_placement_at = None
        self._deployed = set()
        self._spent = set()
        self._frame = None
        self._wall_in_progress = False
        self.wall_progress = None
        self.wall_spent = 0

    def start(self, settings):
        if not self.device.connected:
            raise RecognitionError("Connect the emulator before starting live farming")
        if self.active:
            raise ValueError("A live session is already active")
        self.resumable = True
        self.input_allowed.set()
        self._in_battle = False
        self._deployment_started = False
        self._last_placement_at = None
        self._deployed.clear()
        self._spent.clear()
        self._wall_in_progress = False
        self.wall_progress = None
        self.wall_spent = 0
        super().start(settings)
        self.wallet = dict.fromkeys(RESOURCE_KEYS, 0)

    def pause(self):
        self.input_allowed.clear()
        if self._wall_in_progress:
            self.resumable = False
        super().pause()

    def resume(self):
        if not self.resumable:
            raise RecognitionError("An input outcome is uncertain. Stop, inspect the game, then start from home; it will not be retried.")
        self.input_allowed.set()
        super().resume()

    async def reconnect(self):
        if self.status != 'paused' or not self.resumable:
            raise RecognitionError('Only a safely paused session can reconnect; stop and inspect uncertain input')
        async with self.device_lock:
            await self._io(self.device.connect, self.settings.device.adb_path, self.settings.device.address)
        self.event('Reconnected the session emulator; no gameplay input sent')

    async def stop(self):
        self.input_allowed.clear()
        await super().stop()

    async def _io(self, function, *args, **kwargs):
        # Shield the worker so cancellation cannot release the device lock while
        # an ADB command is still executing in its thread.
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.input_allowed.clear()
            try:
                await task
            except Exception:
                pass
            raise

    async def _capture(self):
        async with self.device_lock:
            frame = await self._io(self.device.capture)
        self._frame = frame
        return frame

    def _diagnose(self, reason):
        self.event(reason)
        self.diagnostics.mkdir(parents=True, exist_ok=True)
        if self._frame is not None:
            name = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            try:
                cv2.imwrite(str(self.diagnostics / f"{name}.png"), self._frame)
                for old in sorted(self.diagnostics.glob("*.png"))[:-20]:
                    old.unlink(missing_ok=True)
            except (OSError, cv2.error):
                self.event("Could not save diagnostic screenshot")

    async def _recover(self, exc):
        self.pause()
        if isinstance(exc, UncertainAction):
            self.resumable = False
        self.reason = str(exc)
        self._diagnose(self.reason)
        await self._gate.wait()

    async def _screen(self, expected, camera=False):
        unknown_since = None
        while True:
            await self._gate.wait()
            try:
                frame = await self._capture()
                self.recognizer.expect(expected, frame)
                if camera and not self.recognizer.matches("home.camera", frame):
                    raise RecognitionError("Village camera/layout differs from calibration; restore it or recalibrate")
                self.phase = expected.capitalize()
                return frame
            except Exception as exc:
                if expected == "base" and self._frame is not None:
                    try:
                        self.recognizer.expect("battle", self._frame)
                    except RecognitionError:
                        pass
                    else:
                        self._in_battle = True
                        self.phase = "Battle"
                        return self._frame
                if isinstance(exc, RecognitionError) and self._in_battle and expected in {"base", "battle"} and self._frame is not None:
                    try:
                        self.recognizer.expect("results", self._frame)
                    except RecognitionError:
                        unknown_since = unknown_since or time.monotonic()
                        if time.monotonic() - unknown_since < self.settings.live.transition_timeout:
                            await self._delay(.2)
                            continue
                    else:
                        raise BattleFinished("Battle finished while paused or deploying") from exc
                await self._recover(exc)

    async def _delay(self, seconds):
        remaining = seconds
        while remaining > 0:
            await self._gate.wait()
            started = self.elapsed
            await asyncio.sleep(min(0.05, remaining))
            remaining -= max(0, self.elapsed - started)

    async def _number(self, screen, name):
        while True:
            try:
                first = self.recognizer.read(name, await self._screen(screen))
                await self._delay(0.2)
                second = self.recognizer.read(name, await self._screen(screen))
                if first != second:
                    raise RecognitionError(f"Inconsistent {name}: {first} / {second}")
                return second
            except Exception as exc:
                if isinstance(exc,RecognitionError):
                    exc.args=(f'{name}: {exc}',)
                await self._recover(exc)

    async def _tap(self, screen, point=None, target=None, camera=False, checks=None, interval=None):
        # Keep recognition and dispatch together, with no preview operation between.
        hero_guard = any('.hero.' in name for name in ([target] if target else [])+list(checks or {}))
        settle_until = time.monotonic()+2 if hero_guard else 0
        while True:
            await self._gate.wait()
            screen_observed = False
            try:
                async with self.device_lock:
                    frame = await self._io(self.device.capture)
                    self._frame = frame
                    try:
                        self.recognizer.expect(screen, frame)
                    except RecognitionError:
                        if screen != "base":
                            raise
                        self.recognizer.expect("battle", frame)
                        self._in_battle = True
                        if target == 'base.home':
                            if self._deployment_started:
                                raise UncertainAction('Automatic search exit is blocked after deployment')
                        elif target is not None and not target.endswith('.ready'):
                            raise UncertainAction('Scouting ended before the requested action; no input sent')
                        screen = "battle"
                        if target and target != 'base.home':
                            target = target.replace("base.", "battle.", 1)
                    screen_observed = True
                    if camera and not self.recognizer.matches("home.camera", frame):
                        raise RecognitionError("Village camera/layout changed; no input sent")
                    for name, expected in (checks or {}).items():
                        actual = (await self._io(self.recognizer.read, name, frame)
                                  if not isinstance(expected, bool) else self.recognizer.matches(name, frame))
                        if actual != expected:
                            raise RecognitionError(f"{name} changed before input; no command sent")
                    deselect = target == 'wall.close' and (self.settings.farming.prepare_army or self.settings.walls.until_max)
                    if deselect:
                        point = self.recognizer.clear_ground(frame)
                    if target and not deselect:
                        if target == 'build.wall' and hasattr(self.recognizer,'find_row'):
                            recognized = self.recognizer.find_row(target,frame) == self.recognizer.asset(target).rect.y
                        else:
                            recognized = self.recognizer.matches(target, frame)
                        if not recognized:
                            raise RecognitionError(f"Action target {target} is not recognized")
                        point = self.recognizer.asset(target).rect.center
                    try:
                        if interval is not None and self._last_placement_at is not None:
                            await self._delay(max(0, interval-(time.monotonic()-self._last_placement_at)))
                        if interval is not None:
                            self._last_placement_at = time.monotonic()
                        await self._io(self.device.tap, *point, allowed=self.input_allowed)
                    except InterruptedError:
                        continue
                    except Exception as exc:
                        raise UncertainAction(f"Input outcome uncertain: {exc}. Stop and inspect before starting again.") from exc
                return
            except UncertainAction:
                raise
            except Exception as exc:
                if isinstance(exc,RecognitionError) and time.monotonic()<settle_until:
                    await self._delay(.2)
                    continue
                if isinstance(exc, RecognitionError) and self._in_battle and screen in {'base','battle'} and not screen_observed:
                    await self._screen(screen)
                    continue
                if self._in_battle and screen in {"base", "battle"} and self._frame is not None:
                    try:
                        self.recognizer.expect("results", self._frame)
                    except RecognitionError:
                        pass
                    else:
                        raise BattleFinished("Battle finished before the next input") from exc
                await self._recover(exc)

    async def _transition(self, before, target, after, *, checks=None):
        await self._tap(before, target=target, checks=checks)
        end = time.monotonic() + self.settings.live.transition_timeout
        matched = False
        while time.monotonic() < end:
            await self._gate.wait()
            frame = await self._capture()
            try:
                self.recognizer.expect(after, frame)
                if before == after and not matched:
                    matched = True
                    await self._delay(.2)
                    continue
                self.phase = after.capitalize()
                return
            except RecognitionError:
                matched = False
                # During an animation we observe only; an unexpected screen never
                # causes another navigation or spending tap.
                if after == 'home' and before == 'results' and 'bonus' in self.recognizer.profile.assets:
                    if self.recognizer.matches('bonus', frame):
                        await self._transition('bonus','bonus.close','home')
                        return
                await self._delay(0.2)
        raise UncertainAction(f"{target} did not reach {after}; inspect the game. No automatic retry.")

    async def _inventory(self, screen, key=None):
        settle_until = time.monotonic()+2 if screen=='battle' and key else 0
        while True:
            try:
                return await self._inventory_once(screen, key)
            except BattleFinished:
                raise
            except RecognitionError as exc:
                if time.monotonic()<settle_until:
                    await self._delay(.2)
                    continue
                await self._recover(exc)
            except Exception as exc:
                await self._recover(exc)

    async def _inventory_once(self, screen, key=None):
        frame = await self._screen(screen)
        if screen == "base" and key is None:
            self.recognizer.select_inventory(frame)
        if not self.recognizer.matches(f"{screen}.roster", frame):
            raise RecognitionError(f"{screen} army layout changed or contains an unconfigured slot")
        slots = [s for s in self.recognizer.profile.slots if (key is None or s.key == key)
                 and not (screen == "battle" and s.key in self._spent)]
        first = {s.key: self.recognizer.slot_state(screen, s, frame) for s in slots}
        await self._delay(0.15)
        frame = await self._screen(screen)
        if not self.recognizer.matches(f"{screen}.roster", frame):
            raise RecognitionError(f"{screen} inventory layout changed during reading")
        values = {s.key: self.recognizer.slot_state(screen, s, frame) for s in slots}
        for slot in slots:
            if first[slot.key] != values[slot.key]:
                raise RecognitionError(f"Unstable availability/count for {slot.key}")
        if screen == "battle":
            values.update({s.key: ("deployed" if s.kind == "hero" else "depleted", 0)
                           for s in self.recognizer.profile.slots
                           if s.key in self._spent and (key is None or s.key == key)})
        return values

    def _deployment_plan(self, inventory):
        if not self.settings.farming.dump_all:
            return self.settings.farming.deployment
        corner = self.settings.farming.deployment[0]
        plan = [
            DeploymentStep(kind=slot.kind, slot=slot.slot, x=corner.x, y=corner.y,
                           count=1 if slot.kind == "hero" else "all", delay=corner.delay)
            for kind in ("troop", "hero", "spell")
            for slot in self.recognizer.profile.slots
            if slot.kind == kind and inventory[slot.key][0] == "ready" and inventory[slot.key][1] > 0
        ]
        if not any(step.kind in {"troop", "hero"} for step in plan):
            raise RecognitionError("No available troops or heroes to start a battle")
        first = plan[0]
        if first.kind != 'hero' and inventory[f'{first.kind}.{first.slot}'][1] > 1:
            # Verify one unit, then cover the other slots before emptying a large stack.
            plan = [first.model_copy(update={'count':1}), *plan[1:], first]
        return plan

    def _check_plan(self, inventory):
        for key, (state, _) in inventory.items():
            if state == 'skipped':
                self.event(f"Skipped identified hero {key}: deployed state is uncalibrated")
        remaining = {key: count for key, (state, count) in inventory.items()}
        sequence = []
        for step in self._deployment_plan(inventory):
            key = f"{step.kind}.{step.slot}"
            if key not in remaining or remaining[key] <= 0:
                raise RecognitionError(f"Prepared army is missing {key}, or preset repeats an exhausted slot")
            amount = remaining[key] if step.count == "all" else step.count
            if amount > remaining[key]:
                raise RecognitionError(f"Preset requires more units than available in {key}")
            remaining[key] -= amount
            sequence.append(f"{key} ×{amount} at ({step.x}, {step.y})")
        if any(remaining.values()):
            raise RecognitionError("Preset must deploy every available troop, hero, and spell; add all-remaining steps")
        self.event("Verified deployment order: " + " → ".join(sequence))

    async def _deploy(self, inventory):
        for index, step in enumerate(self.settings.farming.deployment, 1):
            key = f"{step.kind}.{step.slot}"
            self.phase = f"Deploy {index}: {key}"
            inventory.update(await self._inventory("battle", key))
            amount = inventory[key][1] if step.count == "all" else step.count
            before_count = inventory[key][1]
            selected = False
            for placed in range(amount):
                state, _ = inventory[key]
                count = before_count - placed
                if state in {"depleted", "deployed"} or key in self._deployed:
                    break
                if state != "ready" or count <= 0:
                    raise RecognitionError(f"{key} is unavailable; no input sent")
                # Selecting a hero portrait twice could activate its ability.
                # Mark it before the first command and never automatically retry.
                if step.kind == "hero":
                    self._deployed.add(key)
                if not selected:
                    await self._tap("battle", target=f"battle.{key}.ready")
                    selected = True
                slot = next(s for s in self.recognizer.profile.slots if s.key == key)
                checks = {f'battle.{key}.ready': True}
                if step.kind != 'hero' and not slot.single:
                    checks[f'battle.{key}.count'] = count
                await self._tap("battle", point=(step.x, step.y), checks=checks, interval=step.delay)
                if step.kind != 'hero' and amount-placed > 1:
                    await self._burst(step,amount-placed-1)
                    break
            try:
                observed = (await self._inventory("battle", key))[key]
                if step.kind == "hero" and observed[0] != "deployed":
                    raise UncertainAction(f"Hero {key} deployment is uncertain; no further portrait taps")
                if observed[1] != before_count - amount:
                    raise UncertainAction(f"{key} consumption is uncertain; deployment will not be retried")
            except BattleFinished:
                raise
            except RecognitionError as exc:
                raise UncertainAction(str(exc)) from exc
            inventory[key] = observed
            if observed[1] == 0:
                self._spent.add(key)
        inventory = await self._inventory("battle")
        if any(count for _, count in inventory.values()):
            raise RecognitionError("Units remain after deployment; inspect preset and remaining slots")
        skipped = [k for k,(state,_) in inventory.items() if state == 'skipped']
        self.event("Verified consumption of planned units" + (f"; skipped {', '.join(skipped)}" if skipped else ""))

    async def _burst(self, step, count):
        """The selected stack was checked by _tap; verify its final count in _deploy."""
        intervals = []
        for _ in range(count):
            await self._gate.wait()
            if self._last_placement_at is not None:
                await self._delay(max(0,step.delay-(time.monotonic()-self._last_placement_at)))
            async with self.device_lock:
                await self._gate.wait()
                previous = self._last_placement_at
                now = time.monotonic()
                try:
                    await self._io(self.device.tap,step.x,step.y,allowed=self.input_allowed)
                except InterruptedError:
                    raise UncertainAction('Deployment burst cancelled before dispatch; inspect remaining units')
                except Exception as exc:
                    raise UncertainAction('Deployment burst outcome uncertain; no retry') from exc
                self._last_placement_at = now
                if previous is not None:
                    intervals.append(now-previous)
        if intervals:
            self.event(f'Burst {step.kind}.{step.slot}: {count} taps, requested {step.delay:.3f}s; '
                       f'observed dispatch intervals {min(intervals):.3f}–{max(intervals):.3f}s')

    async def _export(self, discover=False):
        since = int(time.time())
        try:
            before = await self._io(clipboard_export)
        except Exception:
            before = None
        await self._tap('home',target='home.profile')
        end = time.monotonic()+self.settings.live.transition_timeout
        panel = None
        while time.monotonic()<end and panel is None:
            frame = await self._capture()
            for screen in ('more','settings','profile'):
                try:
                    self.recognizer.expect(screen,frame)
                    panel = screen
                    break
                except RecognitionError:
                    continue
            if panel is None:
                await self._delay(.2)
        if panel is None:
            raise RecognitionError('Player panel did not open; return Home and check the account')
        if panel == 'profile':
            await self._transition('profile','profile.settings','settings')
        if panel != 'more':
            await self._transition('settings','settings.more','more')
        await self._find_action('more','more.copy')
        await self._tap('more',target='more.copy')
        await self._delay(.5)
        raw = await self._io(clipboard_export)
        if raw == before:
            raise RecognitionError('Village export did not update the clipboard; check BlueStacks clipboard sharing')
        data = json.loads(raw)
        tag = data.get('tag','') if discover else self.settings.walls.player_tag
        # The game's generated export can lag the observed Copy event (~30s).
        # A changed clipboard plus the strict 60s age bound prevents reuse.
        progress = read_village(raw,tag,since-60,time.time())
        self.village_data = data
        await self._transition('more','more.close','settings')
        await self._transition('settings','settings.close','home')
        previous = self.wall_progress
        if previous and (progress.town_hall != previous.town_hall or progress.levels.total() != previous.levels.total()
                         or progress.timestamp <= previous.timestamp):
            raise RecognitionError('Village identity, wall count or export freshness changed')
        self.wall_progress = progress
        self.event(f'TH{progress.town_hall}: {progress.remaining} walls remaining, target level {progress.target}')
        return progress

    async def _army_capacity(self, screen, group='troops'):
        key = f'{screen}.{group}.capacity'
        values = []
        for _ in range(2):
            frame = await self._screen(screen)
            values.append(self.recognizer.ocr.ratio(self.recognizer.asset(key).rect.crop(frame)))
            await self._delay(.2)
        if values[0] != values[1]:
            raise RecognitionError('Army capacity changed during verification')
        return values[0]

    async def _fill_army(self, group, units, used=0):
        for unit in units:
            slug = UNITS[unit.name][3]
            target = f'army_picker.{slug}'
            for page in range(4):
                frame = await self._screen('army_picker')
                asset = self.recognizer.asset(target)
                template = cv2.imread(str(self.recognizer.root/'templates'/asset.image))
                band = frame[425:700]
                scores = cv2.matchTemplate(band,template,cv2.TM_CCOEFF_NORMED)
                _,score,_,(x,y) = cv2.minMaxLoc(scores)
                if score >= asset.threshold:
                    asset.rect.x,asset.rect.y = x,y+425
                    if self.recognizer.matches(target,frame):
                        break
                if page==3:
                    raise RecognitionError(f'{unit.name} missing from the unlocked army picker')
                async with self.device_lock:
                    self.recognizer.expect('army_picker',await self._io(self.device.capture))
                    await self._io(self.device.swipe,1120,560,420,560,500,allowed=self.input_allowed)
                await self._delay(.5)
            for _ in range(unit.count):
                before,capacity = await self._army_capacity('army_picker',group)
                if before != used:
                    raise UncertainAction('Army preparation count disagrees; no repeat input')
                await self._tap('army_picker',target=target)
                used += UNITS[unit.name][1]
                if (await self._army_capacity('army_picker',group)) != (used,capacity):
                    raise UncertainAction(f'{unit.name} preparation outcome is uncertain; inspect the army')

    async def _prepare_army(self):
        cfg = self.settings
        if recommend(self.village_data,cfg.farming.army.town_hall) != cfg.farming.composition:
            raise RecognitionError('Army capacity or unlocks changed. Check the account to update the banner.')
        if cfg.farming.composition != self.recognizer.profile.prepared_army:
            raise RecognitionError('This army appearance needs calibration in Advanced before automatic preparation.')
        groups = {'troops':'troop','spells':'spell','siege':'siege'}
        for group,kind in groups.items():
            units = [u for u in cfg.farming.composition if UNITS[u.name][2]==kind]
            target = f'army.{group}.layout'
            frame = await self._screen('army')
            if not self.recognizer.matches(target,frame):
                used,capacity = await self._army_capacity('army',group)
                if used:
                    removal = 'remove_spells' if group=='spells' else 'remove_troops'
                    await self._transition('army',f'army.clear_{group}',removal)
                    await self._transition(removal,f'{removal}.accept','army')
                    if (await self._army_capacity('army',group))[0] != 0:
                        raise UncertainAction('Army removal was not confirmed; inspect before continuing')
                if units:
                    await self._transition('army',f'army.edit_{group}','army_picker')
                    await self._fill_army(group,units)
                    await self._tap('army_picker',point=(900,105))
                    await self._delay(.5)
                    await self._screen('army')
            for _ in range(2):
                if not self.recognizer.matches(target,await self._screen('army')):
                    raise RecognitionError(f'Prepared {group} do not match the shown army')
                await self._delay(.2)
        self.event('Verified prepared army types, quantities and capacity against the banner')

    async def _find_action(self, screen, key):
        last = None
        for _ in range(12):
            frame = await self._screen(screen)
            pos = self.recognizer.find_row(key,frame)
            if pos is not None:
                await self._delay(.2)
                if self.recognizer.find_row(key,await self._screen(screen)) == pos:
                    self.recognizer.asset(key).rect.y = pos
                    return
                raise RecognitionError('Menu row moved during verification')
            h,w = frame.shape[:2]
            x = round(w*.86) if screen == 'build' else w//2
            if last is not None and cv2.norm(frame[h//6:h*4//5,x-30:x+30],last,cv2.NORM_L1)/last.size < 1:
                break
            last = frame[h//6:h*4//5,x-30:x+30].copy()
            async with self.device_lock:
                current = await self._io(self.device.capture)
                self.recognizer.expect(screen,current)
                await self._io(self.device.swipe,x,h*4//5,x,h//3,350,allowed=self.input_allowed)
            await self._delay(.6)
        raise RecognitionError(f'{key} missing from scanned menu; inspect the village')

    async def _walls(self, progress=None):
        currency = self.settings.walls.currency
        reserve = getattr(self.settings.walls, f"reserve_{currency}")
        menu = self.settings.walls.build_menu
        points = [None] if progress else ([None] * self.settings.walls.upgrade_limit if menu else self.settings.calibration.walls)
        for point in points:
            if not self.settings.walls.until_max and self.upgrades >= self.settings.walls.upgrade_limit:
                return
            await self._screen("home", camera=not menu)
            balance = await self._number("home", f"home.wallet_{currency}")
            if progress:
                balances = {cur:await self._number('home',f'home.wallet_{cur}') for cur in ('gold','elixir')}
                if await self._number('home','home.builders_free') <= 0:
                    raise RecognitionError('No verified available builder')
            self._wall_in_progress = True
            if menu:
                await self._transition("home", "home.build", "build")
                if hasattr(self.recognizer,'find_row'):
                    await self._find_action('build','build.wall')
                await self._transition("build", "build.wall", "build_wall")
                await self._transition("build_wall", "build_wall.close", "wall")
            else:
                await self._tap("home", point=(point.x, point.y), camera=True)
                await self._screen("wall")
            name = await self._number("wall", "wall.name")
            if not re.fullmatch(r"Wall(?: \(Level [0-9]+\))?", name, re.IGNORECASE):
                raise RecognitionError(f"Selected object is not a verified wall: {name!r}")
            level = await self._number("wall", "wall.level")
            frame = await self._screen("wall")
            if progress:
                if not progress.eligible(level):
                    raise RecognitionError('Selected wall level disagrees with village export')
                offers = {}
                for cur in ('gold','elixir'):
                    if self.recognizer.matches(f'wall.currency_{cur}',frame):
                        price = await self._number('wall',f'wall.cost_{cur}')
                        available = balances[cur] - max(500000,getattr(self.settings.walls,f'reserve_{cur}'))
                        if 0 < price <= available:
                            offers[cur] = (available,price)
                if not offers:
                    if not any(self.recognizer.matches(f'wall.currency_{cur}',frame) for cur in balances):
                        raise RecognitionError('No verified resource upgrade option')
                    await self._transition('wall','wall.close','home')
                    self._wall_in_progress = False
                    return
                currency = max(offers,key=lambda cur:(offers[cur][0],cur=='gold'))
                reserve = max(500000,getattr(self.settings.walls,f'reserve_{currency}'))
                balance = balances[currency]
            if not self.recognizer.matches(f"wall.currency_{currency}", frame):
                raise RecognitionError("Wall upgrade currency does not match the preset")
            selected_balance = await self._number("wall", f"wall.wallet_{currency}")
            if selected_balance != balance:
                raise RecognitionError("Wallet changed while selecting the wall; inspect before spending")
            await self._transition("wall", f"wall.upgrade_{currency}", "confirm", checks={
                f"wall.wallet_{currency}": balance, f"wall.currency_{currency}": True,
                "wall.name": name, "wall.level": level,
            })
            cost = await self._number("confirm", "confirm.cost")
            frame = await self._screen("confirm")
            if not self.recognizer.matches(f"confirm.currency_{currency}", frame) or cost <= 0:
                raise RecognitionError("Wall confirmation has an unexpected currency or cost")
            if progress and cost != offers[currency][1]:
                raise RecognitionError('Displayed wall price changed at confirmation')
            limit = self.settings.walls.spend_limit
            if limit is not None and self.wall_spent + cost > limit:
                await self._transition("confirm","confirm.cancel","wall")
                await self._transition("wall","wall.close","home")
                self._wall_in_progress = False
                self.event("Wall skipped: session spending ceiling")
                return
            if balance - cost < reserve:
                self.event("Wall skipped: upgrade would cross the resource reserve")
                await self._transition("confirm", "confirm.cancel", "wall")
                await self._transition("wall", "wall.close", "home")
                self._wall_in_progress = False
                continue
            self.event(f'Confirming wall level {level} → {level+1}: {cost:,} {currency}; wallet before {balance:,}. Outcome must be verified; do not retry an interrupted purchase.')
            await self._transition("confirm", "confirm.accept", "wall", checks={
                "confirm.cost": cost,
                f"confirm.currency_{currency}": True,
            })
            try:
                after = await self._number("wall", "wall.level")
                if after != level + 1:
                    raise UncertainAction("Wall upgrade outcome is uncertain; do not retry")
                await self._transition("wall", "wall.close", "home")
                observed_balance = await self._number("home", f"home.wallet_{currency}")
                if observed_balance < reserve or observed_balance != balance - cost:
                    raise UncertainAction("Wall balance change does not match the verified cost; inspect before continuing")
            except Exception as exc:
                raise UncertainAction(str(exc)) from exc
            self.wallet[currency] = observed_balance
            self.upgrades += 1
            self.wall_spent += cost
            self._wall_in_progress = False
            self.event(f"Observed wall upgrade: level {level} → {after}, {cost:,} {currency}; wallet {balance:,} → {observed_balance:,}")
            if progress:
                return level

    async def _prepare_corner(self):
        for attempt in range(4):
            frame = await self._screen('base')
            try:
                return self.recognizer.deployment_corner(frame)
            except PlacementUnavailable:
                if attempt == 3:
                    raise
            async with self.device_lock:
                await self._gate.wait()
                current = await self._io(self.device.capture)
                try:
                    self.recognizer.expect('base', current)
                except RecognitionError:
                    self.recognizer.expect('battle', current)
                try:
                    h, w = current.shape[:2]
                    await self._io(self.device.swipe, round(w*.4), round(h*.45),
                                   round(w*.8), round(h*.45), 400, allowed=self.input_allowed)
                except InterruptedError:
                    raise RecognitionError('Camera preparation cancelled')
                except Exception as exc:
                    raise UncertainAction(f'Camera gesture outcome uncertain: {exc}') from exc
            await self._delay(.3)

    async def _await_results(self):
        end = time.monotonic() + self.settings.live.battle_timeout
        unknown_since = None
        while time.monotonic() < end:
            await self._gate.wait()
            frame = await self._capture()
            try:
                self.recognizer.expect('results', frame)
                return frame
            except RecognitionError:
                try:
                    self.recognizer.expect('battle', frame)
                    unknown_since = None
                except RecognitionError:
                    unknown_since = unknown_since or time.monotonic()
                    if time.monotonic() - unknown_since >= self.settings.live.transition_timeout:
                        raise RecognitionError('Battle end remained on an unknown screen')
            await self._delay(.2)
        raise RecognitionError('Battle completion timed out; inspect the game')

    async def _cycle(self):
        cfg = self.settings
        continuous = cfg.walls.until_max
        monitored = continuous or cfg.farming.prepare_army
        if cfg.farming.prepare_army and cfg.farming.auto_corner:
            await self._normalize_camera()
        while True:
            progress = None
            await self._screen("home", camera=cfg.farming.collect or (cfg.walls.enabled and not cfg.walls.build_menu))
            if monitored:
                progress = await self._export()
                while continuous and progress.remaining and (self.attacks > 0 or not cfg.farming.prepare_army):
                    level = await self._walls(progress)
                    if level is None:
                        break
                    expected = progress.levels.copy()
                    expected[level] -= 1
                    expected[level+1] += 1
                    progress = await self._export()
                    if progress.levels != expected:
                        raise UncertainAction('Export did not confirm the purchased wall')
                if not progress.remaining:
                    return 'All existing walls verified at the Town Hall maximum'
            if not continuous and self.elapsed >= cfg.session.duration_minutes * 60:
                return "Session duration limit reached"
            if cfg.farming.collect:
                for point in cfg.calibration.collectors:
                    before = {key: await self._number("home", f"home.wallet_{key}") for key in RESOURCE_KEYS}
                    await self._tap("home", point=(point.x, point.y), camera=True)
                    await self._delay(1.0)
                    await self._screen("home", camera=True)
                    after = {key: await self._number("home", f"home.wallet_{key}") for key in RESOURCE_KEYS}
                    await self._screen("home", camera=True)
                    if not any(after[key] > before[key] for key in RESOURCE_KEYS):
                        raise UncertainAction("Collector did not produce a verified resource increase; inspect the selected object. No repeat tap.")
                    self.collections += 1
                    self.wallet.update(after)
                self.event("Observed resource increases after collector inputs")
            if cfg.farming.attack:
                self._deployment_started = False
                self._last_placement_at = None
                await self._transition("home", "home.attack", "matchmaking")
                await self._transition("matchmaking", "matchmaking.find_regular", "army",
                                       checks={"matchmaking.regular": True})
                frame = await self._screen("army")
                if cfg.farming.prepare_army:
                    await self._prepare_army()
                    frame = await self._screen('army')
                if not self.recognizer.matches("army.ready", frame):
                    raise RecognitionError("Prepared army is not ready")
                if not cfg.farming.dump_all:
                    self._check_plan(await self._inventory("army"))
                await self._transition("army", "army.attack", "base")
                self.recognizer.select_inventory(await self._screen('base'))
                qualified = False
                for attempt in range(cfg.farming.search_limit):
                    loot = {key: await self._number("base", f"base.{key}") for key in RESOURCE_KEYS
                            if getattr(cfg.farming, f"min_{key}") > 0}
                    self.searches += 1
                    self.event(f"Observed candidate loot: {loot}")
                    if all(value >= getattr(cfg.farming, f"min_{key}") for key, value in loot.items()):
                        if cfg.farming.auto_corner and not self.recognizer.supports_deployment_scenery(await self._screen('base')):
                            self.event('Skipped unsupported enemy scenery before deployment; looking for calibrated grass')
                        else:
                            try:
                                if cfg.farming.auto_corner:
                                    x, y = await self._prepare_corner()
                                    cfg.farming.deployment[0].x, cfg.farming.deployment[0].y = x, y
                                    self.event(f'Observed clear ground outside placement boundary: ({x}, {y})')
                            except PlacementUnavailable as exc:
                                self.event(f'Skipped candidate before deployment: {exc}')
                            else:
                                qualified = True
                                break
                    if attempt + 1 < cfg.farming.search_limit:
                        await self._transition("base", "base.next", "base")
                if not qualified or (not continuous and self.elapsed >= cfg.session.duration_minutes * 60):
                    await self._transition("base", "base.home", "home")
                    return "Search or duration limit reached; returned home"
                inventory = await self._inventory("base")
                self._check_plan(inventory)
                # The first deployment starts the battle. Calibrate a begin action
                # only if the current game has an explicit battle-start button.
                self._in_battle = True
                try:
                    await self._begin_and_deploy(inventory)
                except BattleFinished:
                    self.event("Battle finished; remaining deployment steps cancelled")
                await self._await_results()
                gains = self.recognizer.result_loot(await self._screen('results'))
                await self._delay(.2)
                if gains != self.recognizer.result_loot(await self._screen('results')):
                    raise RecognitionError('Battle result readings disagree')
                await self._transition("results", "results.home", "home")
                self._in_battle = False
                self.attacks += 1
                for key in RESOURCE_KEYS:
                    self.loot[key] += gains[key]
                self.event(f"Observed battle results: {gains}")
            if continuous:
                continue
            if self.elapsed >= cfg.session.duration_minutes * 60:
                return "Session duration limit reached; returned home"
            if cfg.walls.enabled:
                level = await self._walls(progress)
                if level is not None and progress:
                    expected = progress.levels.copy()
                    expected[level] -= 1
                    expected[level+1] += 1
                    if (await self._export()).levels != expected:
                        raise UncertainAction('Export did not confirm the purchased wall')
            if not cfg.farming.attack or self.attacks >= cfg.session.attack_limit:
                return "Enabled tasks completed" if not cfg.farming.attack else "Attack limit reached"

    async def _normalize_camera(self):
        for attempt in range(5):
            await self._gate.wait()
            async with self.device_lock:
                before=await self._io(self.device.capture)
                self.recognizer.expect('home',before)
                try:
                    await self._io(self.device.zoom_out,allowed=self.input_allowed)
                except InterruptedError:
                    raise RecognitionError('Camera normalization cancelled; return Home before a new start')
                except Exception as exc:
                    raise UncertainAction(f'Camera normalization failed: {exc}') from exc
            await self._delay(.5)
            after=await self._screen('home')
            difference=cv2.norm(before[120:500,200:900],after[120:500,200:900],cv2.NORM_L1)/(380*700*3)
            if attempt>=2 and difference<5:
                self.event('Verified settled Home zoom after normalization')
                return
        raise RecognitionError('Home zoom did not settle; inspect the emulator camera')

    async def _begin_and_deploy(self, inventory):
        # Base preview transitions to battle with the first unit placement. Treat
        # that unit as a real deployment and verify it before any further taps.
        plan = self._deployment_plan(inventory)
        step = plan[0]
        self._deployed.clear()
        self._spent.clear()
        key = f"{step.kind}.{step.slot}"
        before_count = inventory[key][1]
        if step.kind == "hero":
            self._deployed.add(key)
        await self._tap("base", target=f"base.{key}.ready")
        self._deployment_started = True
        await self._tap("base", point=(step.x, step.y), interval=step.delay)
        frame = await self._screen("battle")
        try:
            after = self.recognizer.slot_state("battle", next(s for s in self.recognizer.profile.slots if s.key == key), frame)
        except RecognitionError as exc:
            raise UncertainAction('First deployment reading is uncertain; inspect before a new session') from exc
        if (step.kind == "hero" and after[0] != "deployed") or (step.kind != "hero" and after[1] != before_count - 1):
            raise UncertainAction("First deployment outcome is uncertain; no retry")
        if after[1] == 0:
            self._spent.add(key)
        # Execute the remainder without changing the session snapshot.
        original = self.settings.farming.deployment
        remaining = [s.model_copy(deep=True) for s in plan]
        if remaining[0].count != "all":
            remaining[0].count -= 1
        if remaining[0].count == 0 or step.kind == "hero" or after[1] == 0:
            remaining.pop(0)
        try:
            self.settings.farming.deployment = remaining
            await self._deploy(await self._inventory("battle"))
        finally:
            self.settings.farming.deployment = original

    async def _run(self):
        try:
            await self._io(self.recognizer.ready, self.settings)
            reason = await self._cycle()
            self._finish("completed", reason)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._recover(exc)
            # Resuming an interrupted workflow at an arbitrary Python statement
            # could repeat inputs. Finish rather than replay the whole cycle.
            cfg = self.settings
            await self._screen("home", camera=cfg.farming.collect or (cfg.walls.enabled and not cfg.walls.build_menu))
            self._finish("stopped", "Home rechecked; start a new session to continue")
        finally:
            self.input_allowed.clear()
