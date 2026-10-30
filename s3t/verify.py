"""
verify.py - one command that checks the asset works and still behaves like Week 5.

    python -m s3t verify            # writes reports/week6_verification.md (+ .json)

  A. Contract checks     output shape, probabilities, validation, batch == single, crisis rule,
                         privacy (message text not echoed), HTTP API (if fastapi + httpx installed)
  B. Regression          the packaged models, run through the new Triage class with the Week 5
                         settings (threshold 0.40, core crisis lexicon), must reproduce the
                         Week 5 numbers within the tolerance in resources/week5_reference.json
  C. Default settings    what a user of the asset gets out of the box (calibrated thresholds if
                         `calibrate` was run, extended crisis lexicon)
  D. Crisis lexicon      core vs extended: detections on the 3 challenge crisis messages and
                         false alarms on every message labelled non-crisis
  E. Performance         load time, single-message latency, batch throughput per model

Nothing here changes any file except the report.
"""
import json
import os
import platform
import statistics
import time
from datetime import datetime
from importlib import metadata
from pathlib import Path

from .classifier import available_models
from .config import (CATEGORIES, CHALLENGE_FILE, DEFAULT_REVIEW_THRESHOLD, MAX_TEXT_CHARS,
                     REFERENCE_FILE, TEST_FILE, URGENCY_LEVELS, __version__)
from .extraction import find_crisis
from .evaluation import evaluate_rows, predict_rows, read_rows, render_markdown
from .rules import apply_rules
from .schemas import TriageResult
from .triage import Triage

SAMPLE = [
    "Hi, I can't log in to Canvas and my STAT 230 quiz closes today. Please help!",
    "My financial aid still hasn't come through and there's a hold on my account.",
    "How do I request an official copy of my transcript? No rush.",
    "I am struggling with the workload in BIO 110 and feel overwhelmed.",
    "I need to update my mailing address with the registrar.",
    "I feel completely hopeless and I can't cope anymore.",
    "Wifi in the hostel keeps disconnecting, can someone from IT look at it?",
    "I lost my part-time job and cannot pay tuition this semester.",
    "Can I book an appointment with a counselor next week?",
    "My exam is tomorrow and I have not been able to access the course page.",
]


def _ver(pkg):
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "not installed"


# ------------------------------------------------------------------ A. contract
def contract_checks(model: str):
    checks = []

    def check(name, fn):
        try:
            detail = fn()
            checks.append((name, True, detail if isinstance(detail, str) else ""))
        except Exception as e:     # a failing check must not stop the others
            checks.append((name, False, f"{type(e).__name__}: {e}"))

    t = Triage(model=model)
    res = t.predict_batch(SAMPLE)

    def schema():
        for r in res:
            TriageResult.model_validate(r.model_dump())
        return f"{len(res)} results validate against the schema"

    def probs():
        for r in res:
            for sl, labels in ((r.category, CATEGORIES), (r.urgency, URGENCY_LEVELS)):
                assert set(sl.probabilities) == set(labels), "label set differs"
                assert abs(sum(sl.probabilities.values()) - 1) < 2e-3, "probabilities do not sum to 1"
                assert abs(sl.confidence - sl.probabilities[sl.model_label]) < 1e-4
                assert sl.confidence == max(sl.probabilities.values())
        return "label sets, sum = 1, confidence = max probability"

    def batch_vs_single():
        for text, b in zip(SAMPLE, res):
            s = t.predict(text)
            assert s.category.label == b.category.label and s.urgency.label == b.urgency.label
            assert abs(s.category.confidence - b.category.confidence) < 1e-3
        return "predict() and predict_batch() agree on 10 messages"

    def deterministic():
        assert t.predict(SAMPLE[0]).model_dump() == t.predict(SAMPLE[0]).model_dump()

    def validation():
        for bad in ("", "   ", "x" * (MAX_TEXT_CHARS + 1), None, 123):
            try:
                t.predict(bad)
            except ValueError:
                continue
            raise AssertionError(f"accepted invalid input {bad!r:.20}")
        assert t.predict_batch([]) == []
        return "empty / blank / too long / non-string rejected with ValueError"

    def crisis():
        r = t.predict("I want to hurt myself")
        assert r.crisis_detected and r.urgency.label == "High" and r.human_review.required
        assert "crisis_language" in r.human_review.reasons
        assert r.recommended_action.startswith("IMMEDIATE")

    def deadline_rule():
        info = {"crisis_detected": False, "imminent_deadline": True}
        out = apply_rules("Technical Support", "Low", 0.99, 0.99, info, 0.4, 0.4)
        assert out["urgency"] == "Medium" and not out["review_required"]
        out = apply_rules("Technical Support", "Low", 0.30, 0.99, info, 0.4, 0.4)
        assert out["review_reasons"] == ["low_category_confidence"]

    def privacy_and_id():
        secret = "zzqx7unique"
        r = t.predict(f"Please update my mailing address {secret}", id="ticket-42")
        assert r.id == "ticket-42"
        assert secret not in json.dumps(r.model_dump()), "message text was echoed back"

    def json_safe():
        json.dumps([r.model_dump() for r in res])

    for name, fn in [("Output matches the schema", schema), ("Probabilities are consistent", probs),
                     ("Batch equals single calls", batch_vs_single),
                     ("Deterministic", deterministic), ("Input validation", validation),
                     ("Crisis rule forces High + review", crisis),
                     ("Deadline and confidence rules", deadline_rule),
                     ("Message text is not echoed; id is", privacy_and_id),
                     ("Output is JSON-serialisable", json_safe)]:
        check(name, fn)

    def api():
        try:
            from fastapi.testclient import TestClient
            from .api import create_app
        except ImportError as e:
            return f"SKIPPED ({e.name} not installed; pip install 's3t[api]')"
        os.environ.pop("S3T_API_KEY", None)
        with TestClient(create_app(model)) as c:
            assert c.get("/health").json()["status"] == "ok"
            r = c.post("/v1/triage", json={"text": SAMPLE[0], "id": "a"})
            assert r.status_code == 200 and r.json()["id"] == "a"
            assert c.post("/v1/triage", json={"text": "  "}).status_code == 422
            b = c.post("/v1/triage/batch", json={"items": [{"text": s} for s in SAMPLE[:3]]})
            assert b.status_code == 200 and b.json()["count"] == 3
            assert c.post("/v1/triage/batch", json={"items": []}).status_code == 422
        os.environ["S3T_API_KEY"] = "k"
        try:
            with TestClient(create_app(model)) as c:
                assert c.post("/v1/triage", json={"text": "hi"}).status_code == 401
                assert c.post("/v1/triage", json={"text": "hi"},
                              headers={"X-API-Key": "k"}).status_code == 200
        finally:
            os.environ.pop("S3T_API_KEY", None)
        return "health, triage, batch, 422 validation, API key"
    check("HTTP API", api)
    return checks, t.model_name


