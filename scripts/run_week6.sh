#!/bin/bash
# Week 6: install, calibrate the review threshold, verify the asset, smoke-test the CLI.
# Run from the repository root.  Takes a few minutes (first run downloads ~90 MB).
set -e
cd "$(dirname "$0")/.."
pip install -e ".[all]"
python -m s3t calibrate            # -> s3t/resources/models/review_thresholds.json, reports/threshold_calibration.md
python -m s3t verify               # -> reports/week6_verification.md
pytest -q                          # fast unit tests
python -m s3t triage --file examples/sample_messages.csv --out reports/sample_output.jsonl
echo "Done. Send me reports/week6_verification.md, reports/threshold_calibration.md and the pytest output."
