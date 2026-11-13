"""Deterministic simulation only. This module deliberately has no device dependency."""

import asyncio
from collections import deque
from datetime import datetime
import logging
import time

from .config import Settings

log = logging.getLogger("boaz")


class Runner:
    mode = "Simulation"
    def __init__(self, step_seconds: float = 0.8):
        self.status = "idle"
        self.phase = "Home"
        self.reason = "Ready for a simulated session"
        self.events = deque(maxlen=200)
        self.settings = Settings()
        self.step_seconds = step_seconds
        self._task = None
        self._gate = asyncio.Event()
        self._started = None
        self._paused_at = None
        self._paused_total = 0.0
        self._finished_elapsed = 0.0
        self._reset_counters()

    def _reset_counters(self):
        self.attacks = self.searches = self.upgrades = self.collections = 0
        self.loot = dict(gold=0, elixir=0, dark_elixir=0)
        self.wallet = dict(gold=1000000, elixir=1000000, dark_elixir=20000)

    @property
    def active(self):
        return self._task is not None and not self._task.done()

    @property
    def elapsed(self):
        if self._started is None:
            return self._finished_elapsed
        end = self._paused_at if self._paused_at is not None else time.monotonic()
        return max(0.0, end - self._started - self._paused_total)

    def event(self, message):
        entry = f"{datetime.now():%H:%M:%S}  {message}"
        self.events.append(entry)
        log.info(message)

    def start(self, settings: Settings):
        if self.active:
            raise ValueError("A session is already running; stop it before starting another")
        self.settings = Settings.model_validate(settings.model_dump())
        self._reset_counters()
        self._started = time.monotonic()
        self._paused_at = None
        self._paused_total = 0.0
        self._finished_elapsed = 0.0
        self._gate.set()
        self.status, self.phase = "running", "Home"
        self.reason = f"{self.mode} running" + ("; no gameplay input" if self.mode == "Simulation" else "; verified device input enabled")
        self.event(f"{self.mode.upper()} started" + (" · resources and results are synthetic" if self.mode == "Simulation" else " · resources and results are observed"))
        self._task = asyncio.create_task(self._run())

    def pause(self):
        if self.status == "running":
            self._paused_at = time.monotonic()
            self.status, self.reason = "paused", "Paused; resume to continue this session"
            self._gate.clear()
            self.event(f"{self.mode} paused")

    def resume(self):
        if self.status == "paused":
            self._paused_total += time.monotonic() - self._paused_at
            self._paused_at = None
            self.status, self.reason = "running", f"{self.mode} running"
            self._gate.set()
            self.event(f"{self.mode} resumed")

    async def stop(self):
        if self.active:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._finish("stopped", "Stopped by you; pending actions cancelled")

    def _finish(self, status, reason):
        self._finished_elapsed = self.elapsed
        self._started = None
        self.status, self.reason = status, reason
        self.event(reason)

    async def _wait(self, seconds):
        remaining = seconds
        while remaining > 0:
            await self._gate.wait()
            if self.elapsed >= self.settings.session.duration_minutes * 60:
                raise TimeoutError
            interval = min(0.05, remaining)
            before = self.elapsed
            await asyncio.sleep(interval)
            remaining -= max(0, self.elapsed - before)
        await self._gate.wait()
        if self.elapsed >= self.settings.session.duration_minutes * 60:
            raise TimeoutError

    async def _stage(self, phase, message):
        await self._gate.wait()
        self.phase = phase
        self.event(message)
        await self._wait(self.step_seconds)

    async def _run(self):
        try:
            cfg = self.settings
            while True:
                await self._stage("Home", "Simulated home screen recognized")
                if cfg.farming.collect:
                    await self._stage("Collect", "Simulating resource collection")
                    self.collections += 1
                    self.wallet["gold"] += 25000
                    self.wallet["elixir"] += 25000
                if cfg.farming.attack:
                    await self._stage("Army", "Simulated army ready")
                    for attempt in range(1, cfg.farming.search_limit + 1):
                        await self._stage("Search", f"Evaluating simulated base {attempt}")
                        self.searches += 1
                        candidate = dict(gold=100000 + attempt * 50000,
                                         elixir=80000 + attempt * 40000,
                                         dark_elixir=1000 + attempt * 200)
                        if all(candidate[key] >= getattr(cfg.farming, f"min_{key}") for key in candidate):
                            break
                    else:
                        self._finish("completed", "Search limit reached; no simulated base qualified")
                        return
                    for step in cfg.farming.deployment:
                        await self._stage("Deploy", f"Simulating {step.kind} slot {step.slot}: {step.count} at ({step.x}, {step.y})")
                        await self._wait((10 if step.count == "all" else step.count) * step.delay)
                    await self._stage("Battle", "Simulating battle completion")
                    await self._stage("Return", "Simulating return home")
                    self.attacks += 1
                    for key, amount in candidate.items():
                        self.loot[key] += amount
                        self.wallet[key] += amount
                if cfg.walls.enabled:
                    for point in cfg.calibration.walls:
                        if self.upgrades >= cfg.walls.upgrade_limit:
                            break
                        currency = cfg.walls.currency
                        reserve = getattr(cfg.walls, f"reserve_{currency}")
                        if self.wallet[currency] - 100000 < reserve:
                            self.event("Simulated wall skipped: resource reserve would be crossed")
                            break
                        await self._stage("Walls", f"Simulating verified wall at ({point.x}, {point.y}); cost 100,000 {currency}")
                        self.wallet[currency] -= 100000
                        self.upgrades += 1
                if not cfg.farming.attack:
                    self._finish("completed", "Enabled village tasks completed once")
                    return
                if self.attacks >= cfg.session.attack_limit:
                    self._finish("completed", "Attack limit reached")
                    return
        except TimeoutError:
            self._finish("completed", "Session duration limit reached")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._finish("error", f"Simulation failed: {exc}. Stop and start a new session.")
            log.exception("Simulation failed")
