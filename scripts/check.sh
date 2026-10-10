#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest discover -s tests
npm run build --prefix frontend
# Configuration-transfer gates (#28/#29/#35) were superseded by #40.
# Historical evidence is retained; local-configuration checks replace those gates.
if [[ "${EUCWATCH_BROWSER_CHECKS:-0}" == 1 ]]; then
  for flow in browser_local_presets browser_preset_editor browser_preset_navigation browser_flow browser_lifecycle; do
    env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python "tests/$flow.py"
  done
fi
for suite in offline runtime alerts alerts-runtime compare-alerts control local-configuration preset-defaults preset-editor preset-editor-runtime preset-navigation preset-editor-bundle; do
  node "watch/tests/$suite.cjs"
done
