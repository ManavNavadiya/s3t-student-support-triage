"""
Group 6 demo page: S3T triage + early-warning decision, with optional partner components
(Group 5 course feedback, Group 7 mentor discovery) reached over HTTP when they are running.

Run inside the S3T virtual environment (standard library only, nothing extra to install):

    cd integration
    PYTHONPATH=.:.. python ui_server.py                     # Group 6 only (partners off)
    # with partner services running (optional):
    PYTHONPATH=.:.. python ui_server.py --group7 http://127.0.0.1:8080 --group5 http://127.0.0.1:8002
    open http://127.0.0.1:5050

Partner services are optional; with them off the page shows Group 6's result and says what would be sent.
"""
import argparse
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from group5_feedback import HttpGroup5, make_group5
from pipeline import run_pipeline

HERE = Path(__file__).resolve().parent
INDEX = HERE / "static" / "index.html"
MAX_TEXT = 2000          # S3T input limit
STATE = {"triage": None, "group7": "off", "timeout": 180.0, "group5": None}


def s3t_summary(r: dict) -> dict:
    return {
        "category": r["category"], "urgency": r["urgency"], "confidence_band": r["confidence_band"],
        "recommended_action": r["recommended_action"], "entities": r["entities"], "emotions": r["emotions"],
        "crisis_detected": r["crisis_detected"], "human_review": r["human_review"],
        "model": r["meta"]["model"], "warnings": r["meta"]["warnings"],
    }


def group7_health(base: str) -> str:
    if not base or base.strip().lower() == "off":
        return "off"
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/v1/health", timeout=3) as r:
            return json.load(r).get("status", "unknown")
    except Exception:
        return "unreachable"


def analyze(body: dict) -> dict:
    text = str(body.get("text", "")).strip()
    if not text:
        raise ValueError("Paste a student email first.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Email is {len(text)} characters; the limit is {MAX_TEXT}.")
    g7 = (body.get("group7_url") or STATE["group7"]).strip()
    override = (body.get("topic_override") or "").strip() or None
    g5 = STATE["group5"]
    g5_url = (body.get("group5_url") or "").strip()
    if g5_url:                        # typed under "Advanced": an HTTP address or "off"
        if g5_url.lower() == "off":
            g5 = None
        elif not g5_url.lower().startswith("local:") and (g5 is None or g5.label != g5_url.rstrip("/")):
            g5 = HttpGroup5(g5_url)
    s3t = STATE["triage"].predict(text, id=body.get("student_id") or "demo-student").model_dump()
    result = run_pipeline(text, s3t, group5=g5, group7_url=g7, topic_override=override, top_k=5,
                          timeout=STATE["timeout"])
    return {"s3t": s3t_summary(s3t), "handoff": result.to_dict()}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/status"):
            g5 = STATE["group5"]
            self._send(200, {"s3t_model": STATE["triage"].model_name, "group7": group7_health(STATE["group7"]),
                             "group7_url": STATE["group7"],
                             "group5": g5.health() if g5 else "off",
                             "group5_source": g5.label if g5 else "off"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/analyze":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, analyze(body))
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:   # keep the demo alive, show the reason
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *a):     # do not log student text or paths
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group7", default="off", help="Group 7 base URL, or off (default)")
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--model", default="auto", help="S3T model: auto | baseline | sbert+tfidf")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--group5", default="off",
                    help="Group 5: HTTP base URL | local:<Group5 folder> (in-process) | off")
    a = ap.parse_args()
    from s3t import Triage
    STATE.update(triage=Triage(model=a.model), group7=a.group7, timeout=a.timeout,
                 group5=make_group5(a.group5))
    g5 = STATE["group5"]
    print(f"S3T model: {STATE['triage'].model_name} | Group 5: {g5.label if g5 else 'off'} | Group 7: {a.group7}")
    print(f"Open http://127.0.0.1:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
