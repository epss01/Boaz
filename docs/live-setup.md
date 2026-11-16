# Set up live farming

The Farming screen is the normal entry point. Open Clash of Clans in the selected BlueStacks instance, choose **Connect & check account**, review the Town Hall, account and army banner, then **Use this account**. The account setup is remembered and reconnects on later launches. Gameplay begins only with **Start farming & upgrade walls**.

Start freshly checks the account export, verifies or replaces the displayed army through recognized army controls, farms, then upgrades affordable walls. Both resource reserves default to 500,000. The remembered combined default continues until a fresh export proves completion. Advanced retains presets, simulation, custom controls, session limits and calibration. Turn off **Run until walls are maxed** to use bounded attack/time/upgrade limits; the optional wall-spending ceiling applies in either mode.

The packaged recognition assets support English 1280×720 and the verified account's calibrated army appearance. Installation preserves existing local assets. Town Hall recommendations use the account's actual unlocked units and camp/spell capacity; a different composition or appearance requires calibration before automatic preparation. Unsupported screens stop with a specific reason. Unlocked heroes shown in the banner are a pool; actual equipped/available heroes are checked from screenshots and unsupported identified heroes are skipped.

The latest follow-up consumed the planned army but stopped before returning Home: its Victory screen uses an uncalibrated **Claim Reward** appearance, and intermittent ADB screenshot timeouts prevented independent validation. This appearance remains a compatibility blocker. Resume can reconnect a safely paused session to its saved emulator; uncertain input outcomes still require Stop and inspection.

Before matchmaking, the combined default normalizes zoom on verified Home using the installed Airtest minitouch helper. The helper is copied through bounded ADB and its two contacts are committed together; Pause/Stop cancels later gesture frames and releases both contacts. The operation is limited to five attempts and must settle on Home. Deployment still requires a visible boundary, clear ground and a verified first unit consumption.

Card selection and deployment can flash briefly. Hero guards and post-placement inventory allow up to two seconds of observation for a settled reading. This never repeats a dispatched placement or hero portrait tap. Persistent uncertainty pauses the run. A bounded normal-button run passed complete planned consumption, stable loot, one verified 750,000-elixir wall upgrade and return Home. Entire-account completion remains fixture-tested; see the handoff for the separate follow-up and exact live limits.

Simulation is independent of this setup. The manual instructions below describe Advanced calibration and custom presets.

## Connect and install OCR

Open Emulator, enter the explicit ADB executable and loopback address, and connect. This machine was verified with `C:\Program Files\BlueStacks_polar\HD-Adb.exe`, `127.0.0.1:6610`, and 1280 × 720 screenshots. Your instance must be running and logged into the game; inactivity dialogs are not valid home screens.

