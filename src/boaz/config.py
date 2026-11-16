"""Validated presets; only complete, valid files replace an existing preset."""

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DeviceSettings(Model):
    adb_path: str = ""
    address: str = "127.0.0.1:5555"


class Point(Model):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Calibration(Model):
    width: int = Field(default=1280, ge=320, le=7680)
    height: int = Field(default=720, ge=240, le=4320)
    collectors: list[Point] = Field(default_factory=list, max_length=100)
    walls: list[Point] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def check_points(self):
        if self.width <= self.height:
            raise ValueError("Calibration must use a landscape resolution")
        if any(p.x >= self.width or p.y >= self.height for p in self.collectors + self.walls):
            raise ValueError("Calibration points must be inside the recorded resolution")
        return self


class DeploymentStep(Point):
    kind: Literal["troop", "hero", "spell"] = "troop"
    slot: int = Field(default=1, ge=1, le=20)
    count: int | Literal["all"] = 10
    delay: float = Field(default=0.5, ge=0, le=30)

    @model_validator(mode="after")
    def check_count(self):
        if isinstance(self.count, int) and not 1 <= self.count <= 500:
            raise ValueError("Deployment count must be 1–500 or 'all'")
        if self.kind == "hero" and self.count != 1:
            raise ValueError("Heroes must have a deployment count of 1")
        return self


class LiveSettings(Model):
    profile: str = ""
    tesseract_path: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    transition_timeout: float = Field(default=30.0, ge=1, le=120)
    battle_timeout: float = Field(default=300.0, ge=30, le=600)


class ArmySuggestions(Model):
    town_hall: int = Field(ge=7, le=18)  # 7 represents the shared TH1–7 starter.
    wall_breakers: bool = False
    troops: int = Field(default=1, ge=1, le=19)
    heroes: int = Field(default=1, ge=0, le=4)
    spells: int = Field(default=1, ge=0, le=20)
    siege: int = Field(default=0, ge=0, le=1)


def town_hall_army(level: int, wall_breakers: bool = False) -> ArmySuggestions:
    return ArmySuggestions(town_hall=level, wall_breakers=wall_breakers if level >= 8 else False,
                           troops=2 if level >= 8 and wall_breakers else 1,
                           heroes=1 + int(level >= 9) + int(level >= 11) + int(level >= 13),
                           spells=2 if level >= 9 else 1, siege=int(level >= 10))


class ArmyUnit(Model):
    name: Literal['Valkyrie', 'Wall Breaker', 'Giant', 'Archer', 'Rage', 'Freeze', 'Lightning', 'Stone Slammer', 'Wall Wrecker']
    count: int = Field(ge=1, le=500)


class Farming(Model):
    prepare_army: bool = False
    composition: list[ArmyUnit] = Field(default_factory=list, max_length=9)
    collect: bool = False
    attack: bool = True
    dump_all: bool = True
    auto_corner: bool = True
    army: ArmySuggestions | None = None
    min_gold: int = Field(default=200000, ge=0, le=100000000)
    min_elixir: int = Field(default=150000, ge=0, le=100000000)
    min_dark_elixir: int = Field(default=0, ge=0, le=10000000)
    search_limit: int = Field(default=10, ge=1, le=1000)
    deployment: list[DeploymentStep] = Field(
        default_factory=lambda: [DeploymentStep(x=100, y=400, count="all")], max_length=50
    )


class WallSettings(Model):
    until_max: bool = False
    player_tag: str = ""
    spend_limit: int | None = Field(default=None, ge=0)
    enabled: bool = False
    build_menu: bool = False
    currency: str = Field(default="gold", pattern=r"^(gold|elixir)$")
    reserve_gold: int = Field(default=500000, ge=0, le=100000000)
    reserve_elixir: int = Field(default=500000, ge=0, le=100000000)
    upgrade_limit: int = Field(default=5, ge=1, le=500)


class SessionSettings(Model):
    attack_limit: int = Field(default=1, ge=1, le=1000)
    duration_minutes: float = Field(default=15.0, gt=0, le=1440)


class Settings(Model):
    live: LiveSettings = Field(default_factory=LiveSettings)
    device: DeviceSettings = Field(default_factory=DeviceSettings)
    calibration: Calibration = Field(default_factory=Calibration)
    farming: Farming = Field(default_factory=Farming)
    walls: WallSettings = Field(default_factory=WallSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)

    @model_validator(mode="after")
    def check_tasks(self):
        if self.farming.prepare_army and (not self.farming.army or not self.farming.composition
                or len({u.name for u in self.farming.composition}) != len(self.farming.composition)
                or not re.fullmatch(r'#[0289PYLQGRJCUV]+',self.walls.player_tag)):
            raise ValueError('Automatic army preparation requires a checked account, Town Hall and unique composition')
        if self.walls.until_max and not (self.farming.attack and self.walls.enabled and self.walls.build_menu
                                        and re.fullmatch(r'#[0289PYLQGRJCUV]+', self.walls.player_tag)):
            raise ValueError("Continuous farming requires attacks, Build-menu walls and the current player tag")
        if not (self.farming.collect or self.farming.attack or self.walls.enabled):
            raise ValueError("Enable at least one farming task")
        if self.farming.attack and not self.farming.deployment:
            raise ValueError("Attacks require at least one deployment step")
        if self.farming.auto_corner and not self.farming.dump_all:
            raise ValueError("Automatic corner placement requires dump mode")
        for step in self.farming.deployment:
            if step.x >= self.calibration.width or step.y >= self.calibration.height:
                raise ValueError("Deployment points must be inside the recorded resolution")
        if self.walls.enabled and not self.walls.build_menu and not self.calibration.walls:
            raise ValueError("Mark at least one wall before enabling wall upgrades")
        return self


def preset_path(directory: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", name):
        raise ValueError("Preset name: use 1–48 letters, numbers, hyphens, or underscores")
    # These names are reserved even when a file extension is present on Windows.
    if name.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        raise ValueError("That preset name is reserved by Windows")
    return directory / f"{name}.json"


def load_settings(path: Path) -> Settings:
    return Settings.model_validate_json(path.read_text(encoding="utf-8"))


def save_settings(path: Path, settings: Settings) -> None:
    validated = Settings.model_validate(settings.model_dump())
    atomic_json(path, validated.model_dump())


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            json.dump(data, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
