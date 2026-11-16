# Boaz auto-farming handoff

Updated 2026-11-16. Read this before continuing.

## Latest checkpoint — follow-up consumed; result recovery incomplete

This checkpoint supersedes the historical run states and budgets below. The user requested committing and pushing the current implementation, including its known live limitations.

- The approved additional **one farm-only attack has been used**. It ran through Advanced → Start custom live session with collection off, walls off, continuous mode off, one attack and `spend_limit=0`. **No further attacks or wall purchases are authorized for acceptance testing.** The prior combined run's 750,000-elixir wall allowance remains fully consumed.
- At **17:17:57 Singapore on 2026-11-16**, production verified consumption of **35 Valkyries, one siege, Warden, five Rage and one Freeze**, with positively identified Queen/King explicitly skipped. Observed burst intervals: Valkyries **0.500–0.516s**, Rage **0.500s**. Evidence: `local/followup-consumed-ui.yml`, `local/followup-consumption-preview.png`.
- Search now skips a candidate whose placement boundary/clear ground remains unavailable after bounded checked pans, before any deployment and within the existing search cap. Unknown screens and uncertain gestures still stop. The exact failed capture is `tests/fixtures/placement-hidden-boundary.png`; the skip path passed live before deployment on the third searched candidate.
- A capture timeout at **17:20:15** disconnected the app after consumption. A read-only probe later showed Victory with **35,392 gold / 605,488 elixir / 6,107 dark** displayed, plus a separate bonus. These are independently observed display values, **not production-verified stable loot**. `local/followup-results-observed.png` preserves the screen.
- Result recovery remains incomplete: this result uses **Claim Reward**, while the validated result-screen/action templates expect the older button appearance. The result-only helper stopped on an unknown screen and sent no reward/navigation input. A second independent capture could not be obtained because ADB screenshot requests timed out again. **No Claim Reward variant was installed or validated; final Home is unverified.** Computer Use was then stopped by the user, and no further computer input was sent.
- Resume now explicitly reconnects only the paused session's saved emulator when disconnected. Reconnection itself sends no gameplay input and does not resume automatically; uncertain input outcomes remain non-resumable. This fix is automated-tested, **not live-verified**; the still-running dashboard process predates that final reconnect fix and needs restarting before use.
- Latest full suite: **202 passed**, thirteen upstream Airtest deprecation warnings, 44.18s. Full unattended wall completion and the uninterrupted post-wall follow-up gate remain unproven. Recover and independently calibrate the exact result appearance before claiming this account ready; do not start another attack or spend more walls under the exhausted test allowance.

## Resume at 16:45 Singapore — combined run PASSED; follow-up awaiting emulator

The paused tool session's normal-button combined test actually completed at **12:17:48**. Its preserved UI journal proves:

- Full planned consumption at 12:14:10: **35 Valkyries, one siege, Warden, five Rage and one Freeze**. Queen and King were positively identified and skipped.
- Stable battle loot **386,524 gold / 428,086 elixir / 1,061 dark**; returned Home.
- ONE observed wall upgrade **12 → 13 for exactly 750,000 elixir**, including level increase and exact wallet decrement above reserve checks. Fresh same-account export confirmed **227 remaining** at 12:17:48; session ended at its one-attack cap, Home. This consumes the entire agent's 750,000 acceptance wall allowance. **NO further wall spending for testing.** Evidence `local/oneclick-combined-passed-ui.yml` records this run; final preview was captured later and must not be treated as its original wallet screenshot.
- Updated-preview live intervals: Rage **0.500–0.531s**, Valkyries **0.500–0.703s**. The requested scheduling interval is 0.5s; observed ADB/OS stalls can be longer. Earlier old-preview run's 2.094s outlier is historical.

On resume, a separate normal-port 8080 session from 13:17 was paused at wall OCR. It was stopped without retrying its purchase/navigation. Its exact capture (`20261116-132334-510240.png`) shows level 13: the old numeric crop clipped the left of `1`. The shared reader now pads the calibrated level crop by four pixels left and one right, with a real 12/13 regression. Do not infer that this paused session spent nothing merely because its verified-upgrade counter was zero. A fresh export on resume shows **TH12, 224 level-12 segments remaining**; account changes since the agent's 227 proof are separate from the bounded acceptance run. New purchase journal entries explicitly report attempted cost/wallet-before and verified wallet-after. Numeric errors now name their field.

The user explicitly approved **“Yes, one farm-only attack”** after the combined pass. That follow-up has NOT started: ADB `get-state` works but `exec-out screencap -p` times out after eight seconds, both in the app and standalone read-only probe. An asynchronous request asks the user to restore/restart BlueStacks at **127.0.0.1:6610** with the game Home. Do not spend more walls. The intended follow-up settings are **Auto farm, one attack, collection off, walls disabled, spend_limit=0** using **Advanced → Start custom live session** (the primary combined button enables walls). Confirm all four settings before Start; no gameplay was sent by the failed reconnect attempt.

