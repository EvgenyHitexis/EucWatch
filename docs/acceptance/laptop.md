# Laptop acceptance evidence (#31)

Current preset behavior uses keypad **OK/Cancel** for one value and field-display
**Save/Cancel** for the whole preset. This owner-confirmed revision supersedes
#43's completion/navigation inside active keypads and the older wheel-owned #41
editor. Four editable defaults, local drafts, migration, separate dip inclusion
and riding-menu application remain. See [current preset behavior](preset-editor.md).
Historical evidence below retains only its original demonstrated scope.

## Current acceptance audit — 2026-10-10

**#31 remains incomplete.** The owner approved the appearance (“I like how app
looks”); complete behavioral owner review and required live evidence are pending.
The [isolated simulator walkthrough](laptop-owner-review.md) is paused at the
owner's request during R4. The [touch layout revision](watch-touch-layout.md)
addresses the owner's feedback about hints, spacing and small controls and
awaits owner review.
The research worktree and private captures remain outside this implementation.

Owner walkthrough progress on the previous layout: [R1 dashboard/freshness/reconnect observed pass](evidence/laptop-31/owner-review/r1.json),
with six owner-supplied screenshots and a completed 7/7 simulator scenario.
[R2 navigation and sleep also passed](evidence/laptop-31/owner-review/r2.json),
including wake-only button behavior and riding-menu entry/return without commands.
[R3 local preset editing also passed](evidence/laptop-31/owner-review/r3.json):
Road sensitivity is saved at 40 after value and whole-preset Save/Cancel checks;
field loops and dip inclusion preserve the other saved content, with no wheel
commands. R4–R6, overall owner acceptance and required live evidence remain pending.

On 2026-11-16 the owner accepted the revised touch layout and R4–R6 on the
evidence of an [agent-run walkthrough](laptop-owner-review.md). Every simulator
review row (R1–R6) is now accepted. The live evidence rows below remain
incomplete.

| #31 requirement | Current outcome | Evidence / next action |
| --- | --- | --- |
| Launch, shutdown, offline relaunch, XDG scenarios | Software pass | `tests/launch_smoke.py` starts the real launcher twice with isolated XDG directories; saved preset, alerts and complete scenario survive, without autostart or transient state. [Launch result](evidence/laptop-31/launch.json); [scenario format/import/export](scenarios.md). |
| Complete actual watch-sized flows | Automated pass; owner accepted R1–R6 | Six built Chrome flows cover dashboard, gestures/sleep, local presets, controls, horn model and lifecycle. Alert validation, keypad, Save/Cancel and all four Test patterns now use Canvas pointers. [Alert result](evidence/laptop-31/alerts.json); walkthrough R1–R6. |
| Simulator, read-only replay, browser/session/storage failures | Software pass | Current [validation manifest](evidence/laptop-31/validation.json) indexes scenario, replay, control, lifecycle and storage evidence. Seed 0 is fixed input with controlled time. Control failure/readback injections are labelled; they are not measured hardware behavior. |
| Live application telemetry, ranges, confirmation, persistence, multi-setting/partial/disconnect and riding behavior | Incomplete | Controlled BLE tests verify software only. Existing research observations below are reused within scope; application/live rows remain in the walkthrough's live-evidence list. |
| Outstanding #9, including audible horn and assist/dip persistence | Incomplete | Horn remains deferred. Changed assist/dip persistence, unverified ranges and owner app versions, complete application presets and riding evidence remain outstanding. |
| Reproducible, versioned, sanitized evidence | Software pass | [Run commands, source/artifact hashes and provenance](evidence/laptop-31/validation.json). New artifacts are under `evidence/laptop-31/`; original historical evidence is preserved. No private recordings or backups are committed. |
| Explicit owner review and all required passes | Partial: appearance approved; R1–R3 observed pass; revised layout and R4–R6 accepted by the owner on 2026-11-16 from an agent-run walkthrough ([owner review](laptop-owner-review.md)) | Physical rows remain pending, and with them overall acceptance. Unknown or failed checks remain incomplete. |
| Separate hardware authorization and deployment gate | Retained | No live scan/connection, physical command or watch deployment in this pass. #37 still follows full #31 acceptance and separate deployment authorization; #38 follows installation. |

