# Laptop acceptance evidence (#31)

This register collects software evidence incrementally. #31 and #9 remain open:
live application evidence and explicit owner review are required for acceptance.
The research worktree and private captures are excluded from implementation commits.

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

### #21 — four fixed preset definitions

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
