# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Name things with `GLOSSARY.md`'s terms. ADR 0002 supersedes part of ADR 0001: editing a preset never touches the wheel; only selecting a preset in the riding menu applies it.

## Agent skills

### Issue tracker

GitHub Issues in EvgenyHitexis/EucWatch, through `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.

## Commands

The only Python project is `experiments/laptop-feasibility/` (Python 3.12, aiohttp, bleak, locked with uv). The app code in `laptop/` runs from that environment through `PYTHONPATH`. There is no root `pyproject.toml`.

```bash
./scripts/setup.sh        # uv sync --locked + npm ci + frontend build
./scripts/check.sh        # every Python unit test, frontend typecheck/build, every watch suite
EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh   # adds launch smoke + Chrome CDP flows (Chrome required)
./scripts/launch.sh       # backend on 127.0.0.1:8765 + browser; EUCWATCH_NO_BROWSER=1, EUCWATCH_PORT=...

# One Python test module or test (tests/ has no __init__.py, so put it on PYTHONPATH)
env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest test_presets
env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest test_presets.PresetTests.test_four_initial_slots_have_editable_owner_defaults

# One watch suite (plain Node, no test runner)
node watch/tests/preset-editor.cjs

npm run typecheck --prefix frontend
```

The `tests/browser_*.py` and `tests/launch_smoke.py` files are scripts, not unittest modules. Run them directly the way `check.sh` does.

Many suites rewrite tracked evidence files (`watch/evidence/**`, `docs/acceptance/evidence/**`) on every run. Check `git status` after running tests. Commit regenerated evidence only when your change is meant to update it.

## Architecture

The same riding application exists twice, and the two copies must behave the same:

- **Laptop** (`laptop/eucwatch/`): a staging prototype. `application.Application` holds all behavior and changes only through explicit actions, raw wheel notifications and an injected `Clock`. `server.py` (aiohttp) serves `/api/state`, `/api/session`, `/api/action`, `/api/ws` and `/api/recording`. `frontend/` (Vite + TS) draws the 240×240 watch on a Canvas plus a scenario/editor panel. It renders server state and posts actions; it holds no behavior of its own. `live.py`/`live_control.py` are the only Bleak (BLE) code. Launching is idle until the user explicitly starts discovery.
- **Watch** (`watch/`): ES5 modules for a P22 watch running Espruino 2v14. `boot.js` is the `.bootrst` recovery startup. It reads `sw-active.json` and starts the selected versioned `main`. Modules call each other as `require('sw-<name>')`, which maps to `watch/<name>.js`. `scripts/watch-bundle.py` (logic in `laptop/eucwatch/installation.py`) rewrites these to `sw-<version>-<name>`, and every Storage name must fit in 28 bytes.

The watch tests load the real production modules into a Node `vm` context with fake pins, NRF radio, Storage, Graphics and timers (see `watch/tests/runtime.cjs`). `compare-alerts.cjs` replays one serialized action/clock/raw-frame script through both Applications. A behavior change usually needs both implementations and both test suites. Espruino quirks the fakes enforce: `clearTimeout(undefined)` clears every timer, and graphics are a 1-bpp 240×240 buffer.

Telemetry decoding starts from the sanitized fixture `experiments/laptop-feasibility/evidence/fixture-recording.jsonl` (Sherman L frames with CRC32). Tests build synthetic frames from it. The protocol notes are in `docs/research/sherman-l-protocol.md`.

## Authorization gates

Software checks use only controlled transports, `ManualClock` and synthetic Storage. Real-world actions need the owner's explicit permission for that specific action:

- live BLE scans or connections
- wheel setting writes (`experiments/wheel-verification/` touches the real wheel)
- the horn
- watch deployment, Storage changes or reset

Submitting a command to the transport is not the same as the wheel confirming it. Keep it reported separately.

Keep private live recordings, watch backups and captures out of git. Commit only sanitized evidence.

## Acceptance evidence

Work tracks GitHub issues. Commits use conventional prefixes with the issue number, e.g. `fix: … (#31)`. Each milestone has a write-up in `docs/acceptance/*.md`, backed by JSON/PNG/SVG evidence. Older evidence is preserved and labelled with the scope it originally showed. Put a new pass in a new evidence file or directory instead of overwriting old evidence. Mark unknown or failed checks as incomplete.
