"""Run: PYTHONPATH=.:<path to S3T_Week6_Asset> python -m pytest tests -q
Uses a fake Group 7 server that follows their documented /api/v1/recommend contract."""
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from s3t_to_discovery import handoff, assess_risk, resolve_topic

EMAIL = ("Dear Professor, I missed the M1 test of Natural Language Processing (CS 521) because I was unwell, "
         "and I have also not submitted some of my assignments. I am worried about failing. "
         "Could you please tell me the passing criterion for internal assessment? Is a make-up test possible?")

def s3t_stub(label="Academic Difficulty", conf=0.8, courses=("CS 521",), crisis=False):
    return {"id": "t1", "category": {"label": label, "confidence": conf},
            "urgency": {"label": "Medium"}, "human_review": {"required": True},
            "entities": {"courses": list(courses)}, "crisis_detected": crisis}

class Fake(BaseHTTPRequestHandler):
    seen = []
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append((self.path, body))
        out = {"query": body["query"], "results": [{"rank": 1, "author_id": "A1", "name": "Dr. X", "score": 0.9,
               "confidence": {"score": 0.8, "level": "HIGH"}, "matched_papers": 3,
               "evidence": [{"title": "Paper", "year": "2020", "similarity": 0.91}]}]}
        b = json.dumps(out).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

@pytest.fixture(scope="module")
def g7():
    srv = HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"; srv.shutdown()

def test_demo_email_flags_risk_and_calls_group7(g7):
    r = handoff(EMAIL, s3t_stub(), g7)
    assert r.status == "ok" and r.early_warning.at_risk and r.early_warning.level == "HIGH"
    assert r.topic.topic == "natural language processing" and r.mentors[0].name == "Dr. X"
    assert Fake.seen[-1] == ("/api/v1/recommend", {"query": "natural language processing", "top_k": 5, "include_evidence": True})

def test_wrong_s3t_category_still_flagged_with_note(g7):
    r = handoff(EMAIL, s3t_stub("Technical Support", 0.44), g7)
    assert r.early_warning.at_risk and any("disagrees" in n for n in r.notes)

def test_routine_query_not_escalated(g7):
    n = len(Fake.seen)
    r = handoff("How do I get my transcript? No rush.", s3t_stub("Administrative", 0.9, ()), g7)
    assert r.status == "no_risk" and len(Fake.seen) == n

def test_unknown_course_needs_topic():
    r = handoff("I missed the M1 test and have not submitted assignments in ZZ 999.", s3t_stub(courses=("ZZ 999",)))
    assert r.status == "needs_topic"

def test_alias_and_override():
    assert resolve_topic("my NLP quiz", s3t_stub(courses=()), ).source == "catalog_alias"
    assert resolve_topic("x", s3t_stub(courses=()), override="graph neural networks").topic == "graph neural networks"

def test_group7_down_is_reported_not_raised():
    r = handoff(EMAIL, s3t_stub(), "http://127.0.0.1:9")
    assert r.status == "group7_unavailable"

def test_crisis_always_high():
    assert assess_risk("I feel hopeless", s3t_stub(crisis=True)).level == "HIGH"

def test_group7_off_reports_topic_without_calling():
    r = handoff(EMAIL, s3t_stub(), "off")
    assert r.status == "group7_off" and r.topic.topic == "natural language processing" and r.mentors == []
    assert r.early_warning.level == "HIGH"
