# Boaz requirements

## Current delivery: simulation and calibrated live workflows

Windows, Python 3.11, uv, Airtest, NiceGUI, pytest, and Tesseract/pytesseract. One process owns one active runner and one explicitly selected BlueStacks 5 connection. The server listens on `127.0.0.1:8080`; no separate frontend, database, public application API, or extension system.

| Capability | Acceptance |
| --- | --- |
| Startup | Dashboard and simulation work with no emulator, ADB, templates, or account. |
| Session | Start snapshots validated settings; duplicate starts are rejected. Pause freezes active time and progress, resume continues, and stop cancels pending stages. Startup is always idle. |
| Simulation | Deterministic home → collect → army readiness → search → deploy → battle → return → optional walls. Counters and logs explicitly identify simulation. No emulator/input calls. |
| Limits | Nonzero resource minimums all pass; unsuccessful search ends at its cap. Attack and active-duration limits end sessions. Village-only tasks finish once. |
| Presets | Named JSON with validated types, ranges, task prerequisites, and in-bounds coordinates. Atomic replacement preserves old data if saving fails. Settings changes affect the next run. |
| Preview | Explicit executable/address; local instance only. Read-only ADB status and capture. Serialized background operations with bounded ADB commands, at most one capture per second. Dimensions and readable failure/reconnect messages. |
| Dashboard | Session, Presets, Emulator, and Calibration tabs. Distinct simulation/live starts, clear status, keyboard controls, and narrow-screen layout. |
| Diagnostics | Bounded in-memory journal, rotating local logs, no stale preview after device loss. Session failures end simulation with a diagnostic reason. |

### Internal interfaces

- `Settings` and its nested Pydantic models define JSON preset validation. `load_settings`, `save_settings`, and `preset_path` own persistence and safe names.
- `Runner.start(settings)`, `pause()`, `resume()`, and async `stop()` own the one simulated task. Status, phase, counters, reason, and events feed the UI. No device dependency.
- `Device.connect`, `capture`, `disconnect`, `tap`, and `swipe` are bounded blocking operations. Async and thread locks serialize access; a dispatch gate blocks pending taps after Pause/Stop.
- `LiveRunner` owns calibrated recognition, input, observed counters, and diagnostic pauses. `Recognizer` validates versioned profiles, templates, OCR, and inventory states. The simulator remains independent of the device.
- Native pixel coordinates are tied to calibration width/height, defaulting to 1280 × 720. English UI and one Home Village account are the live target.

## Live-farming requirements

Implemented workflows require real, user-calibrated screenshots. Readiness gates prevent use without required validated regions and OCR. Do not treat synthetic fixtures as proof of real game compatibility; each profile requires supervised checks. Setup steps are in [live-setup.md](live-setup.md).

| Capability | Live behavior |
| --- | --- |
| Recognition | Use screenshot templates for known screens and buttons. Establish acceptable match confidence from real fixtures. Unknown screens pause with a diagnostic. |
| Collection | Verify the home screen and calibrated village layout before visiting marked collector positions. Verify the resulting screen before continuing. |
| Army readiness | Confirm the configured troop slots and army are ready before entering matchmaking; otherwise pause and explain what is missing. |
| Base search | Add numeric OCR for gold, elixir, and dark elixir. All enabled minimums must pass; unreadable values never become zero or a successful match. Bound searches. |
| Deployment | Interleave troops, heroes, and spells with explicit counts or all remaining. Verify available counts and observed changes. Heroes deploy once; no manual ability taps. |
| Finish and return | Detect actual battle completion, read observed results, return home, and report observed rather than simulated loot. |
| Walls | Use user-marked targets. Verify the object is a wall, currency, upgrade cost, resource balance, and available upgrade action. Preserve configured reserves and enforce the session cap. Default off. |
| Failure | Lost connections, unexpected screens, uncertain readings, and timeouts pause live actions. Re-recognize before resuming. Never blindly retry an upgrade when its outcome is uncertain. |
| Calibration | Store screen dimensions and selected coordinates with the preset; resolution or village-layout changes invalidate calibration. Matching dimensions alone are insufficient. |

Validate real profiles progressively: recognition and collection, search/deploy/return, then verified wall upgrades. Each requires real screen calibration and a supervised emulator check. Fixed camera and visible, non-scrolling army bars are required.

No gem purchases, unattended recovery from unknown spending outcomes, anti-detection claims, account credentials, remote control, multi-account scheduling, or arbitrary strategy plugins are included.

## Validation

Automated checks cover configuration round trips and invalid inputs, atomic-save failures, deterministic loot, state transitions, start snapshot isolation, task and session limits, error reporting, wall reserves, explicit device selection, capture failure, serialized capture, and zero simulation device commands.

Browser verification covers session controls, presets, deployment editing, frozen calibration, second-capture enforcement, profile persistence, blocked incomplete live starts, and OCR readiness. Real BlueStacks capture and home/camera matching have been verified at 1280 × 720. Full live attack and wall-spending verification remains profile-dependent.
