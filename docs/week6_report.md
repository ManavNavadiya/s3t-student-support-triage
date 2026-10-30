# Week 6 Report: Asset Engineering

**Deliverable:** a working, reusable NLP asset, `s3t`: a Python module, a command line and an HTTP API
with one structured input/output contract, documentation and confidence scores.

**Summary.** The Week 5 pipeline was a set of scripts that only worked from inside the project folder.
Week 6 turns the same trained models into a component another program (or a staff dashboard) can call:
install it, call `Triage().predict(text)`, and get a validated, JSON-ready result with category, urgency,
per-class confidence, extracted details, a recommended action and a human-review flag.
**The models were not retrained and their accuracy did not change.** The verification run confirms this:
all 21 regression comparisons against the Week 5 report pass (Section 4). The work is packaging,
interface, safe defaults and checks. Running it also exposed one real problem: the urgency confidence gate
flagged 76% of test messages for review. It was fixed in the same week by no longer using urgency confidence
as a review trigger. The review rate fell to 47%; the measured costs are 3 more silent category errors (18 to
21) and 1 of 54 truly High messages no longer flagged for being uncertain (Section 4.3). What remains open:
there is still no real student data (Section 5).

Evidence: `reports/week6_verification.md` (re-run on 2026-10-11 after the urgency change, Python 3.11,
scikit-learn 1.9.1, sentence-transformers 6.1.0, torch 2.14.1), `reports/threshold_calibration.md`, and 19 of
19 `pytest` cases passing. The "before" figures in Section 4.3 come from the first run, which was overwritten.

---

## 1. What was delivered

| Requirement | Delivered as | Where |
|---|---|---|
| API / module | `from s3t import Triage` (module); `python -m s3t serve` (HTTP: `/v1/triage`, `/v1/triage/batch`, `/health`, `/v1/info`); `python -m s3t triage ...` (CLI) | `s3t/triage.py`, `s3t/api.py`, `s3t/cli.py` |
| Structured input / output | pydantic models for request, result and batch; invalid input rejected with a clear error (422 over HTTP); JSON Schema via `python -m s3t schema` | `s3t/schemas.py`, `docs/API.md` |
| Documentation | README (install, three ways to use it, configuration, limits), API reference, model card, data-collection guide, this report, runnable examples | `README.md`, `docs/`, `examples/` |
| Confidence scores | probability of every class, top confidence, margin to runner-up, a high/medium/low band, per-task review thresholds, for both category and urgency | `ScoredLabel`, `confidence_band`, `human_review` |
| Checks | `python -m s3t verify` (contract, regression, performance) and `pytest` | `s3t/verify.py`, `tests/` |

## 2. Previous approach vs this approach

| | Week 5 (scripts) | Week 6 (asset) |
|---|---|---|
| How you call it | run `src/pipeline.py` from inside the project; import needs `src/` on the path | `pip install -e .`, then `from s3t import Triage`, `python -m s3t ...` or HTTP |
| Loading | `S3TPipeline(model)` prints to stdout; DistilBERT and SBERT paths mixed in one class | `Triage(model)`; loads once; models folder and encoder configurable (`S3T_MODELS_DIR`, `S3T_ENCODER`) |
| Input handling | any string accepted | text trimmed, 1-2,000 characters, batch 1-100, otherwise `ValueError` / HTTP 422 (verified) |
| Output | untyped dict; confidence rounded to 2 decimals for the top class only | typed `TriageResult`: all class probabilities, margin, `model_label` vs final `label`, band, review reasons as codes, `meta` (model, thresholds, warnings, versions) |
| Confidence use | one fixed threshold 0.40 on `min(category, urgency)` | a category threshold calibrated from training data by `calibrate`; urgency confidence is reported but is not a review trigger (Section 4.3); a warning in every result while the default is in use |
| Fallback | `--model auto` silently used the baseline if SBERT files were missing | `auto` falls back and says so in `meta.warnings`; an explicit model name raises instead |
| Side effects | every prediction wrote an embedding file (`.npy`, named by a hash of the messages) to `models/cache/` | one encoding per call serves both tasks; nothing written to disk during inference |
| Crisis detection | 12 phrases; indirect wording missed (1 of 3 on the challenge set) | the same 12 plus an extended list for indirect wording (3 of 3, see 4.4) |
| Evaluation | separate scripts that write many files | `evaluate` for any labelled CSV (e.g. classmate data); `verify` for one report |
| Tests | none | contract checks in `verify`; 15 test functions (19 cases) in `pytest`, all passing |
| Model files and accuracy | the Week 5 `.joblib` files | the same files; Week 5 numbers reproduced (Section 4.1) |
| Privacy | n/a | text is never logged or echoed; `id` for correlation |
| Dependencies | torch, transformers, pandas, matplotlib | core: numpy, scipy, scikit-learn, joblib, nltk, pydantic; optional torch + sentence-transformers (hybrid), fastapi + uvicorn (API) |