Only the normal updated server remains at **http://127.0.0.1:8080**; old completed test server on 8081 was closed after evidence preservation, and the paused older normal process was stopped/replaced. `Start Boaz.cmd` now reuses the current normal server. Latest full suite: **193 passed**, thirteen Airtest deprecation warnings, 17.70s; diff whitespace check passed. Final task: complete the separately approved zero-wall-spending follow-up if the emulator recovers, save final Home and results, refresh README/setup/progress with exact passed gates and limits, then leave the app idle.

## Acceptance resumed — additional approval received

Progress after that approval: the first additional attack completed with all planned units consumed and Queen/King skipped. Stable loot **648,491 gold / 527,340 elixir / 7,688 dark**. It paused BEFORE spending because the Build selected-wall anchor included bright stones behind its caption. Exact regression `wall-selected-changing-scenery.png`; matching the dark text outline fixes that shared source without lowering the threshold. Selected wall was independently verified still level 12 and returned Home without spending. The second approved deploying attack remains UNUSED; a later candidate was rejected before any deployment because it used unsupported dark scenery and was returned Home with zero loot. Unsupported non-grass scenery is now filtered before placement, using ordinary checked Next within the search cap.

The final approved deploying attack is now starting fresh through primary Start, bounded to **ONE attack, ONE upgrade, 750,000 total**. The new preview reuses the live runner's verified frames, avoiding ADB captures that competed with timed burst taps. The previous successful attack's old-preview intervals were 0.500–2.094 seconds, so it does not establish the corrected application's live cadence. Current suite **192 passed**, thirteen upstream warnings, 32.52 seconds; diff check passed. Evidence `local/oneclick-consumption-preview-1.png` visibly shows exhausted troops/spells and skipped Queen/King; its UI journal is saved in `oneclick-consumption-ui.yml` and `oneclick-stopped-before-wall-ui.yml`. Still no wall spending under this allowance.

The user answered **“Yes, run two more attacks”** to the explicit request for two additional normal-button attacks with one wall maximum, the existing **750,000 TOTAL wall ceiling** and both 500,000 reserves. This approval supersedes the stop instruction in the next checkpoint. The bounded two-attack run is starting at http://127.0.0.1:8081 through the primary button. Spending before this run is ZERO. Do not add further attacks or wall spending beyond this additional allowance. Keep observing the current runner rather than launching another against the same emulator.

## Prior checkpoint — 2026-11-16 11:42 Singapore

**STOPPED / HOME / no live runner active. All three deploying attack attempts under the latest approved plan have been used. Wall spending is still ZERO.** An asynchronous request asks the user for two additional attacks while retaining the existing 750,000 total wall ceiling and both 500,000 reserves. Do not start another attack until that new approval arrives. The dashboard is idle at http://127.0.0.1:8081 and restores continuous combined defaults; any acceptance run must explicitly set bounded limits in Advanced before Start.

- Latest full suite: **190 passed**, thirteen upstream Airtest deprecation warnings, 24.57 seconds. `git -c core.whitespace=cr-at-eol -c core.safecrlf=false diff --check` passed.
- Latest primary-button attempts: first stopped after one Valkyrie/siege on the siege flash (6,594 gold / 249,975 elixir / 370 dark); second passed normalized placement and stopped on Warden's deployment flash (11,598 gold / 38,408 elixir / zero dark); third passed siege but paused on the selected Warden ready guard BEFORE its field placement (zero gold / 3,259 elixir / zero dark). These are interrupted attempts, not complete planned-consumption acceptance. All were observed back Home; no wall purchase was sent. One additional search candidate expired with zero units/loot while investigating its missing boundary; it did not consume a deploying attempt.
- Shared fixes now include: two-second READ-ONLY settling windows for keyed battle inventory and hero pre-input guards; selected-ready Warden library variant independently validated against the third attempt's initial and later captures; existing selected-deployed Warden variants retained. Once a portrait/placement is dispatched, uncertain input is still never retried. New tests assert settling does not send a second portrait or placement. The selected-ready state travels with the hero library across card positions.
- The wall Confirm target now uses the Confirm label alone. Price and currency remain separate mandatory checks. This fixed a preflight-discovered gold-specific button crop that would reject elixir. Both real 750,000 offers and elixir confirmation now have regression fixtures.
- `local/oneclick-third-results-stable.png` is the third actual result screen. `oneclick-third-interrupted-results.png` is the independent selected-ready Warden BATTLE capture despite its old helper filename; it proves no Warden placement at that point. `tests/fixtures/warden-selected-ready.png` is the exact failing pre-input guard, and `warden-deployment-flash.png` the prior deployed flash. Do not confuse selected-ready with deployed.
- Updated app UI has editable custom composition JSON under Advanced, accurate continuous/bounded summary and reserves, real unit/hero icons, and preserved legacy presets/calibrations. New calibration profiles initialize preparation metadata from the displayed composition; existing profiles remain untouched. Fresh launch restored the account and all eight visible icons loaded, reconnected and stayed idle with no gameplay input.

Still required before calling this account's one-button workflow ready: uninterrupted full planned consumption → stable loot → one verified wall upgrade within 750,000 → next complete attack → Home. Final-wall stopping is covered by export fixtures, not a live maxed village. Other compositions, resolutions, languages and unsupported scenery still require their own validated recognition. The user has been asked to authorize the additional two attacks needed for this remaining gate.

