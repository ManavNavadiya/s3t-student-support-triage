# Model card - S3T triage models

## What it is
Two classifiers per task (category: 5 classes; urgency: 3 classes), plus rule-based extraction,
crisis detection and a human-review guardrail. Default model: **`sbert+tfidf`** (hybrid).

| Name | Features | Classifier | Where it came from |
|---|---|---|---|
| `baseline` | stemmed TF-IDF (1-2 grams) | Logistic Regression (category), Naive Bayes (urgency) | Week 2 |
| `sbert` | all-MiniLM-L6-v2 sentence embeddings (384 numbers) | Logistic Regression | Week 4 |
| `sbert+tfidf` | embeddings + the baseline's TF-IDF features | Logistic Regression | Week 4, chosen in Week 5 |

The encoder has 22 million parameters and is downloaded once (about 90 MB). The saved `.joblib`
files are exactly those evaluated in Week 5; Week 6 did not retrain anything.

## Intended use
Help support staff sort incoming student messages into the right queue and notice urgent ones faster.
Every output is advisory and flagged for review when risky. **Not** for automatic replies, grading,
discipline, or any decision about a student without a human reading the message.

## Data
- Training: 1,170 generated messages built from 60 distinct template sentences (with varied greetings and
  closings and about 4% deliberately flipped labels). Test: 299 messages built from 15 held-out sentences.
- Challenge set: 30 messages written by the team to break the model (Indian-university terms,
  Hinglish, negation, indirect crisis language, out-of-scope).
- **No messages from real students.** The Week 2 feedback asked for classmate data; it has not been collected.

## Performance (from the Week 5 report; held-out test set, model + rules)
| | Baseline | SBERT | **Hybrid (default)** |
|---|---|---|---|
| Category macro-F1 | 0.588 | 0.880 | 0.859 |
| Urgency macro-F1 | 0.751 | 0.602 | 0.794 |
| High-urgency recall | 0.944 | 0.963 | 0.981 |
| Challenge set category correct (of 28) | 13 | 17 | 17 |
| Challenge set urgency correct (of 28) | 16 | 16 | 20 |

### Behaviour of the packaged asset at its default settings (hybrid; `python -m s3t verify`, 2026-10-11)
Category review threshold 0.55 (calibrated on training data); urgency confidence is not a review trigger.

| | Test set (n = 299) | Challenge set (n = 30) |
|---|---|---|
| Flagged for human review | 47% | 63% |
| Silent category errors (wrong, not flagged) | 21 (7.0%) | 3 |
| Truly High urgency, predicted lower, not flagged | 1 of 54 | 1 of 10 |
| High-urgency recall / precision | 0.981 / 0.515 | 0.900 / 0.643 |

Before the urgency trigger was removed, 76% of test messages were flagged (18 silent category errors); see
`docs/week6_report.md` section 4.3.

How much to trust these: the test set has 15 distinct sentences, so the honest 95% interval for the
hybrid's category macro-F1 is 0.59 to 0.98 (resampling sentences). Design choices in Weeks 4-5 were made
after looking at this test set. Expect real messages to do worse.
Re-measured numbers for the packaged code are produced by `python -m s3t verify`.

## Known failure modes (Week 5)
- Confidently wrong on whole unseen sentences (e.g. "update my mailing address" sent to Technical Support).
- Medium urgency often over-escalated to High (49 of 54 urgency errors). High precision is 0.515, so about a
  third of all messages are predicted High and sent to staff by rule R4; this is the main reason the review
  rate is still 47%.
- Mental Health recall is 0.77 on the test set: about 13 of 56 wellbeing messages were assigned to another
  category.
- A truly High message predicted Medium or Low is no longer flagged just for being uncertain (1 of 54 on the
  test set), because urgency confidence is not a review trigger.
- Boundaries between Financial Aid / Administrative / Academic are genuinely blurry; one label is forced.
- Negation is not understood ("not stressed" still reports stress).
- Truncated messages lose about 0.25 category macro-F1.
- Out-of-scope messages ("thanks", "hi") are forced into a category.
- Crisis detection is keyword/regex only. The extended lexicon (this asset) covers phrases found in
  Week 5, written after seeing them, so how well it generalises is untested. Short phrases cause some false alarms.

## Safety design
Crisis language forces High urgency and human review regardless of confidence. Low category confidence, High
urgency -> human review. Urgency confidence itself is not used to trigger review: calibration showed it does
not separate right from wrong urgency answers, and using it flagged 76% of messages. The system never acts by itself. Review thresholds should be
calibrated (`python -m s3t calibrate`) and the staff review rate monitored: a threshold that flags too much will be
ignored, one that flags too little lets errors through silently.

## Privacy
The API does not log or echo message text. Do not include names or student numbers in `text`; use `id`.
Messages from real students need consent and a data-handling decision before being stored.

## Maintenance
Retrain only in the Week 4 / 5 folders, drop new `.joblib` files in the models folder, then run
`python -m s3t verify` and `python -m s3t calibrate`. Pickled scikit-learn models can warn or fail under a
different scikit-learn version; the asset surfaces such warnings in `meta.warnings`.