## 3. What changed in behaviour, and why

1. **Calibrated review thresholds.** Week 5 found that the fixed 0.40 threshold barely flags anything for the
   SBERT models (31 of 299 test messages wrong and unflagged), and the value it suggested instead (about 0.9)
   was read off the test set. `python -m s3t calibrate` picks thresholds from 5-fold cross-validation on the
   training set, grouped by sentence template, without touching the test set. It chose **0.55 for category**.
   For urgency it measured 0.50 but that value flagged 74% of messages, so it is not used (item 6).
2. **Extended crisis lexicon (on by default).** Week 5's most serious finding was that "Nobody would even
   notice if I disappeared" and "I don't want to live like this anymore" were not detected. The extended
   list adds patterns for indirect wording. It was written after seeing those messages, so catching them is
   not evidence that it generalises (Section 4.4). `--core-crisis` restores the Week 5 behaviour.
3. **No silent downgrade** to the weaker baseline.
4. **One encoding per call, no cache files.**
5. **`confidence_band` fixed after the first run.** The first version required urgency confidence >= 0.90 for
   `high`; the verification run showed 0 of 299 test messages ever reached it, because urgency confidences
   are low for every message (Section 4.3). `high` now requires the category confidence >= 0.90 and no
   confidence below its review threshold. The band counts in Section 4.2 (146 / 104 / 49) come from the
   re-run with the new rule; the first run had 0 / 127 / 172 under the old rule.
6. **Urgency confidence is no longer a review trigger.** `calibrate` writes an urgency threshold of 0.0
   (never fires); R4 and R1 still send High and crisis messages to staff. Evidence and costs in Section 4.3.

Nothing else in the decision logic changed: rules R1-R4 (R3 now fires on category confidence only), the extraction patterns and the recommended
actions are the Week 3 code.

## 4. Results and analysis

### 4.1 Did packaging change the models? No.

Same models, same data, run through the new `Triage` class with the Week 5 settings (threshold 0.40, core
crisis lexicon). All 21 comparisons are within tolerance:

| Model | Category macro-F1 (Week 5 / now) | Urgency macro-F1 | Review rate | Silent errors | Challenge category / urgency correct (of 28) | Crisis detected |
|---|---|---|---|---|---|---|
| baseline | 0.588 / 0.588 | 0.751 / 0.751 | 0.82 / 0.823 | 6 / 6 | 13 / 13 and 16 / 16 | 1 / 1 |
| sbert | 0.880 / 0.880 | 0.602 / 0.602 | 0.42 / 0.421 | 34 / 34 | 17 / 17 and 16 / 16 | 1 / 1 |
| sbert+tfidf | 0.859 / 0.859 | 0.794 / 0.794 | 0.45 / 0.448 | 31 / 31 | 17 / 17 and 20 / 20 | 1 / 1 |

The model-quality conclusions of Week 5 therefore carry over unchanged: the hybrid is much better than the
baseline on category (0.859 vs 0.588), about equal to SBERT alone on category but far better on urgency
(0.794 vs 0.602), and the template-level uncertainty remains large (95% interval for category macro-F1
0.59 to 0.98, Week 5).

### 4.2 Out-of-the-box behaviour (hybrid, category threshold 0.55, urgency confidence not a trigger)

| Metric | Test set (n = 299) | Challenge set (28 in scope + 2 out) |
|---|---|---|
| Category accuracy / macro-F1 | 0.860 / 0.859 | 0.607 / 0.592 |
| Urgency accuracy / macro-F1 | 0.819 / 0.794 | 0.750 / 0.768 |
| High-urgency recall / precision | 0.981 / 0.515 | 0.900 / 0.643 |
| Flagged for human review | **47%** | **63%** |
| Silent category errors (wrong, not flagged) | 21 (7.0% of messages) | 3 |
| Wrong category but flagged | 21 | 8 |
| Silent urgency errors (wrong, not flagged) | 4 (of 54 urgency errors) | 2 (of 7) |
| Truly High, predicted lower, not flagged | 1 of 54 | 1 of 10 |
| Confidence bands high / medium / low | 146 / 104 / 49 | 8 / 12 / 10 |

* **Compared with Week 5's fixed 0.40 threshold**, the review rate is about the same (45% then, 47% now) but
  silent category errors fall from 31 to 21. The calibrated category threshold is doing its job.
