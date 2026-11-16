"""One local dashboard, one simulator, one read-only emulator connection."""

import asyncio
import base64
import json
import time
from pathlib import Path

from nicegui import app, run, ui

from .config import Settings, load_settings, preset_path, save_settings, town_hall_army
from .device import Device
from .runner import Runner
from .live import LiveRunner
from .recognition import OCR, Recognizer, load_profile
from .calibration_ui import calibration_panel
from .accounts import install_assets, initial_settings, remember_account
from .army import recommend, UNITS


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


def apply_town_hall(draft: dict, level: int, wall_breakers: bool):
    draft["farming"]["army"] = town_hall_army(level, wall_breakers).model_dump()
    for step in draft["farming"]["deployment"]:
        step["delay"] = 0.5


def apply_farming_mode(draft: dict, combined: bool):
    draft["farming"]["attack"] = True
    draft["walls"]["enabled"] = combined
    if not combined:
        draft["walls"]["until_max"] = False
    if combined:
        draft["walls"]["build_menu"] = True


def serve(local: Path, *, open_browser: bool = False):
    install_assets(local)
    icons = Path(__file__).parent/'assets'/'units'
    app.add_static_files('/army-icons',icons)
    presets = local / "presets"
    presets.mkdir(parents=True, exist_ok=True)
    runner, device = Runner(), Device()
    simulation = runner
    starting_live = False
    device_lock = asyncio.Lock()
    preview_source = ""
    capture_busy = False

    async def update_preview():
        nonlocal preview_source, capture_busy
        if not device.connected:
            preview_source = ""
            return
        if capture_busy or device_lock.locked():
            return
        capture_busy = True
        try:
            if isinstance(runner,LiveRunner) and runner.active:
                # Preview must not delay timed troop taps with another ADB capture.
                frame=runner._frame
                if frame is None:
                    return
            else:
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
    async def shutdown():
        await runner.stop()
    app.on_shutdown(shutdown)

    @ui.page("/")
    def page():
        ui.colors(primary="#376747", secondary="#596d51", accent="#ad6a23", negative="#9a302a")
        ui.add_css(CSS)
        try:
            initial = initial_settings(local)
            startup_error = ''
        except (ValueError,OSError,KeyError) as exc:
            initial = Settings()
            startup_error = f'Could not restore account settings: {exc}'
        draft = initial.model_dump()
        account_confirmed = bool(initial.walls.player_tag and initial.farming.prepare_army)
        village_data = None
        setup_task = None
        if account_confirmed:
            path = preset_path(local/'accounts',initial.walls.player_tag[1:]+'-village')
            if path.exists():
                village_data = json.loads(path.read_text(encoding='utf-8'))

        with ui.row().classes("masthead w-full items-center justify-between"):
            with ui.row().classes("items-center gap-4"):
                ui.icon("grass", size="32px")
                with ui.column().classes("gap-0"):
                    ui.label("Boaz").classes("brand")
                    ui.label("A little less grind. A little more harvest.").classes("subtitle")
            mode_badge = ui.badge("Simulation · no gameplay input", color="white", text_color="primary").classes("px-3 py-2")

        with ui.column().classes("shell gap-6"):
            with ui.row().classes("w-full items-start justify-between gap-4"):
                with ui.column().classes("gap-2"):
                    ui.label("Your farming workspace").classes("text-3xl font-semibold").props('role="heading" aria-level="1"')
                    ui.label("Prepare your army, farm resources, and upgrade walls.").classes("muted")
                live_button = ui.button("Start farming & upgrade walls", icon="play_arrow", color="primary")
            with ui.tabs().props("align=left inline-label").classes("w-full") as tabs:
                overview = ui.tab("Farming", icon="dashboard")
                settings_tab = ui.tab("Presets", icon="tune")
                connection_tab = ui.tab("Emulator", icon="smartphone")
                calibration_tab = ui.tab("Calibration", icon="crop_free")
                for tab in (settings_tab,connection_tab,calibration_tab):
                    tab.set_visibility(False)
                with ui.button('Advanced',icon='settings').props('flat'):
                    with ui.menu():
                        ui.menu_item('Presets',on_click=lambda:tabs.set_value(settings_tab))
                        ui.menu_item('Emulator',on_click=lambda:tabs.set_value(connection_tab))
                        ui.menu_item('Calibration',on_click=lambda:tabs.set_value(calibration_tab))
                        start_button = ui.menu_item('Run simulation')
                        custom_live_button = ui.menu_item('Start custom live session')
            with ui.tab_panels(tabs, value=overview).classes("w-full"):
                with ui.tab_panel(overview):
                    with ui.column().classes("w-full gap-6"):
                        with ui.column().classes('panel w-full gap-4'):
                            with ui.row().classes('w-full items-center justify-between gap-4'):
                                town_hall = ui.select({n:f'Town Hall {n}' for n in range(7,19)},
                                    value=initial.farming.army.town_hall if initial.farming.army else None,
                                    label='Town Hall',on_change=lambda e:change_town_hall(e.value)).props('outlined').classes('w-56')
                                identify_button = ui.button('Connect & check account',icon='person_search',on_click=lambda:check_account())
                                confirm_button = ui.button('Use this account',on_click=lambda:confirm_account()).props('outline')
                            setup_message = ui.label(startup_error or ('Account restored. Start rechecks the active village.' if account_confirmed else 'Check your account once to calculate and remember its army.')).props('role="status" aria-live="polite"')
                            @ui.refreshable
                            def army_banner():
                                composition = draft['farming'].get('composition',[])
                                if not composition:
                                    ui.label('Recommended army').classes('text-lg font-semibold')
                                    ui.label('Connect your account to read its army capacity and unlocked units.').classes('muted')
                                    return
                                ui.label('Your recommended army').classes('text-lg font-semibold')
                                with ui.row().classes('gap-6 w-full items-start'):
                                    for unit in composition:
                                        name,count = unit['name'],unit['count']
                                        with ui.column().classes('items-center gap-1 w-24'):
                                            ui.image(f'/army-icons/{UNITS[name][3]}.webp').props(f'fit=contain alt="{name}"').classes('w-20 h-20')
                                            ui.label(f'{count} × {name}').classes('text-center font-medium')
                                ui.label('Equipped, recognized heroes deploy once. Unavailable heroes are skipped.').classes('muted text-sm')
                                if village_data:
                                    heroes = {28000000:('Barbarian King','barbarian_king'),28000001:('Archer Queen','archer_queen'),
                                              28000002:('Grand Warden','grand_warden'),28000004:('Royal Champion','royal_champion'),
                                              28000006:('Minion Prince','minion_prince'),28000007:('Dragon Duke','dragon_duke')}
                                    ui.label('Unlocked heroes · equipped availability checked at Start').classes('muted text-sm')
                                    with ui.row().classes('gap-4 flex-wrap'):
                                        for hero in village_data.get('heroes',[]):
                                            if hero.get('lvl',0)>0 and hero['data'] in heroes:
                                                name,slug = heroes[hero['data']]
                                                with ui.column().classes('items-center gap-1 w-24'):
                                                    ui.image(f'/army-icons/{slug}.webp').props(f'fit=contain alt="{name}"').classes('w-14 h-14')
                                                    ui.label(name).classes('text-xs text-center')
                            army_banner()
                            start_summary=ui.label().classes('muted text-sm')
                        with ui.row().classes("notice w-full items-center gap-3"):
                            ui.icon("science", size="24px")
                            mode_notice = ui.label("Practice mode. Every base, troop, resource, and upgrade below is simulated. No gameplay input is sent.")
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
                                        ui.label("Connect your village").classes("text-lg font-medium")
                                        ui.label("Open Clash of Clans in BlueStacks, then check your account above.").classes("muted")
                                        ui.button("Set up emulator", on_click=lambda: tabs.set_value(connection_tab)).props("outline")
                                dimensions = ui.label("Read-only preview · no input controls").classes("muted text-sm")
                                preview_error = ui.label().classes("error text-sm").props('role="alert"')
                            with ui.column().classes("panel gap-4"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    session_heading = ui.label("Simulated session").classes("heading").props('role="heading" aria-level="2"')
                                    status_label = ui.badge("Idle", color="secondary")
                                phase_label = ui.label("Home").classes("text-2xl font-medium")
                                recognition_label = ui.label().classes("muted text-sm")
                                reason_label = ui.label(runner.reason).classes("muted").props('role="status" aria-live="polite"')
                                with ui.row().classes("gap-2"):
                                    pause_button = ui.button("Pause", icon="pause").props("outline")
                                    stop_button = ui.button("Stop", icon="stop", color="negative").props("outline")
                                counter_labels = {}
                                with ui.column().classes("w-full gap-0"):
                                    for key, title in [("elapsed", "Active time"), ("attacks", "Attacks"), ("searches", "Bases searched"), ("collections", "Collections"), ("upgrades", "Wall upgrades"), ("gold", "Gold looted"), ("elixir", "Elixir looted"), ("dark_elixir", "Dark elixir looted")]:
                                        with ui.element("div").classes("metric-row"):
                                            ui.label(title).classes("muted")
                                            counter_labels[key] = ui.label("0").classes("value")
                                counters_notice = ui.label("Loot excludes collections. Preview shows the real screen; counters show simulation results.").classes("muted text-sm")
                        with ui.column().classes("panel w-full gap-3"):
                            ui.label("Session journal").classes("heading").props('role="heading" aria-level="2"')
                            journal = ui.label("Your account setup is restored. Gameplay stays idle until Start." if account_confirmed else "Ready when you are. Check your account to prepare the recommended army.").classes("log w-full")

                with ui.tab_panel(settings_tab):
                    with ui.column().classes("panel w-full gap-5"):
                        ui.label("Make the routine yours").classes("heading").props('role="heading" aria-level="2"')
                        ui.label("Edits apply on the next start. Live farming requires a validated profile; simulation never sends gameplay input.").classes("muted")
                        with ui.row().classes("w-full items-center gap-3"):
                            preset_select = ui.select(["Default"] + sorted(p.stem for p in presets.glob("*.json")), value="Default", label="Saved preset").props("outlined").classes("w-56")
                            load_button = ui.button("Load preset").props("outline")
                            preset_name = ui.input("Save as", value="my-farm").props("outlined").classes("w-56")
                            save_button = ui.button("Save preset", icon="save")
                        form_message = ui.label().props('role="status" aria-live="polite"').classes("text-sm")

                        @ui.refreshable
                        def form():
                            ui.input("Live calibration profile").bind_value(draft["live"], "profile").props("outlined").classes("w-full")
                            def number(group, key, label, integer=True, minimum=0):
                                def change(e):
                                    value = e.value
                                    draft[group][key] = int(value) if integer and value is not None and float(value).is_integer() else value
                                ui.number(label, value=draft[group][key], min=minimum, on_change=change).props("outlined").classes("w-full")

                            def mode_changed(e):
                                if e.value == "advanced":
                                    advanced_tasks.open()
                                    return
                                apply_farming_mode(draft, e.value == "combined")
                                form.refresh()
                            ui.select({"farm": "Auto farm", "combined": "Auto farm + wall upgrades", "advanced": "Advanced tasks"},
                                      value=("combined" if draft["walls"]["enabled"] else "farm") if draft["farming"]["attack"] else "advanced",
                                      label="Farming mode", on_change=mode_changed).props("outlined").classes("w-full")
                            with ui.expansion("Advanced tasks", icon="settings").classes("w-full") as advanced_tasks:
                                def advanced_changed(group, key, value):
                                    draft[group][key] = value
                                    form.refresh()
                                ui.switch("Collect resources", value=draft["farming"]["collect"], on_change=lambda e: advanced_changed("farming", "collect", e.value))
                                ui.switch("Search and attack", value=draft["farming"]["attack"], on_change=lambda e: advanced_changed("farming", "attack", e.value))
                                ui.switch("Upgrade walls", value=draft["walls"]["enabled"], on_change=lambda e: advanced_changed("walls", "enabled", e.value))
                            army = draft["farming"].get("army")
                            def army_changed(level, wall_breakers):
                                apply_town_hall(draft, level, wall_breakers)
                                form.refresh()
                            ui.select({7: "TH1–7 starter", **{n: f"Town Hall {n}" for n in range(8, 19)}},
                                      value=army["town_hall"] if army else None, label="Town Hall preset",
                                      on_change=lambda e: army_changed(e.value, bool(army and army["wall_breakers"]))).props("outlined").classes("w-full")
                            if army:
                                if army["town_hall"] >= 8:
                                    ui.select({False: "Valkyries", True: "Valkyries + wall breakers"}, value=army["wall_breakers"], label="Troop setup",
                                              on_change=lambda e: army_changed(army["town_hall"], e.value)).props("outlined").classes("w-full")
                                ui.label("Suggested slots for new calibration profiles. Counts come from the calibrated screen; these settings do not edit your in-game army or existing profiles.").classes("muted text-sm")
                                with ui.element("div").classes("form-grid"):
                                    for key, label, minimum, maximum in [("troops", "Troop types", 1, 19), ("heroes", "Hero slots", 0, 4), ("spells", "Spell types", 0, 20), ("siege", "Siege slot", 0, 1)]:
                                        def update_army(e, field=key):
                                            value = e.value
                                            army[field] = int(value) if value is not None and float(value).is_integer() else value
                                        ui.number(label, value=army[key], min=minimum, max=maximum, on_change=update_army).props("outlined")
                            with ui.expansion('Custom army composition',icon='edit').classes('w-full'):
                                composition_error=ui.label().classes('error').props('role="alert"')
                                def edit_composition(e):
                                    try:
                                        from .config import ArmyUnit
                                        rows=json.loads(e.value)
                                        if not isinstance(rows,list):
                                            raise ValueError('Enter a JSON list of units')
                                        units=[ArmyUnit.model_validate(row) for row in rows]
                                        if len(units)>9 or len({u.name for u in units})!=len(units):
                                            raise ValueError('Use at most nine unique unit types')
                                        draft['farming']['composition']=[u.model_dump() for u in units]
                                        composition_error.set_text('')
                                        army_banner.refresh()
                                    except (ValueError,TypeError) as exc:
                                        composition_error.set_text(str(exc))
                                ui.textarea('Army units (JSON)',value=json.dumps(draft['farming'].get('composition',[]),indent=2),on_change=edit_composition).props('outlined autogrow').classes('w-full')
                                ui.label('Custom compositions require their own validated preparation and deployment layout. The banner shows what Start will apply.').classes('muted text-sm')
                            ui.label("Base selection").classes("text-lg font-semibold mt-5")
                            ui.label("All nonzero minimums must pass. Zero disables that resource filter.").classes("muted text-sm")
                            with ui.element("div").classes("form-grid"):
                                for key, label in [("min_gold", "Minimum gold"), ("min_elixir", "Minimum elixir"), ("min_dark_elixir", "Minimum dark elixir"), ("search_limit", "Search limit per attack")]:
                                    number("farming", key, label)
                                number("session", "attack_limit", "Attack limit per session", minimum=1)
                                number("session", "duration_minutes", "Active duration (minutes)", integer=False, minimum=0.01)
                            ui.label("Ordered deployment").classes("text-lg font-semibold mt-5")
                            ui.switch("Dump all available units at the first step's corner (live)").bind_value(draft["farming"], "dump_all")
                            ui.switch("Find clear deployment ground from the boundary (live dump mode)").bind_value(draft["farming"], "auto_corner")
                            ui.label("Dump mode uses the first step's X/Y and delay for all calibrated troop, hero, and spell slots. Choose a legal corner deployment point; heroes deploy once. Live attacks use regular Multiplayer Battle only, never Ranked Battle.").classes("muted text-sm")
                            ui.label("Troops, heroes, and spells run in this order. Use all for remaining troops/spells; heroes deploy once with count 1. No manual hero abilities. Slots start at 1; positions are screenshot pixels.").classes("muted text-sm")

                            @ui.refreshable
                            def deployment():
                                for index, step in enumerate(draft["farming"]["deployment"]):
                                    with ui.row().classes("items-center w-full gap-2"):
                                        ui.label(str(index + 1)).classes("font-semibold")
                                        def kind_changed(e, target=step):
                                            target["kind"] = e.value
                                            if e.value == "hero":
                                                target["count"] = 1
                                            deployment.refresh()
                                        ui.select(["troop", "hero", "spell"], value=step.get("kind", "troop"), label="Kind", on_change=kind_changed).props("outlined dense").classes("w-28")
                                        def count_changed(e, target=step):
                                            value = e.value.strip()
                                            target["count"] = int(value) if value.isdigit() else value
                                        ui.input("Count / all", value=str(step["count"]), on_change=count_changed).props("outlined dense").classes("w-28")
                                        for key, label in [("slot", "Slot"), ("x", "X"), ("y", "Y"), ("delay", "Tap interval (s)")]:
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
                                draft["farming"]["deployment"].append(dict(kind="troop", slot=1, x=0, y=0, count="all", delay=0.5))
                                deployment.refresh()
                            ui.button("Add deployment step", icon="add", on_click=add_step).props("outline")
                            ui.label("Wall budget").classes("text-lg font-semibold mt-5")
                            if draft["farming"]["attack"] and draft["walls"]["enabled"]:
                                ui.switch("Run until walls are maxed (live)").bind_value(draft["walls"], "until_max")
                                ui.input("Village player tag for continuous mode").bind_value(draft["walls"], "player_tag").props("outlined")
                                ui.label("Continuous mode uses gold or elixir and replaces the attack, time and upgrade-count limits. Stop ends the session.").classes("muted text-sm")
                            ui.switch("Select walls through the Build menu").bind_value(draft["walls"], "build_menu")
                            ui.label("Simulation uses a fixed 100,000 cost per wall and a starting balance of 1,000,000 gold and elixir.").classes("muted text-sm")
                            with ui.element("div").classes("form-grid"):
                                ui.select(["gold", "elixir"], label="Upgrade currency").bind_value(draft["walls"], "currency").props("outlined")
                                number("walls", "upgrade_limit", "Maximum upgrades per session", minimum=1)
                                number("walls", "reserve_gold", "Keep at least this much gold")
                                number("walls", "reserve_elixir", "Keep at least this much elixir")
                                ui.number('Maximum wall spending this session (optional)',value=draft['walls']['spend_limit'],min=0,precision=0,
                                    on_change=lambda e:draft['walls'].__setitem__('spend_limit',None if e.value is None else int(e.value))).props('outlined clearable')
                            with ui.expansion("Calibration & marked locations", icon="crop_free").classes("w-full mt-4"):
                                ui.label("Changing resolution or moving village objects requires recalibration. Use Calibration to mark these points visually.").classes("muted text-sm mb-4")
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
                        adb_input = ui.input("ADB executable (full path)", value=draft["device"]["adb_path"], placeholder=r"C:\Program Files\BlueStacks_polar\HD-Adb.exe").props("outlined").classes("w-full")
                        address_input = ui.input("Local device address", value=draft["device"]["address"]).props("outlined").classes("w-full")
                        with ui.row().classes("gap-3"):
                            connect_button = ui.button("Connect & check screenshot", icon="link")
                            disconnect_button = ui.button("Disconnect").props("outline")
                        connection_message = ui.label("Not connected. Simulation works without an emulator.").classes("muted").props('role="status" aria-live="polite"')
                        ui.link("BlueStacks ADB setup guide", "https://support.bluestacks.com/hc/en-us/articles/23925869130381-How-to-enable-Android-Debug-Bridge-on-BlueStacks-5", new_tab=True)
                        ui.label("Preview is read-only. Only an explicitly started live session sends calibrated gameplay input.").classes("muted text-sm")

                with ui.tab_panel(calibration_tab):
                    def settings_for_calibration():
                        return get_settings()
                    calibration_panel(local, device, device_lock, settings_for_calibration, draft,
                                      lambda: form.refresh(), lambda: runner.active or starting_live)

            ui.label("Boaz 0.2 · One village. One session. Your settings.").classes("muted text-sm mt-4")
            ui.link('Unit artwork © Supercell · ClashKingAssets','https://github.com/ClashKingInc/ClashKingAssets',new_tab=True).classes('muted text-xs')

        def change_town_hall(level):
            nonlocal account_confirmed
            account_confirmed = False
            draft['farming']['composition'] = []
            if village_data is not None and level is not None:
                try:
                    apply_town_hall(draft,level,False)
                    composition=recommend(village_data,level)
                    draft['farming']['composition'] = [u.model_dump() for u in composition]
                    army=draft['farming']['army']
                    army['troops']=sum(UNITS[u.name][2]=='troop' for u in composition)
                    army['spells']=sum(UNITS[u.name][2]=='spell' for u in composition)
                    army['siege']=int(any(UNITS[u.name][2]=='siege' for u in composition))
                    army['wall_breakers']=any(u.name=='Wall Breaker' for u in composition)
                    setup_message.set_text('Check the army shown, then use this account.')
                except (ValueError,KeyError) as exc:
                    setup_message.set_text(str(exc))
            army_banner.refresh()

        async def check_account():
            nonlocal runner,starting_live,village_data,account_confirmed,setup_task
            if runner.active or starting_live:
                return
            starting_live = True
            setup_task = asyncio.current_task()
            identify_button.props('loading')
            account_confirmed = False
            try:
                cfg = get_settings()
                if not device.connected:
                    async with device_lock:
                        await run.io_bound(device.connect,cfg.device.adb_path,cfg.device.address)
                rec = Recognizer(local,load_profile(local,cfg.live.profile),OCR(cfg.live.tesseract_path,local/'numeric-font'))
                probe = LiveRunner(device,rec,device_lock,local/'diagnostics')
                probe.settings = cfg
                probe._started = time.monotonic()
                probe._gate.set()
                probe.input_allowed.set()
                probe._task = setup_task
                probe.status = 'checking'
                runner = probe
                async def fail(exc):
                    raise exc
                probe._recover = fail
                setup_message.set_text('Reading the account and village. Stop cancels this check.')
                progress = await probe._export(discover=True)
                village_data = probe.village_data
                draft['walls']['player_tag'] = progress.tag
                town_hall.set_value(progress.town_hall)
                change_town_hall(progress.town_hall)
                setup_message.set_text(f'Account {progress.tag} · Town Hall {progress.town_hall} · {progress.remaining} walls remaining. Confirm this is your account.')
                probe._finish('idle','Account checked; confirm it to enable farming')
            except asyncio.CancelledError:
                setup_message.set_text('Account check stopped. Return the game Home before checking again.')
                raise
            except Exception as exc:
                setup_message.set_text(f'Account check stopped: {exc}. Return the game Home and check again.')
                runner.status = 'stopped'
            finally:
                if isinstance(runner,LiveRunner):
                    runner.input_allowed.clear()
                starting_live = False
                setup_task = None
                identify_button.props(remove='loading')

        def confirm_account():
            nonlocal account_confirmed
            try:
                if village_data is None or not draft['farming']['composition']:
                    raise ValueError('Check your account and its recommended army first')
                draft['farming'].update(collect=False,attack=True,prepare_army=True,dump_all=True,auto_corner=True)
                draft['walls'].update(enabled=True,build_menu=True,until_max=True,reserve_gold=500000,reserve_elixir=500000)
                cfg = get_settings()
                remember_account(local,cfg)
                from .config import atomic_json
                atomic_json(preset_path(local/'accounts',cfg.walls.player_tag[1:]+'-village'),village_data)
                account_confirmed = True
                form.refresh()
                setup_message.set_text(f'Account {cfg.walls.player_tag} saved. Start will prepare the shown army and farm with wall upgrades.')
            except (ValueError,OSError) as exc:
                setup_message.set_text(str(exc))

        async def restore_connection():
            if device.connected or runner.active or starting_live or not draft['device']['adb_path']:
                return
            try:
                async with device_lock:
                    await run.io_bound(device.connect,draft['device']['adb_path'],draft['device']['address'])
            except Exception as exc:
                setup_message.set_text(f'Open your saved BlueStacks instance, then check the account. {exc}')
        ui.timer(.1,restore_connection,once=True)

        def get_settings():
            draft["device"] = dict(adb_path=adb_input.value.strip(), address=address_input.value.strip())
            return Settings.model_validate(draft)

        def report_error(exc):
            message = str(exc)
            form_message.set_text(message)
            form_message.classes(add="error")
            ui.notify("Check your settings in Presets: " + message, type="negative", timeout=8000)

        def start():
            nonlocal runner
            try:
                if runner.active or starting_live:
                    raise ValueError("Stop the active session before starting another")
                runner = simulation
                runner.start(get_settings())
            except (ValueError, OSError) as exc:
                report_error(exc)

        async def start_live(custom=False):
            nonlocal runner, starting_live
            if runner.active or starting_live:
                ui.notify("Stop the active session before starting live farming", type="negative")
                return
            starting_live = True
            live_button.props("loading")
            try:
                if not custom and not account_confirmed:
                    raise ValueError('Connect, check and confirm your account first')
                cfg = get_settings()
                if not custom:
                    cfg.farming.prepare_army = True
                    cfg.walls.enabled = cfg.walls.build_menu = True
                    cfg.walls.reserve_gold = max(500000,cfg.walls.reserve_gold)
                    cfg.walls.reserve_elixir = max(500000,cfg.walls.reserve_elixir)
                if not device.connected:
                    async with device_lock:
                        await run.io_bound(device.connect,cfg.device.adb_path,cfg.device.address)
                profile = load_profile(local, cfg.live.profile)
                recognizer = Recognizer(local, profile, OCR(cfg.live.tesseract_path, local / "numeric-font"))
                await run.io_bound(recognizer.ready, cfg)
                async with device_lock:
                    frame = await run.io_bound(device.capture)
                    recognizer.expect("home", frame)
                    if (cfg.farming.collect or (cfg.walls.enabled and not cfg.walls.build_menu)) and not recognizer.matches("home.camera", frame):
                        raise ValueError("Restore the calibrated home camera before starting")
                runner = LiveRunner(device, recognizer, device_lock, local / "diagnostics")
                runner.start(cfg)
                setup_message.set_text('Account and Home verified; live session started')
                tabs.set_value(overview)
            except Exception as exc:
                setup_message.set_text(str(exc))
                report_error(exc)
            finally:
                starting_live = False
                live_button.props(remove="loading")

        async def pause_resume():
            try:
                if runner.status == 'paused':
                    if runner.mode == 'Live' and not device.connected:
                        await runner.reconnect()
                    runner.resume()
                else:
                    runner.pause()
            except Exception as exc:
                ui.notify(str(exc), type="negative", timeout=10000)

        async def stop_session():
            await runner.stop()

        def load():
            nonlocal account_confirmed
            try:
                cfg = Settings() if preset_select.value == "Default" else load_settings(preset_path(presets, preset_select.value))
                draft.clear()
                draft.update(cfg.model_dump())
                account_confirmed=False
                army_banner.refresh()
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
                if runner.active or starting_live:
                    raise ValueError("Stop the active session before changing its emulator connection")
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
            if runner.active or starting_live:
                ui.notify("Stop the active session before disconnecting", type="negative")
                return
            async with device_lock:
                await run.io_bound(device.disconnect)
                preview_source = ""

        start_button.on_click(start)
        live_button.on_click(lambda:start_live())
        custom_live_button.on_click(lambda:start_live(custom=True))
        pause_button.on_click(pause_resume)
        stop_button.on_click(stop_session)
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
            idle_reason='Ready to farm with the shown army. Press Start when your village is Home.' if account_confirmed else 'Check your account, then Start when the shown army is correct.'
            reason_label.set_text(idle_reason if runner.status=='idle' and runner.mode!='Live' else runner.reason)
            is_live = runner.mode == "Live"
            scope='until a fresh export confirms maximum walls' if draft['walls']['until_max'] else 'within your Advanced session limits'
            reserves={key:value if type(value)is int and value>=500000 else 500000 for key,value in draft['walls'].items() if key in ('reserve_gold','reserve_elixir')}
            start_summary.set_text(f"Start applies the shown army, farms and upgrades walls {scope}. Reserves: {reserves['reserve_gold']:,} gold and {reserves['reserve_elixir']:,} elixir.")
            practicing = not is_live and runner.status != 'idle'
            mode_badge.set_text("Simulation · no gameplay input" if practicing else "Live farming" if runner.active else "Idle · waiting for Start")
            session_heading.set_text("Simulated session" if practicing else "Farming session")
            mode_notice.set_text("Practice mode. Gameplay is simulated; no input is sent." if practicing else "Start prepares the shown army, farms, and upgrades affordable walls. Pause or Stop blocks subsequent inputs.")
            counters_notice.set_text("Loot excludes collections. Counters show simulation results." if practicing else "Loot is read from verified battle results. Wall upgrades require a confirmed level and wallet change.")
            if is_live:
                recognition_label.set_text(f"Recognized: {runner.recognizer.screen} · confidence {runner.recognizer.confidence:.3f}")
                if runner.wall_progress:
                    progress = runner.wall_progress
                    recognition_label.set_text(f"TH{progress.town_hall} · target wall level {progress.target} · {progress.remaining} walls remaining")
            else:
                recognition_label.set_text("")
            start_button.set_enabled(not runner.active and not starting_live)
            live_button.set_enabled(not runner.active and not starting_live and account_confirmed and bool(draft['farming'].get('composition')))
            pause_button.set_enabled(runner.status in {"running", "paused"})
            pause_button.set_text("Resume" if runner.status == "paused" else "Pause")
            stop_button.set_enabled(runner.active)
            identify_button.set_enabled(not runner.active and not starting_live)
            confirm_button.set_visibility(not account_confirmed)
            confirm_button.set_enabled(not runner.active and not starting_live and bool(draft['farming'].get('composition')))
            town_hall.set_enabled(not runner.active and not starting_live)
            disconnect_button.set_enabled(device.connected and not device_lock.locked() and not runner.active and not starting_live)
            connect_button.set_enabled(not device_lock.locked() and not runner.active and not starting_live)
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
                refresh_note='verified frames during live input' if runner.active and is_live else '1-second refresh'
                dimensions.set_text(f"{w} × {h} px · {refresh_note} · " + ("Matches saved dimensions; calibration still required" if match else "Resolution differs from preset; recalibration required"))
            else:
                dimensions.set_text("Read-only preview · no input controls")

        ui.timer(0.25, refresh)
        refresh()

    ui.run(host="127.0.0.1", port=8080, title="Boaz · Farming workspace", reload=False, show=open_browser)
