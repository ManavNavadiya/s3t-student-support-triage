# Group 6 integration: S3T early warning with Group 5 and Group 7

**Demo step:** a student email goes into Group 6 (S3T early-warning engine), which flags the student as
at risk. Group 5 (Student Feedback Intelligence) reads the same email for course-experience sentiment:
*which part of the course* (pace, lectures, assignments, exams…) the student is unhappy about. The course
topic is then sent to Group 7 (Research Discovery), which returns researchers whose papers match that
topic. A staff member reviews the result; nothing is sent or acted on automatically.

Each group answers one question:

| Group | Question | Output used |
|---|---|---|
| 6 · S3T triage | Is this student in trouble, and how urgently? | category, urgency, course, crisis, human-review |
| 5 · Feedback intelligence | What about the course is the problem? | aspect-level sentiment → support focus + anonymised course-feedback item |
| 7 · Research discovery | Who could mentor the student on this subject? | ranked researchers + papers |

```
student email
     │
     ├──────────────────────────────────────────────┐
     ▼                                              ▼
 Group 6: S3T triage                         group5_feedback.py
 category, urgency, entities.courses,        1. strip greeting / sign-off, mask roll numbers
 crisis flag, human-review flag              2. POST /v1/analyze {"id": "req-<random>", "text": ...}
     │                                       3. confident (≥0.60) negative aspects → concerns
     │                                          → support focus + course-feedback item
     │                                       (skipped entirely when S3T detects crisis language)
     │                                              │
     ▼                                              ▼
 s3t_to_discovery.handoff()     1. early-warning decision (keyword signals + S3T category) — Group 5 does NOT change it
     │                          2. Group 5 support focus appended to the suggested action (if at risk)
     │                          3. course code / name  →  topic phrase (course_catalog.json)
     ▼
 Group 7: POST /api/v1/recommend    {"query": <topic>, "top_k": 5, "include_evidence": true}
     │
     ▼
 ranked mentors + their papers  →  shown in the web UI (ui_server.py + static/index.html)
```

`pipeline.run_pipeline()` runs the whole chain; `ui_server.py` and `demo.py` call it.

**Data minimisation:** Group 7 receives only the topic string (e.g. "natural language processing").
It never receives the email text, the student's id, or any S3T or Group 5 output. Group 5 receives the
email text (it needs it) with the greeting and sign-off removed and roll-number-like tokens masked, under a
random request id, never the student id. Group 5 itself also masks emails, URLs and phone numbers. Crisis
messages are not sent to Group 5 at all. The course-feedback item contains aspect names only, no text.

## Why Group 5 does not decide risk

Group 5's model was trained on course reviews (RateMyProfessor, 73.7% test accuracy). We ran it on the demo
emails before wiring it in:

| Email | Group 5 overall | What it means |
|---|---|---|
| At-risk demo email (CS 521) | negative 0.47 (**low confidence**), aspects all < 0.60 | unsure on help-request wording |
| Routine transcript request | negative 0.55 (**low confidence**) | wrong: the message is neutral |
| "Lectures in CS 410 go way too fast… missed the quiz…" | negative 0.74; Lectures/Pace negative 0.70 | confident and correct |
| "Lectures are far too fast and the examples do not help" | negative 0.94 | confident and correct |
| "Dear Professor, …" (before cleaning) | falsely adds a *Teaching Quality* aspect | fixed by stripping the greeting |

