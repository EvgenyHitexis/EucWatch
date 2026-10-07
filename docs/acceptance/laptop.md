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
