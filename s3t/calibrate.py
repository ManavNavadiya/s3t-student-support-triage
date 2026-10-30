"""
calibrate.py - choose the human-review confidence thresholds from the TRAINING data only.

Why: the Week 5 report found the old fixed threshold (0.40) almost never fires for the
SBERT models, so confidently-wrong messages reached nobody ("31 silent errors"), and
the 0.9 value that looked good was read off the test set. The fix recommended there was
to pick the threshold from grouped cross-validation on the training set and touch the
test set once. This script does that:

  1. Split the training messages into 5 folds, grouped by sentence template, so each
     validation fold contains wording the model has not seen (the same idea as the
     held-out test set).
  2. For each fold, refit the hybrid model (same features, same C as the shipped model)
     and record its confidence and whether it was right on the held-out fold.
  3. Choose the LOWEST threshold such that the share of messages that are wrong AND
     above the threshold (silent errors) is at most `--target` (default 5%).

Writes review_thresholds.json next to the models; Triage picks it up automatically.
Needs sentence-transformers (the hybrid model). Takes about a minute on a laptop CPU.

Urgency: the same procedure is run and the table is reported, but by default the urgency
score is NOT used as a review trigger (threshold written as 0.0). In Week 6 it was found
that the urgency score does not separate right from wrong answers, so the only threshold
that met the target flagged about three quarters of all messages. Urgency is protected
instead by rule R4 (every High goes to a human) and R1 (crisis language). Use
`--urgency-trigger` to switch the urgency trigger back on.

Limits (also printed in the report): the folds contain only as many distinct sentences
as the training set has; High urgency is flagged separately by rule R4, so counting
every low-confidence message as "flagged" is slightly conservative.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from .classifier import Bundle
from .config import MODELS_DIR, THRESHOLD_FILE_NAME, TRAIN_FILE, DEFAULT_MODEL
from .evaluation import read_rows
from .models import embed
from .preprocess import stem_text

SEED = 42
GRID = np.round(np.arange(0.30, 0.991, 0.01), 2)


def _oof(emb, stemmed, y, groups, C, folds):
    """Out-of-fold (confidence, correct) for one task."""
    conf = np.zeros(len(y))
    ok = np.zeros(len(y), dtype=bool)
    for tr, va in GroupKFold(n_splits=folds).split(emb, y, groups):
        tf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        Xtr = hstack([csr_matrix(emb[tr]), tf.fit_transform([stemmed[i] for i in tr])]).tocsr()
        Xva = hstack([csr_matrix(emb[va]), tf.transform([stemmed[i] for i in va])]).tocsr()
        clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced",
                                 random_state=SEED).fit(Xtr, y[tr])
        p = clf.predict_proba(Xva)
        conf[va] = p.max(axis=1)
        ok[va] = clf.classes_[p.argmax(axis=1)] == y[va]
    return conf, ok


def pick_threshold(conf, ok, target):
    for t in GRID:
        flagged = conf < t
        if float(((~ok) & (~flagged)).mean()) <= target:
            return float(t), True
    return float(GRID[-1]), False


def table(conf, ok, points=(0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)):
    rows = []
    for t in points:
        fl = conf < t
        rows.append({"threshold": t, "flag_rate": round(float(fl.mean()), 3),
                     "silent_error_rate": round(float(((~ok) & (~fl)).mean()), 3),
                     "accuracy_above": round(float(ok[~fl].mean()), 3) if (~fl).any() else None})
    return rows


def calibrate(models_dir=None, target=0.05, folds=5, report_dir="reports", urgency_trigger=False):
    models_dir = Path(models_dir or MODELS_DIR)
    bundle = Bundle(DEFAULT_MODEL, models_dir)          # reads encoder name and best C
    rows = read_rows(TRAIN_FILE)
    texts = [r["text"] for r in rows]
    groups = np.array([r["template"] for r in rows])
    print(f"Encoding {len(texts)} training messages with {bundle.encoder} ...")
    emb = embed(texts, bundle.encoder)
    stemmed = [stem_text(t) for t in texts]

    result = {}
    lines = [f"# Review-threshold calibration ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)", "",
             f"Model `{DEFAULT_MODEL}`, {folds}-fold GroupKFold on {len(texts)} training messages "
             f"({len(set(groups))} templates). Target: silent-error rate <= {target:.0%}. "
             f"The test set is not used.", ""]
    for task in ("category", "urgency"):
        y = np.array([r[task] for r in rows])
        C = bundle.models[task].best_C
        conf, ok = _oof(emb, stemmed, y, groups, C, folds)
        measured, reached = pick_threshold(conf, ok, target)
        use = task == "category" or urgency_trigger
        t = measured if use else 0.0                 # 0.0 = never flags
        result[task] = t
        result[f"{task}_detail"] = {
            "C": C, "target_silent_error_rate": target, "target_reached": reached,
            "out_of_fold_accuracy": round(float(ok.mean()), 3), "table": table(conf, ok),
            "used_as_review_trigger": use, "threshold_that_met_target": measured}
        if use:
            head = f"## {task}: threshold {t:.2f}" + ("" if reached else
                   "  (target NOT reachable; the highest grid value was used)")
        else:
            head = f"## {task}: NOT used as a review trigger (threshold written as 0.00)"
        lines += [head, ""]
        if not use:
            lines += [f"The threshold that met the {target:.0%} target would be {measured:.2f}, "
                      f"but it is not used: the score does not separate right answers from wrong "
                      f"ones (see the last column, which should rise with the threshold and does "
                      f"not). A message with a high-urgency prediction is still reviewed by rule "
                      f"R4 and crisis language by rule R1. Re-run with `--urgency-trigger` to "
                      f"override.", ""]
        lines += [f"Out-of-fold accuracy {ok.mean():.3f} (C = {C}).", "",
                  "| Threshold | Flagged | Silent errors | Accuracy of unflagged |", "|---|---|---|---|"]
        lines += [f"| {r['threshold']:.2f} | {r['flag_rate']:.0%} | {r['silent_error_rate']:.1%} | "
                  f"{r['accuracy_above']} |" for r in result[f"{task}_detail"]["table"]] + [""]
        if use:
            print(f"[{task}] out-of-fold accuracy {ok.mean():.3f} -> threshold {t:.2f}"
                  f"{'' if reached else '  (target not reachable)'}")
        else:
            print(f"[{task}] out-of-fold accuracy {ok.mean():.3f} -> not used as a review "
                  f"trigger (would have been {measured:.2f})")

    existing = {}
    out = models_dir / THRESHOLD_FILE_NAME
    if out.exists():
        try:
            existing = json.loads(out.read_text())
        except ValueError:
            existing = {}
    result.update({"method": f"{folds}-fold GroupKFold on training set, target silent-error "
                             f"rate {target}; urgency trigger "
                             f"{'on' if urgency_trigger else 'off'}", "created": datetime.now(timezone.utc).isoformat()})
    existing[DEFAULT_MODEL] = result
    out.write_text(json.dumps(existing, indent=2))
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    rp = Path(report_dir) / "threshold_calibration.md"
    rp.write_text("\n".join(lines))
    print(f"Saved {out}\nSaved {rp}")
    return result