Install Tesseract 5 and English training data using the Windows build linked from [Tesseract's installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html). Enter its full executable path in Calibration and use **Check OCR installation**. `pytesseract` is the Python wrapper, not the OCR engine. An installation under `local/tesseract/` is supported by entering that absolute executable path.

## Prepare the preset

Prepare the army yourself in the game. In Presets, add ordered troop, hero, and spell steps. Each has a kind, slot number, target X/Y, count, and per-unit delay. Counts may be integers or `all` for troops/spells. Heroes require count 1; no manual ability taps are sent. Multiple steps may use a troop/spell slot to split targets; ensure every available unit is accounted for. For example: troop 1 count 5 → hero 1 count 1 → spell 1 count 2 → troop 1 all → spell 1 all.

For simple resource farming, enable **Dump all available units at the first step's corner (live)**. Only the first step's X/Y and delay are used. One unit is placed and verified first; the other available troop, hero and spell slots follow at that same point, then the remainder of the first stack is emptied. This prevents a large stack from delaying every spell until battle ends. Heroes deploy once, and unavailable slots are skipped. No star or victory requirement is imposed. Keep the complete slot inventory calibrated, even though you no longer need individual deployment steps. Simulation continues to use the listed steps because it has no real army inventory.

The tap interval measures dispatch-to-dispatch time within each troop/spell stack. After the checked first placement of a stack, the remaining units use cancellable timed bursts, then the final count is checked twice. Screenshot checks between stacks add a pause. Burst timing is logged so slow ADB dispatches remain visible. Pause/Stop prevents subsequent pending taps; an uncertain input or final count stops the run without retrying the burst. This replaces screenshot checks before every individual unit, as approved for 0.5-second deployment.

Enable **Find clear deployment ground from the boundary (live dump mode)** to locate a visible placement boundary and check clear ground outside it. Preparation permits at most three checked camera pans; an unknown boundary or obstructed point stops deployment. The first placement must consume exactly one unit before the dump continues. Maximum zoom-out alone does not establish camera position. With this option off, the first step's point must already be verified for the current battle view.

A candidate with no verified placement point after those pans is skipped before deployment, within the same search limit. Unknown screens and uncertain gestures still stop the run; they never trigger another search input automatically. Expired scouting also blocks Next. If no supported candidate is found, the run returns Home without deployment.

Live navigation uses Home → Battle menu → regular **Find a Match** → army confirmation → opponent preview. Calibrate `matchmaking.regular` on the regular Battle card's distinctive label and `matchmaking.find_regular` tightly around that card's Find a Match button. Never use the Ranked Battle card, Sign Up, or its attack button. The regular-card anchor is rechecked immediately before matchmaking input; old generic find-button calibration does not satisfy these requirements.

Set resource minimums, search cap, attack/duration limits, wall currency/reserves, and upgrade cap. Wall upgrades default off. Mark collector/wall points before enabling tasks that require them.

## Build a profile

Choose a Town Hall template in Presets to suggest troop-type, hero, spell-type, and siege slots. TH1–7 shares a generic starter; TH8+ offers Valkyries or Valkyries plus wall breakers. Suggestions are editable and do not change your army in game. Changing Town Hall resets deployment delays to 0.5 seconds but preserves connection, calibration, filters, mode and session limits. Existing profiles remain unchanged. Heroes under upgrade can require a different complete calibrated layout.

Choose Auto farm to leave walls off, or Auto farm + wall upgrades for the Build-menu workflow. Set the currency, resource reserve and session upgrade cap before live use. Collection and standalone tasks remain in Advanced tasks. Loading Default resets to the safe one-attack starter and clears the profile reference; the application never starts farming automatically.

1. Open Calibration and name the profile. Freeze the Home Village screenshot. Dimensions come from the capture; new slot inventory uses Town Hall suggestions when selected, otherwise deployment slots. A suggested siege is represented as a single-use troop slot after the regular troop types. Adjust suggestions to the actual visible inventory before validating; an existing profile is never rewritten by selecting a Town Hall.
2. Select a required region, then click two opposite corners on the frozen image or enter exact bounds. Record selected region. Choose distinctive screen anchors, tightly cropped action buttons, or full OCR numbers according to the region name and in-app guide.
3. Freeze a **new** screenshot, select that region again, and Test on second capture. Templates must pass their displayed threshold (default 0.90); OCR must agree with its reference crop. Inspect the highlighted crop and the reported reading. Recording a replacement removes its validation.
4. Manually visit army, matchmaking, base preview, battle, results, selected-wall, and upgrade-confirmation screens. Capture and validate the required regions on each screen. Required regions are listed from the enabled tasks and slot inventory; wall regions appear when wall upgrades are enabled.
5. Calibrate each troop/spell/hero slot's ready and unavailable appearance, plus battle depleted/deployed appearance. Use identical pixel bounds for every state of a given slot. Count crops must contain the full number with margins. A complete × prefix is supported by a locally calibrated multiplier template; clipped glyphs are rejected. Hero state crops must distinguish ready portraits from deployed/ability portraits. A siege slot can use `single: true` for its implicit count of one.
6. For each slot, record its `.area` rectangle around the full slot, including border, counts, and hero health bar; the state templates remain smaller portrait-only crops. Roster guards cover the entire visible inventory strip, including empty space. Full known slot areas are masked; a new entry outside them causes a mismatch. Include every slot in the JSON inventory editor before validating roster guards. All slots must fit on screen: scrolling army bars are unsupported. Revalidate guards after changing slots.
7. Mark collector and wall points on the frozen home screenshot using Mark on image. Clicking calibration never sends Android input. Keep the same camera position and village layout; the home.camera anchor must be fixed scenery that moves with the camera, not a HUD button.
8. Save profile, then save the preset. The preset stores its profile reference, OCR path, points, and deployment sequence. A profile can be saved while incomplete, but live start lists the missing regions and stays blocked.

OCR accepts full unsigned integers with optional thousands separators, not K/M abbreviations. Uncertain or disagreeing readings pause the runner; they never become zero. Selected-wall name must read `Wall` or `Wall (Level N)`; crop its separate level region to the integer only. Currency templates must identify the configured resource, never gems. Configure confirmation wallet and cost crops so they remain visible on that screen.

## Verify progressively

Known changes to the deployment bar can use separate complete inventory profiles. The primary profile's optional `inventory_profiles` JSON list names additional saved profiles, for example `["queen-unavailable"]`. References cannot nest. Startup accepts only complete profiles; immediately before deployment the runner requires exactly one matching screen, roster, and set of slot states. It uses that profile's own coordinates and available units. Unknown or ambiguous layouts stop deployment. Returning heroes require their corresponding complete layout; missing heroes are never inferred from a failed portrait match.

Slot `.area` regions define roster-mask geometry. Second-capture validation checks that each area contains its state regions and a recognized slot state; the animated scenery under the translucent card is not an identity template.

A siege with `single: true` needs a deployed template identifying its release marker. Its colored card remains visible while alive; the marker's bright shape distinguishes it from the ready card despite its pulsing color. The deployed state consumes the implicit unit without tapping the release control. Use identical ready/deployed bounds and validate independently. Once consumption is verified, later card changes are not read again.

For walls, **Select walls through the Build menu** uses Home → Build → Wall entry → close Build → the selected wall's upgrade controls. This avoids village coordinates and camera alignment for wall selection. Calibrate `home.build`, `build`, `build.wall`, `build_wall`, and `build_wall.close`. The wall entry must remain at its calibrated menu position; a reordered or scrolled menu pauses rather than selecting an unchecked row. Gold/elixir choice is verified on the wall controls, independently of the currency displayed in the menu. Collector coordinates still require their calibrated home view.

Maximum zoom-out fixes scale, not camera position. Build automatically pans and zooms to the selected wall, so wall mode uses that checked navigation instead of assuming zoom alone restores alignment.

For this release, keep collection and walls disabled and supervise one complete attack first. The saved local preset uses minimums of 200,000 gold and 150,000 elixir, dark-elixir filtering off, a ten-base search cap, and a one-attack limit. Increase to repeated verification only after one complete production attack succeeds. Wall spending tests require a separate explicit bounded budget; retain the 500,000-gold reserve.

Results can have two or three resource rows. Each `result_layouts` entry specifies its positively recognized anchor and resource rows; only a recognized layout permits an omitted resource to become zero. Calibrate full right-aligned numbers, including room for larger totals. The optional known Star Bonus popup has its own validated anchor and close target. Other overlays pause safely.

Home is always the starting screen. Do not manually play while live farming runs. Pause/Stop prevent subsequent commands, but cannot undo a command already delivered. Resume rechecks screen and availability; an uncertain deployment/spending outcome locks resume and requires Stop plus manual inspection. Navigation outcomes are not blindly replayed. Stopping can leave an active battle or dialog in progress.

The active session owns a snapshot of settings and calibration. Restarting the application starts idle. Active-duration expiration waits for the current battle's natural end and return home; deployment continues to finish the ordered army, and no new battle is started. A separate battle timeout pauses if results never appear.

Diagnostic images are local and limited to the newest 20. Fixed screen profiles need recalibration after layout, resolution, camera, or game UI changes. The current implementation uses explicit slots and screen templates, not general base understanding or tactical spell placement.