* **7.0% silent category errors is above the 5% target** the calibration aimed for. The training-set estimate
  was between 3.1% (at 0.60) and 6.8% (at 0.50), so calibration on 60 training sentences was slightly
  optimistic for the unseen test sentences, as expected.
* **Category confidence is informative at the top.** At 0.9 and above the hybrid was right on 145 of 146 test
  messages (accuracy 0.993). Between 0.7 and 0.9 it was right 79% of the time on average (stated 0.84), and
  on the challenge set the 0.5-0.7 band was right on only 1 of 7 messages. With 28 messages this is
  anecdotal, but it is the weak spot of the category gate.
* **Per-class (test set):** Administrative recall is 0.64 and Technical Support precision is 0.69. Most
  Administrative messages that fail are sent to Technical Support (the Week 5 mailing-address case).
  Mental Health recall is 0.77 (precision 1.00).

### 4.3 What got worse or was wrong: the urgency gate, and the fix

**The problem (first Week 6 run).** With the calibrated thresholds (category 0.55, urgency 0.50), 76% of test
messages were flagged for review. A team asked to read three of every four messages will stop trusting the
flag. The calibration report shows why. Out-of-fold urgency accuracy is only 0.644 and the urgency
probabilities are bunched together (selected C = 0.1, strong regularisation), so confidence barely separates
right from wrong:

* At threshold 0.40, 25% of messages are flagged and 21.8% are silent errors. At 0.50, 74% are flagged and
  4.6% are silent errors: a cliff, not a trade-off curve.
* The accuracy of unflagged messages is not monotonic (0.826 at 0.50, 0.639 at 0.60, 0.167 at 0.70), meaning
  that **urgency confidence is a weak signal for deciding which urgency predictions to trust**. On the
  messages we inspected the model is typically torn between Medium and High rather than clearly wrong (in one
  example Medium beat High by 0.04), so a low score mostly means "close call", not "likely mistake".
* 99% of training messages have urgency confidence below 0.70, so urgency confidence can never support a
  "high confidence" band.

**The fix.** Urgency confidence is no longer a review trigger: `calibrate` still measures it and reports the
table, but writes an urgency threshold of 0.0, which never fires (`--urgency-trigger` switches it back on).
Review now comes from three sources: low category confidence (R3), High urgency (R4, every High goes to a
human) and crisis language (R1). The reasoning was that urgency errors are mostly Medium predicted as High
(Week 5: 49 of 54), which is the safe direction, and that every High already goes to staff under R4.

**Measured result** (the "before" column is from the first Week 6 run, which has since been overwritten):

| Test set (n = 299) | Before (urgency threshold 0.50) | After (urgency not a trigger) | Week 5 (fixed 0.40) |
|---|---|---|---|
| Flagged for human review | 76% | **47%** | 45% |
| Silent category errors | 18 | 21 | 31 |
| Wrong category but flagged | 24 | 21 | not reported |
| Truly High, predicted lower, not flagged | not measured | 1 of 54 | not measured |
| Challenge set: flagged / silent category errors | 90% / 0 | 63% / 3 | not comparable |

**What this shows, and what it costs.**

* The review rate fell by 29 percentage points, from three of four messages to fewer than half.
* **Silent category errors rose from 18 to 21.** The urgency gate had been flagging some category mistakes by
  accident; without it they pass unflagged. This is a real cost of the change. It is still better than
  Week 5 (31).
* **One truly High message in 54 is no longer flagged** because the model predicted Medium or Low
  (recall 0.981 is unchanged from Week 5, so this miss already existed; what changed is that uncertainty no
  longer flags it). On the challenge set it is 1 of 10, which is too few messages to conclude anything.
* **47% is still high.** Only 49 test messages (16%) have low category confidence. The rest come from R4:
  precision of 0.515 at recall 0.981 means about 103 messages were predicted High (derived, not counted
  directly) against 54 that are High, and the two groups overlap. The model over-predicts High, and R4 sends
  every one of those to staff. Reducing that is the next step (Section 7).

### 4.4 Crisis lexicon (hybrid)

| Lexicon | Challenge crisis messages detected | False alarms on 317 other messages |
|---|---|---|
| core (Week 3) | 1 of 3 | 0 |
| extended | 3 of 3 | 0 |

