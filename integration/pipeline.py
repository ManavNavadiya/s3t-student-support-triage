"""
pipeline.py - the three-group flow in one call.

    student email
        -> Group 6  S3T triage            (is this student in trouble? category, urgency, course, crisis)
        -> Group 5  feedback intelligence  (what about the course is the problem? aspect sentiment)
        -> bridge   early-warning decision + course -> topic
        -> Group 7  research discovery     (who could mentor the student on this subject?)

Each group stays a separate component. Group 5 and Group 7 are reached over HTTP (Group 5 can
also run in-process); a failure in either is reported in the result, never raised.
"""
from __future__ import annotations

from typing import Any, Optional

from group5_feedback import analyse_feedback
from s3t_to_discovery import HandoffResult, handoff


def run_pipeline(text: str, s3t_result: dict[str, Any], *, group5=None,
                 group7_url: str = "http://127.0.0.1:8000", topic_override: Optional[str] = None,
                 top_k: int = 5, catalog: Optional[dict] = None, timeout: float = 30.0,
                 group5_timeout: float = 15.0) -> HandoffResult:
    """group5: a client from group5_feedback.make_group5(...) or None to leave Group 5 out."""
    feedback = analyse_feedback(text, group5, crisis=bool(s3t_result.get("crisis_detected")),
                                timeout=group5_timeout)
    result = handoff(text, s3t_result, group7_url, topic_override=topic_override, top_k=top_k,
                     catalog=catalog, timeout=timeout, feedback=feedback)
    if feedback.status in ("unavailable", "error"):
        result.notes.append("Group 5 not used for this message: " + "; ".join(feedback.warnings))
    return result
