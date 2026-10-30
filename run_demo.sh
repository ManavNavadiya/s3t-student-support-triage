#!/usr/bin/env bash
# Group 6 (S3T) demo: set up the environment (first time only), start the demo page, open the browser.
#   ./run_demo.sh                 Group 6 on its own
#   ./run_demo.sh --setup         only (re)install the environment
# Optional partner services (only if they are already running elsewhere):
#   GROUP7_URL=http://127.0.0.1:8080 GROUP5_URL=http://127.0.0.1:8002 ./run_demo.sh
# Press Ctrl+C to stop.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"; PY="$VENV/bin/python"; LOGS="$ROOT/logs"; mkdir -p "$LOGS"
UI_PORT=${UI_PORT:-5050}   # 5000 is taken by macOS AirPlay
GROUP5_URL=${GROUP5_URL:-off}; GROUP7_URL=${GROUP7_URL:-off}

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mERROR: %s\033[0m\n' "$*"; exit 1; }

setup() {
  command -v python3 >/dev/null || die "python3 not found. Install Python 3.9+ from python.org."
  say "Creating the S3T environment (installs torch for the hybrid model; takes a few minutes)"
  python3 -m venv "$VENV" && "$PY" -m pip install -q --upgrade pip \
    && (cd "$ROOT" && "$PY" -m pip install -q -e ".[all]") || die "Install failed"
}

if [ "${1:-}" = "--setup" ]; then setup; say "Setup done. Now run ./run_demo.sh"; exit 0; fi
[ -x "$PY" ] || setup

if lsof -iTCP:$UI_PORT -sTCP:LISTEN >/dev/null 2>&1; then
  die "Port $UI_PORT is busy. Close the earlier demo, or run: UI_PORT=5060 ./run_demo.sh"
fi

say "Starting the S3T demo page on port $UI_PORT (Group 5: $GROUP5_URL, Group 7: $GROUP7_URL)"
(cd "$ROOT/integration" && PYTHONPATH=".:$ROOT" exec "$PY" ui_server.py --port $UI_PORT \
   --group5 "$GROUP5_URL" --group7 "$GROUP7_URL") > "$LOGS/demo.log" 2>&1 &
PID=$!
trap 'say "Stopping"; kill $PID 2>/dev/null; wait 2>/dev/null; exit 0' INT TERM
for _ in $(seq 1 120); do
  curl -s -o /dev/null "http://127.0.0.1:$UI_PORT/api/status" && break
  kill -0 $PID 2>/dev/null || die "Demo page failed to start. See $LOGS/demo.log"; sleep 1
done
say "Running: http://127.0.0.1:$UI_PORT   (log: logs/demo.log, Ctrl+C stops)"
command -v open >/dev/null && open "http://127.0.0.1:$UI_PORT"
wait $PID