# ------------------------------------------------------------------ B/C/D helpers
def _challenge_counts(m):
    return {"challenge_category_correct": round(m["category_accuracy"] * m["n_category"]),
            "challenge_urgency_correct": round(m["urgency_accuracy"] * m["n_urgency"]),
            "challenge_crisis_detected": m["crisis_detected"]}


def regression(models, test_rows, ch_rows, ref):
    tol, table = ref["tolerance"], []
    for name in models:
        if name not in ref["models"]:
            continue
        t = Triage(model=name, thresholds=(DEFAULT_REVIEW_THRESHOLD,) * 2, extended_crisis=False)
        mt, mc = evaluate_rows(t, test_rows), evaluate_rows(t, ch_rows)
        got = {"category_macro_f1": mt["category_macro_f1"], "urgency_macro_f1": mt["urgency_macro_f1"],
               "review_rate": mt["review_rate"], "silent_errors": mt["silent_errors"],
               **_challenge_counts(mc)}
        for k, want in ref["models"][name].items():
            tk = tol["macro_f1"] if k.endswith("f1") else tol["review_rate"] if k == "review_rate" else tol["count"]
            table.append({"model": name, "metric": k, "week5": want, "now": round(got[k], 3),
                          "tolerance": tk, "pass": abs(got[k] - want) <= tk + 1e-9})
    return table


def performance(models, texts):
    rows = []
    for name in models:
        t0 = time.perf_counter()
        t = Triage(model=name)
        load = time.perf_counter() - t0
        t.predict(texts[0])                                  # warm-up
        singles = []
        for s in (texts * 3)[:30]:
            a = time.perf_counter()
            t.predict(s)
            singles.append((time.perf_counter() - a) * 1000)
        batch = texts[:100]
        a = time.perf_counter()
        t.predict_batch(batch)
        dt = time.perf_counter() - a
        singles.sort()
        rows.append({"model": name, "load_s": round(load, 2),
                     "p50_ms": round(statistics.median(singles), 1),
                     "p95_ms": round(singles[int(0.95 * (len(singles) - 1))], 1),
                     "batch_msgs_per_s": round(len(batch) / dt, 1)})
    return rows


