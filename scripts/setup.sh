#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked --project experiments/laptop-feasibility
npm ci --prefix frontend
npm run build --prefix frontend
