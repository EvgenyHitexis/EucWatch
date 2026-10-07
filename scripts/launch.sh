#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f frontend/dist/index.html || ! -x experiments/laptop-feasibility/.venv/bin/python ]]; then
  ./scripts/setup.sh
fi
port="${EUCWATCH_PORT:-8765}"
url="http://127.0.0.1:$port"
if curl --silent --fail "$url/api/state" >/dev/null; then
  echo "Port $port is occupied; stop the existing application or select EUCWATCH_PORT." >&2
  exit 1
fi
env PYTHONPATH="$PWD/laptop" uv run --offline --no-sync --project experiments/laptop-feasibility python -m eucwatch.server --port "$port" &
backend_pid=$!
cleanup() {
  kill "$backend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM
ready=false
for _ in {1..100}; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Backend stopped before readiness." >&2
    exit 1
  fi
  if curl --silent --fail "$url/api/state" >/dev/null; then
    ready=true
    break
  fi
  sleep .1
done
if [[ "$ready" != true ]]; then
  echo "Backend readiness timed out." >&2
  exit 1
fi
echo "Sherman L laptop application: $url (Ctrl-C to stop)"
if [[ "${EUCWATCH_NO_BROWSER:-0}" != 1 ]]; then
  xdg-open "$url" >/dev/null 2>&1 || echo "Open $url in your browser."
fi
wait "$backend_pid"