## One-button workflow — earlier checkpoint (supersedes historical budgets below)

The user approved a new acceptance run of at most **three attacks and one wall purchase, at most 750,000 total gold/elixir**, retaining both 500,000 reserves. One interrupted attack has been used, no wall purchase yet. The fresh normal-button run now has a TWO-attack cap, one upgrade and a 750,000 ceiling. Do not add extra attacks or purchases beyond this allowance.

- Farming is the landing screen. Town Hall/account confirmation, real unit and unlocked-hero artwork, recommendation quantities and the primary combined Start button are implemented. Presets, simulation, emulator and calibration remain in Advanced. Remembered account settings restore and reconnect while gameplay stays idle.
- Fresh in-game export navigation and clipboard validation have passed live, including the player panel remembering its last tab. The active account is **#QGYJ0VQQ0, TH12**, with 280 troop housing and 11 spell housing. Export observed **228 level-12 and 72 level-13 walls**. The recommendation is 35 Valkyries, five Rage, one Freeze and one unlocked Stone Slammer. Hero availability/equipment is checked on the actual screen; unlocked heroes in the banner are not a claim that all are equipped or deployable.
- Production preparation code restored and verified 35 Valkyries, five Rage/one Freeze and one Stone Slammer through direct army controls with capacity checks around every tap. No saved recipes were overwritten. Preparation currently requires a calibrated composition/appearance; the packaged layout covers this account's composition. TH7–18 recommendations are generated from actual unlocks/camps, but other compositions still need recognition calibration.
- Packaged English 1280×720 recognition profiles/templates/font install only missing assets; existing local calibrations are preserved. `local/accounts/` remembers confirmed setup and the last village snapshot. Actual export freshness and identity are rechecked at Start.
- Normal Start restored the account, freshly verified the export and exact army, found a qualifying base, skipped identified unsupported Queen/King, placed one Valkyrie and the siege. It paused on the selected siege marker's bright flash; no further placements were sent. Its result observer returned Home with **6,594 gold / 249,975 elixir / 370 dark**. Evidence `local/oneclick-interrupted-results.png`, exact failure `tests/fixtures/siege-selected-flash.png`.
- The shared marker matcher now normalizes both ordinary and bright-flash intensity masks, including variants. The exact failed capture and prior ready/deployed negatives pass. Latest full suite: **180 passed**, twelve upstream Airtest warnings, 18.53 seconds. The renewed run must still establish complete planned consumption and combined wall flow.
- Selected wall offers and both currencies were independently calibrated at 750,000. No purchase during calibration. Wall deselection uses a verified clear-grass point, avoiding camera-specific blank coordinates. Android Back was tested and rejected: it opens Exit and Cancel restores selection. No Back or exit-accept input is used by production.
- UI desktop/mobile smoke checks passed idle, remembered account setup, Advanced navigation and no mobile horizontal overflow. Real Start's bounded limit controls were verified. Design detector's only warning was inherited Roboto, retained to preserve the existing interface.

The remaining live acceptance is running through the normal UI at **http://127.0.0.1:8081** (fresh test server). Observe it; do not launch another runner against the same emulator. Record actual deployments/skips, stable loot, purchase level/wallet changes and final Home before claiming readiness. The saved account defaults remain continuous combined mode; the current page alone uses bounded acceptance limits. Other resolutions/languages/sceneries and uncalibrated army appearances remain compatibility limits.

Camera follow-up: a qualifying candidate paused before any placement because its inherited zoom hid the boundary. Selecting a troop did not reveal an edge. That zero-deployment candidate timed out, yielded zero loot, and was returned Home. Home normalization now uses Airtest's existing minitouch backend with synchronized two-contact commits (the stock sequential commits drifted). Standard bounded ADB push fixes the upstream extensionless-binary installer bug. Pinch attempts run only on verified Home before matchmaking, require settled Home geometry, and stop after five attempts. Cancellation always releases both contacts. Independent zoom captures confirmed the minimum view; live placement after normalization remains under verification. Latest full suite: **186 passed**, thirteen upstream Airtest warnings, 25.15 seconds. Regression coverage includes failed/cancelled preparation without replay, bounded camera normalization, synchronized-contact cancellation and the exact siege flash.

## Current work supersedes older checkpoints

