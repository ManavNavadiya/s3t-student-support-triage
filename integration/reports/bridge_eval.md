# Early-warning decision: evaluation against human labels

S3T model: `sbert+tfidf` | messages: 31 | labelled at risk: 14 | labelled not at risk: 17

**Data:** SYNTHETIC: 31 hand-written messages,

## Results

| Metric | Value |
|---|---|
| Precision (of those flagged, how many truly at risk) | 1.00  (95% interval 0.65 to 1.00; 7/7) |
| Recall (of those truly at risk, how many flagged) | 0.50  (95% interval 0.27 to 0.73; 7/14) |
| F1 | 0.67 |
| Accuracy | 0.77  (95% interval 0.60 to 0.89; 24/31) |
| Flag levels given | HIGH 5, MEDIUM 2, LOW 24 |

| | Flagged at risk | Not flagged |
|---|---|---|
| **Truly at risk** | 7 (true positive) | 7 (false negative) |
| **Not at risk** | 0 (false positive) | 17 (true negative) |

With only 31 messages the intervals above are wide; treat the figures as indicative.

## Course → topic mapping

Correct topic for 6 of 6 messages that name a course.


## False positives: flagged but not at risk (0)

None.

## False negatives: at risk but not flagged (7)

These matter most. Note which wording the signals did not recognise.

**Row 3**: hi ma'am, i havent been able to attend class for almost 3 weeks and i dont know what to do about the lab record. i feel like im way behind …
- S3T category: Academic Difficulty (0.49); decision: LOW; signals fired: none

**Row 5**: My attendance in DBMS is below 60% and I scored only 8/30 in M1. Will I be debarred from the end semester exam?
- S3T category: Academic Difficulty (0.42); decision: LOW; signals fired: none

**Row 7**: I think I will probably fail Operating Systems this semester. I did badly in both tests and I have not been submitting the assignments regu…
- S3T category: Academic Difficulty (0.94); decision: LOW; signals fired: fear_of_failing

**Row 8**: Respected Sir, I am writing regarding my performance in Information Retrieval (CS 430). Due to prolonged health issues in September I was a…
- S3T category: Academic Difficulty (0.79); decision: LOW; signals fired: passing_criteria_query

**Row 10**: Could you tell me what the passing criteria is? I got only 12 out of 50 in the midterm and did not hand in the last two labs.
- S3T category: Academic Difficulty (0.93); decision: LOW; signals fired: passing_criteria_query

**Row 12**: Hello, I wasn't able to attend the internals because of a family emergency. Is there any way to appear later? My project submission is also…
- S3T category: Technical Support (0.36); decision: LOW; signals fired: none

**Row 13**: I feel like giving up on this degree. I missed the last two tests and I have no energy to open my books anymore.
- S3T category: Academic Difficulty (0.48); decision: LOW; signals fired: none

## Notes

- Labels come from the humans who wrote the CSV; the result is only as good as that labelling.
- Do not edit the signal patterns to fix these errors and then report the same file as a fresh test.
