# Responsible-AI analysis: Early Warning → Course Insight → Mentor Discovery

Scope: the integrated pipeline of Group 6 (S3T student-email triage), Group 5 (Student Feedback
Intelligence, aspect-based sentiment) and Group 7 (research discovery), joined by `s3t_to_discovery.py`,
`group5_feedback.py` and `pipeline.py`. Group 5's own limits are in its README. Group 6's own limits are detailed in its `MODEL_CARD.md`; this document
covers the pipeline as a whole.

## 1. Purpose and intended use

**Intended:** help support staff notice students who may be failing (missed tests, missing submissions) and
suggest which researchers could mentor them on the course topic, so a person can decide on outreach or a
make-up assessment.

**Not intended:** automatic replies, grading, discipline, eligibility decisions, ranking students, or any
action on a student without a staff member reading the message. The system is advisory only and sends
nothing by itself.

## 2. Who is affected

| Group | How |
|---|---|
| **Students** | Their private emails are analysed; a wrong flag could bring unwanted attention, a missed flag could mean help never arrives. |
| **Support staff** | They receive the flags and decide what to do; they carry the workload of false alarms. |
| **Mentors** | They may be suggested for students without having agreed to it, and the matches are based only on paper similarity. |

## 3. How decisions are made (transparency)

1. S3T predicts a category and urgency, extracts course codes and deadlines, and checks for crisis wording.
2. The bridge applies four keyword signals (missed assessment, missing submissions, passing-criteria
   question, fear of failing) to produce **HIGH / MEDIUM / LOW**.
3. Group 5 scores the (cleaned) email for sentiment on eight course aspects. Confident negative aspects
   become "concerns", which add a support focus to the suggested action. **Group 5 never changes the
   HIGH / MEDIUM / LOW decision.**
4. The course code or name is mapped to a topic through a hand-written catalog.
5. Group 7 ranks researchers by similarity between the topic and their papers.

The page shows every step: the signals that fired, the stated basis, the course-to-topic source, each
mentor's papers, and the raw JSON. A reviewer can see why a student was flagged and challenge it.

## 4. Known failure modes

### 4.1 Wrongly flagged students (false positives)
- Keyword matching ignores negation. "I did **not** miss the quiz and none of my assignments are pending"
  is flagged **HIGH** (tested). S3T itself also does not understand negation.
- S3T over-escalates urgency: about a third of all messages are predicted High, and High-urgency precision
  was 0.515 on its test set. Staff will see many alarms that are not urgent.
- Possible harm: a student who is fine is treated as a problem, or staff time is wasted until alerts are ignored.

### 4.2 Missed students (false negatives)
- Wording the patterns do not know is missed. "I missed the **mid sem**" (no hyphen) fails to register as a
  missed assessment, so the risk drops from HIGH to MEDIUM (tested). Hinglish, indirect phrasing and
  truncated messages are further weak spots.
- S3T's silent category errors were 7% on its test set, and 1 of 54 truly High-urgency messages was
  predicted lower without being flagged.
- Students who write nothing, or write to someone else, are never seen at all.
- Possible harm: a struggling student receives no outreach and the pipeline appears to have "checked".

### 4.3 Crisis detection
Crisis detection is a keyword and regex list written after seeing the Week 5 examples, so how well it
generalises is untested, and short phrases can cause false alarms. It must not be relied on to catch every
wellbeing emergency. The page tells staff to respond immediately when it fires and not to rely on automatic
routing when it does not.

### 4.4 Wrong or missing topic
- Only the first course mentioned is searched; others are silently ignored (tested).
- A course missing from `course_catalog.json` produces no search at all. The catalog has four courses, so
  students in other courses receive no mentor suggestion. This is an **unequal-service risk** that follows
  directly from the catalog's coverage.

### 4.4b Course-experience readings (Group 5)
- **Domain shift.** Group 5 was trained on RateMyProfessor course reviews; student emails are help requests.
  On the at-risk demo email its overall confidence was 0.47 and every aspect was below its 0.60 threshold; a
  neutral transcript request was read as *negative* 0.55; "I missed the quiz and I am really stressed" was
  read as Exams/Grading *positive* (tested). This is why Group 5 is not allowed to decide risk.
- **Keyword aspects.** Aspects are found by keyword (`fast`, `test`, `professor`…), so a word used in another
  sense creates a false aspect. "Dear Professor" created a false *Teaching Quality* aspect until the bridge
  started stripping greetings.
