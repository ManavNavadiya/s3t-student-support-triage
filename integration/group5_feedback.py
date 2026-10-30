"""
group5_feedback.py - bridge to Group 5 (Student Feedback Intelligence).

Role in the pipeline: a *course-experience lens*. Group 6 decides whether the student is at
risk; Group 5 says which part of the course the student is unhappy about (pace, lectures,
assignments, exams, ...). That shapes the suggested support and produces an anonymised
course-feedback item for the course coordinator. Group 5 does NOT change the at-risk decision:
its model was trained on course reviews (RateMyProfessor), and on help-request emails its
confidence is mostly below its own 0.60 review threshold (see INTEGRATION.md, "Why Group 5
does not decide risk").

Two ways to reach Group 5, both using its Week 6 contract ({"id", "text"} -> FeedbackResult):
    * HTTP:        python api.py --port 8002            (in the Group 5 folder)  -> "http://127.0.0.1:8002"
    * in-process:  "local:<path to Group5_Week7 folder>" (imports feedback_nlp; needs numpy, joblib, scikit-learn)

Standard library only (the in-process mode imports Group 5's own module).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_URL = "http://127.0.0.1:8002"
CONFIDENCE_THRESHOLD = 0.60          # Group 5's own low-confidence threshold

# Aspect -> support a staff member could offer. Advisory text only.
SUPPORT_FOCUS = {
    "Pace": "catch-up session or recorded lectures",
    "Lectures": "catch-up session or recorded lectures",
    "Teaching Quality": "tutor or TA session to re-explain the material",
    "Examples": "share worked examples / practice problems",
    "Assignments": "agree a submission plan or extension for pending assignments",
    "Workload": "review the student's workload and deadlines with them",
    "Exams/Grading": "explain the assessment and make-up policy",
    "Availability/Helpfulness": "offer a fixed office-hours slot",
}

# --- data minimisation before anything leaves Group 6's side ---------------------------
_GREETING = re.compile(
    r"^\s*(?:dear|hi|hello|hey|respected|good\s+(?:morning|afternoon|evening))\b[^,\n.!:]{0,40}[,\n.!:]\s*",
    re.I)
_SIGNOFF = re.compile(
    r"[.!?\n]\s*(?:(?:best|kind|warm)\s+regards|regards|thanks(?:\s+and\s+regards)?|thank\s+you|"
    r"sincerely|yours\s+(?:truly|sincerely|faithfully)|best\s+wishes)\s*[,!.\-]*\s*(?:\n|$)[\s\S]{0,80}$",
    re.I)
_ROLL_NO = re.compile(r"\b(?=(?:[A-Za-z]*\d){5})[A-Za-z0-9]{6,}\b")   # 5+ digits: roll / student numbers


def clean_for_group5(text: str) -> tuple[str, list[str]]:
    """Strip greeting / sign-off (names live there, and 'Dear Professor' falsely triggers the
    'Teaching Quality' aspect) and mask roll-number-like tokens. Group 5 also masks emails,
    URLs and phone numbers itself. Returns (clean_text, list of what was removed)."""
    removed: list[str] = []
    out = text.strip()
    m = _GREETING.match(out)
    if m and len(out) - m.end() > 10:
        out = out[m.end():]
        removed.append("greeting")
    m = _SIGNOFF.search(out)
    if m and m.start() > 10:
        out = out[:m.start() + 1].rstrip()
        removed.append("sign-off")
    out, n = _ROLL_NO.subn("[ID]", out)
    if n:
        removed.append(f"{n} id-like number(s)")
    return out.strip(), removed


# --- result shape ------------------------------------------------------------------------
@dataclass
class AspectView:
    aspect: str
    sentiment: str
    confidence: float
    confident: bool                 # confidence >= CONFIDENCE_THRESHOLD
    clause: str


@dataclass
class FeedbackInsight:
    status: str                     # "ok" | "unavailable" | "off" | "skipped" | "error"
    overall: Optional[dict[str, Any]] = None        # label, confidence, low_confidence
    aspects: list[AspectView] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)          # confident negative aspects
    tentative_concerns: list[str] = field(default_factory=list)  # negative but low-confidence
    strengths: list[str] = field(default_factory=list)         # confident positive aspects
    support_focus: list[str] = field(default_factory=list)
    course_feedback_item: Optional[dict[str, Any]] = None      # anonymised, for the coordinator
    removed_before_sending: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = ""                # where Group 5 ran (URL or "in-process")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def summarise(result: dict[str, Any], threshold: float = CONFIDENCE_THRESHOLD) -> FeedbackInsight:
    """Turn Group 5's FeedbackResult into what staff need. Raises KeyError/ValueError on a bad shape."""
    if result.get("status") != "ok":
        err = (result.get("error") or {}).get("message", "unknown error")
        return FeedbackInsight(status="error", warnings=[f"Group 5 rejected the text: {err}"])
    ov = result["overall"]
    aspects = [AspectView(a["aspect"], a["sentiment"], float(a["confidence"]),
                          float(a["confidence"]) >= threshold, a.get("clause", ""))
               for a in result.get("aspects", [])]
    # An aspect counts once; if it appears in several clauses keep its most confident reading.
    best: dict[str, AspectView] = {}
    for a in aspects:
        if a.aspect not in best or a.confidence > best[a.aspect].confidence:
            best[a.aspect] = a
    concerns = [a.aspect for a in best.values() if a.sentiment == "negative" and a.confident]
    tentative = [a.aspect for a in best.values() if a.sentiment == "negative" and not a.confident]
    strengths = [a.aspect for a in best.values() if a.sentiment == "positive" and a.confident]
    return FeedbackInsight(
        status="ok",
        overall={"label": ov["label"], "confidence": ov["confidence"],
                 "low_confidence": bool(ov.get("low_confidence", ov["confidence"] < threshold))},
        aspects=aspects, concerns=concerns, tentative_concerns=tentative, strengths=strengths,
        support_focus=_uniq(SUPPORT_FOCUS[c] for c in concerns if c in SUPPORT_FOCUS),
        warnings=[w for w in result.get("warnings", [])],
    )


