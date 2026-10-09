#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest discover -s tests
npm run build --prefix frontend
# Configuration-transfer gates (#28/#29/#35) were superseded by #40.
# Historical evidence is retained; local-configuration checks replace those gates.
for suite in offline runtime alerts alerts-runtime compare-alerts control local-configuration preset-editor preset-editor-runtime preset-editor-bundle; do
  node "watch/tests/$suite.cjs"
done
if [[ "${EUCWATCH_BROWSER_CHECKS:-0}" == 1 ]]; then
  for flow in browser_flow browser_lifecycle; do
    env PYTHONPATH=laptop:tests uv run --offline --no-sync --project experiments/laptop-feasibility python "tests/$flow.py"
  done
fi
