"""Local calibration assets, fixed-resolution recognition, and conservative OCR."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import subprocess
import threading
from typing import Literal

import cv2
import numpy as np
from pydantic import Field, model_validator

from .config import Model, Settings, atomic_json, preset_path

SCREENS = ("home", "army", "matchmaking", "base", "battle", "results", "wall", "confirm")
RESOURCE_KEYS = ("gold", "elixir", "dark_elixir")


class RecognitionError(RuntimeError):
    pass


class Rect(Model):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=4)
    height: int = Field(ge=4)

    def crop(self, frame):
        if self.x + self.width > frame.shape[1] or self.y + self.height > frame.shape[0]:
            raise RecognitionError("Region exceeds screenshot dimensions; recalibrate")
        return frame[self.y:self.y + self.height, self.x:self.x + self.width]

    @property
    def center(self):
        return self.x + self.width // 2, self.y + self.height // 2


class Asset(Model):
    rect: Rect
    kind: Literal["template", "number", "text"] = "template"
    image: str = Field(pattern=r"^[a-f0-9]{64}\.png$")
    threshold: float = Field(default=0.90, ge=0.80, le=1.0)
    validated: bool = False
    captured_at: str


class Slot(Model):
    kind: Literal["troop", "hero", "spell"]
    slot: int = Field(ge=1, le=20)

    @property
    def key(self):
        return f"{self.kind}.{self.slot}"


class Profile(Model):
    version: Literal[1] = 1
    width: int = Field(ge=320, le=7680)
    height: int = Field(ge=240, le=4320)
    assets: dict[str, Asset] = Field(default_factory=dict)
    slots: list[Slot] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def valid_regions(self):
        if self.width <= self.height:
            raise ValueError("Use a landscape screenshot")
        if len({s.key for s in self.slots}) != len(self.slots):
            raise ValueError("Each deployment slot must be unique")
        for asset in self.assets.values():
            r = asset.rect
            if r.x + r.width > self.width or r.y + r.height > self.height:
                raise ValueError("Profile region exceeds screenshot dimensions")
        for screen in ("army", "base", "battle"):
            for slot in self.slots:
                states = [self.assets[f"{screen}.{slot.key}.{state}"].rect
                          for state in ("ready", "unavailable", "deployed" if slot.kind == "hero" else "depleted")
                          if f"{screen}.{slot.key}.{state}" in self.assets]
                if states and any(r != states[0] for r in states):
                    raise ValueError(f"{screen}.{slot.key} state templates must use identical region bounds")
        return self


def requirements(settings: Settings, profile: Profile) -> dict[str, str]:
    required = {"home": "template", "home.camera": "template"}
    if settings.farming.collect:
        required.update({f"home.wallet_{key}": "number" for key in RESOURCE_KEYS})
    if settings.farming.attack:
        required.update({s: "template" for s in ("army", "matchmaking", "base", "battle", "results")})
        required.update({s: "template" for s in ("home.army", "army.close", "army.ready", "army.roster", "home.attack", "matchmaking.find", "base.next", "base.home", "base.roster", "battle.roster", "results.home")})
        for screen in ("base", "results"):
            required.update({f"{screen}.{key}": "number" for key in RESOURCE_KEYS})
        for slot in profile.slots:
            for screen in ("army", "base", "battle"):
                required[f"{screen}.{slot.key}.area"] = "template"
                required[f"{screen}.{slot.key}.ready"] = "template"
                required[f"{screen}.{slot.key}.unavailable"] = "template"
                if slot.kind != "hero":
                    required[f"{screen}.{slot.key}.count"] = "number"
                if screen == "battle":
                    required[f"{screen}.{slot.key}." + ("deployed" if slot.kind == "hero" else "depleted")] = "template"
    if settings.walls.enabled:
        currency = settings.walls.currency
        required.update({s: "template" for s in ("wall", "confirm", "wall.close", f"wall.upgrade_{currency}", f"wall.currency_{currency}", f"confirm.currency_{currency}", "confirm.accept", "confirm.cancel")})
        required.update({"wall.name": "text", "wall.level": "number", "confirm.cost": "number", f"home.wallet_{currency}": "number", f"confirm.wallet_{currency}": "number"})
    return required


def profile_path(root: Path, name: str):
    return preset_path(root / "profiles", name)


def load_profile(root: Path, name: str) -> Profile:
    return Profile.model_validate_json(profile_path(root, name).read_text(encoding="utf-8"))


def save_profile(root: Path, name: str, profile: Profile):
    validated = Profile.model_validate(profile.model_dump())
    atomic_json(profile_path(root, name), validated.model_dump())


def record_asset(root: Path, profile: Profile, name: str, frame, rect: Rect, kind="template", threshold=0.90):
    check_dimensions(profile, frame)
    if not re.fullmatch(r"[a-z][a-z0-9_.]{0,99}", name):
        raise ValueError("Asset name must use lowercase letters, numbers, dots, and underscores")
    crop = rect.crop(frame)
    if kind == "template" and float(np.std(crop)) < 4:
        raise ValueError("Choose a distinctive image region, not a flat color")
    ok, png = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("Could not encode calibration image")
    filename = hashlib.sha256(png.tobytes()).hexdigest() + ".png"
    folder = root / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    if not path.exists():
        path.write_bytes(png.tobytes())
    profile.assets[name] = Asset(rect=rect, kind=kind, image=filename, threshold=threshold,
                                 captured_at=datetime.now(timezone.utc).isoformat())
    # A changed slot changes which pixels the roster guard ignores.
    if any(f".{state}" in name for state in ("area", "ready", "unavailable", "count", "deployed", "depleted")) and name.count(".") >= 3:
        guard = profile.assets.get(name.split(".")[0] + ".roster")
        if guard:
            guard.validated = False


def check_dimensions(profile, frame):
    if frame is None or frame.shape[:2] != (profile.height, profile.width):
        raise RecognitionError("Screenshot dimensions changed; recalibrate before live input")


class OCR:
    _lock = threading.Lock()

    def __init__(self, executable: str):
        self.executable = executable

    def check(self):
        if not Path(self.executable).is_file():
            raise RecognitionError("Tesseract not found. Install Tesseract with English data and set its executable path.")
        result = subprocess.run([self.executable, "--list-langs"], capture_output=True, text=True,
                                check=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "eng" not in result.stdout.split():
            raise RecognitionError("Tesseract English training data is missing; install eng.traineddata")

    def text(self, crop):
        import pytesseract
        # The game uses bright outlined lettering. Preserve all glyphs (including
        # K/M suffixes) while removing the colored background before OCR.
        white = 255 - cv2.inRange(crop, (170, 170, 170), (255, 255, 255))
        for source in (white, cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)):
            gray = cv2.resize(source, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            gray = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
            with self._lock:
                pytesseract.pytesseract.tesseract_cmd = self.executable
                data = pytesseract.image_to_data(gray, config="--psm 7", lang="eng", timeout=5,
                                                 output_type=pytesseract.Output.DICT)
            words = [(t.strip(), float(c)) for t, c in zip(data["text"], data["conf"]) if t.strip()]
            if words and all(c >= 70 for _, c in words):
                return " ".join(t for t, _ in words)
        raise RecognitionError("OCR is empty or uncertain; inspect and recalibrate its crop")

    @staticmethod
    def parse_number(text):
        # Read letters too: a digits-only OCR pass could silently turn '10K' into '10'.
        if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[ ,][0-9]{3})+)", text):
            raise RecognitionError(f"Expected a full integer, got {text!r}; no abbreviated values are accepted")
        return int(text.replace(" ", "").replace(",", ""))

    def number(self, crop):
        return self.parse_number(self.text(crop))


class Recognizer:
    def __init__(self, root: Path, profile: Profile, ocr: OCR):
        self.root, self.profile, self.ocr = root, profile, ocr
        self.screen = "unknown"
        self.confidence = 0.0
        self._images = {}

    def asset(self, name, validated=True):
        asset = self.profile.assets.get(name)
        if asset is None or (validated and not asset.validated):
            raise RecognitionError(f"Calibrate and validate {name} on a second capture")
        return asset

    def score(self, name, frame):
        check_dimensions(self.profile, frame)
        asset = self.asset(name, validated=False)
        if name not in self._images:
            image = cv2.imread(str(self.root / "templates" / asset.image))
            if image is None:
                raise RecognitionError(f"Template file missing for {name}; recalibrate")
            self._images[name] = image
        template = self._images[name]
        crop = asset.rect.crop(frame)
        if name.endswith(".roster"):
            # Compare the whole strip except explicitly recognized slots. New slots
            # in previously empty areas therefore invalidate the inventory guard.
            mask = np.ones(crop.shape[:2], dtype=np.uint8)
            prefix = name.split(".")[0] + "."
            for key, value in self.profile.assets.items():
                if key.startswith(prefix) and key.count(".") == 3 and key.endswith(".area"):
                    r = value.rect
                    x1, y1 = max(0, r.x - asset.rect.x), max(0, r.y - asset.rect.y)
                    x2, y2 = min(asset.rect.width, r.x + r.width - asset.rect.x), min(asset.rect.height, r.y + r.height - asset.rect.y)
                    if x2 > x1 and y2 > y1:
                        mask[y1:y2, x1:x2] = 0
            if np.count_nonzero(mask) < 32:
                raise RecognitionError("Roster guard needs visible empty space around the calibrated slots")
            difference = np.abs(crop.astype(float) - template.astype(float))[mask.astype(bool)]
            return max(0.0, 1.0 - float(difference.mean()) / 255)
        from airtest.aircv.template_matching import TemplateMatching
        result = TemplateMatching(template, crop, threshold=0, rgb=True).find_best_result()
        return float(result["confidence"]) if result else 0.0

    def matches(self, name, frame):
        return self.score(name, frame) >= self.asset(name).threshold

    def expect(self, screen, frame):
        self.asset(screen)
        # Overlay screens take precedence over the underlying village/battle.
        for name in ("confirm", "wall", "results", "battle", "base", "army", "matchmaking", "home"):
            if name in self.profile.assets and self.profile.assets[name].validated and self.matches(name, frame):
                self.screen, self.confidence = name, self.score(name, frame)
                if name != screen:
                    raise RecognitionError(f"Expected {screen}, recognized {name}")
                return
        self.screen, self.confidence = "unknown", 0.0
        raise RecognitionError(f"Expected {screen}; screen not recognized")

    def read(self, name, frame):
        check_dimensions(self.profile, frame)
        asset = self.asset(name)
        if asset.kind == "number":
            return self.ocr.number(asset.rect.crop(frame))
        if asset.kind == "text":
            return self.ocr.text(asset.rect.crop(frame))
        raise RecognitionError(f"{name} is not an OCR region")

    def slot_state(self, screen, slot, frame):
        prefix = f"{screen}.{slot.key}."
        states = ["ready", "unavailable"] + (["deployed" if slot.kind == "hero" else "depleted"] if screen == "battle" else [])
        found = [state for state in states if self.matches(prefix + state, frame)]
        if len(found) != 1:
            raise RecognitionError(f"Ambiguous or unrecognized {slot.key} on {screen}")
        state = found[0]
        count = (1 if slot.kind == "hero" else self.read(prefix + "count", frame)) if state == "ready" else 0
        if state == "ready" and not 1 <= count <= 500:
            raise RecognitionError(f"Invalid available count for {slot.key}")
        return state, count

    def ready(self, settings):
        Profile.model_validate(self.profile.model_dump())
        missing = [name for name, kind in requirements(settings, self.profile).items()
                   if name not in self.profile.assets or not self.profile.assets[name].validated or self.profile.assets[name].kind != kind]
        if missing:
            raise RecognitionError("Calibration incomplete: " + ", ".join(missing))
        if (self.profile.width, self.profile.height) != (settings.calibration.width, settings.calibration.height):
            raise RecognitionError("Preset resolution differs from calibration profile")
        if settings.farming.collect and not settings.calibration.collectors:
            raise RecognitionError("Mark at least one collector for live collection")
        if settings.farming.attack:
            covered = {f"{s.kind}.{s.slot}" for s in settings.farming.deployment}
            calibrated = {s.key for s in self.profile.slots}
            if not calibrated or covered != calibrated:
                raise RecognitionError("Deployment steps must cover exactly the calibrated troop, hero, and spell slots")
        self.ocr.check()

    def validate_asset(self, name, frame):
        asset = self.asset(name, validated=False)
        if asset.kind == "template":
            score = self.score(name, frame)
            if score < asset.threshold:
                raise RecognitionError(f"{name}: score {score:.3f} is below {asset.threshold:.3f}")
            result = f"Match {score:.3f}"
        else:
            reference = self._images.get(name)
            if reference is None:
                reference = cv2.imread(str(self.root / "templates" / asset.image))
            if reference is None:
                raise RecognitionError("Reference crop is missing")
            reader = self.ocr.number if asset.kind == "number" else self.ocr.text
            before, after = reader(reference), reader(asset.rect.crop(frame))
            if before != after:
                raise RecognitionError(f"Readings disagree: {before!r} vs {after!r}")
            result = f"Consistent reading: {after}"
        asset.validated = True
        return result
