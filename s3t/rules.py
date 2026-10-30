"""
rules.py - rule-based post-processing + human-review guardrail (Week 3 logic).

  R1  crisis language found           -> urgency = High, crisis action
  R2  deadline is today/tomorrow/...  -> urgency +1 level (unless already High)
  R3  low model confidence            -> human review (category and urgency checked
                                          against their own thresholds)
  R4  final urgency is High           -> human review

Review reasons are returned as stable machine-readable codes:
  crisis_language | high_urgency | low_category_confidence | low_urgency_confidence
"""
from .config import (URGENCY_LEVELS, ACTIONS, HIGH_URGENCY_PREFIX, CRISIS_ACTION)


def apply_rules(category: str, urgency: str, cat_conf: float, urg_conf: float,
                info: dict, cat_threshold: float, urg_threshold: float) -> dict:
    rules = []
    final_urgency = urgency

    if info["crisis_detected"]:
        if final_urgency != "High":
            rules.append("R1: crisis language detected -> urgency set to High")
        else:
            rules.append("R1: crisis language detected (urgency already High)")
        final_urgency = "High"
    elif info["imminent_deadline"] and final_urgency != "High":
        final_urgency = URGENCY_LEVELS[URGENCY_LEVELS.index(final_urgency) + 1]
        rules.append(f"R2: imminent deadline -> urgency raised to {final_urgency}")

    if info["crisis_detected"]:
        action = CRISIS_ACTION
    elif final_urgency == "High":
        action = HIGH_URGENCY_PREFIX + ACTIONS[category]
    else:
        action = ACTIONS[category]

    reasons = []
    if info["crisis_detected"]:
        reasons.append("crisis_language")
    if final_urgency == "High":
        reasons.append("high_urgency")
    if cat_conf < cat_threshold:
        reasons.append("low_category_confidence")
        rules.append(f"R3: category confidence {cat_conf:.2f} < {cat_threshold:.2f} -> human review")
    if urg_conf < urg_threshold:
        reasons.append("low_urgency_confidence")
        rules.append(f"R3: urgency confidence {urg_conf:.2f} < {urg_threshold:.2f} -> human review")

    return {"urgency": final_urgency, "action": action,
            "review_required": bool(reasons), "review_reasons": reasons,
            "rules_applied": rules}
