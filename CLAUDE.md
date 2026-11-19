# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Name things with `GLOSSARY.md`'s terms. `CODING_STANDARDS.md` holds the judgement rules a reviewer checks. ADR 0002 supersedes part of ADR 0001: editing a preset never touches the wheel; only selecting a preset in the riding menu applies it.

## Agent skills

### Issue tracker

GitHub Issues in EvgenyHitexis/EucWatch, through `gh`. Read `docs/agents/issue-tracker.md` before opening a PR or closing an issue: PRs don't target the default branch, so closing keywords such as `Fixes #N` never fire.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.

## Commands

The only Python project is `experiments/laptop-feasibility/` (Python 3.12, aiohttp, bleak, locked with uv). The app code in `laptop/` runs from that environment through `PYTHONPATH`. There is no root `pyproject.toml`.

A new worktree has no `.venv` or `frontend/node_modules`: run `./scripts/setup.sh` in it before any check.

```bash
./scripts/setup.sh        # uv sync --locked + npm ci + frontend build
./scripts/check.sh        # every Python unit test, frontend typecheck/build, then check-watch.sh
./scripts/check-watch.sh  # the watch checks alone: ES5 parse of the watch modules, every watch suite
EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh   # adds launch smoke + Chrome CDP flows (Chrome required)
./scripts/launch.sh       # backend on 127.0.0.1:8765 + browser; EUCWATCH_NO_BROWSER=1, EUCWATCH_PORT=...
uv run --offline --no-sync --project experiments/laptop-feasibility python scripts/evidence-compare.py <base-ref> [--browser]   # did behavior change since <base-ref>?
uv run --offline --no-sync --project experiments/laptop-feasibility python scripts/evidence-explain.py <base-ref>               # how does tracked evidence differ from <base-ref>? (reads only)
uv run --offline --no-sync --project experiments/laptop-feasibility python scripts/red-at.py <base-ref> <test> [names...] [--runs N]   # does this test fail without the fix? (exit 0: red)

# One Python test module or test (tests/ has no __init__.py, so put it on PYTHONPATH)
env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest test_presets
env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest test_presets.PresetTests.test_four_initial_slots_have_editable_owner_defaults

# One watch suite (plain Node, no test runner)
node watch/tests/preset-editor.cjs

npm run typecheck --prefix frontend
```

`.github/workflows/check.yml` runs `./scripts/setup.sh` and the plain `./scripts/check.sh` on every push and pull request, without Chrome.

The `tests/browser_*.py` and `tests/launch_smoke.py` files are scripts, not unittest modules. Run them directly the way `check.sh` does.

One flag gates all tracked evidence: the watch suites write `watch/evidence/**` and the browser flows write `docs/acceptance/evidence/**` only when `EUCWATCH_WRITE_EVIDENCE=1` is set (`EUCWATCH_WRITE_EVIDENCE=1 node watch/tests/<suite>.cjs`, `EUCWATCH_WRITE_EVIDENCE=1 EUCWATCH_BROWSER_CHECKS=1 ./scripts/check.sh`). Without it a run leaves `git status` unchanged, and the browser flows write the same files to `.test-output/evidence/` instead. The watch parity suites (`preset-navigation`, `preset-value-editor`, `preset-editor-runtime`) replay laptop traces through `harness.laptopTrace()`: in an `EUCWATCH_BROWSER_CHECKS=1` run, the ones the browser flows just wrote, wherever the flag sent them; otherwise the committed ones. Commit regenerated evidence only when your change is meant to update it.

Check a "behavior unchanged" criterion with `scripts/evidence-compare.py <base-ref>`, adding `--browser` (Chrome) when laptop behavior is in scope. Exit 0 meets the criterion. `--help` says what it regenerates, which provenance fields it ignores and what the other exit codes mean. To explain a regenerated-evidence diff in a commit message, run `scripts/evidence-explain.py <base-ref>`: it groups the JSON field changes, lists the files whose only change is that provenance, and gives each changed PNG's old and new sha256 with the tracked files identical to the new one.

## Architecture

The same riding application exists twice, and the two copies must behave the same:

- **Laptop** (`laptop/eucwatch/`): a staging prototype. `application.Application` holds all behavior and changes only through explicit actions, raw wheel notifications and an injected `Clock`. `server.py` (aiohttp) serves `/api/state`, `/api/session`, `/api/action` and `/api/recording`. `frontend/` (Vite + TS) draws the 240×240 watch on a Canvas plus a scenario/editor panel. It renders server state and posts actions; it holds no behavior of its own. `live.py`/`live_control.py` are the only Bleak (BLE) code. Launching is idle until the user explicitly starts discovery.
- **Watch** (`watch/`): ES5 modules for a P22 watch running Espruino 2v14. `check-watch.sh` (which `check.sh` runs) enforces ES5 on every module the bundle ships (`scripts/check-es5.py`). `watch/tests/` is Node and is not checked. `boot.js` is the `.bootrst` recovery startup. It reads `sw-active.json` and starts the selected versioned `main`. Modules call each other as `require('sw-<name>')`, which maps to `watch/<name>.js`. `scripts/watch-bundle.py` (logic in `laptop/eucwatch/installation.py`) rewrites these to `sw-<version>-<name>`, and every Storage name must fit in 28 bytes.

The watch tests load the real production modules into a Node `vm` context with fake pins, NRF radio, Storage, Graphics and timers. `watch/tests/harness.cjs` owns that fake device, the module loader (cached per environment, as Espruino's `require` is), the fixture rows, the frame builder, the SVG writer, shared replay helpers and the evidence recorder. It is not a suite; suites import it. `compare-alerts.cjs` replays one serialized action/clock/raw-frame script through both Applications. A behavior change usually needs both implementations and both test suites. Espruino quirks the fakes enforce: `clearTimeout(undefined)` clears every timer, and graphics are a 1-bpp 240×240 buffer.

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

Work tracks GitHub issues. Commits use conventional prefixes with the issue number, e.g. `fix: … (#31)`. Each milestone has a write-up in `docs/acceptance/*.md`, backed by JSON/PNG/SVG evidence. Older evidence is preserved and labelled with the scope it originally showed. Two kinds of evidence, two rules: a new acceptance pass for a write-up goes in a new evidence file or directory, leaving the earlier pass intact; a file a test suite regenerates (every `watch/evidence/**` file, and the `docs/acceptance/evidence/**` files a browser flow writes) is updated in place, in the commit whose change is meant to alter it, with the diff explained in the commit message. Mark unknown or failed checks as incomplete.

A pass's manifest under `docs/acceptance/evidence/` records the sha256 of each evidence file it produced in `artifact_sha256` (repository-relative paths; the laptop-31 pass uses `artifacts_sha256`, relative to its own directory). `tests/test_evidence_manifests.py` fails when one of those files is missing or no longer matches. When a later commit regenerates such a file in place, leave the recorded hash as it is and add a `superseded` entry beside `artifact_sha256` in the same manifest: `"superseded": {"<path>": {"sha256": "<current sha256>", "commit": "<commit that wrote those bytes>"}}`, plus `"earlier_commits": [...]` if other commits changed it in between (`git log -- <path>` finds them). The check then holds the file to the superseded hash, so any further change fails again. `source_sha256` and `final_source_sha256` record the code a pass ran on and are not checked.