Read this cautiously. The extended phrases were written from exactly these three messages. The 317
non-crisis messages are the generated test set (templated sentences) and 27 hand-written messages, none
of which tests the risky wording ("I don't want to live in the hostel", "I wish I could disappear from this
course"), so zero false alarms there is weak evidence. Real wording will behave differently.

### 4.5 Cost

| Model | Single message, median (ms) | 95th percentile (ms) | Batch of 100 (messages/s) |
|---|---|---|---|
| baseline | 1.4 | 1.6 | 2707 |
| sbert | 7.4 | 8.3 | 1171 |
| sbert+tfidf (default) | 8.6 | 9.7 | 755 |

On this laptop the hybrid is about 6 times slower per message than the baseline and still answers in under
10 ms, which is negligible for a support inbox. (Timings differ between runs and machines: the first run
measured 5.9 ms for the hybrid.) The real costs are dependencies (torch, sentence-transformers) and the
one-off encoder download (about 90 MB). The "load time" column in the verification report reads about 0 s
for every model because the encoder was already in memory from earlier checks in the same process; cold
start time was not measured. Is the gain worth it? On category, yes (0.859 vs 0.588 macro-F1, Week 5); the
latency does not change that judgement.

### 4.6 Contract checks

All 10 checks pass: output matches the schema, probabilities sum to 1, `predict` equals `predict_batch`,
deterministic output, empty/blank/oversized/non-string input rejected, crisis phrase forces High + review +
crisis action, deadline and confidence rules, message text not echoed and `id` returned, JSON-serialisable
output, HTTP API (health, single, batch, 422, API key). A live call to the running service with the
hybrid model returned a complete result with calibrated thresholds in `meta`.

## 5. Limitations and disclosures

1. **Still no real data.** The Week 2 feedback asked for messages collected from classmates. Training
   (60 distinct sentences) and test (15 distinct sentences) data are generated, and the 30-message challenge
   set was written by the team to break the model. `evaluate` and `docs/DATA_COLLECTION.md` make it possible
   to score real data immediately, but collecting it is still the biggest gap. Expect real-world performance
   to be lower: category accuracy already falls from 0.86 on the generated test set to 0.61 on the
   hand-written challenge set.
2. **The test set was used for design decisions** in Weeks 4-5, and the urgency-trigger change in Section 4.3
   was decided after reading test-set results, so Section 4.2 is a consistency check, not a fresh blind test.
3. **The category threshold is calibrated on 60 training sentences**; the test set shows it is slightly
   optimistic (7.0% silent category errors vs a 5% target), and on the challenge set the 0.5-0.7 confidence
   band was right on only 1 of 7 messages.
4. **Urgency is not protected by its own confidence any more.** It relies on R4 and R1. One truly High test
   message (1 of 54) and one of 10 on the challenge set were predicted lower and not flagged. Four of 54
   urgency errors on the test set, and two of 7 on the challenge set, were silent.
5. **The review rate is still high (47%)** because R4 sends every predicted High to staff and the model
   over-predicts High (Section 4.3). It no longer flags three of four messages, but it is not yet a light-touch
   filter.
6. **Mental Health recall is 0.77** on the test set: about 13 of 56 wellbeing messages were routed to another
   category. This report does not break down how many of those were silent.
7. **Crisis detection is a keyword/regex rule**; the extended list is untested on real wording.
8. **Service limits:** one process, no rate limiting, only an optional shared API key, no audit log. Not for
   public exposure; no names or student numbers in `text`.
9. **Pickled models are tied to library versions** (here scikit-learn 1.9.1 loaded them without warnings).
10. **Cold start time was not measured** (Section 4.5).

## 6. How to reproduce

```bash
uv venv .venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[all]"
python -m s3t calibrate        # reports/threshold_calibration.md
python -m s3t verify           # reports/week6_verification.md
python -m pytest -q
```

## 7. Recommended next steps (priority order)

1. **Collect and double-label classmate messages** (50-100, with consent, no names), measure how often the two
   labellers agree, and score them once with `python -m s3t evaluate` without tuning on them
   (`docs/DATA_COLLECTION.md`). This is the open Week 2 feedback and the biggest gap.
2. **Reduce High over-prediction.** High-urgency precision is 0.515: about 103 of 299 test messages are
   predicted High (derived from precision and recall) against 54 that are High. Rule R4 sends all of them to
   staff, so this is now the main source of the 47% review rate. Candidates: retrain urgency with more varied
   data, or review whether R2 (deadline escalation) over-escalates. Re-run `verify` and report the review rate
   and the High misses together, so the workload is never reduced at the cost of missed High messages unseen.
3. Review the crisis list with counselling or wellbeing staff; test it against harmless sentences that share
   its phrases.
4. Add an "out of scope / no action" class and negation handling (Week 5 items 5-6).
5. Retrain with the sentences that failed in Week 5, replace the model files, re-run `calibrate` and `verify`.
6. Before any real deployment: authentication, rate limiting, audit logging, a data-handling agreement.

*Done in Week 6:* the urgency confidence gate was removed as a review trigger (Section 4.3).