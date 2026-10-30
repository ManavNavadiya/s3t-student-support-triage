"""Group 5 integration tests.

Run: PYTHONPATH=. python -m pytest tests -q
Uses fake Group 5 and Group 7 servers that follow their documented contracts, so no models are needed.
test_real_group5_in_process runs Group 5's real model when the Group5_Week7 folder sits next to integration/.
"""
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

from group5_feedback import (HttpGroup5, LocalGroup5, analyse_feedback, clean_for_group5, make_group5,
                             summarise)
from pipeline import run_pipeline
from s3t_to_discovery import handoff

EMAIL = ("Dear Professor, I missed the M1 test of Natural Language Processing (CS 521) because I was unwell, "
         "and I have also not submitted some of my assignments. I am worried about failing. "
         "Could you please tell me the passing criterion for internal assessment? Is a make-up test possible?")
G5_DIR = Path(__file__).resolve().parents[2] / "Group5_Week7"


def s3t_stub(label="Academic Difficulty", conf=0.8, courses=("CS 521",), crisis=False):
    return {"id": "stu-001", "category": {"label": label, "confidence": conf},
            "urgency": {"label": "Medium"}, "human_review": {"required": True},
            "entities": {"courses": list(courses)}, "crisis_detected": crisis}


def g5_result(aspects, overall=("negative", 0.74)):
    return {"id": "x", "status": "ok", "text": "...",
            "overall": {"label": overall[0], "confidence": overall[1], "low_confidence": overall[1] < 0.6,
                        "probabilities": {}},
            "aspects": [{"aspect": a, "sentiment": s, "confidence": c, "low_confidence": c < 0.6,
                         "clause": f"clause about {a}", "evidence": a.lower()} for a, s, c in aspects],
            "warnings": [], "meta": {}}


