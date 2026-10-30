"""
evaluation.py - score the asset on any labelled CSV (used by `s3t evaluate` and `s3t verify`).

CSV needs a text column and, for scoring, a category and/or urgency column. Optional
columns: `template` (groups of repeated sentences) and `crisis` (True/False).
Rows whose category is not one of the five categories (e.g. "Out of scope") are kept
for the review/crisis numbers but left out of category/urgency accuracy.
"""
import csv
from collections import Counter
from typing import Dict, List

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, f1_score

from .config import CATEGORIES, MAX_BATCH, URGENCY_LEVELS


def read_rows(path, text_col="text", category_col="category", urgency_col="urgency",
              crisis_col="crisis", template_col="template") -> List[Dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if text_col not in (reader.fieldnames or []):
            raise ValueError(f"column '{text_col}' not found; columns are {reader.fieldnames}")
        for r in reader:
            if not (r.get(text_col) or "").strip():
                continue
            rows.append({
                "text": r[text_col].strip(),
                "category": (r.get(category_col) or "").strip() or None,
                "urgency": (r.get(urgency_col) or "").strip() or None,
                "crisis": ((r.get(crisis_col) or "").strip().lower() == "true")
                          if crisis_col in r and (r.get(crisis_col) or "").strip() else None,
                "template": (r.get(template_col) or "").strip() or None})
    return rows


def predict_rows(triage, rows):
    out = []
    for i in range(0, len(rows), MAX_BATCH):
        out += triage.predict_batch([r["text"] for r in rows[i:i + MAX_BATCH]])
    return out


def evaluate_rows(triage, rows: List[Dict]) -> Dict:
    results = predict_rows(triage, rows)
    m = {"n": len(rows), "model": triage.model_name,
         "thresholds": {"category": triage.cat_threshold, "urgency": triage.urg_threshold},
         "review_rate": float(np.mean([r.human_review.required for r in results]))}

    # ---- category
    idx = [i for i, r in enumerate(rows) if r["category"] in CATEGORIES]
    m["n_out_of_scope"] = sum(1 for r in rows if r["category"] and r["category"] not in CATEGORIES)
    if idx:
        y = [rows[i]["category"] for i in idx]
        p = [results[i].category.label for i in idx]
        conf = np.array([results[i].category.confidence for i in idx])
        ok = np.array([a == b for a, b in zip(y, p)])
        flagged = np.array([results[i].human_review.required for i in idx])
        m["n_category"] = len(idx)
        m["category_accuracy"] = float(accuracy_score(y, p))
        m["category_macro_f1"] = float(f1_score(y, p, labels=CATEGORIES, average="macro",
                                                zero_division=0))
        m["category_report"] = classification_report(y, p, labels=CATEGORIES, zero_division=0)
        m["silent_errors"] = int((~ok & ~flagged).sum())
        m["wrong_but_flagged"] = int((~ok & flagged).sum())
        bins = [(0, .5), (.5, .7), (.7, .9), (.9, 1.0001)]
        m["calibration"] = [
            {"bin": f"{lo:.1f}-{min(hi, 1):.1f}", "n": int(sel.sum()),
             "mean_confidence": round(float(conf[sel].mean()), 3),
             "accuracy": round(float(ok[sel].mean()), 3)}
            for lo, hi in bins for sel in [(conf >= lo) & (conf < hi)] if sel.any()]
        if any(rows[i]["template"] for i in idx):
            by = {}
            for i, good in zip(idx, ok):
                by.setdefault(rows[i]["template"], []).append(bool(good))
            m["n_templates"] = len(by)
            m["templates_with_category_error"] = sum(1 for v in by.values() if not all(v))

    # ---- urgency
    uidx = [i for i, r in enumerate(rows) if r["urgency"] in URGENCY_LEVELS
            and r["category"] in (CATEGORIES + [None])]
    if uidx:
        y = [rows[i]["urgency"] for i in uidx]
        p = [results[i].urgency.label for i in uidx]
        m["n_urgency"] = len(uidx)
        m["urgency_accuracy"] = float(accuracy_score(y, p))
        m["urgency_macro_f1"] = float(f1_score(y, p, labels=URGENCY_LEVELS, average="macro",
                                               zero_division=0))
        tp = sum(a == "High" and b == "High" for a, b in zip(y, p))
        m["high_recall"] = tp / max(1, sum(a == "High" for a in y))
        m["high_precision"] = tp / max(1, sum(b == "High" for b in p))
        uflag = [results[i].human_review.required for i in uidx]
        m["silent_urgency_errors"] = sum(a != b and not f for a, b, f in zip(y, p, uflag))
        m["wrong_urgency_but_flagged"] = sum(a != b and f for a, b, f in zip(y, p, uflag))
        m["true_high_missed_unflagged"] = sum(a == "High" and b != "High" and not f
                                              for a, b, f in zip(y, p, uflag))
        m["n_true_high"] = sum(a == "High" for a in y)
        if any(rows[i]["template"] for i in uidx):
            by = {}
            for i, a, b in zip(uidx, y, p):
                by.setdefault(rows[i]["template"], []).append(a == b)
            m["templates_with_urgency_error"] = sum(1 for v in by.values() if not all(v))

    # ---- crisis
    crisis_rows = [i for i, r in enumerate(rows) if r["crisis"] is not None]
    if crisis_rows:
        pos = [i for i in crisis_rows if rows[i]["crisis"]]
        neg = [i for i in crisis_rows if not rows[i]["crisis"]]
        m["crisis_detected"] = sum(results[i].crisis_detected for i in pos)
        m["crisis_total"] = len(pos)
        m["crisis_false_alarms"] = sum(results[i].crisis_detected for i in neg)
        m["crisis_distinct_texts"] = len({rows[i]["text"] for i in pos})
    m["confidence_bands"] = dict(Counter(r.confidence_band for r in results))
    return m


def render_markdown(m: Dict, title: str) -> str:
    L = [f"## {title}", "",
         f"Model `{m['model']}`; review thresholds category {m['thresholds']['category']:.2f} / "
         f"urgency {m['thresholds']['urgency']:.2f}"
         + (" (urgency score not used as a trigger)" if m['thresholds']['urgency'] <= 0 else "")
         + f"; n = {m['n']} messages"
         + (f" ({m['n_out_of_scope']} out of scope)" if m.get("n_out_of_scope") else "") + ".", ""]
    rows = []
    if "category_accuracy" in m:
        rows += [("Category accuracy", f"{m['category_accuracy']:.3f}"),
                 ("Category macro-F1", f"{m['category_macro_f1']:.3f}")]
        if "n_templates" in m:
            rows.append(("Templates with a category error",
                         f"{m['templates_with_category_error']} of {m['n_templates']}"))
    if "urgency_accuracy" in m:
        rows += [("Urgency accuracy", f"{m['urgency_accuracy']:.3f}"),
                 ("Urgency macro-F1", f"{m['urgency_macro_f1']:.3f}"),
                 ("High-urgency recall / precision", f"{m['high_recall']:.3f} / {m['high_precision']:.3f}")]
        rows += [("Silent urgency errors (wrong, not flagged)", str(m["silent_urgency_errors"])),
                 ("Truly High but predicted lower and not flagged",
                  f"{m['true_high_missed_unflagged']} of {m['n_true_high']}")]
        if "templates_with_urgency_error" in m:
            rows.append(("Templates with an urgency error",
                         f"{m['templates_with_urgency_error']} of {m['n_templates']}"))
    rows.append(("Flagged for human review", f"{m['review_rate']:.0%}"))
    if "silent_errors" in m:
        rows += [("Silent category errors (wrong, not flagged)", str(m["silent_errors"])),
                 ("Wrong but flagged", str(m["wrong_but_flagged"]))]
    if "crisis_total" in m:
        rows.append(("Crisis messages detected",
                     f"{m['crisis_detected']} of {m['crisis_total']} "
                     f"({m['crisis_distinct_texts']} distinct); false alarms: {m['crisis_false_alarms']}"))
    rows.append(("Confidence bands (high / medium / low)",
                 " / ".join(str(m["confidence_bands"].get(b, 0)) for b in ("high", "medium", "low"))))
    L += ["| Metric | Value |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows] + [""]
    if m.get("calibration"):
        L += ["Calibration of category confidence:", "",
              "| Confidence | Messages | Mean confidence | Actual accuracy |", "|---|---|---|---|"]
        L += [f"| {c['bin']} | {c['n']} | {c['mean_confidence']} | {c['accuracy']} |"
              for c in m["calibration"]] + [""]
    if m.get("category_report"):
        L += ["Per-class category report:", "", "```", m["category_report"].rstrip(), "```", ""]
    return "\n".join(L)