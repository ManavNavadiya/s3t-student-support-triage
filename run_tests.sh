#!/usr/bin/env bash
# Run every Group 6 test suite (Week 8 final testing).
#   ./run_tests.sh          S3T asset tests + verification report + integration tests
#   ./run_tests.sh --e2e    also the end-to-end check (start ./run_demo.sh in another terminal first)
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"; PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { echo "Environment missing: run ./run_demo.sh --setup first."; exit 1; }
FAILED=""; SUMMARY=""
run() { local name="$1"; shift; printf '\n\033[1m==> %s\033[0m\n' "$name"
  if (cd "$ROOT" && "$@"); then SUMMARY="$SUMMARY\n  PASS  $name"; else SUMMARY="$SUMMARY\n  FAIL  $name"; FAILED=1; fi; }

run "S3T asset tests (pytest)"            "$PY" -m pytest tests -q
run "S3T verification (contract + Week 5 regression)"  "$PY" -m s3t verify
run "Integration tests"                   env PYTHONPATH="integration:." "$PY" -m pytest integration/tests -q
if [ "${1:-}" = "--e2e" ]; then
  run "End-to-end check (running demo)"   "$PY" integration/e2e_check.py --out docs/e2e_results.md
fi
printf '\n\033[1mSummary\033[0m%b\n' "$SUMMARY"
[ -z "$FAILED" ] && echo "All suites passed." || { echo "Some suites failed (see above)."; exit 1; }
