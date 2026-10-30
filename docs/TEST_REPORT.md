# Week 8 final test report: S3T (Group 6)

## How to reproduce

```bash
./run_demo.sh --setup      # once: creates .venv and installs S3T with the hybrid model
./run_tests.sh             # pytest + s3t verify + integration tests
./run_demo.sh              # in a second terminal, then:
./run_tests.sh --e2e       # adds the end-to-end check; writes docs/e2e_results.md
```

## 1. Summary

| Suite | What it covers | Tests | Result |
|---|---|---|---|
| S3T asset (`tests/`, pytest) | Schema, input validation, confidence fields, rules R1–R4, crisis lexicon, CLI, HTTP API | 19 | **19 passed** on the team Mac (11 Oct); 17 passed + 2 skipped (no FastAPI) in the Week 8 build environment |
| Contract checks (`s3t verify`) | Output schema, probabilities sum to 1, batch = single, deterministic, validation, crisis rule, no text echo, JSON output, HTTP API | 10 | **10 passed** |
| Week 5 regression (`s3t verify`) | Packaged models reproduce Week 5 numbers for baseline, SBERT and hybrid | 21 | **21 passed** |
| Integration (`integration/tests`) | Early-warning rules, course → topic, partner contracts with fake servers, privacy, outages, partners switched off | 20 | **19 passed**, 1 skipped (needs Group 5's code, not in this repo) |
| End-to-end (`integration/e2e_check.py`) | 14 scenarios through the running demo, Group 6 alone | 28 checks | **26 passed** on the baseline model; see note |

**Note on the end-to-end run.** The Week 8 build environment could only load S3T's baseline model. The
two checks that failed (demo email categorised *Academic Difficulty*; human review required) are the
baseline's known error on that email (Week 5). On the team Mac with the default hybrid model the same email
gives *Academic Difficulty* (0.83), urgency High and human review required, so both checks hold there.
Run `./run_tests.sh --e2e` on the Mac for the final table. Four partner-only checks are skipped when
Group 5 and Group 7 are not connected.

## 2. End-to-end scenarios (Group 6 alone)

| # | Scenario | Checks | Result (baseline) |
|---|---|---|---|
| 1 | At-risk student (missed M1 test, missing assignments, CS 521) | category, course extracted, review flag, HIGH, both signals, topic NLP, topic reported with Group 7 off | 5 of 7 (2 = baseline error, pass on hybrid) |
| 2 | Canvas login, quiz closes today (STAT 230) | Technical Support; deadline "today"; course extracted | 3 of 3 |
| 3 | Financial aid not disbursed | Financial Aid; not an academic-risk case | 2 of 2 |
| 4 | Transcript request, no rush | Administrative; not at risk; no crisis | 3 of 3 |
| 5 | "I feel hopeless and I don't want to live anymore" | crisis detected; High + review; immediate human follow-up | 3 of 3 |
| 6 | "Nobody would even notice if I disappeared" | crisis detected by the extended lexicon | 1 of 1 |
| 7 | Unknown course ZZ 999 | at risk; asks for a topic instead of guessing | 2 of 2 |
| 8 | Topic override | override used | 1 of 1 |
| 9 | Partner Group 5 down | reported unavailable; Group 6 result unaffected | 2 of 2 |
| 10 | Partner Group 7 down | reported, not crashed | 1 of 1 |
| 11 | Negation ("I did **not** miss the quiz") | wrongly flagged: known limitation reproduced | 1 of 1 |
| 12–13 | Over-long and empty input | rejected with a clear error | 2 of 2 |

## 3. Model results (unchanged since Week 5; confirmed by the regression checks)

| Metric (hybrid `sbert+tfidf`) | Test set (n = 299) | Challenge set (n = 30) |
|---|---|---|
| Category accuracy / macro-F1 | 0.860 / 0.859 | 0.607 / 0.592 |
| Urgency accuracy / macro-F1 | 0.819 / 0.794 | 0.750 / 0.768 |
| High-urgency recall / precision | 0.981 / 0.515 | 0.900 / 0.643 |
| Flagged for human review | 47% | 63% |
| Silent category errors | 21 (7.0%) | 3 |
| Crisis messages detected (extended lexicon) | — | 3 of 3, 0 false alarms on 317 others |

| Model | Category macro-F1 | Urgency macro-F1 | Median latency |
|---|---|---|---|
| Baseline (TF-IDF) | 0.588 | 0.751 | 1.4 ms |
| SBERT | 0.880 | 0.602 | 7.4 ms |
| **Hybrid (default)** | **0.859** | **0.794** | 8.6 ms |

Early-warning flag (bridge), 31 synthetic emails: precision 1.00, recall 0.50 (`integration/reports/bridge_eval.md`).

## 4. Known limitations confirmed by testing

- All training and test data is generated; no real student messages yet.
- Keyword early-warning signals ignore negation (scenario 11) and miss unseen wording (recall 0.50).
- The model over-predicts High urgency (precision 0.515), which drives the 47% review rate.
- The baseline model misreads the main demo email; the hybrid (default) is required for the demo.
