#!/usr/bin/env bash
# Start the WriteAI API (port 8000) and web UI (port 5173) in the background.
# Logs: data/logs/api.log, data/logs/web.log.  Stop: scripts/dev.sh stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/data/logs"
mkdir -p "$LOGS"

stop() {
  pkill -f "uvicorn backend.main:app" 2>/dev/null || true
  pkill -f "vite --host" 2>/dev/null || true
}

if [ "${1:-}" = "stop" ]; then stop; echo "stopped"; exit 0; fi
stop

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

cd "$ROOT"
nohup "$PY" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 > "$LOGS/api.log" 2>&1 &
cd "$ROOT/frontend"
nohup npx vite --host 0.0.0.0 --port 5173 > "$LOGS/web.log" 2>&1 &

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
    echo "WriteAI is running:  web http://localhost:5173   API docs http://localhost:8000/api/docs"
    exit 0
  fi
  sleep 1
done
echo "WriteAI did not start in time — see $LOGS" >&2
exit 1
