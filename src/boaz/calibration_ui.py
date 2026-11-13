"""Guided screenshot-only calibration; selecting the image never touches Android."""

import base64
from datetime import datetime, timezone
import json

import cv2
from nicegui import run, ui

from .recognition import (OCR, Profile, Rect, Recognizer, Slot, load_profile,
                          record_asset, requirements, save_profile)


def image_source(frame):
    ok, png = cv2.imencode(".png", frame)
    if not ok:
        raise ValueError("Could not encode screenshot")
    return "data:image/png;base64," + base64.b64encode(png.tobytes()).decode("ascii")


def calibration_panel(root, device, device_lock, get_settings, draft, changed, busy):
    frozen = None
    frozen_at = None
    profile = None
    corners = []

    def check_idle():
        if busy():
            raise ValueError("Stop the active session before changing calibration")

    def report(exc):
        message.set_text(str(exc))
        message.classes(add="error")

    def refresh_options():
        if profile is not None:
            opts = requirements(get_settings(), profile)
            asset_name.set_options(list(opts), value=asset_name.value if asset_name.value in opts else next(iter(opts)))
            summary.set_text("\n".join(f"{'Validated' if a.validated else 'Needs second capture'}: {n}" for n, a in profile.assets.items()) or "No regions captured yet")
            slot_summary.set_text(
                "Deployment slots: " + ", ".join(s.key for s in profile.slots)
                + ". Include every visible troop, hero, and spell slot before validating roster guards."
            )
            slots_json.set_value(json.dumps([s.model_dump() for s in profile.slots], indent=2))

    async def freeze():
        nonlocal frozen, frozen_at, profile
        try:
            check_idle()
            async with device_lock:
                frozen = await run.io_bound(device.capture)
            frozen_at = datetime.now(timezone.utc).isoformat()
            if profile is None:
                cfg = get_settings()
                profile = Profile(width=frozen.shape[1], height=frozen.shape[0],
                                  slots=[Slot(kind=k, slot=s) for k, s in sorted({(a.kind, a.slot) for a in cfg.farming.deployment})])
            if (profile.width, profile.height) != (frozen.shape[1], frozen.shape[0]):
                raise ValueError("Resolution changed. Create a new profile before capturing regions.")
            image.set_source(image_source(frozen))
            corners.clear()
            image.set_content("")
            draft["calibration"].update(width=profile.width, height=profile.height)
            changed()
            refresh_options()
            message.classes(remove="error")
            message.set_text(f"Frozen {profile.width} × {profile.height}. Mark two corners for a region, or choose collector/wall to mark a point.")
        except Exception as exc:
            report(exc)

    def mark(e):
        try:
            check_idle()
            if frozen is None or e.type != "click":
                return
            x, y = int(e.image_x), int(e.image_y)
            if not (0 <= x < profile.width and 0 <= y < profile.height):
                return
            if selection.value != "Recognition region":
                field = "collectors" if selection.value == "Collector point" else "walls"
                draft["calibration"][field].append(dict(x=x, y=y))
                changed()
                message.set_text(f"Marked {field}: ({x}, {y}). Save the preset to retain these points.")
                image.set_content(image.content + f'<circle cx="{x}" cy="{y}" r="8" fill="none" stroke="#ffbd4a" stroke-width="3"/>')
                return
            if len(corners) == 2:
                corners.clear()
            corners.append((x, y))
            if len(corners) == 2:
                (x1, y1), (x2, y2) = corners
                region_x.set_value(min(x1, x2))
                region_y.set_value(min(y1, y2))
                region_w.set_value(abs(x2 - x1))
                region_h.set_value(abs(y2 - y1))
                image.set_content(f'<rect x="{min(x1,x2)}" y="{min(y1,y2)}" width="{abs(x2-x1)}" height="{abs(y2-y1)}" fill="none" stroke="#ffbd4a" stroke-width="3"/>')
        except Exception as exc:
            report(exc)

    def rect():
        values = (region_x.value, region_y.value, region_w.value, region_h.value)
        if any(v is None or not float(v).is_integer() for v in values):
            raise ValueError("Region bounds must be whole pixel values")
        return Rect(x=int(values[0]), y=int(values[1]), width=int(values[2]), height=int(values[3]))

    def record():
        try:
            check_idle()
            if frozen is None or profile is None:
                raise ValueError("Freeze a screenshot first")
            key = asset_name.value
            kind = requirements(get_settings(), profile)[key]
            record_asset(root, profile, key, frozen, rect(), kind, float(threshold.value))
            crop.set_source(image_source(rect().crop(frozen)))
            refresh_options()
            asset_name.set_value(key)
            message.classes(remove="error")
            message.set_text(f"Recorded {key}. Navigate manually if needed, freeze a NEW screenshot, then test this region.")
        except Exception as exc:
            report(exc)

    async def test():
        try:
            check_idle()
            if frozen is None or profile is None:
                raise ValueError("Freeze a new screenshot first")
            key = asset_name.value
            asset = profile.assets.get(key)
            if asset is None:
                raise ValueError("Record this region first")
            if frozen_at <= asset.captured_at:
                raise ValueError("Freeze a second screenshot after recording the region; do not test the original capture")
            recognizer = Recognizer(root, profile, OCR(ocr_path.value.strip()))
            result = await run.io_bound(recognizer.validate_asset, key, frozen)
            crop.set_source(image_source(asset.rect.crop(frozen)))
            refresh_options()
            asset_name.set_value(key)
            message.classes(remove="error")
            message.set_text(f"{key}: {result}. Save profile to retain validation.")
        except Exception as exc:
            report(exc)

    def save():
        try:
            check_idle()
            if profile is None:
                raise ValueError("Freeze a screenshot or load a profile first")
            name = profile_name.value.strip()
            save_profile(root, name, profile)
            draft["live"].update(profile=name, tesseract_path=ocr_path.value.strip())
            changed()
            message.classes(remove="error")
            message.set_text(f"Saved profile {name}. Save your preset too to retain its profile reference and marked points.")
        except Exception as exc:
            report(exc)

    def load():
        nonlocal profile, frozen, frozen_at
        try:
            check_idle()
            profile = load_profile(root, profile_name.value.strip())
            frozen = frozen_at = None
            image.set_source("")
            draft["calibration"].update(width=profile.width, height=profile.height)
            draft["live"]["profile"] = profile_name.value.strip()
            changed()
            refresh_options()
            message.set_text("Profile loaded. Freeze the current game screen before editing or testing.")
        except Exception as exc:
            report(exc)

    def new():
        nonlocal profile, frozen, frozen_at
        try:
            check_idle()
            profile = frozen = frozen_at = None
            image.set_source("")
            summary.set_text("Freeze a screenshot to begin a new profile")
        except Exception as exc:
            report(exc)

    def update_slots():
        try:
            check_idle()
            if profile is None:
                raise ValueError("Freeze a screenshot first")
            candidate = profile.model_copy(deep=True)
            candidate.slots = [Slot.model_validate(v) for v in json.loads(slots_json.value)]
            Profile.model_validate(candidate.model_dump())
            profile.slots = candidate.slots
            for name, asset in profile.assets.items():
                if name.endswith(".roster"):
                    asset.validated = False
            refresh_options()
            message.set_text("Slots updated. Revalidate roster guards and check deployment coverage.")
        except Exception as exc:
            report(exc)

    def keyboard_point():
        try:
            if selection.value == "Recognition region":
                raise ValueError("Choose Collector point or Wall point first")
            mark(type("PointEvent", (), dict(type="click", image_x=region_x.value, image_y=region_y.value))())
        except Exception as exc:
            report(exc)

    with ui.column().classes("panel w-full gap-4"):
        ui.label("Teach Boaz your game screens").classes("heading").props('role="heading" aria-level="2"')
        ui.label("Work through home → army → matchmaking → base → battle → results → wall → confirm. Visit screens manually in BlueStacks. This image only records calibration; it never sends input.").classes("muted")
        with ui.row().classes("w-full items-center gap-3"):
            profile_name = ui.input("Profile name", value=draft["live"]["profile"] or "my-village").props("outlined")
            ui.button("New profile", on_click=new).props("outline")
            ui.button("Load profile", on_click=load).props("outline")
            ui.button("Save profile", on_click=save)
        ocr_path = ui.input("Tesseract executable", value=draft["live"]["tesseract_path"], on_change=lambda e: draft["live"].update(tesseract_path=e.value)).props("outlined").classes("w-full")
        async def check_ocr():
            try:
                await run.io_bound(OCR(ocr_path.value.strip()).check)
                message.set_text("Tesseract is available. Test numeric and text crops below.")
            except Exception as exc:
                report(exc)
        ui.button("Check OCR installation", on_click=check_ocr).props("outline")
        with ui.expansion("Region guide and slot inventory", icon="help_outline").classes("w-full"):
            ui.label("Screen names (home, army, etc.) need distinctive screen-only anchors. home.camera must include fixed village scenery. Button regions must contain only their clickable target; their centers are tapped. OCR count crops must exclude the × icon; resource crops must contain the full integer. wall.name must read Wall (optionally with its level), wall.level only the level number. Currency anchors must identify gold/elixir, never gems.").classes("muted")
            ui.label("For each slot, .area covers the entire slot including its border, counts, and health bar. State templates use identical, smaller portrait regions, excluding the selection border. Roster guards cover the ENTIRE visible inventory strip including empty space; they mask the calibrated .area rectangles and detect changes outside them. Keep all slots visible; scrolling army bars are unsupported.").classes("muted")
            slot_summary = ui.label("Slots are initialized from the deployment preset").classes("muted")
            slots_json = ui.textarea("Complete slot inventory (JSON)", value='[{"kind":"troop","slot":1}]').props("outlined").classes("w-full")
            ui.button("Apply slot inventory", on_click=update_slots).props("outline")
        with ui.row().classes("items-center gap-3"):
            ui.button("Freeze screenshot", icon="camera_alt", on_click=freeze)
            selection = ui.select(["Recognition region", "Collector point", "Wall point"], value="Recognition region", label="Mark on image").props("outlined")
        image = ui.interactive_image("", on_mouse=mark, events=["click"]).props('aria-label="Frozen calibration screenshot"').classes("w-full bg-stone-100 rounded")
        ui.label("Select two corners for a region. You can also enter exact pixel bounds below using the keyboard.").classes("muted text-sm")
        with ui.row().classes("w-full gap-3"):
            region_x = ui.number("Region X", value=0, min=0).props("outlined").classes("w-28")
            region_y = ui.number("Region Y", value=0, min=0).props("outlined").classes("w-28")
            region_w = ui.number("Region width", value=40, min=4).props("outlined").classes("w-32")
            region_h = ui.number("Region height", value=40, min=4).props("outlined").classes("w-32")
            threshold = ui.number("Match threshold", value=0.9, min=0.8, max=1, step=0.01).props("outlined").classes("w-40")
        asset_name = ui.select([], label="Required region", with_input=True).props("outlined").classes("w-full")
        with ui.row().classes("gap-3"):
            ui.button("Mark point at X/Y", on_click=keyboard_point).props("outline")
            ui.button("Record selected region", on_click=record)
            ui.button("Test on second capture", on_click=test).props("outline")
        crop = ui.image().props('fit=contain alt="Selected recognition or OCR crop"').classes("max-w-sm")
        message = ui.label("Connect your emulator, then freeze a screenshot to begin.").props('role="status" aria-live="polite"').classes("w-full")
        summary = ui.label("No profile loaded").classes("log w-full")
