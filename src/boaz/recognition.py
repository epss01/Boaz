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

from .config import ArmyUnit, Model, Settings, atomic_json, preset_path

SCREENS = ("home", "army", "army_picker", "remove_troops", "remove_spells", "exit", "matchmaking", "base", "battle", "results", "wall", "confirm", "build", "build_wall", "bonus", "profile", "settings", "more")
RESOURCE_KEYS = ("gold", "elixir", "dark_elixir")


class RecognitionError(RuntimeError):
    pass


class PlacementUnavailable(RecognitionError):
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
    variants: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def valid_variants(self):
        if any(not re.fullmatch(r'[a-f0-9]{64}\.png',name) for name in self.variants):
            raise ValueError('Variant images must be calibrated template filenames')
        return self


class Slot(Model):
    kind: Literal["troop", "hero", "spell"]
    slot: int = Field(ge=1, le=20)
    single: bool = False

    @property
    def key(self):
        return f"{self.kind}.{self.slot}"


class Profile(Model):
    version: Literal[1] = 1
    width: int = Field(ge=320, le=7680)
    height: int = Field(ge=240, le=4320)
    assets: dict[str, Asset] = Field(default_factory=dict)
    slots: list[Slot] = Field(default_factory=list, max_length=60)
    prepared_army: list[ArmyUnit] = Field(default_factory=list,max_length=9)
    inventory_profiles: list[str] = Field(default_factory=list, max_length=8)
    result_layouts: dict[str, list[Literal['gold', 'elixir', 'dark_elixir']]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_regions(self):
        if self.width <= self.height:
            raise ValueError("Use a landscape screenshot")
        if len({s.key for s in self.slots}) != len(self.slots):
            raise ValueError("Each deployment slot must be unique")
        for name, resources in self.result_layouts.items():
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,30}', name) or not resources or len(resources) != len(set(resources)):
                raise ValueError('Result layouts need a simple name and unique resource rows')
        for asset in self.assets.values():
            r = asset.rect
            if r.x + r.width > self.width or r.y + r.height > self.height:
                raise ValueError("Profile region exceeds screenshot dimensions")
        for screen in ("army", "base", "battle"):
            for slot in self.slots:
                states = [self.assets[f"{screen}.{slot.key}.{state}"].rect
                          for state in ("ready", "unavailable", "deployed", "depleted")
                          if f"{screen}.{slot.key}.{state}" in self.assets]
                if states and any(r != states[0] for r in states):
                    raise ValueError(f"{screen}.{slot.key} state templates must use identical region bounds")
        return self


def initial_slots(settings: Settings) -> list[Slot]:
    army = settings.farming.army
    if army is None:
        return [Slot(kind=k, slot=s) for k, s in sorted(
            {(a.kind, a.slot) for a in settings.farming.deployment})]
    slots = [Slot(kind="troop", slot=i) for i in range(1, army.troops + 1)]
    if army.siege:
        slots.append(Slot(kind="troop", slot=army.troops + 1, single=True))
    slots.extend(Slot(kind=kind, slot=i) for kind, count in
                 (("hero", army.heroes), ("spell", army.spells)) for i in range(1, count + 1))
    return slots


