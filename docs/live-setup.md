# Set up live farming

Simulation is independent of this setup. Live farming requires your actual screens; the code does not contain guessed Clash of Clans button positions or old game templates.

## Connect and install OCR

Open Emulator, enter the explicit ADB executable and loopback address, and connect. This machine was verified with `C:\Program Files\BlueStacks_polar\HD-Adb.exe`, `127.0.0.1:6610`, and 1280 × 720 screenshots. Your instance must be running and logged into the game; inactivity dialogs are not valid home screens.

Install Tesseract 5 and English training data using the Windows build linked from [Tesseract's installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html). Enter its full executable path in Calibration and use **Check OCR installation**. `pytesseract` is the Python wrapper, not the OCR engine. An installation under `local/tesseract/` is supported by entering that absolute executable path.

## Prepare the preset

Prepare the army yourself in the game. In Presets, add ordered troop, hero, and spell steps. Each has a kind, slot number, target X/Y, count, and per-unit delay. Counts may be integers or `all` for troops/spells. Heroes require count 1; no manual ability taps are sent. Multiple steps may use a troop/spell slot to split targets; ensure every available unit is accounted for. For example: troop 1 count 5 → hero 1 count 1 → spell 1 count 2 → troop 1 all → spell 1 all.

Set resource minimums, search cap, attack/duration limits, wall currency/reserves, and upgrade cap. Wall upgrades default off. Mark collector/wall points before enabling tasks that require them.

## Build a profile

1. Open Calibration and name the profile. Freeze the Home Village screenshot. Dimensions and initial slot inventory come from the capture and deployment preset.
2. Select a required region, then click two opposite corners on the frozen image or enter exact bounds. Record selected region. Choose distinctive screen anchors, tightly cropped action buttons, or full OCR numbers according to the region name and in-app guide.
3. Freeze a **new** screenshot, select that region again, and Test on second capture. Templates must pass their displayed threshold (default 0.90); OCR must agree with its reference crop. Inspect the highlighted crop and the reported reading. Recording a replacement removes its validation.
4. Manually visit army, matchmaking, base preview, battle, results, selected-wall, and upgrade-confirmation screens. Capture and validate the required regions on each screen. Required regions are listed from the enabled tasks and slot inventory; wall regions appear when wall upgrades are enabled.
5. Calibrate each troop/spell/hero slot's ready and unavailable appearance, plus battle depleted/deployed appearance. Use identical pixel bounds for every state of a given slot. Numeric count crops must exclude × icons; hero state crops must distinguish ready portraits from deployed/ability portraits.
6. For each slot, record its `.area` rectangle around the full slot, including border, counts, and hero health bar; the state templates remain smaller portrait-only crops. Roster guards cover the entire visible inventory strip, including empty space. Full known slot areas are masked; a new entry outside them causes a mismatch. Include every slot in the JSON inventory editor before validating roster guards. All slots must fit on screen: scrolling army bars are unsupported. Revalidate guards after changing slots.
7. Mark collector and wall points on the frozen home screenshot using Mark on image. Clicking calibration never sends Android input. Keep the same camera position and village layout; the home.camera anchor must be fixed scenery that moves with the camera, not a HUD button.
8. Save profile, then save the preset. The preset stores its profile reference, OCR path, points, and deployment sequence. A profile can be saved while incomplete, but live start lists the missing regions and stays blocked.

OCR accepts full unsigned integers with optional thousands separators, not K/M abbreviations. Uncertain or disagreeing readings pause the runner; they never become zero. Selected-wall name must read `Wall` or `Wall (Level N)`; crop its separate level region to the integer only. Currency templates must identify the configured resource, never gems. Configure confirmation wallet and cost crops so they remain visible on that screen.

## Verify progressively

Start with attacks and walls disabled and one marked collector. Calibrate the three home wallet-number crops. Collection is counted only after a resource increases and the home/camera checks remain valid. A selected-building menu, changed camera, or no measured gain pauses rather than counting success. Then calibrate and supervise one complete attack using troops, heroes, and spells. Finally enable walls with an upgrade limit of one and supervise its actual cost, reserve, level increase, and post-upgrade balance.

Home is always the starting screen. Do not manually play while live farming runs. Pause/Stop prevent subsequent commands, but cannot undo a command already delivered. Resume rechecks screen and availability; an uncertain deployment/spending outcome locks resume and requires Stop plus manual inspection. Navigation outcomes are not blindly replayed. Stopping can leave an active battle or dialog in progress.

The active session owns a snapshot of settings and calibration. Restarting the application starts idle. Active-duration expiration waits for the current battle's natural end and return home; deployment continues to finish the ordered army, and no new battle is started. A separate battle timeout pauses if results never appear.

Diagnostic images are local and limited to the newest 20. Fixed screen profiles need recalibration after layout, resolution, camera, or game UI changes. The current implementation uses explicit slots and screen templates, not general base understanding or tactical spell placement.
