"""One local dashboard, one simulator, one read-only emulator connection."""

import asyncio
import base64
import json
from pathlib import Path

from nicegui import app, run, ui

from .config import Settings, load_settings, preset_path, save_settings
from .device import Device
from .runner import Runner


CSS = """
:root { --ink:#253b31; --muted:#586359; --line:#d7ddd5; --paper:#f5f5ef; }
body { background:var(--paper); color:var(--ink); font-family:Roboto, sans-serif; }
.nicegui-content { padding:0; gap:0; }
.shell { max-width:1360px; margin:auto; padding:32px 40px 48px; width:100%; }
.masthead { background:#253b31; color:#fff; padding:22px 40px; }
.brand { font-size:30px; font-weight:700; letter-spacing:-.025em; }
.subtitle { color:#d4dfd1; }
.panel { background:white; border:1px solid var(--line); border-radius:12px; padding:24px; min-width:0; }
.workspace { display:grid; grid-template-columns:minmax(0,1.5fr) minmax(300px,1fr); align-items:start; gap:24px; width:100%; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; width:100%; }
.heading { font-size:22px; line-height:1.3; font-weight:600; margin:0; }
.muted { color:var(--muted); }
.preview { background:#edf0e9; border:1px dashed #a2ad9e; border-radius:8px; min-height:240px; width:100%; }
.preview .q-img { width:100%; }
.metric-row { display:flex; justify-content:space-between; gap:20px; padding:12px 0; border-bottom:1px solid var(--line); width:100%; }
.metric-row:last-child { border-bottom:0; }
.value { font-variant-numeric:tabular-nums; font-weight:600; }
.notice { background:#e9eedf; border-radius:8px; padding:14px 18px; }
.q-tab { text-transform:none; min-height:48px; }
.q-tab-panel { padding:24px 0 0; }
.q-tabs { border-bottom:1px solid var(--line); }
.q-tab-panels { background:transparent; }
.q-btn { text-transform:none; letter-spacing:0; min-height:40px; }
.q-field { min-width:0; }
.q-field__label { color:#526052; }
.q-field--outlined .q-field__control:before { border-color:#a6afa5; }
.q-btn:focus-visible, a:focus-visible, .q-tab:focus-visible { outline:3px solid #ad6a23; outline-offset:3px; }
input, textarea { caret-color:#376747; }
::selection { background:#d5e7bd; color:#253b31; }
* { scrollbar-color:#9aa793 #f5f5ef; scrollbar-width:thin; }
.log { white-space:pre-wrap; overflow-wrap:anywhere; max-height:260px; overflow:auto; font-size:13px; line-height:1.8; }
.error { color:#9a302a; overflow-wrap:anywhere; }
@media(max-width:850px) { .workspace {grid-template-columns:1fr;} .workspace > :nth-child(2) {order:-1;} .shell {padding:24px 20px;} .masthead {padding:20px;} }
@media(max-width:520px) { .form-grid {grid-template-columns:1fr;} .panel {padding:18px;} }
"""