- Deployment cadence update: user explicitly approved timed bursts with stack checks before/after instead of per-unit screenshot checks. `DeploymentStep.delay` now sets tap-to-tap intervals within a stack; screenshot verification adds time between stacks. Heroes retain once-only input. Pause/Stop cancels pending burst taps; failed final consumption locks further deployment.
- On-device cadence proof: `local/verify_cadence.py` verified 34 remaining Valkyries before/after a burst, including 33 additional taps with observed dispatch intervals **0.500–0.515 seconds**. Evidence `local/cadence-events.json` and `cadence-consumed.png`. The production test before this stopped on an unrelated siege-state mismatch; the cadence helper continued only the positively recognized remaining troop stack and never retried siege/hero inputs. Full army acceptance for the burst path is not established by this targeted measurement.
- Latest timing suite: **173 passed**, twelve upstream Airtest warnings, 14.84 seconds. Tests cover 0.5-second cadence with input overhead, cancellation before the next tap, and refusal to continue to another stack after failed consumption. The existing 750,000 wall-testing allowance remains fully consumed.
- Cadence observer finished and explicitly reported **Cadence verification returned Home**. No cadence verification process remains running.
- **Final resumed state (2026-11-15): HOME confirmed by recognition on `local/resumed-final-home.png`. No acceptance process remains running.** Latest follow-up stopped before deployment because the boundary remained unclear after the allowed pans; checked End Battle returned Home. `local/accept-farm.json/.png` (or `accept-farm-last.png`) now represent that latest failed follow-up, not the earlier successful attack. Its successful consumption summary is retained in `local/verified-consumption-summary.json`, and `full-consumption-late.png` shows the independently observed empty army before battle end. Results images can also be overwritten by later runs; inspect their matching run before attribution.
- Final suite: **170 passed**, twelve upstream Airtest warnings, 18.68 seconds; `git diff --check` passed. Scouting now reads only resources with nonzero filters, while all result loot retains stable-read checks. Selected card count crops can search at most two pixels within their calibrated card, accepting only a unique value across successful complete-glyph reads.
- Verified this session: a full farm attack with planned consumption and explicit Queen/King skips; another full planned-consumption attack; one separately resumed level-12→13 wall purchase for exactly 750,000 gold. Still unverified: uninterrupted attack→wall→next-attack session, a completed post-purchase follow-up attack, live village-export navigation/clipboard synchronization, and final-wall continuous stopping. Unsupported placement scenery remains a safe-stop case. Do not call the application fully operational for unattended wall completion.
- **NEW 750,000 acceptance wall allowance CONSUMED.** `local/resumed-combined.json` records a production `_walls` upgrade at 19:33:00: level 12 → 13, exactly 750,000 gold, with the level and wallet decrement checked. No additional wall spending is authorized for testing. The preceding combined attack consumed the planned army and returned Home with 286,409 gold / 481,942 elixir / 5,856 dark. Build-menu selection paused on an outdated selected-wall anchor, which was independently recalibrated before resuming the wall phase.
- The resumed helper's follow-up search incorrectly loaded only `queen-unavailable`, omitting the full hero library, and stopped before deployment. It was returned Home and a farm-only follow-up using `my-village` was launched with walls disabled. The helper source now loads `cfg.live.profile`, but DO NOT rerun it: its budget guard correctly refuses after the recorded purchase. This is a resumed attack/wall/follow-up sequence, not an uninterrupted session proof.
- **Fresh production farm-only acceptance PASSED on 2026-11-15.** `local/accept-farm.json` records one completed attack, all 35 Valkyries, siege, Warden, five Rage and Freeze consumed; Queen/King explicitly skipped. Production event `Verified consumption of planned units; skipped hero.2, hero.3` occurred before battle end. Independent `full-consumption-late.png` shows zero troop/spell cards with 43 seconds left. Stable loot: **1,556,444 gold / 451,158 elixir / 6,200 dark**. Production returned Home and ended at the one-attack limit. Results evidence: `accept-farm-results-1.png`. This proves planned consumption with skipped heroes, not every available hero.
- Warden selected-state fix: hero portraits now use the same calibrated scale search as troops/spells. Added optional validated image variants to template assets and independently captured selected-deployed Warden states. Composition retains the richer deployed template when older geometry profiles also recognize the same hero. Ready and deployed remain distinct in real-image regressions. `warden-selected-three-heroes.png`, `warden-selected-deployed.png`, and `warden-selected-deployed-second.png` cover this.
- Latest suite after Warden fixes: **169 passed**, twelve upstream Airtest warnings, 14.62 seconds; `git diff --check` passed. Fresh end-to-end live verification is still pending. Several supervised failed attacks consumed one Valkyrie, siege and/or Warden before safe post-check pauses; their result observers returned Home. None establish full army consumption. No wall purchase has been sent.
- Resume on 2026-11-15: emulator reconnected at the original serial after the user opened BlueStacks. Three heroes now visible: Warden, Queen and King. A seven-card empty-strip reference was independently captured in `three-hero-geometry`; recognition reads the Warden ready and skips Queen/King pending deployed-state validation. The added `three-hero-preview.png` regression passes. This still uses calibrated empty-strip references and portrait templates, so arbitrary skins and army types remain unsupported until identified.
- A live first placement at (154,369) did NOT decrement troop count. No retry was sent. The failure frame showed a bright inner wall mistaken for the outer deployment boundary. Added a dim-boundary veto and `placement-inner-wall.png` regression. The battle ended at zero loot and the observer confirmed Home. Fresh verification after this change is pending.
- Latest automated result: **168 passed**, twelve upstream Airtest warnings, 16.22 seconds. Additional tests cover post-purchase export distribution confirmation, gold/elixir selection, tie-breaking, reserve boundaries, and simulation refusal for the live-only completion mode. A failed new test initially omitted Build-menu settings and was corrected to use the actual continuous-mode configuration.
- The user approved implementing card-relative hero recognition and continuous farming until walls are maxed. Unknown cards still stop. Positively identified heroes with incomplete deployed calibration are skipped and logged. Existing complete hero states retain the once-only deployment guard.
- The user approved a NEW bounded combined acceptance test: attack → ONE wall purchase → next attack, with a TOTAL 750,000 gold-or-elixir ceiling and 500,000 reserves. No purchase has been sent under this approval yet. The older consumed wall approval below is historical.
- Card-library replay covers Queen, King, Warden, two heroes, and no heroes. Selected troop 34 and Freeze 1 crops have new real-image corrections. Current Home Battle label was independently revalidated after its full-button appearance changed.
- Continuous-mode code, fresh-export validation, moving Build-menu row selection, currency choice, reserves and the confirmation-time spending ceiling are implemented but live completion and export calibration remain pending. Required new settings/export controls, builder marker and elixir controls are not yet calibrated on this account. Windows clipboard synchronization of the in-game export is also unverified. Do not claim continuous wall completion operational.
- Last full suite before resume: 160 passed. Additional resumed tests cover continuous currency choice, ties and reserves. Latest results are recorded as work proceeds.
- The current accepted run helper is `local/accept_card_farm.py farm` or `combined`. Combined enforces `spend_limit=750000` and one upgrade, with two attacks. Never clear that ceiling during this acceptance test. Saved normal presets keep walls off.

