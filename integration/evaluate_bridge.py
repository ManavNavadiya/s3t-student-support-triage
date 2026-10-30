"""
Measure the early-warning decision (the bridge's at-risk flag) against human labels.

Input CSV columns:
    text        the student email (no names or student numbers)
    at_risk     your human label: yes / no   (would a staff member want to follow up on academic risk?)
  optional:
    topic       the topic the course SHOULD map to (e.g. "machine learning"); leave blank if no course is named

Run inside the S3T environment, from the integration folder (Group 7 is NOT needed):

    PYTHONPATH=. python evaluate_bridge.py --csv my_labelled_emails.csv --out reports/bridge_eval.md

The report gives precision, recall, F1 with 95% intervals, and lists every false positive and false negative
with the signals that fired, so the errors can be read and discussed (the "false-positive analysis").
Two people should label independently; report how often they agreed before using the labels.
"""
import argparse
import csv
import math
from pathlib import Path

from s3t_to_discovery import assess_risk, resolve_topic

YES = {"yes", "y", "true", "1", "at risk", "at_risk"}
NO = {"no", "n", "false", "0", "not at risk", "not_at_risk"}


def wilson(k: int, n: int, z: float = 1.96):
    """95% Wilson interval for a proportion k/n (honest about small samples)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    if n == 0:
        return "n/a (no cases)"
    lo, hi = wilson(k, n)
    return f"{k / n:.2f}  (95% interval {lo:.2f} to {hi:.2f}; {k}/{n})"


def short(t: str, width: int = 140) -> str:
    t = " ".join(t.split())
    return t if len(t) <= width else t[: width - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default="reports/bridge_eval.md")
    ap.add_argument("--model", default="auto", help="S3T model: auto | baseline | sbert+tfidf")
    ap.add_argument("--data-note", default="", help="one line describing the data, printed in the report "
                    "(e.g. 'synthetic, labelled by one person')")
    a = ap.parse_args()

    from s3t import Triage
    triage = Triage(model=a.model)

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    if not rows:
        raise SystemExit("The CSV has no rows.")
    missing = {"text", "at_risk"} - set(rows[0].keys())
    if missing:
        raise SystemExit(f"CSV is missing column(s): {', '.join(sorted(missing))}")

    tp = fp = fn = tn = 0
    fps, fns = [], []
    levels = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    topic_cases = topic_ok = 0
    topic_wrong = []
    for i, r in enumerate(rows, 1):
        text = (r["text"] or "").strip()
        label = (r["at_risk"] or "").strip().lower()
        if not text or label not in YES | NO:
            raise SystemExit(f"Row {i}: needs text and an at_risk label of yes/no (got {label!r}).")
        truth = label in YES
        s3t = triage.predict(text, id=f"eval-{i}").model_dump()
        ew = assess_risk(text, s3t)
        levels[ew.level] += 1
        if ew.at_risk and truth:
            tp += 1
        elif ew.at_risk and not truth:
            fp += 1
            fps.append((i, text, ew, s3t))
        elif not ew.at_risk and truth:
            fn += 1
            fns.append((i, text, ew, s3t))
        else:
            tn += 1
        want = (r.get("topic") or "").strip().lower()
        if want:
            topic_cases += 1
            got = (resolve_topic(text, s3t).topic or "").lower()
            if got == want:
                topic_ok += 1
            else:
                topic_wrong.append((i, want, got or "none"))

    n = len(rows)
    prec_n, rec_n = tp + fp, tp + fn
    f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else float("nan")
    out = [
        "# Early-warning decision: evaluation against human labels",
        "",
        f"S3T model: `{triage.model_name}` | messages: {n} | labelled at risk: {rec_n} | labelled not at risk: {n - rec_n}",
        "",
        *([f"**Data:** {a.data_note}", ""] if a.data_note else []),
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision (of those flagged, how many truly at risk) | {fmt(tp, prec_n)} |",
        f"| Recall (of those truly at risk, how many flagged) | {fmt(tp, rec_n)} |",
        f"| F1 | {f1:.2f} |",
        f"| Accuracy | {fmt(tp + tn, n)} |",
        f"| Flag levels given | HIGH {levels['HIGH']}, MEDIUM {levels['MEDIUM']}, LOW {levels['LOW']} |",
        "",
        "| | Flagged at risk | Not flagged |",
        "|---|---|---|",
        f"| **Truly at risk** | {tp} (true positive) | {fn} (false negative) |",
        f"| **Not at risk** | {fp} (false positive) | {tn} (true negative) |",
        "",
    ]
    if n < 100:
        out += [f"With only {n} messages the intervals above are wide; treat the figures as indicative.", ""]
    if topic_cases:
        out += [f"## Course → topic mapping", "",
                f"Correct topic for {topic_ok} of {topic_cases} messages that name a course.", ""]
        for i, want, got in topic_wrong:
            out.append(f"- Row {i}: expected `{want}`, got `{got}`")
        out.append("")

    def section(title, items, why):
        out.extend([f"## {title} ({len(items)})", ""])
        if not items:
            out.extend(["None.", ""])
            return
        out.extend([why, ""])
        for i, text, ew, s3t in items:
            out.extend([f"**Row {i}**: {short(text)}",
                        f"- S3T category: {s3t['category']['label']} ({s3t['category']['confidence']:.2f}); "
                        f"decision: {ew.level}; signals fired: {', '.join(ew.signals) or 'none'}", ""])

    section("False positives: flagged but not at risk", fps,
            "Read each one and note the cause (negation, a keyword used in a different sense, S3T category wrong).")
    section("False negatives: at risk but not flagged", fns,
            "These matter most. Note which wording the signals did not recognise.")

    out += ["## Notes", "",
            "- Labels come from the humans who wrote the CSV; the result is only as good as that labelling.",
            "- Do not edit the signal patterns to fix these errors and then report the same file as a fresh test.",
            ""]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:16]))
    print(f"\nFull report written to {a.out}")


if __name__ == "__main__":
    main()
