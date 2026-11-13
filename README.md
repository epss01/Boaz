# Boaz

A local farming assistant for Windows and BlueStacks 5. Named after Boaz, the biblical landowner associated with Ruth's harvest.

**Simulation and live farming are separate actions.** Simulation never sends device input. Live farming sends verified, calibrated inputs only after its readiness checks pass; loot is read from actual battle results. A connected emulator alone is not a complete live configuration.

## Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed, then open PowerShell in this folder:

```powershell
uv python install 3.11
uv sync --frozen
uv run python -m boaz
```

Open <http://127.0.0.1:8080>. Stop the server with Ctrl+C. Python 3.11 is required; `uv.lock` records the tested dependencies. No Node.js, database, account credentials, or emulator is required for simulation.

During initial setup on this machine, Python was installed under `.python/`, and `.venv/` already points to it. The normal run command works with that environment. To recreate it using the same project-local Python installation:

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD '.python'
uv python install 3.11 --no-bin
uv sync --frozen
```

## Use

- **Session:** Start simulation, Pause/Resume, and Stop. Observe synthetic activity, loot, counters, and the newest journal entries first.
- **Presets:** Edit task toggles, loot thresholds, deployment steps, wall reserves, and session limits. Save under a name, then select and Load preset later. Saving the same name replaces that preset atomically. Default is built in and cannot be overwritten.
- **Emulator:** Enter the full ADB executable path and the intended local instance address. Connect & check screenshot verifies that instance and captures a frame. It never chooses the first available device. This machine uses `C:\Program Files\BlueStacks_polar\HD-Adb.exe` and was observed at `127.0.0.1:6610`.
- **Calibration:** Freeze screenshots, select recognition/OCR rectangles and collector/wall points, test every region against a second capture, then save a named profile and its referencing preset. See [the setup guide](docs/live-setup.md).
- **Start live farming:** Requires the prepared army, a complete validated profile, matching home camera/resolution, and Tesseract with English data. Deploys ordered troop, hero, and spell steps; heroes deploy once, with no manual ability inputs.

Unsaved form edits are local to that browser page and are lost on refresh. Starting snapshots the current form; later edits never alter the active session. Multiple browser tabs share the same runner and emulator, with their own editable forms. Restarting the server always starts idle.

### Simulation rules

- Each candidate base `n` offers `100,000 + 50,000n` gold, `80,000 + 40,000n` elixir, and `1,000 + 200n` dark elixir. Candidate numbering restarts for each attack.
- All nonzero loot minimums must pass. Exhausting the search limit ends the session without attacking. A zero threshold disables that filter.
- Deployment steps run in order. Slots start at 1; X/Y are screenshot pixels. Troop/spell counts accept an integer or `all`; hero counts must be 1. Simulation represents `all` as 10 synthetic units. Per-unit delay affects simulated deployment duration.
- Collections add 25,000 gold and elixir to the synthetic wallet. The loot counters count attacks only.
- Wallets begin at 1,000,000 gold/elixir and 20,000 dark elixir. Marked walls cost a synthetic 100,000 of the chosen currency each; resource reserves and the session upgrade limit are enforced.
- Active duration excludes paused time. Attack count and duration end a farming session. With attacks disabled, enabled village tasks run once and finish. A duration limit can interrupt a simulated stage without counting its result.
- Simulation intentionally does not require real screen templates or calibrated game objects. Collector coordinates are stored for later live implementation; marked walls and deployment points are used in simulation logs.

### BlueStacks preview

1. Install and open BlueStacks 5. Follow the [official ADB setup guide](https://support.bluestacks.com/hc/en-us/articles/23925869130381-How-to-enable-Android-Debug-Bridge-on-BlueStacks-5) to enable **Settings → Advanced → Android Debug Bridge**.
2. Enter the actual executable path, commonly `C:\Program Files\BlueStacks_nxt\HD-Adb.exe`, or your Android platform-tools `adb.exe`.
3. Enter the intended instance's loopback address. `127.0.0.1:5555` is only an editable default; instances may use other ports.
4. Connect. Frames refresh at most once per second, with no overlapping captures. A slow capture reduces the effective refresh rate. ADB commands have an eight-second timeout; a connection check can issue several commands.
5. If the instance goes offline or capture fails, Boaz clears the stale frame and asks you to reconnect. Simulation is independent of the preview and continues.

Preview is read-only and is not an interactive calibration canvas. Record width, height, and collector/wall coordinate lists in **Presets → Calibration & marked locations**. Resolution or village-layout changes require recalibration before any future live implementation. Matching dimensions alone do not prove calibration is valid.

Real screenshot capture was verified at 1280 × 720 using the connected BlueStacks instance. Home/camera recognition was tested on second captures. A supervised collector tap was sent, but collection was not verified after a selection/camera transition. Live collection now requires two-frame wallet readings, an actual resource increase, and the calibrated home view. Full collection, battle, and wall-spending checks require the remaining game-screen calibration; they are not inferred from fake-device tests.

## Files and development

`src/boaz/` contains the dashboard, configuration, simulator, live runner, recognition, calibration editor, and bounded device adapter. `config/default.json` documents the built-in defaults; change the corresponding models too if changing defaults. The test suite prevents them drifting. Old preset deployment steps load as troop steps with their original counts; live fields default to an unconfigured profile.

`local/presets/` stores saved JSON; `local/profiles/` and `local/templates/` hold calibration. Failed live operations retain at most 20 diagnostic screenshots under `local/diagnostics/`. `local/logs/boaz.log` rotates at 1 MB with three backups. Local files, virtual environments, caches, and test artifacts are ignored by Git. There are no credentials, telemetry, or public API endpoints added by Boaz. NiceGUI supplies its normal internal transport routes; the server binds to loopback only.

```powershell
uv run --frozen pytest -q
```

In a restricted agent sandbox, Windows asyncio may hang while creating its internal loopback sockets. Run the application/tests from an ordinary local terminal or grant the execution tool local-network access. If the default temporary folder is unavailable, use `uv run --frozen pytest -q --basetemp=.pytest-tmp`.

See [requirements](docs/requirements.md) for the live-farming roadmap and acceptance criteria.

## References and limits

- [Airtest](https://github.com/AirtestProject/Airtest): actual dependency for ADB operations, screen images, and template recognition.
- [NiceGUI](https://nicegui.io/documentation): Python dashboard and background I/O support.
- [MyBot](https://github.com/MyBotRun/MyBot/blob/master/README.md): Clash workflow reference only. No code or proprietary libraries copied; current game compatibility is unverified.
- [AzurLaneAutoScript](https://github.com/LmeSzinc/AzurLaneAutoScript/blob/master/README_en.md): task configuration and diagnostic workflow inspiration only.

Live gameplay bots violate [Supercell's Safe and Fair Play Policy](https://supercell.com/en/safe-and-fair-play/) and can result in permanent account bans. No multi-account support, gem spending, army management, tactical targeting, or remote access is implemented. The prepared army and fixed-camera calibration are supplied by the user.
