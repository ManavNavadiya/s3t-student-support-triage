"""
s3t_to_discovery.py - bridge: Group 6 (S3T early-warning) -> Group 7 (Research Discovery),
with optional Group 5 (Student Feedback Intelligence) input.

Flow for the 31 Oct demo:
    student email --S3T--> category/urgency/courses --(this file)--> early-warning flag + topic
                                                     --Group 7 /api/v1/recommend--> faculty mentors
    student email --Group 5 (group5_feedback.py)--> course-experience concerns
                  --> shapes the suggested support + anonymised course-feedback item
                      (does NOT change the at-risk decision)

pipeline.run_pipeline() wires all three together.

Only the standard library is needed here. S3T and Group 7 stay separate processes
(or S3T can be imported in-process) so their dependencies never clash
(S3T: Python >=3.9, Group 7: Python >=3.12, Flask).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

CATALOG_PATH = Path(__file__).with_name("course_catalog.json")

# --- early-warning signals on top of S3T ------------------------------------------------
# S3T has no "at risk of failing" field, and its category can be wrong on this kind of
# email, so we add transparent keyword signals and report which ones fired.
SIGNALS = {
    "missed_assessment": re.compile(r"\b(?:miss(?:ed|ing)?|skipp?ed|could not (?:attend|write)|couldn'?t (?:attend|write))\b[^.?!]{0,40}\b(?:test|exam|quiz|m1|m2|midterm|mid-sem|assessment)\b", re.I),
    "missing_submissions": re.compile(r"\b(?:not (?:yet )?submitted|haven'?t submitted|did not submit|didn'?t submit|missed submitting|pending|overdue)\b[^.?!]{0,40}\b(?:assignments?|labs?|homework|projects?)\b|\b(?:assignments?|labs?)\b[^.?!]{0,30}\b(?:not (?:yet )?submitted|pending|overdue)\b", re.I),
    "passing_criteria_query": re.compile(r"\b(?:passing|pass)\s+(?:criteri\w+|marks?|percentage)\b|\binternal assessment\b|\bminimum marks\b", re.I),
    "fear_of_failing": re.compile(r"\b(?:fail(?:ing)?|detain(?:ed)?|backlog|worried about (?:my )?(?:grade|marks|result))\b", re.I),
}
MAKEUP_ASK = re.compile(r"\bmake-?up\b|\bre-?test\b|\bre-?exam\b|\bsupplementary\b", re.I)


@dataclass
class EarlyWarning:
    at_risk: bool
    level: str                      # "HIGH" | "MEDIUM" | "LOW"
    signals: list[str]
    suggested_intervention: str
    basis: str                      # why we decided this (for the demo audience)


@dataclass
class TopicResolution:
    topic: Optional[str]
    course_code: Optional[str]
    source: str                     # "override" | "catalog_code" | "catalog_alias" | "unresolved"


@dataclass
class MentorResult:
    rank: int
    name: str
    author_id: str
    score: float
    confidence: float
    confidence_level: str
    top_papers: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HandoffResult:
    student_id: Optional[str]
    s3t_category: str
    s3t_urgency: str
    s3t_human_review: bool
    early_warning: EarlyWarning
    topic: TopicResolution
    mentors: list[MentorResult]
    status: str                     # "ok" | "no_risk" | "needs_topic" | "group7_unavailable" | "group7_off"
    notes: list[str] = field(default_factory=list)
    course_experience: Optional[dict[str, Any]] = None   # Group 5 insight (FeedbackInsight.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- step 1: early warning ---------------------------------------------------------------
def assess_risk(text: str, s3t: dict[str, Any]) -> EarlyWarning:
    fired = [name for name, rx in SIGNALS.items() if rx.search(text)]
    academic_cat = s3t["category"]["label"] == "Academic Difficulty"
    # Two hard evidence signals; category / fear-of-failing only support a single one.
    hard = sum(s in fired for s in ("missed_assessment", "missing_submissions"))
    at_risk = hard == 2 or (hard == 1 and (academic_cat or "fear_of_failing" in fired))
    if hard == 2:
        level = "HIGH"
    elif at_risk:
        level = "MEDIUM"
    else:
        level = "LOW"
    if s3t.get("crisis_detected"):
        level, at_risk = "HIGH", True
        fired.append("crisis_language")
    if at_risk:
        parts = ["Faculty/mentor outreach and a check on eligibility for a make-up assessment"]
        if "passing_criteria_query" in fired:
            parts.append("reply to the passing-criteria question")
        if MAKEUP_ASK.search(text):
            parts.append("student explicitly asked about a make-up")
        if s3t.get("crisis_detected"):
            parts = ["IMMEDIATE human follow-up (crisis language) - do not auto-route"]
        intervention = "; ".join(parts)
    else:
        intervention = "No academic-risk action suggested."
    basis = (f"S3T category={s3t['category']['label']} ({s3t['category']['confidence']:.2f}); "
             f"text signals={fired or 'none'}")
    return EarlyWarning(at_risk, level, fired, intervention, basis)


# --- step 2: course -> topic -------------------------------------------------------------
def _norm_code(code: str) -> str:
    return re.sub(r"\s+", "", code).upper()


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["courses"]


def resolve_topic(text: str, s3t: dict[str, Any], catalog: Optional[dict] = None,
                  override: Optional[str] = None) -> TopicResolution:
    catalog = catalog if catalog is not None else load_catalog()
    if override:
        return TopicResolution(override.strip(), None, "override")
    for code in s3t["entities"]["courses"]:
        entry = catalog.get(_norm_code(code))
        if entry:
            return TopicResolution(entry["topic"], _norm_code(code), "catalog_code")
    low = text.lower()
    for code, entry in catalog.items():
        for alias in entry.get("aliases", []):
            if re.search(rf"\b{re.escape(alias.lower())}\b", low):
                return TopicResolution(entry["topic"], code, "catalog_alias")
    return TopicResolution(None, None, "unresolved")


# --- step 3: call Group 7 ----------------------------------------------------------------
def call_group7(topic: str, base_url: str = "http://127.0.0.1:8000", top_k: int = 5,
                timeout: float = 30.0) -> dict[str, Any]:
    """POST /api/v1/recommend (Group 7 Week 6 contract: query, top_k, include_evidence)."""
    body = json.dumps({"query": topic, "top_k": top_k, "include_evidence": True}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/api/v1/recommend", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def parse_mentors(resp: dict[str, Any]) -> list[MentorResult]:
    return [MentorResult(
        rank=r["rank"], name=r["name"], author_id=r["author_id"], score=r["score"],
        confidence=r["confidence"]["score"], confidence_level=r["confidence"]["level"],
        top_papers=[{"title": e["title"], "year": e["year"], "similarity": e["similarity"]}
                    for e in r.get("evidence", [])[:2]]) for r in resp.get("results", [])]


# --- orchestration -----------------------------------------------------------------------
def handoff(text: str, s3t_result: dict[str, Any], group7_url: str = "http://127.0.0.1:8000",
            topic_override: Optional[str] = None, top_k: int = 5,
            catalog: Optional[dict] = None, timeout: float = 30.0,
            feedback: Any = None) -> HandoffResult:
    """s3t_result = Triage().predict(text).model_dump()  (or the JSON from POST /v1/triage).

    feedback: optional group5_feedback.FeedbackInsight. It adds a support focus to the suggested
    intervention and an anonymised course-feedback item; it never changes at_risk or level."""
    ew = assess_risk(text, s3t_result)
    topic = resolve_topic(text, s3t_result, catalog, topic_override)
    course_exp = None
    if feedback is not None:
        from group5_feedback import course_feedback_item
        if ew.at_risk and feedback.support_focus and not s3t_result.get("crisis_detected"):
            ew.suggested_intervention += "; support focus (Group 5): " + "; ".join(feedback.support_focus)
        code = topic.course_code or (_norm_code(s3t_result["entities"]["courses"][0])
                                     if s3t_result["entities"]["courses"] else None)
        feedback.course_feedback_item = course_feedback_item(feedback, code)
        course_exp = feedback.to_dict()
    base = dict(student_id=s3t_result.get("id"), s3t_category=s3t_result["category"]["label"],
                s3t_urgency=s3t_result["urgency"]["label"],
                s3t_human_review=s3t_result["human_review"]["required"],
                early_warning=ew, topic=topic, mentors=[], course_experience=course_exp)
    notes: list[str] = []
    if s3t_result["category"]["confidence"] < 0.5 and ew.at_risk and \
            s3t_result["category"]["label"] != "Academic Difficulty":
        notes.append("S3T category disagrees with the text signals (low confidence); "
                     "risk decision rests on the text signals - staff should confirm.")
    if not ew.at_risk:
        return HandoffResult(**base, status="no_risk", notes=notes)
    if topic.topic is None:
        notes.append("No course topic found. Add the course to course_catalog.json or pass topic_override.")
        return HandoffResult(**base, status="needs_topic", notes=notes)
    if not group7_url or str(group7_url).strip().lower() == "off":
        notes.append("Mentor search (Group 7) is not connected; this is the topic it would search.")
        return HandoffResult(**base, status="group7_off", notes=notes)
    try:
        mentors = parse_mentors(call_group7(topic.topic, group7_url, top_k, timeout))
    except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError) as exc:
        notes.append(f"Group 7 call failed: {exc}")
        return HandoffResult(**base, status="group7_unavailable", notes=notes)
    base["mentors"] = mentors
    return HandoffResult(**base, status="ok", notes=notes)