- **Faculty-facing risk.** Course-feedback items name aspects of a course (e.g. *Teaching Quality*
  negative). One student's frustrated email is not representative feedback; items must be aggregated with
  Group 5's minimum-group rule (≥ 3 mentions) before anyone draws conclusions about an instructor, and must
  not be used in staff evaluation.
- **Possible harm:** a wrong support focus (e.g. suggesting recorded lectures when the real problem is
  illness) if staff treat it as a diagnosis rather than a hint.

### 4.5 Mentor suggestions (Group 7)
- Mentors are **OpenAlex researchers matched on paper similarity**; they are not necessarily this
  university's faculty and there is no teaching roster. The demo plan's "faculty who teach this in other
  divisions" is therefore **not delivered**; only the research-expertise half is.
- In our run, all five results were labelled HIGH confidence even though scores ranged from 0.47 to 0.57
  and the fifth result was a paper on climate-change sentiment. The label is not a calibrated probability.
- Each match rests on a single paper, so one loosely related paper can place a person high in the list.
- Possible harm: a student is directed to someone who cannot actually help, or a researcher is named as a
  mentor without their agreement.

## 4A. What has and has not been measured

**Measured (Group 6 alone, on generated data):** category and urgency precision, recall and F1, silent-error
rate and review rate, reported in Group 6's model card and Week 6 report.

**Checked by hand (the bridge):** five purpose-built emails, run through the early-warning rules. The rules
behaved as described in section 4 (two correct fallbacks, one ignored second course, one false positive, one
downgrade). Five hand-picked cases show that these failure modes exist; they say nothing about how often
they occur.