Reproduce after setup:

```sh
EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh
uvx --offline ty check --python experiments/laptop-feasibility/.venv/bin/python laptop
```

The full check includes the real launcher smoke check, Python tests, frontend
typechecking/build, six Chrome flows and thirteen offline watch suites. Isolated
test stores do not change the owner's normal configuration. Offline relaunch
means installed dependencies/assets and `uv --offline --no-sync`; this does not
claim that the laptop's network was physically disconnected.

The production panel's stale wheel-writing editor instructions were reproduced
with a failing browser assertion and corrected to local draft/value completion.
The previously desktop-driven alert Save/Test evidence is replaced by a full
watch-sized pointer journey, including exact simulated pulse/gap observations.
The [independent Standards and Spec review](laptop-review.md) corrected shutdown
test sensitivity and walkthrough navigation. Its focused launcher rerun passed;
the remaining shared-label-helper suggestion is nonblocking.

### Existing live evidence retained within scope

The [three stationary roundtrips](https://github.com/EvgenyHitexis/EucWatch/issues/9#issuecomment-6038773104)
on Sherman L 006.0.10 confirmed sensitivity 30→31→30, assist 25→26→25 and dip
10→11→10 with two fresh CRC-valid settings frames per change/restoration.
[Sensitivity power-cycle evidence](https://github.com/EvgenyHitexis/EucWatch/issues/9#issuecomment-6039826955)
confirmed 31 remained after the owner-operated off/on cycle, then restored 30.
The [owner's moving-support report](https://github.com/EvgenyHitexis/EucWatch/issues/9#issuecomment-6040353913)
remains valid planning evidence. These observations came from research tools,
not the current application. They do not establish full ranges, assist/dip
persistence, complete presets, current riding behavior or audible horn support.

## Application boundary

Tests enter through explicit actions, raw notifications, session transitions and
controlled elapsed time, then observe view state and external effects. Source
fixture: WheelLog revision `f44e39e5388e500a5d2f315d1dcf32f167607bf8`, Sherman L
006.0.03. Owner-observed complete lengths 75/77/87/99 are supported; synthetic
fixtures of those sizes establish parser coverage rather than physical cadence.

## Launch

From repository root: `./scripts/launch.sh`. First setup: `./scripts/setup.sh`.
Expected: idle dashboard, no BLE connection, browser opens after readiness.
Ctrl-C shuts down; subsequent launch is offline with dependencies/assets installed.

## Evidence register

Results will be appended per completed issue, with exact checks, expected/observed
outcomes and commit references recorded on the ticket. Hardware results require
their own provenance and cannot be inferred from simulator success.

### #18 — dashboard foundation

`tests/test_dashboard.py` covers the pinned source fixture, every supported frame
split, coalesced frames, all 696 source-frame single-bit corruptions, large noise,
unknown identity, battery boundaries, one-second freshness, disconnect, resume
and old callbacks. `tests/test_http.py` covers idle launch and origin/credential
enforcement. Observed: passing through the real Application/parser boundary.

`env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python tests/browser_flow.py`
drives the built UI using Chrome CDP. Expected/observed: 100% at 148.05 V, 0% at
119.02 V; paused traffic plus 1.1-second advance shows dashes and dimmed retained
battery; corrupt CRC does not recover; valid input restores; disconnect invalidates
immediately and a fresh frame restores after reconnect. All passed. Artifacts:
[result](evidence/dashboard.json), [rendering](evidence/dashboard.png).

Python `ty` and frontend `tsc`/Vite build pass. `EUCWATCH_NO_BROWSER=1 EUCWATCH_PORT=18765 ./scripts/launch.sh`
reached readiness offline and Ctrl-C stopped the backend (port then unavailable).
Browser opening is supplied by `xdg-open` after readiness; automated checks use
Chrome directly. No hardware operations were performed.

Two-axis #18 review found no documented standards violations and identified
credential recovery after backend restart and loss of controlled time on reconnect.
Both were corrected. Regression checks preserve the selected clock and recover
the same controlling tab token; competing viewers receive disabled controls.

### #19 — navigation and sleep

Six Application-boundary navigation checks pass, including 30-second initial
idle sleep, interaction reset, complete wake-cycle consumption, keep-awake after
an established transport loses its link and modeled independent recovery hold.
The real browser flow now dispatches pointer input to the Canvas and side button:
left reaches four fixed slots, right returns, a swipe from the top opens Settings,
Sleep turns the display off, the side-button cycle wakes only, and initial idle
sleep and established-loss keep-awake match the backend. Observed: passed.
[Navigation result](evidence/navigation.json). Python typechecking and the
frontend build pass. The combined #20 browser flow opens the watch alert editor,
changes an unsaved switch and swipes back: the draft is discarded and the saved
disabled/null setting remains unchanged. Observed: passed.

#19 review corrections: the rendered keep-awake check now advances 31 seconds
after disconnection and waits for the rendered elapsed time before asserting awake.
Abandoned browser holds are released on lifecycle loss, with a two-second backend
input lease as the fallback. The HTTP boundary verifies abandonment cannot become
a prolonged recovery hold. Browser timing remains unrelated to telemetry/recording.

### #24 — capture and replay

Recordings are append-only schema-1 JSONL under the XDG data directory, with
bounded queues and visible fatal overflow/storage errors. Raw ingress includes
malformed input and late callbacks before parsing/session rejection. Wall time
and suspend-aware host receipt time are separate from controlled simulator
behavior time. Replay preserves bytes/boundaries/order, advances virtual behavior
time, rejects command paths and treats outgoing evidence as inert.

The real file-import/step flow runs the sanitized source fixture's 13 events and
produces exactly three valid frames through the actual Application/parser. Final
observed values are speed 0, PWM 2%, estimated battery 97%, average cell 4.09 V;
simulator command input remains disabled. [Replay result](evidence/replay.json)
retains fixture SHA256 and provenance. The recording HTTP boundary checks raw
download, validated replay import and read-only rejection. External recording
checks cover ordering, bounds and failures; no private raw capture is committed.

Two-axis #24 review corrections separate the writer from the behavior ticker,
preserve batch order/accounting during cancellation, preserve disconnected resume
state and discard a delayed replay-file read after a newer session choice. Eight
recording checks now include direct application capture/replay dashboard equivalence
across corruption and gaps. Two recording HTTP checks include a blocked writer:
autonomous simulator frames continue without browser polling. Observed: passed.

### #20 — vibration alerts and durable configuration

Eighteen Application-boundary alert checks cover exact pulse lengths, repeat
intervals, hysteresis, battery rearming, interruption latching, priority and no
overlap, stale input, resume cancellation, Save/Cancel and restart recovery. The
default PWM/speed/battery alerts remain disabled with no invented thresholds;
lost telemetry starts enabled. Atomic configuration writes retain a validated
backup; failed saves remain visible and do not replace the active configuration.

The actual Canvas/HTML/aiohttp flow verifies back discards a draft, an enabled
alert without a threshold is refused, saving PWM 70 persists the authoritative
setting, and the Test action emits three 150 ms simulated pulses separated by
150 ms. [Alert result](evidence/alerts.json). Watch editing includes explicit
Save/Cancel, switch controls, threshold adjustments and a numeric keypad. Pattern
output is simulated; physical vibration/timing acceptance remains pending.

Two-axis review found no hard standards violations. Its material spec finding,
a measurement repeat launching at the exact freshness expiry, is fixed and
covered at that exact deadline; earlier pulse phases still finish in order.

### #21 — four fixed preset definitions (historical)

This early editor account and the later wheel-owned #41 account are historical;
#43 defines the current local watch-sized editor.
The retained artifacts describe the former scope; current editor behavior and
checks are recorded in [preset editor acceptance](preset-editor.md).

Eight Application-boundary checks cover defaults, required whole percentages,
optional dip omission, Save/Cancel, staged clearing, stable identities, watch
editing refusal, persistence failure and FileStore restart. Source-backed 0–100
validation does not establish full physical ranges; #9 remains open. The actual
HTML editor/Canvas/aiohttp flow rejects a missing required field, saves slot 2
as Rain with sensitivity 30/assist 20 and no dip field, shows the name in the
four-slot menu, cancels a staged clear and retains the definition after restart.
[Preset result](evidence/presets.json). Editing emits no wheel commands and saves
no wheel confirmation. Two-axis review: no material findings; two optional
maintainability suggestions. Python typechecking and the frontend build pass.

### #25 — explicit live telemetry adapter

Thirteen controlled-transport checks exercise the real Application/parser and
capture path: discovery/selection, FFE0/FFE1 validation, family/firmware decoding,
CRC rejection and freshness, source loss, bounded reconnection, old callbacks,
resume, failure/timeouts and cancellation-safe cleanup. Recorded live-shaped
bytes replay to the same per-notification dashboard states. No real Bluetooth
operation is executed by these checks.

Two HTTP checks and the actual built HTML/Canvas flow demonstrate explicit scan
and selection, identity pending until valid telemetry, disconnect invalidation,
new-session/fresh recovery and mode-switch cleanup. Concurrent duplicate HTTP
selection creates exactly one transport client. [Live result](evidence/live.json)
labels controlled transport provenance and pending physical evidence. Discovery
and connection run only on explicit UI actions through ordinary-user Bleak/BlueZ;
no initialization command, root/Docker transport or MTU workaround is introduced.

Both review axes identified awaited-request duplication and cancelled-child
cleanup starvation. Corrected with serialized intents/deduplication and bounded
uncertain-cleanup handling; regression checks pass. Actual application telemetry,
cadence, owner firmware identity and reconnect evidence remain pending under #31.

### #22 — immediate preset application and confirmation

Nineteen main-boundary checks exercise exact encoded/CRC packets, omitted dip,
serialized submission, extra taps, controlled submission/confirmation deadlines,
two consecutive post-submission fresh settings frames, stale/session/revision
invalidation, partial/unknown outcomes, explicit retry and late actual readings.
Submission is bounded to 5 seconds; confirmation to 10 seconds after all writes
complete. Cached, pre-request, pre-completion and old-session input cannot confirm.

The actual moving-simulator Canvas flow taps Rain once and immediately returns
to the dashboard with Applying feedback; two fresh settings frames confirm it.
HTML scenarios exercise missing/mismatching/partial readback, failed/stalled
submission, timeout and fresh explicit retry. Late readings preserve terminal
failure. Stale/session loss removes current confirmation; historical results are
labelled separately. [Control result](evidence/control.json). Outputs establish
simulated command/evidence behavior, not physical control or riding acceptance.

### #27 — configuration backup and review

Ten Application checks cover complete saved-only export, explicit preview,
Cancel/Restore, schema validation, unsupported/duplicate/incomplete/oversized or
deeply nested imports, revision change after preview, ongoing-operation sleep,
interrupted replacement, last-good recovery and restart. Restoration activates
saved alerts, invalidates confirmation and stops unsent settings requests.

The actual HTML/aiohttp/file flow downloads a JSON backup, reviews a complete
candidate without activation, cancels it, then explicitly restores. Unsupported
versions are visibly rejected; no wheel commands are produced.
[Backup result](evidence/backup.json). This historical result used schema 1 as the only product
format: compatible application updates preserve its meaning and fixed identities;
unknown schemas require owner review rather than invented historical migrations.

### #23 — modeled physical-button horn request

Ten main-boundary checks verify exactly one source-pinned LkAp packet per eligible
press, full wake-cycle consumption, no hold repetition/queue/stop command,
freshness/preset/recovery eligibility, discarded presses, bounded feedback,
transport failures and old-session/duplicate results. The actual side-button and
Canvas flow verifies an awake request, explicit Sleep plus a wake-only cycle,
the required subsequent fresh press, and blocked preset/stale presses.
[Horn result](evidence/horn.json). Feedback says request sent, never audible
success. No physical horn command or hardware operation was performed.

Two-axis review: #22/#27 have no material spec or hard standards findings;
#23 has no material spec or hard standards findings. Optional maintainability
suggestions remain separate from acceptance criteria. Watch #32 review corrections
and remaining physical evidence are recorded in the watch register.

### #34/#35 — watch controls and historical configuration exchange

The configuration-exchange portion below is historical: its gates and test
commands were superseded by #40 on 2026-10-09. Retained transfer evidence proves
only the former scope. Watch control acceptance retains its separate provenance.
Current checks are recorded under [local configuration](local-configuration.md).

The watch implements one-tap presets and bounded horn requests; its offline
control traces match the laptop application. Python owns the Nordic UART client;
the watch endpoint implements bounded JSONL, complete saved-content validation,
staging, verified activation and last-known-good recovery. Each selected watch
has independent shared-base and uncertain-commit evidence. See
[watch controls](watch-controls.md), [configuration transfer](watch-transfer.md)
and [the two-axis review](review-34-35.md).

The actual Chrome Canvas/HTML → aiohttp → Python Nordic client → original watch
JavaScript/Storage flow uses a **fake BLE transport**. It verifies explicit
Settings entry, discovery/selection, reviewed transfer, complete disconnect
before return, lost commit acknowledgement, explicit reconnect/readback after
watch restart and laptop restart persistence. Two activations were submitted;
readback reconciliation did not submit another activation. Configuration
exchange emitted no wheel commands or wheel confirmation.
[Browser transfer result](evidence/watch-transfer-browser.json).

Final verification on 2026-10-08: `EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh`
passed 192 Python tests, TypeScript checking/Vite production build, all eight
watch suites, and all three Chrome flows (complete behavior, lifecycle and
watch transfer). Python `ty` passes against the exercised Python 3.12 virtual
environment. The complete version `20261008` watch bundle contains 17 files
and 93,050 bytes; local staging/activation rehearsal passed using synthetic
Storage only. This does not establish actual-device capacity or memory fit.

Review regressions preserve the sole validated backup during subsequent saves
after recovery, and bind staging to the exact freshly read watch byte digest
when Python/Espruino numeric JSON formatting differs. These establish software
behavior, not physical flash atomicity or real BLE reliability.

### #40 — independent local configuration

The laptop panel, watch-sized Settings and production-watch Settings offer no
configuration synchronization/transfer or conflict reconciliation. The laptop
rejects former transfer/Nordic actions; the watch no longer loads or bundles its
configuration-exchange endpoint. Existing schema-1 presets and alert preferences
retain their formats and local save/recovery paths. Local backup/import/restore,
recording/replay, direct wheel sessions and staged installation/recovery remain.
See [expected/observed results and reproduction](local-configuration.md).

The check entry point replaces transfer suites and the browser transfer flow with
local-configuration checks and the revised complete browser journey. Historical
transfer artifacts are preserved unchanged and are not rerun as current gates.

### Historical #41 — superseded by local editing in #43

Settings → Presets exposes all four slot editors inside the 240×240 Canvas.
New current-session complete settings seed each opening; completed field edits
submit the corresponding command directly and update only the selected local
slot. Submission and two-frame wheel confirmation remain distinct. Text/numeric
keypads, local names/include/omit/clear, stopped-unsent operations, bounded
failure/unknown results, persistence errors, restart/reload and duplicate
suppression are covered by the main application seam and actual browser flow.
The desktop definition editor is removed. See the [reproduction, expected/observed
register and retained rendering/action/frame evidence](preset-editor.md).
Controlled live-transport tests exercise the real session/parser/chunk writer
using a fake BLE client. Hardware evidence and owner review remain pending.

### Remaining laptop acceptance

#31 and #9 remain open. Existing source, simulator, replay, controlled transport
and earlier owner-wheel observations retain their recorded scope. Completion
still requires live evidence through this application for telemetry/cadence,
included setting ranges/readback, assist/dip persistence, complete multi-setting
and partial/disconnect behavior, and implementation behavior while riding.
Audible horn result, variant, latency/duration, repeated presses and alarm
coexistence remain deferred until separately authorized. Explicit owner review
must cover the complete watch-sized flows, not only the desktop editors.

Run `./scripts/launch.sh` for owner review. The simulator, recording replay and
controlled scenarios support review while physical evidence remains pending.
Unknown checks remain incomplete. Watch installation (#37) follows full laptop
acceptance and separate authorization; physical watch acceptance (#38) follows
installation. Software verification does not grant either hardware permission.
