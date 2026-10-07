#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env PYTHONPATH=laptop uv run --offline --no-sync --project experiments/laptop-feasibility python -m unittest discover -s tests
npm run build --prefix frontend
