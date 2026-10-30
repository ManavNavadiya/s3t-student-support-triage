# S3T asset guide (Week 6: reusable NLP asset)

**Deliverable:** a working, reusable NLP asset: an importable Python module, a command line,
and an HTTP API, all sharing one structured input/output contract, with documentation and
confidence scores.

Given a student's message, the asset returns the **category** (5 classes), the **urgency**
(Low / Medium / High), **confidence scores** for both, the extracted details (courses, deadlines,
blockers, emotion signals), a **recommended action**, and a **human-review flag** with reasons.
It is advisory only: a staff member makes every decision.

> Status: verified on 2026-10-11 (Python 3.11): all contract and Week 5 regression checks pass and
> 19 `pytest` cases pass (see `reports/week6_verification.md`). Urgency confidence is not a review trigger
> (it flagged 76% of test messages and did not separate right from wrong answers). On the test set the
> review rate is now 47%, with 21 silent category errors (7.0%) and 1 of 54 truly High messages not flagged;
> details in `docs/week6_report.md` section 4.3. Still open: all training and test data is generated,
> not collected from real students (`docs/DATA_COLLECTION.md`).

- Report for the course: [`week6_report.md`](week6_report.md)
- Field-by-field reference: [`API.md`](API.md)
- Model facts, limits, intended use: [`MODEL_CARD.md`](MODEL_CARD.md)

---

## 1. Install

```bash
cd <repository folder>
python -m venv .venv && source .venv/bin/activate     # optional
pip install -e ".[all]"            # hybrid model + API + tests
#   pip install -e .               # core only: baseline model, no torch, no API
#   pip install -e ".[sbert]"      # + hybrid model (torch, sentence-transformers)
#   pip install -e ".[api]"        # + HTTP service
```

The first call of the hybrid model downloads the sentence encoder once (about 90 MB).
Offline machine? Download `sentence-transformers/all-MiniLM-L6-v2` elsewhere, copy the folder
across, and set `S3T_ENCODER=/path/to/folder`.

## 2. Use it

### As a Python module
```python
from s3t import Triage

triage = Triage()                                    # load once, reuse
r = triage.predict("I can't log in to Canvas and my quiz is due today", id="ticket-001")

r.category.label, r.category.confidence              # e.g. 'Technical Support', 0.93
r.urgency.label,  r.urgency.confidence
r.confidence_band                                    # 'high' | 'medium' | 'low'
r.human_review.required, r.human_review.reasons
r.entities.courses, r.entities.deadlines, r.emotions
r.model_dump()                                       # plain dict, JSON-ready

results = triage.predict_batch(list_of_messages)     # up to 100 per call
```
More: [`examples/use_as_a_module.py`](../examples/use_as_a_module.py).

### From the command line
```bash
python -m s3t triage "My financial aid has not been disbursed"          # one message, JSON
python -m s3t triage --file examples/sample_messages.csv --out out.jsonl   # a file (csv/jsonl/txt)
python -m s3t evaluate --csv my_labelled_messages.csv --out reports/my_eval.md
python -m s3t info                                                       # model, thresholds, warnings
python -m s3t schema                                                     # JSON Schema of input/output
```

### As an HTTP service
```bash
python -m s3t serve                  # http://127.0.0.1:8000  - interactive docs at /docs
curl -s localhost:8000/v1/triage -H 'Content-Type: application/json' \
     -d '{"text": "My scholarship money has not arrived", "id": "ticket-7"}'
```
Endpoints: `GET /health`, `GET /v1/info`, `POST /v1/triage`, `POST /v1/triage/batch`.
Set `S3T_API_KEY` to require an `X-API-Key` header. Example client:
[`examples/call_the_api.py`](../examples/call_the_api.py).

## 3. What you get back

Shape of one result (the **values below are illustrative examples, not output from a run**;
the field names and types are exact, see `docs/API.md`):

```json
{
  "id": "ticket-001",
  "category": {"label": "Technical Support", "model_label": "Technical Support",
               "adjusted_by_rules": false, "confidence": 0.93, "margin": 0.81,
               "probabilities": {"Academic Difficulty": 0.03, "Mental Health & Wellbeing": 0.01,
                                 "Financial Aid": 0.01, "Administrative": 0.02,
                                 "Technical Support": 0.93}},
  "urgency":  {"label": "High", "model_label": "Medium", "adjusted_by_rules": true,
               "confidence": 0.62, "margin": 0.30, "probabilities": {"Low": 0.08, "Medium": 0.62, "High": 0.30}},
  "confidence_band": "medium",
  "recommended_action": "PRIORITY: contact student within 24 hours - Route to IT help desk",
  "entities": {"courses": ["STAT 230"], "deadlines": ["today"], "blockers": ["LMS (Canvas)", "login / access issue"]},
  "emotions": [],
  "crisis_detected": false, "crisis_matches": [],
  "human_review": {"required": true, "reasons": ["high_urgency"]},
  "rules_applied": ["R2: imminent deadline -> urgency raised to High"],
  "advisory_only": true,
  "disclaimer": "Advisory triage suggestion only. ...",
  "meta": {"schema_version": "1.0", "asset_version": "1.0.0", "model": "sbert+tfidf",
           "encoder": "sentence-transformers/all-MiniLM-L6-v2",
           "review_thresholds": {"category": 0.4, "urgency": 0.4}, "thresholds_source": "default",
           "extended_crisis_lexicon": true, "warnings": []}
}
```

