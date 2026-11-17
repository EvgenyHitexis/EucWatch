#!/usr/bin/env bash
# The watch checks alone: the ES5 parse of the bundled modules, then every watch suite. check.sh runs this last.
set -euo pipefail
cd "$(dirname "$0")/.."
# Watch modules must stay ES5 for Espruino 2v14: parse exactly what the bundle builder ships.
uv run --offline --no-sync --project experiments/laptop-feasibility python scripts/check-es5.py
for suite in offline runtime alerts alerts-runtime compare-alerts alert-editor control local-configuration preset-defaults preset-editor preset-editor-runtime preset-navigation preset-value-editor preset-editor-bundle wheel-selection paint-signature; do
  node "watch/tests/$suite.cjs"
done