## Latest feature implementation and resume point

- Implemented Auto farm / Auto farm + wall upgrades, shared TH1–7 and individual TH8–18 templates, Valkyrie / Valkyrie + wall-breaker variants, and editable army-slot suggestions. Suggestions initialize only NEW profiles; existing calibration assets/layouts are untouched. Actual availability/counts still come from calibrated recognition.
- Default and startup now use collection/walls OFF, dump_all/auto_corner ON, 0.5-second delay, one attack, fifteen minutes, blank live profile. Town Hall changes replace suggestions and reset deployment delays only. Other saved presets retain explicit delays; local `my-farm` was updated to 0.5 seconds.
- One authorized production attempt at the new delay STOPPED BEFORE DEPLOYMENT: `Expected exactly one validated army layout; found 0`. Archer Queen is now available, creating a five-slot bar: 35 Valkyries, siege, Queen, five Rage, Freeze. The existing five-slot profile represents Warden, not Queen. Do not substitute or relax the layout gate. Zero deployments, completed attacks, or wall upgrades.
- Used the recognized End Battle control without deployment, then captured `local/after-preset-verification.png`, visually confirming HOME. No live verification process remains running.
- Next live step: complete/validate a separate Queen-available layout, then rerun ONE production attack at 0.5 seconds. The full-consumption gate still has not passed. Repeated sessions and all new wall spending remain out of scope for this milestone.
- New failed-attempt evidence: `local/verified-attack.json/.png`. Previous screenshots were copied into `local/evidence-before-05s/` before this attempt entered deployment/results (it never did). The copied `verified-attack` files may represent the new stopped attempt; prior `production-*.png` remain historical evidence.
- An older dashboard already occupied port 8080; UI smoke verification uses a separate temporary port 8081 server. Restart the normal dashboard to pick up new code. Check final test/UI results below before relying on the older counts and army notes in this document.
- Final automated verification: **146 passed**, twelve upstream Airtest warnings, 10.60 seconds; `git diff --check` passed. Browser verification confirmed idle launch, TH13 suggestions (four heroes/two spell types/one siege), two-troop variant, combined-mode wall enable/Build-menu selection, farm-only wall disable, advanced task selection, and restoration of Default (0.5 seconds/one attack/blank profile). No browser console errors. The temporary port 8081 smoke server was stopped afterward; the older port 8080 server was left alone.

## Immediate state

- Workspace: `C:\Users\admin\OneDrive\Documents\Programming\project_farmer`.
- The last calibration observation helper finished and explicitly reported **Calibration battle returned home**. No tool-launched live verification remains running.
- Latest complete automated run: **115 passed**, twelve upstream Airtest `tostring()` deprecation warnings, 7.94 seconds.
- Three separate production `LiveRunner` attacks have completed, read loot, and returned home without intervention. **A full all-slot-consumption gate is still unproven.** Those are separate one-attack sessions, not a verified repeated session.
- The latest correction fixes the selected Freeze count crop. It passes two independent real-image captures and the full suite, but **has not yet been exercised in a fresh complete live attack**.
- Keep collection and walls OFF. Keep the saved one-attack limit until the full-consumption gate passes.
- The checkout contains accumulated uncommitted changes from earlier chats and this chat. Preserve them. No commits were made.

## User's intended workflow and boundaries

Regular **Multiplayer Battle**, never Ranked Battle. Dump available troops, siege, heroes once, and all spells at one verified legal corner. Most troops are Valkyries. Resources matter; stars and winning do not. No tactical strategy, automatic army editing, gem spending, blind recovery from uncertain input, or indefinite unattended operation.

