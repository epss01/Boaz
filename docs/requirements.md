# Boaz requirements

## Current delivery: runnable foundation

Windows, Python 3.11, uv, Airtest, NiceGUI, pytest. One process owns one runner and one explicitly selected BlueStacks 5 connection. The server listens on `127.0.0.1:8080`; no separate frontend, database, public application API, or extension system.

| Capability | Acceptance |
| --- | --- |
| Startup | Dashboard and simulation work with no emulator, ADB, templates, or account. |
| Session | Start snapshots validated settings; duplicate starts are rejected. Pause freezes active time and progress, resume continues, and stop cancels pending stages. Startup is always idle. |
| Simulation | Deterministic home → collect → army readiness → search → deploy → battle → return → optional walls. Counters and logs explicitly identify simulation. No emulator/input calls. |
| Limits | Nonzero resource minimums all pass; unsuccessful search ends at its cap. Attack and active-duration limits end sessions. Village-only tasks finish once. |
| Presets | Named JSON with validated types, ranges, task prerequisites, and in-bounds coordinates. Atomic replacement preserves old data if saving fails. Settings changes affect the next run. |
| Preview | Explicit executable/address; local instance only. Read-only ADB status and capture. Serialized background operations with bounded ADB commands, at most one capture per second. Dimensions and readable failure/reconnect messages. |
| Dashboard | Session, Presets, and Emulator tabs. Clear empty/disabled/running/paused/stopped/completed/error states, keyboard-operable controls, narrow-screen layout. |
| Diagnostics | Bounded in-memory journal, rotating local logs, no stale preview after device loss. Session failures end simulation with a diagnostic reason. |

### Internal interfaces

- `Settings` and its nested Pydantic models define JSON preset validation. `load_settings`, `save_settings`, and `preset_path` own persistence and safe names.
- `Runner.start(settings)`, `pause()`, `resume()`, and async `stop()` own the one simulated task. Status, phase, counters, reason, and events feed the UI. No device dependency.
- `Device.connect(adb_path, address)`, `capture()`, and `disconnect()` are blocking and run through NiceGUI's background I/O utility. An async lock coordinates requests, and an internal thread lock serializes device operations. The adapter exposes no gameplay input functions.
- Native pixel coordinates are tied to calibration width/height, defaulting to 1280 × 720. English UI and one Home Village account are the future live target.

## Follow-on live-farming requirements

These are requirements, not implemented features. Collect real screenshots and validate the current game version before implementing any action. Do not ship guessed coordinates or copied historical game templates as working calibration.

| Capability | Live behavior |
| --- | --- |
| Recognition | Use screenshot templates for known screens and buttons. Establish acceptable match confidence from real fixtures. Unknown screens pause with a diagnostic. |
| Collection | Verify the home screen and calibrated village layout before visiting marked collector positions. Verify the resulting screen before continuing. |
| Army readiness | Confirm the configured troop slots and army are ready before entering matchmaking; otherwise pause and explain what is missing. |
| Base search | Add numeric OCR for gold, elixir, and dark elixir. All enabled minimums must pass; unreadable values never become zero or a successful match. Bound searches. |
| Deployment | Validate the battle screen, configured slots and deployment points, then execute ordered counts and delays. Recheck state at meaningful transitions. |
| Finish and return | Detect actual battle completion, read observed results, return home, and report observed rather than simulated loot. |
| Walls | Use user-marked targets. Verify the object is a wall, currency, upgrade cost, resource balance, and available upgrade action. Preserve configured reserves and enforce the session cap. Default off. |
| Failure | Lost connections, unexpected screens, uncertain readings, and timeouts pause live actions. Re-recognize before resuming. Never blindly retry an upgrade when its outcome is uncertain. |
| Calibration | Store screen dimensions and selected coordinates with the preset; resolution or village-layout changes invalidate calibration. Matching dimensions alone are insufficient. |

Deliver live behavior in three increments: (1) recognition and collection, (2) search/deploy/return, (3) verified wall upgrades. Each increment needs real screen fixtures, bounded failure tests, and a supervised emulator check before being marked available.

No gem purchases, unattended recovery from unknown spending outcomes, anti-detection claims, account credentials, remote control, multi-account scheduling, or arbitrary strategy plugins are included.

## Validation

Automated checks cover configuration round trips and invalid inputs, atomic-save failures, deterministic loot, state transitions, start snapshot isolation, task and session limits, error reporting, wall reserves, explicit device selection, capture failure, serialized capture, and zero simulation device commands.

Browser verification covers session controls, preset load/save, add/remove deployment steps, invalid inputs, connection errors, tab/keyboard operation, and responsive layout. Real BlueStacks preview remains pending until a working instance is available.
