# Review-threshold calibration (2026-10-11 14:32 UTC)

Model `sbert+tfidf`, 5-fold GroupKFold on 1170 training messages (60 templates). Target: silent-error rate <= 5%. The test set is not used.

## category: threshold 0.55

Out-of-fold accuracy 0.839 (C = 10).

| Threshold | Flagged | Silent errors | Accuracy of unflagged |
|---|---|---|---|
| 0.40 | 8% | 9.8% | 0.893 |
| 0.50 | 16% | 6.8% | 0.919 |
| 0.60 | 25% | 3.1% | 0.959 |
| 0.70 | 31% | 1.4% | 0.98 |
| 0.80 | 38% | 0.6% | 0.99 |
| 0.90 | 57% | 0.1% | 0.998 |
| 0.95 | 83% | 0.0% | 1.0 |

## urgency: NOT used as a review trigger (threshold written as 0.00)

The threshold that met the 5% target would be 0.50, but it is not used: the score does not separate right answers from wrong ones (see the last column, which should rise with the threshold and does not). A message with a high-urgency prediction is still reviewed by rule R4 and crisis language by rule R1. Re-run with `--urgency-trigger` to override.

Out-of-fold accuracy 0.644 (C = 0.1).

| Threshold | Flagged | Silent errors | Accuracy of unflagged |
|---|---|---|---|
| 0.40 | 25% | 21.8% | 0.708 |
| 0.50 | 74% | 4.6% | 0.826 |
| 0.60 | 95% | 1.9% | 0.639 |
| 0.70 | 99% | 0.9% | 0.167 |
| 0.80 | 100% | 0.0% | None |
| 0.90 | 100% | 0.0% | None |
| 0.95 | 100% | 0.0% | None |