The agreed sequence is:

1. Valid saved attack preset and complete actionable readiness errors.
2. Actual ready/deployed/depleted inventory calibration, including changing hero availability.
3. Regular matchmaking, loot filtering, Next, bounded searches and verified exits.
4. One production attack with first placement verified, all available inventory consumed, loot read and return home.
5. Three consecutive attacks in one production session, then a five-attack / fifteen-minute bounded session; verify stopping and failure cases.
6. Attack → Build-menu wall upgrade → next attack, under an explicit spending budget.
7. Save verified configuration, expose readiness in dashboard, fresh idle-launch check and accurate release limitations.

Tasks 1–3 have substantial implementation and live evidence. Task 4 remains at the full-consumption gate. Do not claim tasks 5–7 complete.

The earlier approval for ONE 750,000-gold wall upgrade was consumed in a prior chat. **No additional wall spending is authorized.** Combined wall testing needs a new explicit bounded budget. Preserve the 500,000-gold reserve.

## Instructions and environment

- Read `C:\Users\admin\.codex\RTK.md`: **prefix every shell command with `rtk`**. Use `rtk proxy ...` when needed.
- PowerShell, Windows, Python 3.11 virtual environment `.venv`.
- Ponytail full mode remains active: smallest complete changes; final response states skipped checks and material risks. No subagents unless the user or applicable instructions explicitly ask.
- User authorizes regular attacks and calibration/fixes. Do not repeatedly ask approval for those. Wall-spending restrictions are separate.
- ADB executable: `C:\Program Files\BlueStacks_polar\HD-Adb.exe`.
- Explicit serial: `127.0.0.1:6610`. Resolution: **1280 × 720**.
- Live ADB and asyncio tests need `sandbox_permissions: require_escalated`. The Windows asyncio loopback socket initialization hangs under sandbox networking restrictions. This was diagnosed with faulthandler; do not mistake it for a test regression.
- Run tests with:

  `rtk proxy .venv/Scripts/python.exe -m pytest -q`

  Request escalation with the loopback explanation. Wait for the command's final result before starting dependent live tests.
- Prefer the repository's ADB adapter and helpers. No browser, desktop UI, web research or new dependencies are needed for the immediate next test.
- **Do not use Maxtouch, Airtest pinch, or the old `maxpresent.jar` experiment.** It once left injected pointers down on Android 16 and broke tapping; the emulator was rebooted to restore input. That experiment was removed from shipped code. Maximum zoom-out is scale only, not camera alignment.

## Current preset and army

`local/presets/my-farm.json`:

- collection false; walls enabled false; dump_all true; auto_corner true;
- gold minimum 200,000; elixir minimum 150,000; dark minimum 0;
- search cap ten; attack limit ONE; duration fifteen minutes;
- stored deployment candidate (100, 400), delay 0.1. Auto-corner overrides the active session point only after visual boundary/ground checks;
- wall reserve 500,000 gold; Build-menu selection retained.

Current army: **35 Valkyries, one Stone Slammer/siege balloon, five Rage, one Freeze**. All heroes are upgrading, hence FOUR visible slots. The siege may be empty of Clan Castle troops; do not edit the army automatically or tap its release control.

Profiles:

- Primary: `local/profiles/my-village.json`.
- `inventory_profiles` references `queen-unavailable` (five slots, Grand Warden available) and `heroes-unavailable` (current four slots).
- Old six-slot primary layout remains incomplete and is excluded from ready candidates. Returning heroes need a complete corresponding layout; do not infer their availability from a failed match.
- Select exactly one complete matching layout; reject zero or ambiguous matches.

## Important implementation details

### `src/boaz/live.py`

- Uses real device, screenshot recognition and gated inputs; simulation is separate.
- Attack-only navigation no longer requires `home.camera`; collection and coordinate-wall selection retain it.
- Home → regular Battle card → Find a Match → army confirmation → opponent preview. The regular-card anchor is checked before input.
- Current inventory profile is selected before searching, so navigation uses the correct layout's controls.
- Next uses `_transition('base', 'base.next', 'base')`, not a one-second fixed sleep. Same-screen transitions require two settled recognized captures; a stale old-base frame followed by search clouds must not end the wait.
- `_deployment_started` resets at start/per attack and becomes true before the first placement attempt. If scouting expires, Next is blocked; calibrated `base.home` may exit the known battle only before deployment starts. Actual no-deployment End Battle returned directly home without a confirmation dialog.
- `_prepare_corner` detects boundary/clear grass, with at most three checked single-finger pans. An obstructed/unknown point pauses without deploying. It does not normalize zoom or blindly assume (100, 400).
- First unit placement must decrement by exactly one before anything else proceeds.
- **Latest dump order:** one verified unit from the first stack → other troop/siege slots → heroes once → spell slots → remaining first stack. All use the same point. This covers smaller slots before the bulk Valkyrie stack can strand spells at battle end. `_deployment_plan` inserts the first-unit step only for a nonhero stack larger than one.
- For the rest, each `_tap` freshly checks the battle screen, ready state and expected count immediately before placement. That capture verifies the preceding decrement too. Each slot's end gets a two-capture consumption check. Redundant two-capture postchecks after every unit were removed because they exhausted the battle timer.
- `_deployed` prevents repeated hero portrait/ability taps. `_spent` caches verified consumed slots, avoiding later rereads when a deployed unit dies or its card changes.
- Preserve `BattleFinished` through deployment checks. Natural battle end cancels remaining inputs and proceeds to observed results/home; it must not be wrapped as an uncertain input or retried. The event currently says `Battle finished; remaining deployment steps cancelled` even if battle ends during the final consumption check. That event alone does NOT prove every slot was consumed.
- `_await_results` observes battle/end animation, with bounded unknown-screen and battle timeouts; no blind recovery taps.
- Two matching result-loot readings are required, then Return Home. Only a calibrated known Star Bonus popup is acknowledged.
- Device lock + input event prevent further commands after pause/stop. Uncertain deployment/spending outcomes lock resume.

