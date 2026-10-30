"""
config.py - every setting of the asset in one place.

Environment variables (all optional):
    S3T_MODELS_DIR   folder with the *.joblib model files (default: packaged resources)
    S3T_ENCODER      sentence-encoder name OR a local folder path (for offline machines)
    S3T_MODEL        model used by the API: auto | baseline | sbert | sbert+tfidf
    S3T_API_KEY      if set, the API requires this value in the X-API-Key header
"""
import os
from pathlib import Path

__version__ = "1.0.0"
SCHEMA_VERSION = "1.0"          # bump when the JSON output shape changes

PACKAGE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = PACKAGE_DIR / "resources"
MODELS_DIR = Path(os.environ.get("S3T_MODELS_DIR", RESOURCES_DIR / "models"))
DATA_DIR = RESOURCES_DIR / "data"
TRAIN_FILE = DATA_DIR / "train.csv"
TEST_FILE = DATA_DIR / "test.csv"
CHALLENGE_FILE = DATA_DIR / "challenge_set.csv"
REFERENCE_FILE = RESOURCES_DIR / "week5_reference.json"
THRESHOLD_FILE_NAME = "review_thresholds.json"     # written by `python -m s3t calibrate`

# ---------- Labels ----------
CATEGORIES = [
    "Academic Difficulty",
    "Mental Health & Wellbeing",
    "Financial Aid",
    "Administrative",
    "Technical Support",
]
URGENCY_LEVELS = ["Low", "Medium", "High"]

# ---------- Models ----------
MODEL_NAMES = ["baseline", "sbert", "sbert+tfidf"]
DEFAULT_MODEL = "sbert+tfidf"   # the hybrid chosen in the Week 5 report
FALLBACK_MODEL = "baseline"     # used by model="auto" if the encoder is unavailable
SBERT_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# ---------- Confidence and human-review guardrail ----------
# Used when no calibrated threshold file exists. 0.40 is the Week 3 value; the Week 5
# report showed it is too low for the SBERT models, which is why `calibrate` exists.
DEFAULT_REVIEW_THRESHOLD = 0.40
# Urgency confidence is NOT used as a review trigger by default (threshold 0.0 never fires).
# Week 6 calibration showed the urgency score does not separate right from wrong answers
# (out-of-fold accuracy 0.64; at the only threshold meeting the 5% target, 74% of messages were
# flagged). Urgency is still protected by rule R4 (every High goes to a human) and R1 (crisis).
# Set to a value > 0 only if you have a better urgency model.
DEFAULT_URGENCY_REVIEW_THRESHOLD = 0.0
HIGH_CONFIDENCE = 0.90          # at or above this the Week 5 hybrid was right 99% of the time

# ---------- Input limits ----------
MAX_TEXT_CHARS = 2000
MAX_BATCH = 100

# ---------- Recommended actions ----------
ACTIONS = {
    "Academic Difficulty": "Academic advisor follow-up",
    "Mental Health & Wellbeing": "Refer to counseling / student wellbeing team",
    "Financial Aid": "Route to financial aid office",
    "Administrative": "Route to registrar / help desk",
    "Technical Support": "Route to IT help desk",
}
HIGH_URGENCY_PREFIX = "PRIORITY: contact student within 24 hours - "
CRISIS_ACTION = ("IMMEDIATE: escalate to on-call counselor / crisis team "
                 "and contact the student today")
DISCLAIMER = ("Advisory triage suggestion only. A staff member makes the final "
              "decision. No action is taken automatically.")