def serve(local: Path):
    presets = local / "presets"
    presets.mkdir(parents=True, exist_ok=True)
    runner, device = Runner(), Device()
    device_lock = asyncio.Lock()
    preview_source = ""
    capture_busy = False

    async def update_preview():
        nonlocal preview_source, capture_busy
        if capture_busy or device_lock.locked() or not device.connected:
            return
        capture_busy = True
        try:
            async with device_lock:
                frame = await run.io_bound(device.capture)
                from airtest.aircv.utils import img_2_string

                png = await run.io_bound(img_2_string, frame)
                preview_source = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        except Exception as exc:
            preview_source = ""
            runner.event(str(exc))
        finally:
            capture_busy = False

    app.timer(1.0, update_preview)
    app.on_shutdown(runner.stop)

    @ui.page("/")
    def page():
        ui.colors(primary="#376747", secondary="#596d51", accent="#ad6a23", negative="#9a302a")
        ui.add_css(CSS)
        draft = Settings().model_dump()

        with ui.row().classes("masthead w-full items-center justify-between"):
            with ui.row().classes("items-center gap-4"):
                ui.icon("grass", size="32px")
                with ui.column().classes("gap-0"):
                    ui.label("Boaz").classes("brand")
                    ui.label("A little less grind. A little more harvest.").classes("subtitle")
            ui.badge("Foundation · simulation only", color="white", text_color="primary").classes("px-3 py-2")

        with ui.column().classes("shell gap-6"):
            with ui.row().classes("w-full items-start justify-between gap-4"):
                with ui.column().classes("gap-2"):
                    ui.label("Your farming workspace").classes("text-3xl font-semibold").props('role="heading" aria-level="1"')
                    ui.label("Tune a preset, rehearse a session, or inspect your emulator.").classes("muted")
                ui.button("Live farming unavailable", icon="lock").props("outline disable")
            with ui.tabs().props("align=left inline-label").classes("w-full") as tabs:
                overview = ui.tab("Session", icon="dashboard")
                settings_tab = ui.tab("Presets", icon="tune")
                connection_tab = ui.tab("Emulator", icon="smartphone")
            with ui.tab_panels(tabs, value=overview).classes("w-full"):
                with ui.tab_panel(overview):
                    with ui.column().classes("w-full gap-6"):
                        with ui.row().classes("notice w-full items-center gap-3"):
                            ui.icon("science", size="24px")
                            ui.label("Practice mode. Every base, troop, resource, and upgrade below is simulated. No gameplay input is sent.")
                        with ui.element("div").classes("workspace"):
                            with ui.column().classes("panel gap-4"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label("Emulator preview").classes("heading").props('role="heading" aria-level="2"')
                                    connection_label = ui.label("Disconnected").classes("muted")
                                with ui.column().classes("preview items-center justify-center gap-3"):
                                    preview = ui.image().props('fit=contain alt="Read-only emulator screenshot"').classes("w-full")
                                    preview.set_visibility(False)
                                    with ui.column().classes("items-center p-8 gap-3 text-center") as empty:
                                        ui.icon("phonelink_off", size="40px", color="secondary")
                                        ui.label("An emulator is optional").classes("text-lg font-medium")
                                        ui.label("Run a simulation now, or connect BlueStacks to see its screen here.").classes("muted")
                                        ui.button("Set up emulator", on_click=lambda: tabs.set_value(connection_tab)).props("outline")
                                dimensions = ui.label("Read-only preview · no input controls").classes("muted text-sm")
                                preview_error = ui.label().classes("error text-sm").props('role="alert"')
                            with ui.column().classes("panel gap-4"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label("Simulated session").classes("heading").props('role="heading" aria-level="2"')
                                    status_label = ui.badge("Idle", color="secondary")
                                phase_label = ui.label("Home").classes("text-2xl font-medium")
                                reason_label = ui.label(runner.reason).classes("muted").props('role="status" aria-live="polite"')
                                with ui.row().classes("gap-2"):
                                    start_button = ui.button("Start simulation", icon="play_arrow")
                                    pause_button = ui.button("Pause", icon="pause").props("outline")
                                    stop_button = ui.button("Stop", icon="stop", color="negative").props("outline")
                                counter_labels = {}
                                with ui.column().classes("w-full gap-0"):
                                    for key, title in [("elapsed", "Active time"), ("attacks", "Attacks"), ("searches", "Bases searched"), ("collections", "Collections"), ("upgrades", "Wall upgrades"), ("gold", "Gold looted"), ("elixir", "Elixir looted"), ("dark_elixir", "Dark elixir looted")]:
                                        with ui.element("div").classes("metric-row"):
                                            ui.label(title).classes("muted")
                                            counter_labels[key] = ui.label("0").classes("value")
                                ui.label("Loot excludes collections. Preview shows the real screen; counters show simulation results.").classes("muted text-sm")
                        with ui.column().classes("panel w-full gap-3"):
                            ui.label("Session journal").classes("heading").props('role="heading" aria-level="2"')
                            journal = ui.label("No activity yet. Start a simulation to see its decisions.").classes("log w-full")

                with ui.tab_panel(settings_tab):
                    with ui.column().classes("panel w-full gap-5"):
                        ui.label("Make the routine yours").classes("heading").props('role="heading" aria-level="2"')
                        ui.label("These settings affect simulation only. Edits apply on the next start; save a named preset to keep them.").classes("muted")
                        with ui.row().classes("w-full items-center gap-3"):
                            preset_select = ui.select(["Default"] + sorted(p.stem for p in presets.glob("*.json")), value="Default", label="Saved preset").props("outlined").classes("w-56")
                            load_button = ui.button("Load preset").props("outline")
                            preset_name = ui.input("Save as", value="my-farm").props("outlined").classes("w-56")
                            save_button = ui.button("Save preset", icon="save")
                        form_message = ui.label().props('role="status" aria-live="polite"').classes("text-sm")

                        @ui.refreshable
                        def form():
                            def number(group, key, label, integer=True, minimum=0):
                                def change(e):
                                    value = e.value
                                    draft[group][key] = int(value) if integer and value is not None and float(value).is_integer() else value
                                ui.number(label, value=draft[group][key], min=minimum, on_change=change).props("outlined").classes("w-full")

                            with ui.row().classes("gap-6"):
                                ui.switch("Collect resources").bind_value(draft["farming"], "collect")
                                ui.switch("Search and attack").bind_value(draft["farming"], "attack")
                                ui.switch("Upgrade marked walls").bind_value(draft["walls"], "enabled")
                            ui.label("Base selection").classes("text-lg font-semibold mt-5")
                            ui.label("All nonzero minimums must pass. Zero disables that resource filter.").classes("muted text-sm")
                            with ui.element("div").classes("form-grid"):
                                for key, label in [("min_gold", "Minimum gold"), ("min_elixir", "Minimum elixir"), ("min_dark_elixir", "Minimum dark elixir"), ("search_limit", "Search limit per attack")]:
                                    number("farming", key, label)
                                number("session", "attack_limit", "Attack limit per session", minimum=1)
                                number("session", "duration_minutes", "Active duration (minutes)", integer=False, minimum=0.01)
                            ui.label("Troop deployment").classes("text-lg font-semibold mt-5")
                            ui.label("Steps run in order. Slots are numbered from 1; coordinates are screenshot pixels.").classes("muted text-sm")

                            @ui.refreshable
                            def deployment():
                                for index, step in enumerate(draft["farming"]["deployment"]):
                                    with ui.row().classes("items-center w-full gap-2"):
                                        ui.label(str(index + 1)).classes("font-semibold")
                                        for key, label in [("slot", "Slot"), ("x", "X"), ("y", "Y"), ("count", "Troops"), ("delay", "Delay / troop (s)")]:
                                            def update(e, target=step, field=key):
                                                value = e.value
                                                target[field] = int(value) if field != "delay" and value is not None and float(value).is_integer() else value
                                            ui.number(label, value=step[key], min=0, on_change=update).props("outlined dense").classes("w-28 grow")
                                        def remove(target=step):
                                            draft["farming"]["deployment"].remove(target)
                                            deployment.refresh()
                                        ui.button(icon="delete_outline", on_click=remove).props(f'flat aria-label="Remove deployment step {index + 1}"')
                            deployment()
                            def add_step():
                                draft["farming"]["deployment"].append(dict(slot=1, x=0, y=0, count=10, delay=0.1))
                                deployment.refresh()
                            ui.button("Add deployment step", icon="add", on_click=add_step).props("outline")
                            ui.label("Wall budget").classes("text-lg font-semibold mt-5")
                            ui.label("Simulation uses a fixed 100,000 cost per wall and a starting balance of 1,000,000 gold and elixir.").classes("muted text-sm")
                            with ui.element("div").classes("form-grid"):
                                ui.select(["gold", "elixir"], label="Upgrade currency").bind_value(draft["walls"], "currency").props("outlined")
                                number("walls", "upgrade_limit", "Maximum upgrades per session", minimum=1)
                                number("walls", "reserve_gold", "Keep at least this much gold")
                                number("walls", "reserve_elixir", "Keep at least this much elixir")
                            with ui.expansion("Calibration & marked locations", icon="crop_free").classes("w-full mt-4"):
                                ui.label("Stored for future live farming. Changing resolution or moving village objects requires recalibration. Preview does not calibrate automatically.").classes("muted text-sm mb-4")
                                with ui.element("div").classes("form-grid"):
                                    number("calibration", "width", "Screenshot width (px)", minimum=320)
                                    number("calibration", "height", "Screenshot height (px)", minimum=240)
                                for key, label in [("collectors", "Collector points (JSON)"), ("walls", "Marked wall points (JSON)")]:
                                    def points_changed(e, field=key):
                                        try:
                                            draft["calibration"][field] = json.loads(e.value)
                                        except json.JSONDecodeError:
                                            draft["calibration"][field] = e.value
                                    ui.textarea(label, value=json.dumps(draft["calibration"][key]), placeholder='[{"x": 640, "y": 360}]', on_change=points_changed).props("outlined").classes("w-full mt-4")
                        form()

                with ui.tab_panel(connection_tab):
                    with ui.column().classes("panel w-full gap-5"):
                        ui.label("Connect BlueStacks 5").classes("heading").props('role="heading" aria-level="2"')
                        ui.label("Enable Android Debug Bridge in BlueStacks Settings → Advanced. Enter its executable path and the address of the intended instance.").classes("muted")
                        adb_input = ui.input("ADB executable (full path)", value=draft["device"]["adb_path"], placeholder=r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe").props("outlined").classes("w-full")
                        address_input = ui.input("Local device address", value=draft["device"]["address"]).props("outlined").classes("w-full")
                        with ui.row().classes("gap-3"):
                            connect_button = ui.button("Connect & check screenshot", icon="link")
                            disconnect_button = ui.button("Disconnect").props("outline")
                        connection_message = ui.label("Not connected. Simulation works without an emulator.").classes("muted").props('role="status" aria-live="polite"')
                        ui.link("BlueStacks ADB setup guide", "https://support.bluestacks.com/hc/en-us/articles/23925869130381-How-to-enable-Android-Debug-Bridge-on-BlueStacks-5", new_tab=True)
                        ui.label("Connection fields are included when you save a preset. Only connection checks and screenshot capture are available.").classes("muted text-sm")

            ui.label("Boaz 0.1 · One village. One session. Your settings.").classes("muted text-sm mt-4")

        def get_settings():
            draft["device"] = dict(adb_path=adb_input.value.strip(), address=address_input.value.strip())
            return Settings.model_validate(draft)

        def report_error(exc):
            message = str(exc)
            form_message.set_text(message)
            form_message.classes(add="error")
            ui.notify("Check your settings in Presets: " + message, type="negative", timeout=8000)

        def start():
            try:
                runner.start(get_settings())
            except (ValueError, OSError) as exc:
                report_error(exc)

        def load():
            try:
                cfg = Settings() if preset_select.value == "Default" else load_settings(preset_path(presets, preset_select.value))
                draft.clear()
                draft.update(cfg.model_dump())
                adb_input.set_value(cfg.device.adb_path)
                address_input.set_value(cfg.device.address)
                form.refresh()
                form_message.classes(remove="error")
                form_message.set_text("Preset loaded. Changes apply on the next start.")
            except (ValueError, OSError) as exc:
                report_error(exc)

        def save():
            try:
                name = preset_name.value.strip()
                if name.casefold() == "default":
                    raise ValueError("Default is built in; choose a different name")
                save_settings(preset_path(presets, name), get_settings())
                preset_select.set_options(["Default"] + sorted(p.stem for p in presets.glob("*.json")), value=name)
                form_message.classes(remove="error")
                form_message.set_text(f"Saved {name}. Active session settings are unchanged.")
                ui.notify(f"Saved {name}", type="positive")
            except (ValueError, OSError) as exc:
                report_error(exc)

        async def connect():
            nonlocal preview_source
            connect_button.props("loading")
            try:
                async with device_lock:
                    preview_source = ""
                    await run.io_bound(device.connect, adb_input.value.strip(), address_input.value.strip())
                await update_preview()
                tabs.set_value(overview)
            except Exception as exc:
                ui.notify(str(exc), type="negative", timeout=8000)
                runner.event(str(exc))
            finally:
                connect_button.props(remove="loading")

        async def disconnect():
            nonlocal preview_source
            async with device_lock:
                await run.io_bound(device.disconnect)
                preview_source = ""

        start_button.on_click(start)
        pause_button.on_click(lambda: runner.resume() if runner.status == "paused" else runner.pause())
        stop_button.on_click(runner.stop)
        load_button.on_click(load)
        save_button.on_click(save)
        connect_button.on_click(connect)
        disconnect_button.on_click(disconnect)

        last_preview = None
        last_journal = None
        def refresh():
            nonlocal last_preview, last_journal
            status_label.set_text(runner.status.capitalize())
            phase_label.set_text(runner.phase)
            reason_label.set_text(runner.reason)
            start_button.set_enabled(not runner.active)
            pause_button.set_enabled(runner.status in {"running", "paused"})
            pause_button.set_text("Resume" if runner.status == "paused" else "Pause")
            stop_button.set_enabled(runner.active)
            disconnect_button.set_enabled(device.connected and not device_lock.locked())
            connect_button.set_enabled(not device_lock.locked())
            counter_labels["elapsed"].set_text(f"{int(runner.elapsed) // 60:02}:{int(runner.elapsed) % 60:02}")
            for key in ("attacks", "searches", "collections", "upgrades"):
                counter_labels[key].set_text(f"{getattr(runner, key):,}")
            for key, value in runner.loot.items():
                counter_labels[key].set_text(f"{value:,}")
            entries = "\n".join(reversed(runner.events))
            if entries and entries != last_journal:
                journal.set_text(entries)
                last_journal = entries
            connection_label.set_text("Connected · read only" if device.connected else "Disconnected")
            connection_message.set_text(device.error or (f"Connected to {device.address}" if device.connected else "Not connected. Simulation works without an emulator."))
            preview_error.set_text(device.error)
            if preview_source != last_preview:
                preview.set_source(preview_source)
                preview.set_visibility(bool(preview_source))
                empty.set_visibility(not preview_source)
                last_preview = preview_source
            if device.dimensions:
                w, h = device.dimensions
                match = (w, h) == (draft["calibration"]["width"], draft["calibration"]["height"])
                dimensions.set_text(f"{w} × {h} px · 1-second refresh · " + ("Matches saved dimensions; calibration still required" if match else "Resolution differs from preset; recalibration required"))
            else:
                dimensions.set_text("Read-only preview · no input controls")

        ui.timer(0.25, refresh)
        refresh()

    ui.run(host="127.0.0.1", port=8080, title="Boaz · Farming workspace", reload=False, show=False)