### `src/boaz/recognition.py`

- Fixed-resolution profiles, alternate inventories and complete readiness errors.
- Roster guards mask calibrated slot areas and compare bright empty-slot outlines. Thresholding now uses **150**, excluding more scenery under the translucent bar; a real bright-background fixture is accepted while an added unknown card is rejected.
- Slot-area validation checks geometry and known states, not animated enemy scenery.
- Selected troop/spell portraits enlarge; state matching searches a margin and calibrated scales 1, 1.04, 1.08, 1.12. Heroes use smaller search and no scaling. Color penalty still distinguishes gray unavailable portraits.
- **Siege state correction:** old siege `depleted` captures actually showed a LIVE deployed siege with its release arrow. A `single: true` slot now requires/uses one `deployed` state (implicit count becomes zero), not two competing states for pulse variants. Its bright arrow shape is normalized at 140 for matching; ready remains distinct. Legacy extra `.depleted` assets can remain unused. Once consumed, `_spent` avoids rereading the destroyed card.
- Results metadata identifies two-row (gold/elixir, omitted dark = zero) and three-row layouts by positive anchors. Unknown/ambiguous layouts fail; unreadable values do not become zero.
- Result numbers are wide right-aligned crops x=440, width=228; three rows y=319/367/415 and two rows y=342/394, height=28.
- Local `numeric-font` digit templates replace unreliable generic OCR for numbers. Tesseract remains configured for text/installation checks.
- `OCR.count` supports a positively calibrated full multiplication prefix; `OCR.number` does not. Clipped horizontal glyphs, ambiguous digits and meaningful punctuation/noise fail.
- A one-pixel top card border touching a crop edge can be ignored; do not broaden noise acceptance to accommodate bad crops.
- Added selected-digit 9 calibration at count 29. That exposed result-digit 5 ambiguity, fixed by an independently validated actual result sample. All retained numeric regressions pass.

### Latest calibration values (important)

- Full count labels originally used x = slot.area.x + 31, y=591, width=60, height=27.
- **Spell counts now y=592, height=26**, retaining complete digits while excluding the selected Rage corner.
- **Freeze (`spell.2`) count width now 56**, excluding its right selection corner without clipping the complete `1`. Both base and battle regions were updated in both alternate profiles and fixture profiles.
- The last failing live screenshot showed selected Freeze `×1`, 34 Valkyries remaining, Rage zero, siege spent. No Freeze placement was sent after that uncertain count reading. New full-crop reads pass on that screenshot and independent `freeze1-second.png`.
- Base elixir crop now x=64, y=132, width=140, height=21. A monochrome scenery had bright pixels above the older crop; two independent full-number captures now read 725,048.
- Auto-corner requires clear grass. Non-grass scenery or obstructed boundaries may safely pause. Do not claim general scenery support.

### Device/UI

`src/boaz/device.py`: explicit serial; eight-second ADB bounds; serialized screenshot/input; retry three entirely black captures then disconnect/clear stale state. Tap and single-finger swipe check the cancellation event inside the device lock.

`src/boaz/config.py`, dashboard and default JSON preserve existing fields/defaults, add `dump_all` and `auto_corner` (default false; auto_corner requires dump_all). The saved local preset enables both. Build-menu selection remains visible. Startup must stay idle and require explicit live start.

## Real-device evidence: what actually passed

### Search

Production two-base search smoke test completed and returned home without deployment/spending on walls. It read 188,731/229,919 and 413,143/407,728 gold/elixir, used Next once, respected the two-base test cap. Normal preset remains ten bases. See `local/verified-search.json` / `.png`.

### Completed production attacks (separate one-attack sessions)

1. **249,615 gold / 354,436 elixir / 3,343 dark**. Base reached 100%; final Freeze remained. Evidence `local/verified-attack-early-victory.json`. This proves end-to-end production navigation/results/home, not full consumption.
2. **580,534 gold / 634,640 elixir / 6,941 dark**. Reached Freeze step, ended during final verification; full consumption not independently captured. Evidence `local/verified-attack-freeze-step.json`.
3. **333,173 gold / 17,269 elixir / 199 dark**. Captured results explicitly showed 35 Valkyries, one siege and FOUR Rage expended; last Rage/Freeze remained. This motivated the new order. `local/production-results.png` still represents this completed run, not the later stopped calibration. Preserve it before overwriting.