def requirements(settings: Settings, profile: Profile) -> dict[str, str]:
    required = {"home": "template"}
    if settings.farming.collect or (settings.walls.enabled and not settings.walls.build_menu):
        required['home.camera'] = 'template'
    if settings.farming.collect:
        required.update({f"home.wallet_{key}": "number" for key in RESOURCE_KEYS})
    if settings.farming.attack:
        if settings.farming.prepare_army:
            required['army_picker'] = 'template'
            required['army_picker.dismiss'] = 'template'
            for group in ('troops','spells','siege'):
                removal = 'remove_spells' if group=='spells' else 'remove_troops'
                required.update(dict.fromkeys((f'army.{group}.layout',f'army.clear_{group}',f'army.edit_{group}',
                    removal,f'{removal}.accept'),'template'))
                required.update(dict.fromkeys((f'army.{group}.capacity',f'army_picker.{group}.capacity'),'text'))
            from .army import UNITS
            for unit in settings.farming.composition:
                required[f'army_picker.{UNITS[unit.name][3]}'] = 'template'
        if 'bonus' in profile.assets:
            required.update({'bonus':'template','bonus.close':'template'})
        required.update({s: "template" for s in ("army", "matchmaking", "base", "battle", "results")})
        required.update({s: "template" for s in ("army.attack", "army.ready", "home.attack", "matchmaking.regular", "matchmaking.find_regular", "base.next", "base.home", "base.roster", "battle.roster", "results.home")})
        if not settings.farming.dump_all:
            required["army.roster"] = "template"
        for screen in ("base", "results"):
            if screen == 'results' and profile.result_layouts:
                for layout, resources in profile.result_layouts.items():
                    required[f'results.{layout}.anchor'] = 'template'
                    required.update({f'results.{layout}.{key}': 'number' for key in resources})
                continue
            required.update({f"{screen}.{key}": "number" for key in RESOURCE_KEYS})
        for slot in profile.slots:
            for screen in (("base", "battle") if settings.farming.dump_all else ("army", "base", "battle")):
                required[f"{screen}.{slot.key}.area"] = "template"
                prefix = f"{screen}.{slot.key}."
                state = "ready" if prefix + "ready" in profile.assets else "unavailable"
                required[prefix + state] = "template"
                if slot.kind != "hero" and not slot.single and state == "ready":
                    required[f"{screen}.{slot.key}.count"] = "number"
                if screen == "battle" and state == "ready":
                    required[f"{screen}.{slot.key}." + ("deployed" if slot.kind == "hero" or slot.single else "depleted")] = "template"
    if settings.walls.enabled:
        currency = settings.walls.currency
        if settings.walls.build_menu:
            required.update({s: "template" for s in ("home.build", "build", "build.wall", "build_wall", "build_wall.close")})
        required.update({s: "template" for s in ("wall", "confirm", "wall.close", f"wall.upgrade_{currency}", f"wall.currency_{currency}", f"confirm.currency_{currency}", "confirm.accept", "confirm.cancel")})
        required.update({"wall.name": "text", "wall.level": "number", "confirm.cost": "number", f"home.wallet_{currency}": "number", f"wall.wallet_{currency}": "number"})
        if settings.walls.until_max or settings.farming.prepare_army:
            required.update(dict.fromkeys(("home.profile","profile","profile.settings","settings","settings.more","more","more.copy",
                "more.close","settings.close"), "template"))
            required['home.builders_free'] = 'number'
            for cur in ('gold','elixir'):
                required.update(dict.fromkeys((f"wall.upgrade_{cur}",f"wall.currency_{cur}",f"confirm.currency_{cur}"),"template"))
                required.update(dict.fromkeys((f"home.wallet_{cur}",f"wall.wallet_{cur}",f"wall.cost_{cur}"),"number"))
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

    def __init__(self, executable: str, digit_directory: Path | None = None):
        self.executable = executable
        self.digits = {}
        self.multipliers = []
        self.slashes = []
        if digit_directory is not None and digit_directory.is_dir():
            for digit in '0123456789':
                samples = [cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                           for path in sorted(digit_directory.glob(f'{digit}-*.png'))]
                if not samples or any(sample is None or sample.shape != (32, 32) for sample in samples):
                    raise RecognitionError(f'Numeric font calibration is missing or invalid for {digit}')
                self.digits[digit] = samples
            self.multipliers = [cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) for path in sorted(digit_directory.glob('x-*.png'))]
            if any(sample is None or sample.shape != (32,32) for sample in self.multipliers):
                raise RecognitionError('Count multiplier calibration is invalid')
            self.slashes = [cv2.imread(str(p),cv2.IMREAD_GRAYSCALE) for p in digit_directory.glob('slash-*.png')]
            if any(sample is None or sample.shape != (32,32) for sample in self.slashes):
                raise RecognitionError('Capacity separator calibration is invalid')

    def ratio(self, crop):
        if not self.slashes or not self.digits:
            raise RecognitionError('Capacity font calibration is missing')
        # Incomplete armies display a red warning beside the capacity counter.
        red = cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,100,100),(10,255,255))
        _,_,stats,_ = cv2.connectedComponentsWithStats(red)
        warnings = [x for x,y,w,h,area in stats[1:] if w>=8 and h>=8 and area>=25]
        if warnings:
            left = min(x for x,y,w,h,area in stats[1:] if x>=min(warnings)-10)
            crop = crop[:,:max(0,left-5)]
        text = ''
        try:
            glyphs = self.numeric_glyphs(cv2.inRange(crop,(180,)*3,(255,)*3))
            for glyph in glyphs:
                scores = sorted((min(float(np.abs(glyph.astype(float)-s).mean())/255 for s in samples),char)
                    for char,samples in {**self.digits,'/':self.slashes}.items())
                if scores[0][0] > .12 or scores[1][0]-scores[0][0] < .025:
                    raise RecognitionError('Army capacity is ambiguous')
                text += scores[0][1]
        except RecognitionError:
            text = self.text(crop).replace(' ','')
        if not re.fullmatch(r'[0-9]{1,3}/[0-9]{1,3}',text):
            raise RecognitionError('Invalid army capacity')
        used,capacity = map(int,text.split('/'))
        if not 0<=used<=capacity<=500 or capacity==0:
            raise RecognitionError('Unsupported army capacity')
        return used,capacity

    @staticmethod
    def numeric_glyphs(mask):
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count <= 1:
            raise RecognitionError('No numeric glyphs detected')
        height = max(stats[1:, cv2.CC_STAT_HEIGHT])
        top = min(row[cv2.CC_STAT_TOP] for row in stats[1:] if row[cv2.CC_STAT_HEIGHT] >= height * .6)
        # A slot's one-pixel top border can enter the count crop when selected.
        noise = [row for row in stats[1:] if row[cv2.CC_STAT_HEIGHT] < height * .6 and row[cv2.CC_STAT_AREA] >= 3]
        if any(not (row[cv2.CC_STAT_HEIGHT] == 1 and row[cv2.CC_STAT_TOP] <= top
                    and (row[cv2.CC_STAT_LEFT] == 0 or row[cv2.CC_STAT_LEFT] + row[cv2.CC_STAT_WIDTH] == mask.shape[1])) for row in noise):
            raise RecognitionError('Unexpected punctuation or noise in numeric crop')
        boxes = sorted((tuple(row[:4]) for row in stats[1:]
                        if row[cv2.CC_STAT_HEIGHT] >= height * .6), key=lambda box: box[0])
        glyphs = []
        for x, y, w, h in boxes:
            if x == 0 or x+w == mask.shape[1]:
                raise RecognitionError('Numeric glyph touches the crop edge; recalibrate the crop')
            if h < 6 or w > h * 1.2:
                raise RecognitionError('Numeric glyphs are clipped or joined; recalibrate the crop')
            resized = cv2.resize(mask[y:y+h, x:x+w], (max(1, round(w * 28 / h)), 28), interpolation=cv2.INTER_AREA)
            glyph = np.zeros((32, 32), dtype=np.uint8)
            left = (32 - resized.shape[1]) // 2
            glyph[2:30, left:left+resized.shape[1]] = resized
            glyphs.append(glyph)
        return glyphs

    def check(self):
        if not Path(self.executable).is_file():
            raise RecognitionError("Tesseract not found. Install Tesseract with English data and set its executable path.")
        result = subprocess.run([self.executable, "--list-langs"], capture_output=True, text=True,
                                check=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "eng" not in result.stdout.split():
            raise RecognitionError("Tesseract English training data is missing; install eng.traineddata")

    def text(self, crop, *, numeric=False):
        import pytesseract
        # The game uses bright outlined lettering. Preserve all glyphs (including
        # K/M suffixes) while removing the colored background before OCR.
        white = 255 - cv2.inRange(crop, (180, 180, 180), (255, 255, 255))
        bright = 255 - cv2.inRange(crop, (210, 210, 210), (255, 255, 255))
        green = 255 - cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (30, 180, 170), (75, 255, 255))
        for source, thin in ((white, False), (bright, True), (green, False), (cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), False)):
            gray = cv2.resize(source, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
            if thin:
                gray = cv2.dilate(gray, np.ones((3, 3), dtype=np.uint8))
            gray = cv2.copyMakeBorder(gray, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
            with self._lock:
                pytesseract.pytesseract.tesseract_cmd = self.executable
                data = pytesseract.image_to_data(gray, config="--psm 7", lang="eng", timeout=5,
                                                 output_type=pytesseract.Output.DICT)
            words = [(t.strip(), float(c)) for t, c in zip(data["text"], data["conf"]) if t.strip()]
            if words and all(c >= 70 for _, c in words):
                text = " ".join(t for t, _ in words)
                if numeric:
                    # OCR word boundaries are not reliable thousands separators.
                    text = text.replace(" ", "")
                    try:
                        self.parse_number(text)
                    except RecognitionError:
                        continue
                return text
        raise RecognitionError("OCR is empty or uncertain; inspect and recalibrate its crop")

    @staticmethod
    def parse_number(text):
        # Read letters too: a digits-only OCR pass could silently turn '10K' into '10'.
        if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[ ,][0-9]{3})+)", text):
            raise RecognitionError(f"Expected a full integer, got {text!r}; no abbreviated values are accepted")
        return int(text.replace(" ", "").replace(",", ""))

    def number(self, crop):
        return self._numeric(crop)

    def count(self, crop):
        if not self.digits:
            text = self.text(crop)
            return self.parse_number(re.sub(r'^[xX×]\s*','',text))
        return self._numeric(crop, multiplier=True)

    def _numeric(self, crop, multiplier=False):
        if self.digits:
            values = set()
            masks = [cv2.inRange(crop, (180,)*3, (255,)*3),
                     cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (30,180,170), (75,255,255))]
            for mask in masks:
                try:
                    text = ''
                    for index,glyph in enumerate(self.numeric_glyphs(mask)):
                        templates = self.digits
                        if multiplier and index == 0 and self.multipliers:
                            templates = {**templates,'x':self.multipliers}
                        scores = sorted((min(float(np.abs(glyph.astype(float) - sample).mean()) / 255
                                             for sample in samples), digit) for digit, samples in templates.items())
                        if scores[0][0] > .12 or scores[1][0] - scores[0][0] < .025:
                            raise RecognitionError('Unknown or ambiguous numeric glyph')
                        if scores[0][1] != 'x': text += scores[0][1]
                    values.add(self.parse_number(text))
                except RecognitionError:
                    continue
            if len(values) != 1:
                raise RecognitionError('Numeric font match is uncertain; inspect and recalibrate the crop')
            return values.pop()
        return self.parse_number(self.text(crop, numeric=True))