**Measured on a synthetic set (the bridge's early-warning flag):** 31 hand-written messages
(`synthetic_eval_emails.csv`: 14 at risk, 17 not), labelled by one person who knew how the rules work. These
are **not real students**. The full figures, with 95% intervals and every false positive and false negative
listed, are in `reports/bridge_eval.md`, produced by `evaluate_bridge.py`. What the run showed:

- **The flag is conservative: few false alarms, many misses.** It flagged few messages that were not at risk
  (one, caused by negation: "I did *not* miss the exam"), but it missed about half of the messages labelled at
  risk. As a screen it is better at avoiding false alarms than at catching every student.
- **Misses came from wording the patterns do not recognise.** Verified directly on the patterns: "I missed
  the last test" is caught but "I missed the last two *tests*" is not (plural); "absent for the mid-sem
  examination" is not (no verb "absent", and "examination" is not "exam"); "did not hand in the labs", "have
  not been submitting the assignments" and "wasn't able to attend the internals" are not. Messages that
  describe risk without any of these words ("my attendance is below 60%", "I feel way behind") fire no signal.
- **A flag needs two kinds of evidence, so one-sided messages are not flagged.** A student who states a
  failing score and a missing submission, but in unrecognised words, is not flagged.

**How far to trust these figures:** not far. The set is small (the intervals are wide), the labeller knew the
rules, hard cases were included on purpose and the routine messages are mostly easy. So the miss rate is
probably pessimistic and the false-alarm rate optimistic for real mail. The figures show the failure modes;
they do not estimate real-world accuracy.

**Not yet measured:** performance on real student emails. None have been collected, which was also the open
Week 2 feedback, so no accuracy claim is made for real students. `collect_emails.py` and `merge_labels.py`
exist to gather and label real messages (consented, anonymous, two independent labellers), after which
`evaluate_bridge.py` can be re-run on them and its report should replace the synthetic one above.

## 5. Data and fairness

- **Training data is generated, not real.** S3T was trained on 1,170 messages built from 60 template
  sentences, with a test set built from 15 held-out sentences. No real student messages were used, so
  accuracy on real students is **unknown**; the model card states to expect real performance to be worse.
  Its own 95% interval for category macro-F1 is 0.59 to 0.98.
- **Language and writing style.** Templated English favours formal, native-style writing. Students who write
  informally, in Hinglish, in a second language, or very briefly may be flagged less reliably. This has not
  been measured by group, so we cannot claim parity.
- **No sensitive attributes are used.** The pipeline does not take names, gender, caste, religion or
  nationality as inputs. Indirect effects through writing style, as above, can still occur.
- **Researcher fairness.** Group 7 ranks authors by how similar their papers are to the topic. We have not
  checked whether this favours some researchers over others (for example by publication volume, recency or
  title wording). In our one query, all five top papers were from 2024 to 2026. The suggested mentors are
  therefore the best textual matches in Group 7's data, not a fair sample of who could help.

## 6. Privacy and data handling

- The demo server does **not log** request paths or email text (`log_message` is disabled). S3T's API does
  not log or echo message text.
- **Data minimisation:** Group 7 receives only a topic phrase, never the email, the student id, or the S3T result.
- **Group 5** must see the email text to analyse it. Before sending, the bridge removes the greeting and
  sign-off (where names usually are) and masks roll-number-like tokens; Group 5 then masks emails, URLs and
  phone numbers. Names inside the body are **not** removed. The request id is random, not the student id.
  Messages with crisis language are not sent to Group 5 at all. Group 5's API does not store requests.
- The anonymised course-feedback item carries only course code and aspect names, no text and no id.
- The UI uses a placeholder student id (`demo-student`). Do not paste names or student numbers.
- Nothing is stored by the integration code. The browser page keeps the result only on screen.
- Before any real use: consent for processing student emails, a retention rule, access control on who sees
  flags, and a decision about whether flags may be written to a student record.

## 7. Human oversight and accountability

| Safeguard | Where |
|---|---|
| Advisory-only: staff decide every action; nothing is sent automatically | UI footer; `advisory_only` in S3T |
| Human-review flag and reasons shown for every message | Card 1 in the UI |
| Crisis language forces HIGH, human review and an "immediate follow-up" action | S3T rule R1; bridge |
| Baseline-model warning | UI banner |
| Evidence shown, not just a verdict (signals, basis, papers) | Cards 2 and 3 |
| Uncalibrated-confidence notice for Group 7 | UI banner |
| Group 7 outage shown plainly, not hidden | `group7_unavailable` status |
| Group 5 cannot change the risk decision | `handoff()`; test `test_group5_never_changes_risk_decision` |
| Only confident Group 5 readings count; others marked "low confidence" | `summarise()`; Card 2 |
| Group 5 outage does not stop the pipeline | `course_experience.status = unavailable` |
| Crisis messages bypass Group 5 | `analyse_feedback(crisis=True)` |

**Review load:** S3T flags about 47% of test messages for human review. If staff cannot keep up, flags
will be ignored; a threshold that flags too much is as unsafe as one that flags too little. The review rate
should be monitored and the thresholds recalibrated.

## 8. Risk summary

| Risk | Likelihood | Severity | Mitigation now | Still needed |
|---|---|---|---|---|
| Student wrongly flagged | Medium | Low to medium | Staff review; evidence shown | Negation handling; test on real emails |
| At-risk student missed | Medium | High | Hybrid model; two signal routes | Real data; broader patterns; monitoring |
| Crisis message not detected | Unknown | Very high | Keyword rule; wording in UI | Counsellor-reviewed process; do not rely on automation |
| Student in an uncatalogued course gets nothing | High | Medium | `needs_topic` message and topic override | Real course catalog |
| Mentor not a good or real fit | Medium | Low to medium | Papers shown; warning banner | Faculty roster; calibrated confidence |
| Wrong course-experience reading (Group 5) | High on emails | Low | Cannot change risk; ≥0.60 only; low-confidence banner | Retrain / evaluate Group 5 on labelled emails |
| Single email used to judge an instructor | Low | Medium to high | Item is aspect-only, not sent automatically | Aggregate with min-3 rule; policy forbidding use in staff evaluation |
| Private email exposed | Low | High | No logging; topic-only handoff; local run | Access control, retention rules |
| Over-trust in the tool | Medium | Medium | Advisory footer and notices | Staff training |

## 9. What must happen before real use

1. Collect and evaluate on real, consented student emails, and report results by language and writing style.
2. Handle negation and widen the signal patterns (e.g. "mid sem"); search every course mentioned.
3. Replace the placeholder catalog with the real course list.
4. Add a verified faculty or teaching roster to Group 7, and calibrate its confidence labels.
5. Evaluate Group 5 on labelled student emails (it is only evaluated on reviews), and mask names in the body.
6. Have counsellors review the crisis process and the lexicon.
7. Agree on data retention, access control and a way for students to ask what was recorded and to contest a flag.
8. Monitor flag rates and false alarms after launch.

**Position for the demo:** this is a prototype showing how three components connect. Its outputs are leads for
a person to check, not findings about a student.