These are NOT a three-attack continuous `LiveRunner` session. Several earlier attempts stopped safely on real issues now covered by regressions. Manual/supervised calibration dumps are not end-to-end production proof.

### Latest run, after changing order

It verified one Valkyrie, deployed siege and all five Rage, then stopped on selected Freeze count before dumping the remaining 34 Valkyries. Crop fixed afterward and two-capture regression passes. That calibration battle naturally ended at zero loot; `local/finish_calibration.py` read results twice and returned home. This is the **immediate resume point**: fresh one-attack production test with the fixed Freeze crop.

## Helpers and artifact cautions

Local helpers are ignored development tools; they are not shipped dashboard features.

- `local/verify_live.py attack`: production `runner.start(cfg)`; attack cap ONE; collection/walls off; auto-corner from preset. Monitor stops at pause and records events/result JSON. It now captures intermediate Rage counts, latest battle frame and results for independent inspection. Result print is ASCII JSON to avoid Windows console Unicode errors.
- `local/verify_live.py search`: unattainable loot threshold and cap TWO, no deployment; production search/exit smoke test.
- **Do not run `local/verify_live.py wall`** without a new explicit spending budget.
- `local/calibrate_live.py capture NAME`: read-only live capture to `local/NAME.png`, validates size/nonblack. The `tap` subcommand is raw; prefer production checked navigation instead.
- `local/finish_calibration.py`: observe existing battle → stable loot → checked Return Home, handles known bonus. NO deployment. At this handoff it has finished.
- `local/inspect_exit.py`: only recognizes base/battle End Battle, then captures resulting screen. Will fail safely on results/home. No need to run when already home.
- Latest successful correction scripts: `local/fix_freeze_count_width.py`, `local/fix_spell_count_top.py`, `local/fix_base_elixir_crop.py`, `local/save_result_five.py`, `local/calibrate_selected_nine.py`, `local/save_siege_deployed.py`.
- **Do not blindly rerun calibration scripts.** Some depend on `verified-attack.png` having the specific failing image from their creation; later verification overwrites it. Older profile creators (`save_no_heroes_layout.py`, `save_queen_away_layout.py`, `setup_result_layouts.py`, `update_count_labels.py`) can overwrite newer count/result/marker corrections.
- `local/verified-attack.json/.png` currently represent the last stopped Freeze calibration, NOT a successful completed attack. Actual device is home, despite that saved screenshot showing battle.
- `local/production-results.png`, `production-last-battle.png`, `production-rage-*.png` are overwritten by helpers. Copy meaningful evidence before another test.
- `local/four-slot-results.png` was overwritten by the latest zero-loot calibration result.
- Permanent regressions are under `tests/fixtures/` with corresponding profile/template/font files. They include ready/consumed layouts, selected troop counts, full/clipped prefixes, spell counts 4/3/2/1, independent Freeze 1, pulsing siege markers, bright roster background, result layouts and real numeric crops.

## Exact next steps

1. Read instructions and inspect current files without reverting changes. No need to repeat the 115-test suite unless new code/calibration changes are made.
2. Confirm game is Home via a read-only capture if uncertain. Run ONE production verification:

   `rtk proxy .venv/Scripts/python.exe local/verify_live.py attack`

   Use escalation for ADB. Keep normal loot thresholds, collection/walls off, one-attack cap.
3. Verify first placement, deployed-marker recognition, Rage and Freeze consumption, then the remaining Valkyries. Inspect saved `production-results.png` and latest battle capture. Required full inventory: **35 Valkyries, one siege, five Rage, one Freeze**. Record actual resource gains and return home. A `BattleFinished` event alone does not establish full consumption.
4. If any recognition error: stop, inspect the exact real screenshot, fix the shared cause/crop, add a focused real-image regression, rerun tests, and retry fresh from home. Do not relax validation or retry an uncertain placement blindly.
5. Only after that gate passes, proceed to task 5's continuous THREE-attack session, then the bounded FIVE-attack / fifteen-minute session. Separate one-attack successes do not substitute. Add needed duration/failure tests and actual stopping evidence.
6. Keep walls OFF until a new explicit bounded spending approval. Combined wall verification remains unproven even though one standalone Build-menu upgrade was proved in an earlier chat.
7. Update `docs/auto-farming-progress.md` (older historical checkpoints and latest count are stale), setup/README as needed, and record automated versus real-device results separately. `docs/live-setup.md` already reflects the new dump order and siege marker semantics.

## Do not overstate readiness

Working now: regular production attacks can navigate, deploy, observe results, return home and respect the one-attack cap. Safe pauses exposed and helped correct genuine calibration/timing issues.

Still unproven: a fresh full-consumption attack after the latest Freeze fix; repeated continuous sessions; combined wall workflow/budgets; fresh idle release launch. Heroes returning, unsupported scenery, changed UI or army layouts can still require calibration. Collection, pinch normalization and indefinite unattended operation remain deferred.
