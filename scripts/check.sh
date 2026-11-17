#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest discover -s tests
npm run build --prefix frontend
# Configuration-transfer gates (#28/#29/#35) were superseded by #40.
# Historical evidence is retained; local-configuration checks replace those gates.
if [[ "${EUCWATCH_BROWSER_CHECKS:-0}" == 1 ]]; then
  env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python tests/launch_smoke.py
  for flow in browser_local_presets browser_preset_editor browser_preset_navigation browser_preset_value_editor browser_navigation browser_alerts browser_control browser_horn browser_dashboard browser_replay browser_live browser_backup browser_scenarios browser_resume browser_lifecycle; do
    env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python "tests/$flow.py"
  done
fi
# The ES5 check and the watch suites, after the browser flows: the parity suites replay the traces those flows wrote.
./scripts/check-watch.sh