class Recognizer:
    def __init__(self, root: Path, profile: Profile, ocr: OCR):
        self.root, self.profile, self.ocr = root, profile, ocr
        self.screen = "unknown"
        self.confidence = 0.0
        self._images = {}
        self._inventory_profiles = [("default", profile)]
        for name in profile.inventory_profiles:
            candidate = load_profile(root, name)
            if candidate.inventory_profiles:
                raise RecognitionError("Inventory profiles cannot reference other inventory profiles")
            self._inventory_profiles.append((name, candidate))
        self._ready_profiles = self._inventory_profiles
        self.skipped_heroes = set()
        self._empty_strip_offsets = {}

    def _locate_card(self, asset, frame, strip):
        """Find a validated portrait across the strip at its calibrated height."""
        template = cv2.imread(str(self.root / "templates" / asset.image))
        if template is None:
            raise RecognitionError("Missing calibrated card image")
        r = asset.rect
        band = frame[r.y-4:r.y+r.height+4, strip.x:strip.x+strip.width]
        scores = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        diff = cv2.absdiff(template, band[y:y+r.height, x:x+r.width]).mean()/255
        if score - diff < asset.threshold:
            return None
        scores[:, max(0,x-r.width):x+r.width+1] = -1
        if scores.max() >= asset.threshold:
            raise RecognitionError("Card portrait matches multiple positions")
        return strip.x + x - r.x

    def _compose_cards(self, frame):
        # Use a complete profile for counts, controls and non-hero states.
        for _, seed in self._ready_profiles:
            if not seed.slots or "base.roster" not in seed.assets:
                continue
            result = seed.model_copy(deep=True)
            result.inventory_profiles = []
            result.slots = []
            result.assets = {k:v for k,v in result.assets.items() if k.count('.') != 3
                             or k.split('.')[1] not in ('troop','hero','spell')}
            strip = seed.assets['base.roster'].rect
            found = []
            def locate(source, slot):
                prefix = 'base.' + slot.key
                portrait = source.assets.get(prefix+'.ready')
                area = source.assets.get(prefix+'.area')
                if not portrait or not portrait.validated or not area or not area.validated:
                    return None
                dx = self._locate_card(portrait, frame, strip)
                if dx is not None:
                    return area.rect.x+dx, source, slot, dx
            for slot in seed.slots:
                if slot.kind != 'hero':
                    item = locate(seed, slot)
                    if item is None:
                        break
                    found.append(item)
            else:
                heroes = {}
                for _, source in self._inventory_profiles:
                    for slot in source.slots:
                        if slot.kind != 'hero':
                            continue
                        item = locate(source, slot)
                        if item is None:
                            continue
                        x = item[0]
                        deployed = source.assets.get('battle.'+slot.key+'.deployed')
                        ready = source.assets.get('battle.'+slot.key+'.ready')
                        complete = bool(ready and ready.validated and deployed and deployed.validated)
                        if x not in heroes or (complete and (not heroes[x][1] or deployed.variants)):
                            heroes[x] = (item, complete)
                found.extend(item for item, _ in heroes.values())
                skipped = set()
                hero_index = 0
                previous_end = -1
                for x, source, slot, dx in sorted(found, key=lambda item:item[0]):
                    area = source.assets['base.'+slot.key+'.area'].rect
                    if (x < previous_end - 3 or x < strip.x - 3 or x+area.width > strip.x+strip.width
                            or (previous_end < 0 and x-strip.x > area.width//2)
                            or (previous_end > 0 and x-previous_end > area.width//2)):
                        raise RecognitionError("Ambiguous card boundaries")
                    previous_end = x+area.width
                    target = slot
                    if slot.kind == 'hero':
                        hero_index += 1
                        target = Slot(kind='hero', slot=hero_index)
                        if not heroes[x][1]:
                            skipped.add(target.key)
                    result.slots.append(target)
                    for k,v in source.assets.items():
                        parts = k.split('.')
                        if len(parts)!=4 or parts[0] not in ('base','battle') or '.'.join(parts[1:3])!=slot.key:
                            continue
                        moved = v.model_copy(deep=True)
                        moved.rect.x += dx
                        result.assets[f'{parts[0]}.{target.key}.{parts[3]}'] = moved
                candidate = Recognizer(self.root, result, self.ocr)
                candidate.skipped_heroes = skipped
                for _, geometry in sorted(self._inventory_profiles,key=lambda entry:abs(len(entry[1].slots)-len(result.slots))):
                    if not geometry.slots:
                        continue
                    if not all(geometry.assets.get(k) and geometry.assets[k].validated
                               for k in ('base.roster','battle.roster')):
                        continue
                    for k in ('base.roster','battle.roster'):
                        result.assets[k] = geometry.assets[k]
                        screen = k.split('.')[0]
                        def extent(profile):
                            rects = [profile.assets[f'{screen}.{s.key}.area'].rect for s in profile.slots]
                            return max(r.x+r.width for r in rects)
                        candidate._empty_strip_offsets[k] = (extent(result),extent(geometry))
                    candidate._images.clear()
                    if candidate.matches('base.roster',frame):
                        break
                else:
                    continue
                for slot in result.slots:
                    candidate.slot_state('base',slot,frame)
                self._empty_strip_offsets = candidate._empty_strip_offsets
                return result, skipped
        raise RecognitionError("Expected exactly one validated army layout; found 0")

    def select_inventory(self, frame):
        if len(self._inventory_profiles) == 1 and 'base.roster' not in self.profile.assets:
            return
        matches = []
        for name, profile in self._ready_profiles:
            candidate = Recognizer(self.root, profile.model_copy(update={"inventory_profiles": []}, deep=True), self.ocr)
            try:
                try:
                    candidate.expect("base", frame)
                except RecognitionError:
                    candidate.expect('battle',frame)
                if not candidate.matches("base.roster", frame):
                    continue
                for slot in profile.slots:
                    candidate.slot_state("base", slot, frame)
            except RecognitionError:
                continue
            matches.append((name, candidate.profile))
        if not matches and isinstance(frame, np.ndarray):
            self.profile, self.skipped_heroes = self._compose_cards(frame)
            self._images.clear()
            return
        if len(matches) != 1:
            raise RecognitionError("Expected exactly one validated army layout; found " + str(len(matches)))
        self.profile = matches[0][1]
        self._empty_strip_offsets.clear()
        self.skipped_heroes.clear()
        self._images.clear()

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
            if name in self._empty_strip_offsets:
                # Compare empty outlines after the observed final card with the
                # calibrated empty tail, regardless of how many heroes precede it.
                end, reference_end = self._empty_strip_offsets[name]
                x, rx = end-asset.rect.x, reference_end-asset.rect.x
                # Card-area padding differs across captures. Align the first
                # empty dashed outline within that padding before comparing the tail.
                observed_edge = cv2.inRange(crop[:,x:x+90],(150,)*3,(255,)*3)
                left = max(0,rx-8)
                reference_edge = cv2.inRange(template[:,left:rx+98],(150,)*3,(255,)*3)
                if reference_edge.shape[1] >= observed_edge.shape[1] == 90:
                    scores = cv2.matchTemplate(reference_edge,observed_edge,cv2.TM_CCOEFF_NORMED)
                    rx = left + cv2.minMaxLoc(scores)[3][0]
                width = min(crop.shape[1]-x,template.shape[1]-rx)
                if width < 90:
                    raise RecognitionError('No complete empty slot after the last card')
                tail = template[:,rx:rx+width]
                if width < crop.shape[1]-x:
                    return 0.0
                template, crop = tail, crop[:,x:x+width]
            # Compare the whole strip except explicitly recognized slots. New slots
            # in previously empty areas therefore invalidate the inventory guard.
            mask = np.ones(crop.shape[:2], dtype=np.uint8)
            prefix = name.split(".")[0] + "."
            for key, value in self.profile.assets.items():
                if name not in self._empty_strip_offsets and key.startswith(prefix) and key.count(".") == 3 and key.endswith(".area"):
                    r = value.rect
                    x1, y1 = max(0, r.x - asset.rect.x), max(0, r.y - asset.rect.y)
                    x2, y2 = min(asset.rect.width, r.x + r.width - asset.rect.x), min(asset.rect.height, r.y + r.height - asset.rect.y)
                    if x2 > x1 and y2 > y1:
                        mask[y1:y2, x1:x2] = 0
            if np.count_nonzero(mask) < 32:
                raise RecognitionError("Roster guard needs visible empty space around the calibrated slots")
            # The bar is translucent; compare its bright empty-slot outlines, not the enemy village beneath it.
            reference = (cv2.inRange(template, (150,)*3, (255,)*3) > 0) & mask.astype(bool)
            observed = (cv2.inRange(crop, (150,)*3, (255,)*3) > 0) & mask.astype(bool)
            total = np.count_nonzero(reference) + np.count_nonzero(observed)
            if not total:
                return 0.0
            # Translucent dashed outlines shift their bright edge by a pixel with scenery.
            kernel = np.ones((3,3), np.uint8)
            near_ref = cv2.dilate(reference.astype('uint8'),kernel).astype(bool)
            near_obs = cv2.dilate(observed.astype('uint8'),kernel).astype(bool)
            # A single missing empty card can be hidden by the rest of a long strip.
            for x in range(0, crop.shape[1], 90):
                ref = reference[:,x:x+90]
                if ref.sum() >= 40 and (ref & near_obs[:,x:x+90]).sum() < .7*ref.sum():
                    return 0.0
            return ((reference & near_obs).sum() + (observed & near_ref).sum()) / total
        if name in {'wall','build_wall'}:
            # Text outlines stay fixed while bright village scenery moves behind it.
            template=cv2.cvtColor(cv2.inRange(template,(0,)*3,(25,)*3),cv2.COLOR_GRAY2BGR)
            crop=cv2.cvtColor(cv2.inRange(crop,(0,)*3,(25,)*3),cv2.COLOR_GRAY2BGR)
            if template.std()<4 or crop.std()<4:
                return 0.0
        elif name in SCREENS or name in {"army.ready", "matchmaking.regular"} or (name.startswith('results.') and name.endswith('.anchor')):
            template = cv2.cvtColor(cv2.inRange(template, (170,)*3, (255,)*3), cv2.COLOR_GRAY2BGR)
            crop = cv2.cvtColor(cv2.inRange(crop, (170,)*3, (255,)*3), cv2.COLOR_GRAY2BGR)
            if template.std() < 4 or crop.std() < 4:
                return 0.0
        elif name.count('.') == 3 and name.rsplit('.', 1)[1] in {'ready', 'unavailable', 'deployed', 'depleted'}:
            r = asset.rect
            margin = 18
            crop = frame[max(0,r.y-margin):min(frame.shape[0],r.y+r.height+margin),
                         max(0,r.x-margin):min(frame.shape[1],r.x+r.width+margin)]
            siege_marker = name.endswith('.deployed') and any(s.single and s.key == '.'.join(name.split('.')[1:3]) for s in self.profile.slots)
            crops = [crop]
            if siege_marker:
                # The siege release marker pulses in color; its bright arrow shape is stable.
                template = cv2.cvtColor(cv2.inRange(template,(140,)*3,(255,)*3),cv2.COLOR_GRAY2BGR)
                # The selected-card flash brightens its green surround as well.
                crops = [cv2.cvtColor(cv2.inRange(crop,(level,)*3,(255,)*3),cv2.COLOR_GRAY2BGR) for level in (140,210)]
            best = 0.0
            templates = [template]
            for filename in asset.variants:
                variant = cv2.imread(str(self.root/'templates'/filename))
                if variant is None or variant.shape != template.shape:
                    raise RecognitionError('Missing or differently sized card variant')
                if siege_marker:
                    variant = cv2.cvtColor(cv2.inRange(variant,(140,)*3,(255,)*3),cv2.COLOR_GRAY2BGR)
                templates.append(variant)
            # Selected cards, including heroes, enlarge their portraits.
            for portrait in templates:
                for scale in (1,1.04,1.08,1.12):
                    sample = cv2.resize(portrait,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
                    if sample.shape[0]>crop.shape[0] or sample.shape[1]>crop.shape[1]: continue
                    for observed in crops:
                        _, confidence, _, (x,y) = cv2.minMaxLoc(cv2.matchTemplate(observed,sample,cv2.TM_CCOEFF_NORMED))
                        matched = observed[y:y+sample.shape[0],x:x+sample.shape[1]]
                        color_difference = np.abs(matched.astype(float)-sample.astype(float)).mean() / 255
                        best = max(best,float(confidence)-float(color_difference))
            return best
        from airtest.aircv.template_matching import TemplateMatching
        result = TemplateMatching(template, crop, threshold=0, rgb=True).find_best_result()
        return float(result["confidence"]) if result else 0.0

    def matches(self, name, frame):
        return self.score(name, frame) >= self.asset(name).threshold

    def find_row(self, name, frame):
        asset = self.asset(name)
        r = asset.rect
        template = cv2.imread(str(self.root/'templates'/asset.image))
        if template is None:
            raise RecognitionError(f"Missing calibrated image for {name}")
        if name == 'build.wall':
            # The text after "Wall" is a changing count of eligible segments.
            template = template[:,:max(4,r.width//2)]
        check_dimensions(self.profile,frame)
        top, bottom = frame.shape[0]//15, frame.shape[0]*9//10
        strip = frame[top:bottom,r.x:r.x+template.shape[1]]
        scores = cv2.matchTemplate(strip,template,cv2.TM_CCOEFF_NORMED)
        _, score, _, (_,y) = cv2.minMaxLoc(scores)
        if score < asset.threshold:
            return None
        scores[max(0,y-r.height):y+r.height+1] = -1
        if scores.max() >= asset.threshold:
            raise RecognitionError(f'Ambiguous {name} rows')
        return top+y

    def expect(self, screen, frame):
        self.asset(screen)
        # Overlay screens take precedence over the underlying village/battle.
        for name in ("exit","remove_troops","remove_spells","army_picker","more","settings","profile","confirm", "bonus", "build_wall", "build", "wall", "results", "battle", "base", "army", "matchmaking", "home"):
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
            if name == 'home.builders_free':
                return self.ocr.ratio(asset.rect.crop(frame))[0]
            if name.startswith('wall.cost_'):
                crop = asset.rect.crop(frame)
                mask = cv2.inRange(crop,(210,)*3,(255,)*3)
                return self.ocr.number(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            if name.endswith('.count'):
                try:
                    return self.ocr.count(asset.rect.crop(frame))
                except RecognitionError:
                    area = self.asset(name.rsplit('.',1)[0]+'.area').rect
                    values = set()
                    for dx in (-2,-1,0,1,2):
                        for extra in (0,1,2):
                            rect = asset.rect.model_copy(update={'x':asset.rect.x+dx,'width':asset.rect.width+extra})
                            if rect.x < area.x or rect.x+rect.width > area.x+area.width:
                                continue
                            try:
                                values.add(self.ocr.count(rect.crop(frame)))
                            except RecognitionError:
                                continue
                    if len(values) != 1:
                        raise RecognitionError('Card count position or value is ambiguous')
                    return values.pop()
            if name == 'base.gold':
                # Opponent gold uses pale yellow lettering over moving village scenery.
                crop = asset.rect.crop(frame)
                mask = cv2.inRange(crop,(173,218,225),(211,255,255))
                try:
                    return self.ocr.number(crop)
                except RecognitionError:
                    return self.ocr.number(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            if name == 'base.elixir':
                crop = asset.rect.crop(frame)
                try:
                    return self.ocr.number(crop)
                except RecognitionError:
                    mask = cv2.inRange(crop,(235,215,235),(255,240,255))
                    return self.ocr.number(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            if name == 'base.dark_elixir':
                crop = asset.rect.crop(frame)
                mask = cv2.inRange(crop,(231,)*3,(255,)*3)
                mask[np.ptp(crop,axis=2)>1] = 0
                try:
                    return self.ocr.number(crop)
                except RecognitionError:
                    return self.ocr.number(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            if name == 'wall.level':
                # Two-digit captions shift slightly with the width of the new level.
                rect=asset.rect.model_copy(update={'x':max(0,asset.rect.x-4),'width':asset.rect.width+5})
                crop = rect.crop(frame)
                try:
                    return self.ocr.number(crop)
                except RecognitionError:
                    mask = cv2.inRange(crop,(170,240,240),(195,255,255))
                    return self.ocr.number(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            return self.ocr.number(asset.rect.crop(frame))
        if asset.kind == "text":
            return self.ocr.text(asset.rect.crop(frame))
        raise RecognitionError(f"{name} is not an OCR region")

    def result_loot(self, frame):
        self.expect('results', frame)
        if not self.profile.result_layouts:
            return {key: self.read(f'results.{key}', frame) for key in RESOURCE_KEYS}
        found = [name for name in self.profile.result_layouts if self.matches(f'results.{name}.anchor', frame)]
        if len(found) != 1:
            raise RecognitionError('Expected exactly one calibrated result layout')
        name = found[0]
        # Only a positively identified layout may supply an absent resource as zero.
        return {key: self.read(f'results.{name}.{key}', frame) if key in self.profile.result_layouts[name] else 0
                for key in RESOURCE_KEYS}

    def clear_ground(self, frame):
        check_dimensions(self.profile,frame)
        h,w = frame.shape[:2]
        grass = cv2.inRange(cv2.cvtColor(frame,cv2.COLOR_BGR2HSV),(20,50,70),(85,255,230))
        grass[:round(h*.18)] = 0
        grass[round(h*.60):] = 0
        grass[:,:round(w*.15)] = 0
        grass[:,round(w*.75):] = 0
        distance = cv2.distanceTransform(grass,cv2.DIST_L2,5)
        _,radius,_,point = cv2.minMaxLoc(distance)
        if radius < 20:
            raise RecognitionError('No clear grass to deselect the wall; tap empty ground and return Home')
        return point

    def supports_deployment_scenery(self,frame):
        check_dimensions(self.profile,frame)
        h,w=frame.shape[:2]
        field=frame[round(h*.15):round(h*.65),round(w*.15):round(w*.85)]
        grass=cv2.inRange(cv2.cvtColor(field,cv2.COLOR_BGR2HSV),(20,50,70),(85,255,230))
        return np.count_nonzero(grass)/grass.size >= .2

    def deployment_corner(self, frame):
        check_dimensions(self.profile, frame)
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        boundary = cv2.inRange(hsv, (8,160,170), (14,240,230))
        boundary[:round(h*.11)] = 0
        boundary[round(h*.70):] = 0
        boundary[:,:round(w*.13)] = 0
        boundary[:,round(w*.84):] = 0
        lines = cv2.HoughLinesP(boundary, 1, np.pi/180, 25, minLineLength=round(w*.045), maxLineGap=12)
        segments = [] if lines is None else [line[0] for line in lines
                     if .3 <= abs((line[0][3]-line[0][1]) / (line[0][2]-line[0][0] or .001)) <= .8]
        if len(segments) >= 3:
            x, y = min((int(x), int(y)) for a,b,c,d in segments for x,y in ((a,b),(c,d)))
        else:
            # At minimum zoom the anti-aliased boundary is paler; retain only long, thin components.
            pale = cv2.inRange(hsv, (7,140,140), (25,245,235))
            pale[:round(h*.11)] = 0
            pale[round(h*.70):] = 0
            pale[:,:round(w*.13)] = 0
            pale[:,round(w*.84):] = 0
            count, labels, stats, _ = cv2.connectedComponentsWithStats(pale)
            keep = np.zeros_like(pale)
            for i in range(1,count):
                _,_,cw,ch,area = stats[i]
                if max(cw,ch) >= w*.06 and area / (cw*cw+ch*ch)**.5 < 3:
                    keep[labels==i] = 255
            ys,xs = np.nonzero(keep)
            if len(xs) < 300:
                raise PlacementUnavailable('Placement boundary is not clear; no deployment point selected')
            x = int(xs.min())
            y = int(np.median(ys[xs <= x+2]))
        x -= round(w*.035)
        # A dim outer boundary can be missed while brighter inner walls match.
        # Reject points inside that outer edge and let checked panning find it.
        dim = cv2.inRange(hsv,(7,100,60),(15,255,240))
        dim[:round(h*.11)] = 0
        dim[round(h*.70):] = 0
        outer = cv2.HoughLinesP(dim,1,np.pi/180,25,minLineLength=round(w*.075),maxLineGap=12)
        if outer is not None:
            for (x1,y1,x2,y2), in outer:
                if .3 <= abs((y2-y1)/(x2-x1 or .001)) <= .8 and min(x1,x2) < x:
                    if min(y1,y2)-40 <= y <= max(y1,y2)+40:
                        raise PlacementUnavailable('Placement boundary is outside the candidate; checked camera pan required')
        if x < round(w*.10) or not round(h*.20) <= y <= round(h*.66):
            raise PlacementUnavailable('Placement boundary is too close to the visible edge')
        patch = hsv[y-8:y+9,x-8:x+9]
        grass = cv2.inRange(patch,(20,50,70),(85,255,230))
        if np.count_nonzero(grass) / grass.size < .9:
            raise PlacementUnavailable('No clear ground outside the placement boundary')
        return x, y

    def slot_state(self, screen, slot, frame):
        prefix = f"{screen}.{slot.key}."
        if slot.key in self.skipped_heroes:
            if not self.matches(prefix+'ready', frame):
                raise RecognitionError(f"Skipped hero card {slot.key} changed identity")
            return "skipped", 0
        states = ["ready", "unavailable"] + (["deployed" if slot.kind == "hero" or slot.single else "depleted"] if screen == "battle" else [])
        found = [state for state in states if prefix + state in self.profile.assets
                 and self.profile.assets[prefix + state].validated and self.matches(prefix + state, frame)]
        if len(found) != 1:
            raise RecognitionError(f"Ambiguous or unrecognized {slot.key} on {screen}")
        state = found[0]
        count = (1 if slot.kind == "hero" or slot.single else self.read(prefix + "count", frame)) if state == "ready" else 0
        if state == "ready" and not 1 <= count <= 500:
            raise RecognitionError(f"Invalid available count for {slot.key}")
        return state, count

    def ready(self, settings):
        if len(self._inventory_profiles) == 1:
            return self._ready_current(settings)
        ready, failures = [], []
        for name, profile in self._inventory_profiles:
            candidate = Recognizer(self.root, profile.model_copy(update={"inventory_profiles": []}, deep=True), self.ocr)
            try:
                candidate._ready_current(settings)
            except RecognitionError as exc:
                failures.append(f"{name}: {exc}")
            else:
                ready.append((name, profile))
        self._ready_profiles = ready
        if not ready:
            raise RecognitionError("No complete inventory profile:\n" + "\n".join(failures))
        self.profile = ready[0][1].model_copy(update={"inventory_profiles": []}, deep=True)
        self._images.clear()

    def _ready_current(self, settings):
        Profile.model_validate(self.profile.model_dump())
        problems = []
        if settings.farming.prepare_army and self.profile.prepared_army != settings.farming.composition:
            problems.append('Recommended army needs a validated preparation layout in Advanced')
        missing = [name for name, kind in requirements(settings, self.profile).items()
                   if name not in self.profile.assets or not self.profile.assets[name].validated or self.profile.assets[name].kind != kind]
        if missing:
            problems.append("Calibration incomplete: " + ", ".join(missing))
        if (self.profile.width, self.profile.height) != (settings.calibration.width, settings.calibration.height):
            problems.append("Preset resolution differs from calibration profile")
        if settings.farming.collect and not settings.calibration.collectors:
            problems.append("Mark at least one collector for live collection")
        if settings.farming.attack:
            covered = {f"{s.kind}.{s.slot}" for s in settings.farming.deployment}
            calibrated = {s.key for s in self.profile.slots}
            if not calibrated or (not settings.farming.dump_all and covered != calibrated):
                problems.append("Deployment steps must cover exactly the calibrated troop, hero, and spell slots")
        try:
            self.ocr.check()
        except Exception as exc:
            problems.append(str(exc))
        if problems:
            raise RecognitionError("\n".join(problems))

    def validate_asset(self, name, frame):
        asset = self.asset(name, validated=False)
        if name.count('.') == 3 and name.endswith('.area') and asset.kind == 'template':
            check_dimensions(self.profile, frame)
            prefix = name[:-4]
            states = [value for key, value in self.profile.assets.items()
                      if key.startswith(prefix) and key.rsplit('.', 1)[1] in {'ready', 'unavailable', 'deployed', 'depleted'}]
            r = asset.rect
            if not states or any(s.rect.x < r.x or s.rect.y < r.y or s.rect.x+s.rect.width > r.x+r.width
                                 or s.rect.y+s.rect.height > r.y+r.height for s in states):
                raise RecognitionError('Slot area must contain its state regions')
            if not any(self.score(key, frame) >= value.threshold for key, value in self.profile.assets.items()
                       if key.startswith(prefix) and key.rsplit('.', 1)[1] in {'ready', 'unavailable', 'deployed', 'depleted'}):
                raise RecognitionError('No recognized slot state inside area on second capture')
            result = 'Slot bounds verified against recognized state'
        elif asset.kind == "template":
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
            reader = (self.ocr.count if name.endswith('.count') else self.ocr.number) if asset.kind == "number" else self.ocr.text
            before, after = reader(reference), reader(asset.rect.crop(frame))
            if before != after:
                raise RecognitionError(f"Readings disagree: {before!r} vs {after!r}")
            result = f"Consistent reading: {after}"
        asset.validated = True
        return result
