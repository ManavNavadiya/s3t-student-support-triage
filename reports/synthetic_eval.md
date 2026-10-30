## Evaluation of classmate_emails.csv

Model `sbert+tfidf`; review thresholds category 0.55 / urgency 0.00 (urgency score not used as a trigger); n = 31 messages.

| Metric | Value |
|---|---|
| Category accuracy | 0.742 |
| Category macro-F1 | 0.726 |
| Urgency accuracy | 0.710 |
| Urgency macro-F1 | 0.695 |
| High-urgency recall / precision | 0.917 / 0.611 |
| Silent urgency errors (wrong, not flagged) | 2 |
| Truly High but predicted lower and not flagged | 1 of 12 |
| Flagged for human review | 61% |
| Silent category errors (wrong, not flagged) | 3 |
| Wrong but flagged | 5 |
| Confidence bands (high / medium / low) | 7 / 15 / 9 |

Calibration of category confidence:

| Confidence | Messages | Mean confidence | Actual accuracy |
|---|---|---|---|
| 0.0-0.5 | 8 | 0.419 | 0.625 |
| 0.5-0.7 | 4 | 0.621 | 0.75 |
| 0.7-0.9 | 12 | 0.823 | 0.667 |
| 0.9-1.0 | 7 | 0.963 | 1.0 |

Per-class category report:

```
                           precision    recall  f1-score   support

      Academic Difficulty       0.86      0.86      0.86        14
Mental Health & Wellbeing       1.00      0.50      0.67         2
            Financial Aid       1.00      1.00      1.00         2
           Administrative       1.00      0.55      0.71        11
        Technical Support       0.25      1.00      0.40         2

                 accuracy                           0.74        31
                macro avg       0.82      0.78      0.73        31
             weighted avg       0.89      0.74      0.77        31
```