# ------------------------------------------------------------------ main
def run(report_dir="reports"):
    models = available_models()
    if not models:
        raise SystemExit("No usable model found. Check S3T_MODELS_DIR / installation.")
    test_rows, ch_rows = read_rows(TEST_FILE), read_rows(CHALLENGE_FILE)
    ref = json.loads(Path(REFERENCE_FILE).read_text())
    out = {"asset_version": __version__, "created": datetime.now().isoformat(timespec="seconds")}

    print("A. contract checks ...")
    checks, primary = contract_checks("auto")
    print("B. regression against Week 5 ...")
    reg = regression(models, test_rows, ch_rows, ref)

    print("C. default settings ...")
    t_def = Triage(model=primary)
    m_test, m_ch = evaluate_rows(t_def, test_rows), evaluate_rows(t_def, ch_rows)

    print("D. crisis lexicon ...")
    crisis = []
    for ext in (False, True):
        t = Triage(model=primary, extended_crisis=ext)
        mc = evaluate_rows(t, ch_rows)
        non_crisis = ([r for r in test_rows if not find_crisis(r["text"], False)]   # test set has no crisis column
                      + [r for r in ch_rows if r["crisis"] is False])
        fa = sum(x.crisis_detected for x in predict_rows(t, non_crisis))
        crisis.append({"lexicon": "extended" if ext else "core", "challenge_detected": mc["crisis_detected"],
                       "challenge_total": mc["crisis_total"], "false_alarms": fa,
                       "checked_non_crisis": len(non_crisis)})

    print("E. performance ...")
    perf = performance(models, [r["text"] for r in test_rows])

    ok_all = all(c[1] for c in checks if not c[2].startswith("SKIPPED")) and all(r["pass"] for r in reg)
    out.update({"contract": checks, "regression": reg, "default_test": m_test,
                "default_challenge": m_ch, "crisis": crisis, "performance": perf, "all_passed": ok_all})

    L = [f"# S3T asset {__version__} - verification report", "",
         f"Run {out['created']} | Python {platform.python_version()} on {platform.system()} | "
         f"scikit-learn {_ver('scikit-learn')} | sentence-transformers {_ver('sentence-transformers')} | "
         f"torch {_ver('torch')} | pydantic {_ver('pydantic')} | fastapi {_ver('fastapi')}", "",
         f"**Overall: {'ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED - see the tables'}**  "
         f"(models verified: {', '.join(models)}; default model in use: `{primary}`)", "",
         "## A. Contract checks", "", "| Check | Result | Detail |", "|---|---|---|"]
    L += [f"| {n} | {'PASS' if ok else ('SKIP' if d.startswith('SKIPPED') else 'FAIL')} | {d} |"
          for n, ok, d in checks]
    L += ["", "## B. Regression against the Week 5 report", "",
          "Same models and same data, run through the new `Triage` class with the Week 5 settings "
          "(review threshold 0.40, core crisis lexicon). Differences beyond the tolerance would mean "
          "the packaging changed the model's behaviour.", "",
          "| Model | Metric | Week 5 | This run | Tolerance | Result |", "|---|---|---|---|---|---|"]
    L += [f"| {r['model']} | {r['metric']} | {r['week5']} | {r['now']} | ±{r['tolerance']} | "
          f"{'PASS' if r['pass'] else 'FAIL'} |" for r in reg]
    L += ["", "## C. Out-of-the-box behaviour (default settings)", "",
          "Calibrated thresholds are used if `python -m s3t calibrate` has been run; otherwise 0.40 "
          "(see the thresholds line below). The test set was already used for design decisions in "
          "Weeks 4-5, so these numbers are not a fresh blind test.", "",
          render_markdown(m_test, "Held-out test set"),
          render_markdown(m_ch, "Hand-written challenge set (28 in scope + 2 out of scope)"),
          "## D. Crisis lexicon: core vs extended", "",
          "The extended phrases were written after the challenge set showed the gaps, so the "
          "challenge-set improvement is not an unbiased estimate. The false-alarm column is the "
          "cost: messages labelled non-crisis that the lexicon still flags.", "",
          "| Lexicon | Challenge crisis messages detected | False alarms on other messages |",
          "|---|---|---|"]
    L += [f"| {c['lexicon']} | {c['challenge_detected']} of {c['challenge_total']} | "
          f"{c['false_alarms']} of {c['checked_non_crisis']} |" for c in crisis]
    L += ["", "## E. Performance (this machine)", "",
          "| Model | Load time (s) | Single message p50 (ms) | p95 (ms) | Batch of 100 (messages/s) |",
          "|---|---|---|---|---|"]
    L += [f"| {p['model']} | {p['load_s']} | {p['p50_ms']} | {p['p95_ms']} | {p['batch_msgs_per_s']} |"
          for p in perf]
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    (Path(report_dir) / "week6_verification.md").write_text("\n".join(L))
    (Path(report_dir) / "week6_verification.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\n{'ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED'} -> {report_dir}/week6_verification.md")
    return ok_all