class FakeG5(BaseHTTPRequestHandler):
    seen = []
    reply = g5_result([("Pace", "negative", 0.70), ("Lectures", "negative", 0.70),
                       ("Exams/Grading", "positive", 0.52)])
    def do_GET(self):
        self._json(200, {"status": "ok"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeG5.seen.append((self.path, body))
        if not body.get("text", "").strip():
            return self._json(422, {"id": body.get("id"), "status": "error",
                                    "error": {"code": "EMPTY_TEXT", "message": "Text is empty."}})
        self._json(200, FakeG5.reply)
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass


class FakeG7(BaseHTTPRequestHandler):
    seen = []
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeG7.seen.append(body)
        out = {"query": body["query"], "results": [{"rank": 1, "author_id": "A1", "name": "Dr. X", "score": 0.9,
               "confidence": {"score": 0.8, "level": "HIGH"}, "evidence": [{"title": "P", "year": "2020", "similarity": 0.9}]}]}
        b = json.dumps(out).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass


def _serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


@pytest.fixture(scope="module")
def servers():
    s5, u5 = _serve(FakeG5); s7, u7 = _serve(FakeG7)
    yield u5, u7
    s5.shutdown(); s7.shutdown()


# --- cleaning / privacy -----------------------------------------------------------------
def test_clean_removes_greeting_signoff_and_ids():
    out, removed = clean_for_group5("Dear Professor, my roll no is 21BCE10234 and I missed the quiz.\nRegards,\nRahul")
    assert "Professor" not in out and "Rahul" not in out and "21BCE10234" not in out
    assert "missed the quiz" in out and "greeting" in removed and "sign-off" in removed


def test_clean_keeps_ordinary_text():
    t = "I did my best. I want to thank you for the help in CS 521."
    assert clean_for_group5(t) == (t, [])


def test_group5_gets_clean_text_and_random_id_and_group7_only_topic(servers):
    u5, u7 = servers
    run_pipeline(EMAIL + " Thanks,\nAsha", s3t_stub(), group5=HttpGroup5(u5), group7_url=u7)
    path, body = FakeG5.seen[-1]
    assert path == "/v1/analyze" and set(body) == {"id", "text"}
    assert body["id"].startswith("req-") and body["id"] != "stu-001"
    assert not body["text"].startswith("Dear") and "Asha" not in body["text"]
    assert FakeG7.seen[-1] == {"query": "natural language processing", "top_k": 5, "include_evidence": True}


# --- summarising Group 5 ----------------------------------------------------------------
def test_summarise_splits_confident_and_tentative():
    fi = summarise(g5_result([("Pace", "negative", 0.70), ("Assignments", "negative", 0.45),
                              ("Examples", "positive", 0.81), ("Pace", "negative", 0.40)]))
    assert fi.concerns == ["Pace"] and fi.tentative_concerns == ["Assignments"] and fi.strengths == ["Examples"]
    assert fi.support_focus == ["catch-up session or recorded lectures"]


def test_group5_rejection_is_reported(servers):
    u5, _ = servers
    fi = analyse_feedback("Dear Sir, Thanks,\nX", HttpGroup5(u5))   # empty after cleaning -> 422 from Group 5
    assert fi.status in ("error", "ok")      # never raises
    fi = summarise({"status": "error", "error": {"message": "Text is empty."}})
    assert fi.status == "error" and "empty" in fi.warnings[0]


# --- pipeline behaviour -----------------------------------------------------------------
def test_full_pipeline_adds_support_focus_and_course_item(servers):
    u5, u7 = servers
    r = run_pipeline(EMAIL, s3t_stub(), group5=HttpGroup5(u5), group7_url=u7)
    assert r.status == "ok" and r.early_warning.level == "HIGH" and r.mentors[0].name == "Dr. X"
    ce = r.course_experience
    assert ce["status"] == "ok" and set(ce["concerns"]) == {"Pace", "Lectures"}
    assert "support focus (Group 5)" in r.early_warning.suggested_intervention
    item = ce["course_feedback_item"]
    assert item["course_code"] == "CS521" and item["contains_text"] is False and "clause" not in json.dumps(item)


def test_group5_never_changes_risk_decision(servers):
    u5, u7 = servers
    for text, stub in [(EMAIL, s3t_stub()),
                       ("How do I get my transcript? No rush.", s3t_stub("Administrative", 0.9, ())),
                       ("I missed the quiz in CS 521.", s3t_stub("Technical Support", 0.6))]:
        a = handoff(text, stub, u7).early_warning
        b = run_pipeline(text, stub, group5=HttpGroup5(u5), group7_url=u7).early_warning
        assert (a.at_risk, a.level, a.signals) == (b.at_risk, b.level, b.signals)


def test_no_risk_still_gets_course_feedback(servers):
    u5, u7 = servers
    n7 = len(FakeG7.seen)
    r = run_pipeline("Some feedback on CS 521: the lectures are too fast.", s3t_stub("Administrative", 0.9),
                     group5=HttpGroup5(u5), group7_url=u7)
    assert r.status == "no_risk" and len(FakeG7.seen) == n7
    assert r.course_experience["course_feedback_item"]["concerns"] == ["Pace", "Lectures"]
    assert "support focus" not in r.early_warning.suggested_intervention


def test_group5_down_pipeline_continues(servers):
    _, u7 = servers
    r = run_pipeline(EMAIL, s3t_stub(), group5=HttpGroup5("http://127.0.0.1:9"), group7_url=u7)
    assert r.status == "ok" and r.course_experience["status"] == "unavailable"
    assert any(n.startswith("Group 5 not used") for n in r.notes)


def test_crisis_not_sent_to_group5(servers):
    u5, u7 = servers
    n = len(FakeG5.seen)
    r = run_pipeline("I feel hopeless and I missed the exam.", s3t_stub(crisis=True), group5=HttpGroup5(u5), group7_url=u7)
    assert r.course_experience["status"] == "skipped" and len(FakeG5.seen) == n
    assert r.early_warning.level == "HIGH" and "support focus" not in r.early_warning.suggested_intervention


def test_group5_off_and_old_handoff_unchanged(servers):
    _, u7 = servers
    assert make_group5("off") is None
    r = run_pipeline(EMAIL, s3t_stub(), group5=None, group7_url=u7)
    assert r.course_experience["status"] == "off"
    assert handoff(EMAIL, s3t_stub(), u7).course_experience is None   # Group 6 -> 7 path as before


@pytest.mark.skipif(not (G5_DIR / "feedback_nlp.py").exists(), reason="Group5_Week7 folder not next to integration/")
def test_real_group5_in_process():
    pytest.importorskip("sklearn")
    g5 = LocalGroup5(G5_DIR)
    fi = analyse_feedback("Hi, the lectures in CS 410 are far too fast and the examples do not help at all.", g5)
    assert fi.status == "ok" and "Pace" in fi.concerns and fi.overall["label"] == "negative"
