# Collecting real classmate messages (the open Week 2 feedback)

Week 2 feedback asked for data collected from people in your class, not generated data. Week 6 does
not close that gap: the training and test data in this asset are still generated. What Week 6 adds is
a way to score real data the moment you have it, without writing new code.

1. Ask classmates (consent first, no names or student numbers) to write 3-5 short messages they
   might send to student support: what they would actually say, in their own words (Hinglish and
   abbreviations are welcome, those are exactly what the model has not seen).
2. Two people label each message independently using the five categories and three urgency levels.
   Put them in a CSV with columns `text,category,urgency` (see `examples/classmate_template.csv`).
   Record how often the two labellers agree; where they disagree, discuss and write down the rule.
3. Score it:

   ```bash
   python -m s3t evaluate --csv classmate_messages.csv --out reports/classmate_eval.md
   ```
   The report gives accuracy, macro-F1, per-class results, silent errors and the confidence table.
   Report these numbers as the main result, ahead of the generated test set.
4. Do not tune the thresholds on this file if you also want to report on it; calibrate on training
   data (`python -m s3t calibrate`), then evaluate once.