So Group 5 is reliable when a student actually complains about the course and unreliable otherwise. It is
therefore used as a **lens, not a judge**: only confident (≥ 0.60, Group 5's own threshold) negative
aspects become "concerns"; lower ones are shown as "low confidence" hints; the at-risk flag and level come
from Group 6's rules exactly as before (tested in `test_group5_never_changes_risk_decision`). The
early-warning evaluation in `reports/bridge_eval.md` is therefore still valid for the three-group pipeline.

## Files

| File | Purpose |
|---|---|
| `s3t_to_discovery.py` | The bridge: `assess_risk()`, `resolve_topic()`, `call_group7()`, `handoff()` (now takes optional Group 5 `feedback`) |
| `group5_feedback.py` | Group 5 adapter: `clean_for_group5()`, HTTP and in-process clients, `summarise()`, `course_feedback_item()` |
| `pipeline.py` | `run_pipeline()`: Group 6 result + Group 5 + Group 7 in one call |
| `course_catalog.json` | Maps course codes and aliases to a research-topic phrase |
| `demo.py` | Command-line demo of one fixed email (CS 521) |
| `ui_server.py` | Local web server for the demo page (standard library only) |
| `static/index.html` | The demo page |
| `tests/test_bridge.py` | Contract tests against a fake Group 7 server (no models needed) |
| `tests/test_group5.py` | Group 5 contract, privacy, failure and "does not change risk" tests (fake Group 5 + Group 7); one test runs Group 5's real model in-process |
| `evaluate_bridge.py` | Measures the early-warning flag against human labels: precision, recall, F1, false-positive listing |
| `RESPONSIBLE_AI.md` | Responsible-AI analysis |

## How to run

This repository holds Group 6's code only: S3T and this bridge. Group 5 and Group 7 are separate
projects; the bridge talks to them over HTTP when they are running and works without them.

**Group 6 on its own (from the repository root):**
```bash
./run_demo.sh            # first run creates .venv and installs S3T; opens http://127.0.0.1:5050
```
With partners off, the page shows S3T's triage and the early-warning decision, and says which topic would
be sent to Group 7.

**With the partner services** (each started from its own project first):
```bash
# Group 7 (its repo):  uv run python -m src.week6.api            -> port 8080
# Group 5 (its repo):  python api.py --port 8002                  -> port 8002
GROUP7_URL=http://127.0.0.1:8080 GROUP5_URL=http://127.0.0.1:8002 ./run_demo.sh
```
Group 5 can also run inside the demo process: `GROUP5_URL=local:/path/to/Group5_Week7 ./run_demo.sh`.

**Manual start:**
```bash
source .venv/bin/activate
cd integration
PYTHONPATH=.:.. python ui_server.py [--group7 URL|off] [--group5 URL|local:<folder>|off] [--port 5050]
```

**Command line** (no browser): `PYTHONPATH=.:.. python demo.py --group7 off --group5 off`

**Tests:** `./run_tests.sh` (S3T tests, `s3t verify`, integration tests); `./run_tests.sh --e2e` adds the
end-to-end check against the running demo.

**Evaluate the early-warning flag** (CSV with `text,at_risk` and optionally `topic`):
```bash
PYTHONPATH=.:.. python evaluate_bridge.py --csv my_labelled_emails.csv --out reports/bridge_eval.md
```

**Environments:** S3T works from Python 3.9. Group 7 needs 3.12+ and Group 5 needs Flask; each partner keeps
its own environment.

## Contract between the groups

| Group 6 provides (S3T result) | Bridge does | Group 7 receives |
|---|---|---|
| `category.label`, `urgency.label`, `entities.courses`, `crisis_detected`, `human_review` | adds early-warning signals; maps course code or alias to a topic via `course_catalog.json` | `query` (topic), `top_k`, `include_evidence` |

| Group 6 provides | Bridge does | Group 5 receives | Group 5 returns (used) |
|---|---|---|---|
| email text, `crisis_detected`, course code | cleans text; skips crisis messages; random id | `POST /v1/analyze` `{"id": "req-…", "text": …}` | `overall.{label, confidence, low_confidence}`, `aspects[].{aspect, sentiment, confidence, clause}`, `warnings` |

Group 5 answers 422 with a JSON error body for text it rejects; the bridge reports that as status `error`.

Group 7 returns `results[]` with `name`, `author_id`, `score`, `confidence`, and `evidence[]` (papers). The
bridge keeps the name, score, confidence label and the top 2 papers.

**Bridge statuses:** `ok` (mentors returned), `no_risk` (no search run), `needs_topic` (course not in
catalog), `group7_unavailable` (call failed; the page shows the reason).

**Group 5 statuses** (`course_experience.status`, separate so the overall status keeps its meaning):
`ok`, `unavailable` (call failed; pipeline continues without it), `error` (Group 5 rejected the text),
`skipped` (crisis language: a person reads it), `off`.

### What Group 5 adds to the output
- **Concerns / strengths:** aspects with negative / positive sentiment at ≥ 0.60 confidence (each aspect counted
  once, at its most confident reading). Lower-confidence negatives are shown as "low confidence".
- **Support focus** (appended to the suggested action when the student is at risk): Pace/Lectures → catch-up
  session or recorded lectures; Teaching Quality → tutor/TA session; Examples → worked examples;
  Assignments → submission plan or extension; Workload → review workload; Exams/Grading → explain assessment
  and make-up policy; Availability → office-hours slot.
- **Course-feedback item:** `{course_code, concerns, strengths, contains_text: false}` for the course
  coordinator's Group 5 report. Built even when the student is not at risk (the *Course feedback* sample),
  never contains text or ids, and is not sent anywhere automatically.

### How the early-warning decision is made
S3T has no "at risk of failing" field, so the bridge adds transparent keyword signals and reports which fired:
`missed_assessment`, `missing_submissions`, `passing_criteria_query`, `fear_of_failing`.

- **HIGH:** both a missed assessment and missing submissions.
- **MEDIUM:** one of those two, plus either S3T's category is *Academic Difficulty* or the email mentions failing.
- **LOW / not at risk:** anything else.
- Crisis language from S3T forces **HIGH** and the suggested action becomes immediate human follow-up.

## Status of the open items

| # | Item | Status |
|---|---|---|
| 1 | S3T has no "at risk" or "make-up test" output | **Handled in the bridge** with the keyword signals above. Group 6 may adopt this or add a schema field (bump `SCHEMA_VERSION`). |
| 2 | S3T misclassified the demo email on the baseline model | **Resolved on the hybrid.** `sbert+tfidf` labels the demo email *Academic Difficulty* (0.83). The baseline got it wrong, so the page warns when it is running on the baseline. |
| 3 | Course → topic mapping | **Still a placeholder.** `course_catalog.json` has only CS521, CS410, CS430, STAT230. Replace with real codes before using this beyond the demo. |
| 4 | Group 7 cannot return "faculty who teach this in other divisions" | **Open.** Their data is OpenAlex papers (research expertise only), with no teaching roster. State this in the demo, or ask Group 7 to add a roster. |
| 5 | Group 7 data and API | **Resolved.** The API runs locally and returns results (checked with `curl` and `demo.py`). |
| 6 | Python version split | Documented above. |
| 7 | Advisory only | The page shows the human-review flag and a footer stating that staff decide every action. |
| 8 | Group 5 domain shift (reviews → emails) | **Handled:** Group 5 never decides risk; only ≥0.60 readings count; low-confidence banner. Retraining on labelled emails would let it do more. |
| 9 | Group 5 port clash with Group 7 (both default 8000) | **Resolved:** Group 5 runs on 8002. |
| 10 | Course-feedback items are not yet aggregated | **Open.** Items are shown per message; feeding many into Group 5's `/v1/report` per course needs storage, consent and the min-3-mentions privacy rule. |

## Known limitations (tested)

These were checked by running the bridge on purpose-built emails.

| Email | What happens | Why |
|---|---|---|
| "No course code, but says *nlp*" | Works: topic found via alias (`catalog_alias`) | Alias fallback |
| "CS 999 Machine Learning" (unknown code) | Works: falls back to the name and searches *machine learning* | Alias fallback |
| Two courses in one email | **Only the first course is searched**; the other is ignored | `resolve_topic()` returns one topic |
| "I did **not** miss the quiz and none of my assignments are pending" | **Wrongly flagged HIGH** | Keyword matching ignores negation |
| "I missed the *mid sem*" (no hyphen) | Missed-assessment signal does not fire, so risk is **downgraded to MEDIUM** | The pattern only knows "mid-sem" |
| Unknown course, no alias | `needs_topic`: no search is run; use *Topic override* under Advanced | Catalog coverage |
| Routine transcript request | Group 5 says **negative 0.55** (low confidence); no concern raised | Model trained on reviews; threshold filters it |
| "I missed the quiz and I am really stressed" | Group 5 says Exams/Grading **positive** (0.59, low confidence) | Domain shift; shown only as a hint |
| Email with a greeting ("Dear Professor") | Without cleaning, Group 5 adds a false *Teaching Quality* aspect | Fixed by `clean_for_group5()` |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `handoff() got an unexpected keyword argument 'timeout'` | `handoff()` must accept and pass on `timeout`: add `timeout: float = 30.0` to its signature and pass it as the 4th argument of `call_group7(...)` |
| `FileNotFoundError ... static/index.html` | `index.html` must be in `integration/static/` |
| Group 7 pill is red / "unreachable" | Group 7's API is not running, or the address under *Advanced* is wrong |
| First Analyze is very slow | Group 7 loads its model on the first query; warm it up beforehand |
| `ModuleNotFoundError: s3t` | Activate the S3T virtual environment first |
| Group 5 pill is red / card says "could not analyse" | Group 5's API is not running on 8002, or start the demo with `GROUP5_URL=local:/path/to/Group5_Week7` |
| `OSError: [Errno 98] Address already in use` when starting Group 5 | Something (often Group 7) is on that port; use `--port 8002` |
| `InconsistentVersionWarning` from scikit-learn | Harmless; Group 5's model was saved with 1.8 |

## Suggested demo script (31 Oct)

1. Show the three status pills (Group 6 model, Group 5 up, Group 7 up).
2. Load **At risk · pace** and press **Analyze**. Walk through the four cards: triage → course experience
   (Group 5: Lectures and Pace negative, support focus, anonymised course item) → early-warning decision
   (note the Group 5 support focus in the suggested action) → mentors and their papers.
3. Load **At-risk student**: Group 5 is low-confidence here, so it adds nothing — say why (trained on reviews).
4. Show **Course feedback** (no risk, no mentor search, but Group 5 still produces a course-feedback item),
   **Routine query** and **Unknown course** to demonstrate the guardrails.
5. Say the limits out loud: advisory only, trained on generated data, researchers are not necessarily this university's faculty, keyword signals can be wrong. See `RESPONSIBLE_AI.md`.
