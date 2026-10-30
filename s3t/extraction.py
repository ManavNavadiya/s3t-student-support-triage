"""
extraction.py - rule-based information extraction + crisis detection (Week 3,
unchanged except for the optional extended crisis lexicon described below).

  courses          e.g. "CS101", "MATH 204"
  deadlines        e.g. "friday", "tomorrow", "12/05"
  blockers         e.g. "account / registration hold"
  emotions         e.g. "anxiety", "hopelessness"
  crisis_matches   the crisis phrases found (empty list = none)

Crisis lexicons
  core      the Week 3 phrase list. Using only this reproduces Week 5 behaviour exactly.
  extended  core + indirect phrasing ("don't want to live like this", "if I disappeared").
            The extra phrases were written AFTER the Week 5 challenge set exposed them, so
            their effect on that set is not an unbiased estimate. They have only been
            checked on the three messages that motivated them. Phrases such as
            "don't want to live" are guarded against common harmless continuations
            ("...in the hostel") but will still produce some false alarms; a false
            alarm costs a staff member a minute, a miss can cost far more.
"""
import re

COURSE_PATTERNS = [re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b"),
                   re.compile(r"\b([a-z]{2,4})(\d{3})\b")]

DEADLINE_PATTERN = re.compile(
    r"\b(today|tonight|tomorrow|this week|next week|in an hour|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", re.IGNORECASE)

IMMINENT = {"today", "tonight", "tomorrow", "in an hour"}

BLOCKERS = {
    "hold": "account / registration hold",
    "tuition": "tuition payment",
    "disburse": "financial aid disbursement",
    "aid": "financial aid",
    "scholarship": "scholarship",
    "rent": "housing cost",
    "evict": "housing / eviction",
    "food": "food insecurity",
    "visa": "visa / enrollment status",
    "transcript": "transcript",
    "enrollment letter": "enrollment letter",
    "prerequisite": "prerequisite error",
    "log in": "login / access issue",
    "locked out": "login / access issue",
    "password": "login / access issue",
    "canvas": "LMS (Canvas)",
    "lms": "LMS",
    "portal": "portal / system error",
    "crash": "portal / system error",
    "probation": "academic probation",
    "withdrawal deadline": "withdrawal deadline",
}

EMOTIONS = {
    "anxiety": ["anxious", "anxiety", "panic", "worried", "nervous"],
    "stress": ["stress", "overwhelm", "too much", "pressure"],
    "sadness": ["feeling low", "really low", "sad", "depressed", "feeling down"],
    "hopelessness": ["hopeless", "no way forward", "don't see a way", "can't cope"],
    "isolation": ["isolated", "alone", "lonely", "haven't really talked"],
    "desperation": ["desperate", "don't know what to do"],
}

CORE_CRISIS_PHRASES = [
    "hurt myself", "hurting myself", "harm myself", "kill myself", "suicid",
    "end my life", "don't feel safe", "do not feel safe", "can't go on",
    "in crisis", "can't cope anymore", "don't see a way forward",
]

_NOT_HARMLESS = r"(?! (?:in|with|at|on|near|there|off|here in)\b)"
EXTENDED_CRISIS_PATTERNS = [re.compile(p) for p in (
    r"\b(?:do not|don't|dont) want to (?:live|be alive|be here|go on)\b" + _NOT_HARMLESS,
    r"\bwant(?:ed)? to die\b", r"\bwanna die\b",
    r"\bwish i (?:was|were) (?:dead|gone)\b", r"\bbetter off (?:dead|without me)\b",
    r"\bno reason to (?:live|go on)\b", r"\bnothing to live for\b",
    r"\bend it all\b", r"\btake my own life\b",
    r"\bif i (?:just )?(?:disappeared|vanished|wasn't here|weren't here|was gone)\b",
    r"\b(?:won't|will not) be here (?:much )?longer\b",
)]


def _normalise(text: str) -> str:
    """Lowercase and turn curly quotes into straight ones so "don’t" matches "don't"."""
    return (text.lower().replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"'))


def extract_courses(text: str) -> list:
    found = []
    for pattern in COURSE_PATTERNS:
        for dept, num in pattern.findall(text):
            code = f"{dept.upper()} {num}"
            if code not in found:
                found.append(code)
    return found


def find_crisis(text: str, extended: bool = True) -> list:
    lower = _normalise(text)
    hits = [p for p in CORE_CRISIS_PHRASES if p in lower]
    if extended:
        hits += [m.group(0) for pat in EXTENDED_CRISIS_PATTERNS
                 for m in [pat.search(lower)] if m]
    return hits


def extract(text: str, extended_crisis: bool = True) -> dict:
    lower = _normalise(text)
    deadlines = sorted({d.lower() for d in DEADLINE_PATTERN.findall(text)})
    crisis = find_crisis(text, extended_crisis)
    return {
        "courses": extract_courses(text),
        "deadlines": deadlines,
        "blockers": sorted({name for kw, name in BLOCKERS.items()
                            if re.search(rf"\b{re.escape(kw)}", lower)}),
        "emotions": sorted({emo for emo, words in EMOTIONS.items()
                            if any(re.search(rf"\b{re.escape(w)}", lower) for w in words)}),
        "crisis_matches": crisis,
        "crisis_detected": bool(crisis),
        "imminent_deadline": any(d in IMMINENT for d in deadlines),
    }