# --- transport ---------------------------------------------------------------------------
class LocalGroup5:
    """Run Group 5's FeedbackAnalyzer in this process (no second server)."""

    def __init__(self, folder: str | Path):
        folder = Path(folder).expanduser().resolve()
        if not (folder / "feedback_nlp.py").exists():
            raise FileNotFoundError(f"feedback_nlp.py not found in {folder}")
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
        import warnings
        from feedback_nlp import FeedbackAnalyzer       # Group 5's module
        with warnings.catch_warnings():                  # sklearn version-mismatch warnings
            warnings.simplefilter("ignore")
            self.analyzer = FeedbackAnalyzer.load(str(folder / "artifacts"))
        self.label = "in-process"

    def analyze(self, text: str, request_id: str, timeout: float = 30.0) -> dict[str, Any]:
        return self.analyzer.analyze(text, request_id)

    def health(self) -> str:
        return "ok"


class HttpGroup5:
    def __init__(self, base_url: str = DEFAULT_URL):
        self.base = base_url.rstrip("/")
        self.label = self.base

    def analyze(self, text: str, request_id: str, timeout: float = 30.0) -> dict[str, Any]:
        """POST /v1/analyze. Group 5 answers 422 (with a JSON body) for text it rejects."""
        body = json.dumps({"id": request_id, "text": text}).encode()
        req = urllib.request.Request(self.base + "/v1/analyze", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):
                return json.load(exc)
            raise

    def health(self) -> str:
        try:
            with urllib.request.urlopen(self.base + "/health", timeout=3) as r:
                return json.load(r).get("status", "unknown")
        except Exception:
            return "unreachable"


def make_group5(spec: Optional[str]):
    """'off' / '' -> None;  'local:<folder>' -> LocalGroup5;  otherwise an HTTP base URL."""
    if not spec or spec.strip().lower() in ("off", "none", "no"):
        return None
    spec = spec.strip()
    if spec.lower().startswith("local:"):
        return LocalGroup5(spec[6:])
    return HttpGroup5(spec)


def analyse_feedback(text: str, client, *, crisis: bool = False, timeout: float = 30.0,
                     threshold: float = CONFIDENCE_THRESHOLD) -> FeedbackInsight:
    """Clean the email, send it to Group 5 under a random request id, summarise the result.
    Never raises: failures come back as status 'unavailable' / 'error'."""
    if client is None:
        return FeedbackInsight(status="off")
    if crisis:
        return FeedbackInsight(status="skipped", warnings=[
            "Crisis language: not sent to Group 5. A person must read this message directly."])
    clean, removed = clean_for_group5(text)
    request_id = "req-" + uuid.uuid4().hex[:10]   # never the student id
    try:
        raw = client.analyze(clean, request_id, timeout)
        fi = summarise(raw, threshold)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return FeedbackInsight(status="unavailable", source=client.label,
                               warnings=[f"Group 5 call failed: {exc}"])
    except (KeyError, ValueError, TypeError) as exc:
        return FeedbackInsight(status="error", source=client.label,
                               warnings=[f"Group 5 returned an unexpected response: {exc}"])
    fi.removed_before_sending = removed
    fi.source = client.label
    return fi


def course_feedback_item(fi: FeedbackInsight, course_code: Optional[str]) -> Optional[dict[str, Any]]:
    """Anonymised item for the course coordinator's Group 5 report: aspects and labels only,
    no text, no student id. Only built from confident readings and when the course is known."""
    if fi.status != "ok" or not course_code or not (fi.concerns or fi.strengths):
        return None
    return {"course_code": course_code, "concerns": fi.concerns, "strengths": fi.strengths,
            "source": "group5-feedback-intelligence", "contains_text": False}
