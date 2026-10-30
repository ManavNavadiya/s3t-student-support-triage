# S3T asset 1.0.0 - verification report

Run 2026-10-11T20:03:17 | Python 3.11.14 on Darwin | scikit-learn 1.9.1 | sentence-transformers 6.1.0 | torch 2.14.1 | pydantic 2.14.0 | fastapi 0.143.0

**Overall: ALL CHECKS PASSED**  (models verified: baseline, sbert, sbert+tfidf; default model in use: `sbert+tfidf`)

## A. Contract checks

| Check | Result | Detail |
|---|---|---|
| Output matches the schema | PASS | 10 results validate against the schema |
| Probabilities are consistent | PASS | label sets, sum = 1, confidence = max probability |
| Batch equals single calls | PASS | predict() and predict_batch() agree on 10 messages |
| Deterministic | PASS |  |
| Input validation | PASS | empty / blank / too long / non-string rejected with ValueError |
| Crisis rule forces High + review | PASS |  |
| Deadline and confidence rules | PASS |  |
| Message text is not echoed; id is | PASS |  |
| Output is JSON-serialisable | PASS |  |
| HTTP API | PASS | health, triage, batch, 422 validation, API key |

## B. Regression against the Week 5 report

Same models and same data, run through the new `Triage` class with the Week 5 settings (review threshold 0.40, core crisis lexicon). Differences beyond the tolerance would mean the packaging changed the model's behaviour.

| Model | Metric | Week 5 | This run | Tolerance | Result |
|---|---|---|---|---|---|
| baseline | category_macro_f1 | 0.588 | 0.588 | ±0.01 | PASS |
| baseline | urgency_macro_f1 | 0.751 | 0.751 | ±0.01 | PASS |
| baseline | review_rate | 0.82 | 0.823 | ±0.01 | PASS |
| baseline | silent_errors | 6 | 6 | ±2 | PASS |
| baseline | challenge_category_correct | 13 | 13 | ±2 | PASS |
| baseline | challenge_urgency_correct | 16 | 16 | ±2 | PASS |
| baseline | challenge_crisis_detected | 1 | 1 | ±2 | PASS |
| sbert | category_macro_f1 | 0.88 | 0.88 | ±0.01 | PASS |
| sbert | urgency_macro_f1 | 0.602 | 0.602 | ±0.01 | PASS |
| sbert | review_rate | 0.42 | 0.421 | ±0.01 | PASS |
| sbert | silent_errors | 34 | 34 | ±2 | PASS |
| sbert | challenge_category_correct | 17 | 17 | ±2 | PASS |
| sbert | challenge_urgency_correct | 16 | 16 | ±2 | PASS |
| sbert | challenge_crisis_detected | 1 | 1 | ±2 | PASS |
| sbert+tfidf | category_macro_f1 | 0.859 | 0.859 | ±0.01 | PASS |
| sbert+tfidf | urgency_macro_f1 | 0.794 | 0.794 | ±0.01 | PASS |
| sbert+tfidf | review_rate | 0.45 | 0.448 | ±0.01 | PASS |
| sbert+tfidf | silent_errors | 31 | 31 | ±2 | PASS |
| sbert+tfidf | challenge_category_correct | 17 | 17 | ±2 | PASS |
| sbert+tfidf | challenge_urgency_correct | 20 | 20 | ±2 | PASS |
| sbert+tfidf | challenge_crisis_detected | 1 | 1 | ±2 | PASS |

## C. Out-of-the-box behaviour (default settings)

Calibrated thresholds are used if `python -m s3t calibrate` has been run; otherwise 0.40 (see the thresholds line below). The test set was already used for design decisions in Weeks 4-5, so these numbers are not a fresh blind test.

## Held-out test set

Model `sbert+tfidf`; review thresholds category 0.55 / urgency 0.00 (urgency score not used as a trigger); n = 299 messages.