### How to read the confidence scores
- `confidence` is the model's probability for its own top choice. `probabilities` gives every class;
  `margin` is top minus runner-up (small = torn between two labels).
- For urgency, `label` is the final value after the rules (crisis language, imminent deadline);
  `model_label` is what the classifier said and `confidence` belongs to `model_label`.
- Week 5 measured the hybrid's category confidence on the test set: at 0.90 and above it was right on
  145 of 146 messages; below 0.90 on 112 of 153. Between 0.8 and 0.9 it was over-confident
  (stated 0.86, actual 0.75). So it ranks messages usefully but is **not a calibrated probability**.
- `confidence_band`: `high` = not low and category confidence >= 0.90, `low` = either is below its review
  threshold, `medium` = otherwise.
- `human_review.required` is true if there is crisis language, final urgency is High, or a
  confidence is below its threshold. Reasons: `crisis_language`, `high_urgency`,
  `low_category_confidence`, `low_urgency_confidence`.

## 4. The review threshold (important)

Week 5 showed the old fixed threshold (0.40) almost never fires for the SBERT models, which led to 31
"silent errors" (wrong and not flagged). Until you calibrate, every result carries a warning
(`meta.warnings`) saying the default is in use. To choose the threshold from the **training set**
(grouped cross-validation; the test set is not touched):

```bash
python -m s3t calibrate --target 0.05     # writes s3t/resources/models/review_thresholds.json
```
After that, `Triage()` uses the calibrated thresholds automatically
(`meta.thresholds_source = "calibrated"`). A higher threshold means more messages go to staff; the
report `reports/threshold_calibration.md` shows that trade-off.

**Urgency is not a review trigger.** `calibrate` still reports the urgency table, but writes an urgency
threshold of `0.0` (never fires), because the urgency score is not informative: the only threshold that
met the 5% target flagged about three quarters of messages. Urgency is protected by R4 (every High goes
to a human) and R1 (crisis language). Cost: a Low or Medium prediction that is truly High is no longer
flagged merely for being uncertain; `verify` now reports how many of those occur
("Truly High but predicted lower and not flagged"). To turn the urgency trigger back on:
`python -m s3t calibrate --urgency-trigger`.

## 5. Check that it works

```bash
bash scripts/run_week6.sh        # install, calibrate, verify, tests, sample run
# or separately
python -m s3t verify             # -> reports/week6_verification.md
pytest -q
```
`verify` checks the output contract, input validation, the crisis rule, the HTTP API, and that the
packaged models reproduce the Week 5 numbers when run through the new code (tolerances in
`s3t/resources/week5_reference.json`). It also measures load time and latency.

## 6. Configuration

| Setting | How | Default |
|---|---|---|
| Model | `Triage(model=...)` / `--model` / `S3T_MODEL` | `auto` = hybrid, else baseline **with a warning** |
| Review thresholds | `Triage(thresholds=(cat, urg))`, or `calibrate` | calibrated file, else category 0.40 / urgency 0.0 (off) |
| Crisis lexicon | `Triage(extended_crisis=False)` / `--core-crisis` | extended |
| Models folder | `Triage(models_dir=...)` / `S3T_MODELS_DIR` | packaged |
| Encoder (offline) | `S3T_ENCODER` | the name saved in the model |
| API key | `S3T_API_KEY` | none |

An explicit `model="sbert+tfidf"` never falls back silently: it raises an error if the encoder is
unavailable. Only `model="auto"` falls back, and says so in `meta.warnings`.

## 7. Layout

```
s3t/                      the package
  triage.py               Triage class (public API)
  schemas.py              input/output contract (pydantic)
  classifier.py, models.py  load models, probabilities
  extraction.py, rules.py   Week 3 extraction + review guardrail
  api.py                  FastAPI service          cli.py  command line
  evaluation.py           scoring of labelled CSVs calibrate.py  threshold selection
  verify.py               full verification report
  resources/              packaged models, data, Week 5 reference numbers
docs/                     API.md, MODEL_CARD.md, week6_report.md, DATA_COLLECTION.md
examples/  tests/  scripts/
```
Training code is not part of the asset; it lives in the Week 4 / Week 5 folders. The asset loads
the saved models only.

## 8. Limits you should know

- Trained and tested on **generated** messages (60 distinct training sentences, 15 test
  sentences) plus a 30-message hand-written challenge set. Performance on real student
  messages is **unknown**. See `docs/MODEL_CARD.md` and `docs/DATA_COLLECTION.md`.
- Crisis detection is a keyword/regex rule, not a model. It misses wording it does not list.
- No "out of scope / no action needed" class: every message is forced into one of five teams.
- Single-process service, no rate limiting, no authentication beyond the optional API key.
  Do not expose it to the internet as it is. Do not put names or student numbers in `text`.