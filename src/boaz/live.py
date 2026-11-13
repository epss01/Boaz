"""Verified live workflow. Uncertain inputs require a stop and manual inspection."""

import asyncio
from datetime import datetime
from pathlib import Path
import re
import threading
import time

import cv2

from .recognition import RecognitionError, RESOURCE_KEYS
from .runner import Runner


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
        self._deployed = set()
        self._frame = None

    def start(self, settings):
        if not self.device.connected:
            raise RecognitionError("Connect the emulator before starting live farming")
        if self.active:
            raise ValueError("A live session is already active")
        self.resumable = True
        self.input_allowed.set()
        self._in_battle = False
        self._deployed.clear()
        super().start(settings)
        self.wallet = dict.fromkeys(RESOURCE_KEYS, 0)

    def pause(self):
        self.input_allowed.clear()
        super().pause()

    def resume(self):
        if not self.resumable:
            raise RecognitionError("An input outcome is uncertain. Stop, inspect the game, then start from home; it will not be retried.")
        self.input_allowed.set()
        super().resume()

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
                if self._in_battle and expected in {"base", "battle"} and self._frame is not None:
                    try:
                        self.recognizer.expect("results", self._frame)
                    except RecognitionError:
                        pass
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
                await self._recover(exc)

    async def _tap(self, screen, point=None, target=None, camera=False, checks=None):
        # Keep recognition and dispatch together, with no preview operation between.
        while True:
            await self._gate.wait()
            try:
                async with self.device_lock:
                    frame = await self._io(self.device.capture)
                    self._frame = frame
                    self.recognizer.expect(screen, frame)
                    if camera and not self.recognizer.matches("home.camera", frame):
                        raise RecognitionError("Village camera/layout changed; no input sent")
                    for name, expected in (checks or {}).items():
                        actual = (await self._io(self.recognizer.read, name, frame)
                                  if not isinstance(expected, bool) else self.recognizer.matches(name, frame))
                        if actual != expected:
                            raise RecognitionError(f"{name} changed before input; no command sent")
                    if target:
                        if not self.recognizer.matches(target, frame):
                            raise RecognitionError(f"Action target {target} is not recognized")
                        point = self.recognizer.asset(target).rect.center
                    try:
                        await self._io(self.device.tap, *point, allowed=self.input_allowed)
                    except InterruptedError:
                        continue
                    except Exception as exc:
                        raise UncertainAction(f"Input outcome uncertain: {exc}. Stop and inspect before starting again.") from exc
                return
            except UncertainAction:
                raise
            except Exception as exc:
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
        while time.monotonic() < end:
            await self._gate.wait()
            frame = await self._capture()
            try:
                self.recognizer.expect(after, frame)
                return
            except RecognitionError:
                # During an animation we observe only; an unexpected screen never
                # causes another navigation or spending tap.
                await self._delay(0.2)
        raise UncertainAction(f"{target} did not reach {after}; inspect the game. No automatic retry.")

    async def _inventory(self, screen, key=None):
        while True:
            try:
                return await self._inventory_once(screen, key)
            except BattleFinished:
                raise
            except Exception as exc:
                await self._recover(exc)

    async def _inventory_once(self, screen, key=None):
        frame = await self._screen(screen)
        if not self.recognizer.matches(f"{screen}.roster", frame):
            raise RecognitionError(f"{screen} army layout changed or contains an unconfigured slot")
        slots = [s for s in self.recognizer.profile.slots if key is None or s.key == key]
        first = {s.key: self.recognizer.slot_state(screen, s, frame) for s in slots}
        await self._delay(0.15)
        frame = await self._screen(screen)
        if not self.recognizer.matches(f"{screen}.roster", frame):
            raise RecognitionError(f"{screen} inventory layout changed during reading")
        values = {s.key: self.recognizer.slot_state(screen, s, frame) for s in slots}
        for slot in slots:
            if first[slot.key] != values[slot.key]:
                raise RecognitionError(f"Unstable availability/count for {slot.key}")
        return values

    def _check_plan(self, inventory):
        remaining = {key: count for key, (state, count) in inventory.items()}
        sequence = []
        for step in self.settings.farming.deployment:
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
            selected = False
            for _ in range(amount):
                current = await self._inventory("battle", key)
                state, count = current[key]
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
                await self._tap("battle", point=(step.x, step.y))
                await self._delay(max(0.2, step.delay))
                try:
                    observed = (await self._inventory("battle", key))[key]
                    if step.kind == "hero":
                        if observed[0] != "deployed":
                            raise UncertainAction(f"Hero {key} deployment is uncertain; no further portrait taps")
                    elif observed[1] != count - 1:
                        raise UncertainAction(f"{key} count did not decrease by exactly one; deployment will not be retried")
                except RecognitionError as exc:
                    raise UncertainAction(str(exc)) from exc
                inventory[key] = observed
        inventory = await self._inventory("battle")
        if any(count for _, count in inventory.values()):
            raise RecognitionError("Units remain after deployment; inspect preset and remaining slots")

    async def _walls(self):
        currency = self.settings.walls.currency
        reserve = getattr(self.settings.walls, f"reserve_{currency}")
        for point in self.settings.calibration.walls:
            if self.upgrades >= self.settings.walls.upgrade_limit:
                return
            await self._screen("home", camera=True)
            balance = await self._number("home", f"home.wallet_{currency}")
            await self._tap("home", point=(point.x, point.y), camera=True)
            await self._screen("wall")
            name = await self._number("wall", "wall.name")
            if not re.fullmatch(r"Wall(?: \(Level [0-9]+\))?", name, re.IGNORECASE):
                raise RecognitionError(f"Selected object is not a verified wall: {name!r}")
            level = await self._number("wall", "wall.level")
            frame = await self._screen("wall")
            if not self.recognizer.matches(f"wall.currency_{currency}", frame):
                raise RecognitionError("Wall upgrade currency does not match the preset")
            await self._transition("wall", f"wall.upgrade_{currency}", "confirm")
            cost = await self._number("confirm", "confirm.cost")
            frame = await self._screen("confirm")
            if not self.recognizer.matches(f"confirm.currency_{currency}", frame) or cost <= 0:
                raise RecognitionError("Wall confirmation has an unexpected currency or cost")
            balance = await self._number("confirm", f"confirm.wallet_{currency}")
            if balance - cost < reserve:
                self.event("Wall skipped: upgrade would cross the resource reserve")
                await self._transition("confirm", "confirm.cancel", "wall")
                await self._transition("wall", "wall.close", "home")
                continue
            await self._transition("confirm", "confirm.accept", "wall", checks={
                "confirm.cost": cost, f"confirm.wallet_{currency}": balance,
                f"confirm.currency_{currency}": True,
            })
            try:
                after = await self._number("wall", "wall.level")
                if after != level + 1:
                    raise UncertainAction("Wall upgrade outcome is uncertain; do not retry")
                await self._transition("wall", "wall.close", "home")
                observed_balance = await self._number("home", f"home.wallet_{currency}")
                if observed_balance < reserve or observed_balance > balance - cost:
                    raise UncertainAction("Wall balance change does not match the verified cost; inspect before continuing")
            except Exception as exc:
                raise UncertainAction(str(exc)) from exc
            self.wallet[currency] = observed_balance
            self.upgrades += 1
            self.event(f"Observed wall upgrade: level {level} → {after}, {cost:,} {currency}")

    async def _cycle(self):
        cfg = self.settings
        while True:
            await self._screen("home", camera=True)
            if self.elapsed >= cfg.session.duration_minutes * 60:
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
                await self._transition("home", "home.army", "army")
                frame = await self._screen("army")
                if not self.recognizer.matches("army.ready", frame):
                    raise RecognitionError("Prepared army is not ready")
                self._check_plan(await self._inventory("army"))
                await self._transition("army", "army.close", "home")
                await self._transition("home", "home.attack", "matchmaking")
                await self._transition("matchmaking", "matchmaking.find", "base")
                qualified = False
                for attempt in range(cfg.farming.search_limit):
                    loot = {key: await self._number("base", f"base.{key}") for key in RESOURCE_KEYS}
                    self.searches += 1
                    self.event(f"Observed candidate loot: {loot}")
                    if all(loot[key] >= getattr(cfg.farming, f"min_{key}") for key in RESOURCE_KEYS):
                        qualified = True
                        break
                    if attempt + 1 < cfg.farming.search_limit:
                        await self._tap("base", target="base.next")
                        await self._delay(1.0)
                        await self._screen("base")
                if not qualified or self.elapsed >= cfg.session.duration_minutes * 60:
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
                end = time.monotonic() + cfg.live.battle_timeout
                while True:
                    frame = await self._capture()
                    try:
                        self.recognizer.expect("results", frame)
                        break
                    except RecognitionError:
                        self.recognizer.expect("battle", frame)
                    if time.monotonic() >= end:
                        raise RecognitionError("Battle completion timed out; inspect the game")
                    await self._delay(0.5)
                gains = {key: await self._number("results", f"results.{key}") for key in RESOURCE_KEYS}
                await self._transition("results", "results.home", "home")
                self._in_battle = False
                self.attacks += 1
                for key in RESOURCE_KEYS:
                    self.loot[key] += gains[key]
                self.event(f"Observed battle results: {gains}")
            if self.elapsed >= cfg.session.duration_minutes * 60:
                return "Session duration limit reached; returned home"
            if cfg.walls.enabled:
                await self._walls()
            if not cfg.farming.attack or self.attacks >= cfg.session.attack_limit:
                return "Enabled tasks completed" if not cfg.farming.attack else "Attack limit reached"

    async def _begin_and_deploy(self, inventory):
        # Base preview transitions to battle with the first unit placement. Treat
        # that unit as a real deployment and verify it before any further taps.
        step = self.settings.farming.deployment[0]
        self._deployed.clear()
        key = f"{step.kind}.{step.slot}"
        before_count = inventory[key][1]
        if step.kind == "hero":
            self._deployed.add(key)
        await self._tap("base", target=f"base.{key}.ready")
        await self._tap("base", point=(step.x, step.y))
        await self._delay(max(0.2, step.delay))
        frame = await self._screen("battle")
        after = self.recognizer.slot_state("battle", next(s for s in self.recognizer.profile.slots if s.key == key), frame)
        if (step.kind == "hero" and after[0] != "deployed") or (step.kind != "hero" and after[1] != before_count - 1):
            raise UncertainAction("First deployment outcome is uncertain; no retry")
        # Execute the remainder without changing the session snapshot.
        original = self.settings.farming.deployment
        remaining = [s.model_copy(deep=True) for s in original]
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
            await self._screen("home", camera=True)
            self._finish("stopped", "Home rechecked; start a new session to continue")
        finally:
            self.input_allowed.clear()