| Metric | Value |
|---|---|
| Category accuracy | 0.860 |
| Category macro-F1 | 0.859 |
| Templates with a category error | 5 of 15 |
| Urgency accuracy | 0.819 |
| Urgency macro-F1 | 0.794 |
| High-urgency recall / precision | 0.981 / 0.515 |
| Silent urgency errors (wrong, not flagged) | 4 |
| Truly High but predicted lower and not flagged | 1 of 54 |
| Templates with an urgency error | 7 of 15 |
| Flagged for human review | 47% |
| Silent category errors (wrong, not flagged) | 21 |
| Wrong but flagged | 21 |
| Confidence bands (high / medium / low) | 146 / 104 / 49 |

Calibration of category confidence:

| Confidence | Messages | Mean confidence | Actual accuracy |
|---|---|---|---|
| 0.0-0.5 | 37 | 0.429 | 0.541 |
| 0.5-0.7 | 35 | 0.584 | 0.8 |
| 0.7-0.9 | 81 | 0.838 | 0.79 |
| 0.9-1.0 | 146 | 0.949 | 0.993 |

Per-class category report:

```
                           precision    recall  f1-score   support

      Academic Difficulty       1.00      0.89      0.94        55
Mental Health & Wellbeing       1.00      0.77      0.87        56
            Financial Aid       0.84      0.97      0.90        70
           Administrative       0.95      0.64      0.77        59
        Technical Support       0.69      1.00      0.81        59

                 accuracy                           0.86       299
                macro avg       0.90      0.85      0.86       299
             weighted avg       0.89      0.86      0.86       299
```

## Hand-written challenge set (28 in scope + 2 out of scope)

Model `sbert+tfidf`; review thresholds category 0.55 / urgency 0.00 (urgency score not used as a trigger); n = 30 messages (2 out of scope).

| Metric | Value |
|---|---|
| Category accuracy | 0.607 |
| Category macro-F1 | 0.592 |
| Urgency accuracy | 0.750 |
| Urgency macro-F1 | 0.768 |
| High-urgency recall / precision | 0.900 / 0.643 |
| Silent urgency errors (wrong, not flagged) | 2 |
| Truly High but predicted lower and not flagged | 1 of 10 |
| Flagged for human review | 63% |
| Silent category errors (wrong, not flagged) | 3 |
| Wrong but flagged | 8 |
| Crisis messages detected | 3 of 3 (3 distinct); false alarms: 0 |
| Confidence bands (high / medium / low) | 8 / 12 / 10 |

Calibration of category confidence:

| Confidence | Messages | Mean confidence | Actual accuracy |
|---|---|---|---|
| 0.0-0.5 | 6 | 0.403 | 0.167 |
| 0.5-0.7 | 7 | 0.607 | 0.143 |
| 0.7-0.9 | 7 | 0.792 | 1.0 |
| 0.9-1.0 | 8 | 0.956 | 1.0 |

Per-class category report:

```
                           precision    recall  f1-score   support

      Academic Difficulty       0.50      0.40      0.44         5
Mental Health & Wellbeing       0.83      0.83      0.83         6
            Financial Aid       0.80      0.57      0.67         7
           Administrative       0.50      0.33      0.40         6
        Technical Support       0.44      1.00      0.62         4

                 accuracy                           0.61        28
                macro avg       0.62      0.63      0.59        28
             weighted avg       0.64      0.61      0.60        28
```

## D. Crisis lexicon: core vs extended

The extended phrases were written after the challenge set showed the gaps, so the challenge-set improvement is not an unbiased estimate. The false-alarm column is the cost: messages labelled non-crisis that the lexicon still flags.

| Lexicon | Challenge crisis messages detected | False alarms on other messages |
|---|---|---|
| core | 1 of 3 | 0 of 317 |
| extended | 3 of 3 | 0 of 317 |

## E. Performance (this machine)

| Model | Load time (s) | Single message p50 (ms) | p95 (ms) | Batch of 100 (messages/s) |
|---|---|---|---|---|
| baseline | 0.01 | 1.4 | 1.6 | 2706.6 |
| sbert | 0.0 | 7.4 | 8.3 | 1170.7 |
| sbert+tfidf | 0.01 | 8.6 | 9.7 | 754.5 |