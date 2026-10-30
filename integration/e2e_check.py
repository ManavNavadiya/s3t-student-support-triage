"""
End-to-end check of the running Group 6 (S3T) demo (Week 8 final testing).

Start the demo first (./run_demo.sh), then in another terminal: ./run_tests.sh --e2e
(or: python3 integration/e2e_check.py --out docs/e2e_results.md)

Each scenario goes through the real demo server: S3T triage, rules, the early-warning decision and the
bridge. Checks that need a partner service (Group 5 or Group 7) run only when that service is connected
and are reported as SKIP otherwise. Standard library only.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

RISK = ("Dear Professor, I missed the M1 test of Natural Language Processing (CS 521) because I was unwell, "
        "and I have also not submitted some of my assignments. I am worried about failing. Could you please tell "
        "me the passing criterion for internal assessment? Is a make-up test possible?")
PACE = ("Hello sir, the lectures in CS 410 go way too fast and I cannot follow them. I missed the quiz last week "
        "and I have not submitted two assignments. I am worried about failing. Regards, Student")

# (name, request body, list of (description, check, needs)); needs: None = Group 6 only,
# "g5" / "g7" = only checked when that partner service is connected, "no_g7" = only when it is not.
H = lambda r: r["handoff"]
SCENARIOS = [
    ("At-risk student (main demo email)", {"text": RISK}, [
        ("Group 6 category Academic Difficulty", lambda r: r["s3t"]["category"]["label"] == "Academic Difficulty", None),
        ("course CS 521 extracted", lambda r: "CS 521" in r["s3t"]["entities"]["courses"], None),
        ("human review required", lambda r: r["s3t"]["human_review"]["required"], None),
        ("early warning HIGH", lambda r: H(r)["early_warning"]["level"] == "HIGH", None),
        ("signals: missed assessment + missing submissions", lambda r: {"missed_assessment", "missing_submissions"} <= set(H(r)["early_warning"]["signals"]), None),
        ("course mapped to topic NLP", lambda r: H(r)["topic"]["topic"] == "natural language processing", None),
        ("topic reported, nothing sent (Group 7 off)", lambda r: H(r)["status"] == "group7_off", "no_g7"),
        ("Group 7 returned mentors", lambda r: H(r)["status"] == "ok" and len(H(r)["mentors"]) > 0, "g7"),
        ("Group 5 ran on cleaned text", lambda r: "greeting" in H(r)["course_experience"]["removed_before_sending"], "g5"),
    ]),
    ("Technical issue with a deadline", {"text": "Hi, I can't log in to Canvas and my STAT 230 quiz closes today."}, [
        ("Group 6 category Technical Support", lambda r: r["s3t"]["category"]["label"] == "Technical Support", None),
        ("deadline 'today' extracted", lambda r: any("today" in d.lower() for d in r["s3t"]["entities"]["deadlines"]), None),
        ("course STAT 230 extracted", lambda r: "STAT 230" in r["s3t"]["entities"]["courses"], None),
    ]),
    ("Financial aid", {"text": "My financial aid has not been disbursed and rent is due soon."}, [
        ("Group 6 category Financial Aid", lambda r: r["s3t"]["category"]["label"] == "Financial Aid", None),
        ("not an academic-risk case", lambda r: H(r)["status"] == "no_risk", None),
    ]),
    ("Routine query", {"text": "Hello, how do I request an official copy of my transcript? There is no rush, "
                               "any time this month is fine."}, [
        ("Group 6 category Administrative", lambda r: r["s3t"]["category"]["label"] == "Administrative", None),
        ("not flagged as at risk", lambda r: H(r)["status"] == "no_risk", None),
        ("no crisis", lambda r: not r["s3t"]["crisis_detected"], None),
    ]),
    ("Crisis language", {"text": "I feel hopeless and I don't want to live anymore. I missed the CS 521 exam."}, [
        ("crisis detected (rule R1)", lambda r: r["s3t"]["crisis_detected"], None),
        ("urgency High and human review", lambda r: r["s3t"]["urgency"]["label"] == "High" and r["s3t"]["human_review"]["required"], None),
        ("immediate human follow-up", lambda r: "IMMEDIATE" in H(r)["early_warning"]["suggested_intervention"], None),
        ("NOT sent to Group 5", lambda r: H(r)["course_experience"]["status"] == "skipped", "g5"),
    ]),
    ("Indirect crisis wording", {"text": "Nobody would even notice if I disappeared."}, [
        ("crisis detected (extended lexicon)", lambda r: r["s3t"]["crisis_detected"], None),
    ]),
    ("Unknown course", {"text": "Hi, I missed the mid-sem exam of ZZ 999 and I have not submitted the last two "
                                "assignments. I am worried about failing the course."}, [
        ("flagged at risk", lambda r: H(r)["early_warning"]["at_risk"], None),
        ("asks for a topic instead of guessing", lambda r: H(r)["status"] == "needs_topic", None),
    ]),
    ("Topic override", {"text": "Hi, I missed the mid-sem exam of ZZ 999 and I have not submitted the last two "
                                "assignments.", "topic_override": "computer vision"}, [
        ("override used", lambda r: H(r)["topic"]["source"] == "override", None),
    ]),
    ("Roll number and name in email", {"text": "Dear Sir, my roll no is 21BCE10234. I missed the CS 410 quiz and have "
                                               "not submitted the lab assignments. Thanks,\nRavi"}, [
        ("roll number and sign-off removed before Group 5", lambda r: any("id-like" in x for x in H(r)["course_experience"]["removed_before_sending"])
            and "sign-off" in H(r)["course_experience"]["removed_before_sending"], "g5"),
    ]),
    ("Partner Group 5 down", {"text": RISK, "group5_url": "http://127.0.0.1:9"}, [
        ("reported unavailable", lambda r: H(r)["course_experience"]["status"] == "unavailable", None),
        ("Group 6 result unaffected", lambda r: H(r)["early_warning"]["level"] == "HIGH", None),
    ]),
    ("Partner Group 7 down", {"text": RISK, "group7_url": "http://127.0.0.1:9"}, [
        ("reported, not crashed", lambda r: H(r)["status"] == "group7_unavailable", None),
    ]),
    ("Known limitation: negation", {"text": "I did not miss the CS 521 quiz and none of my assignments are pending."}, [
        ("wrongly flagged (documented limitation)", lambda r: H(r)["early_warning"]["at_risk"], None),
    ]),
]


def post(base, body):
    req = urllib.request.Request(base + "/api/analyze", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5050")
    ap.add_argument("--out")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/status", timeout=5) as r:
            status = json.load(r)
    except Exception as exc:
        sys.exit(f"Demo server not reachable at {base} ({exc}). Start it with ./run_demo.sh first.")

    lines = ["# End-to-end check results", "",
             f"Group 6 model: `{status['s3t_model']}` | Group 5: `{status['group5']}` ({status['group5_source']}) | "
             f"Group 7: `{status['group7']}` ({status['group7_url']})", "",
             "| # | Scenario | Check | Result |", "|---|---|---|---|"]
    connected = {"g5": status["group5"] not in ("off",), "g7": status["group7"] not in ("off",)}
    passed = total = skipped = 0
    for i, (name, body, checks) in enumerate(SCENARIOS, 1):
        code, resp = post(base, body)
        for desc, fn, needs in checks:
            if needs == "no_g7" and connected["g7"] or needs in ("g5", "g7") and not connected[needs]:
                skipped += 1
                lines.append(f"| {i} | {name} | {desc} | SKIP (partner not connected) |")
                continue
            total += 1
            try:
                ok = code == 200 and bool(fn(resp))
            except Exception:
                ok = False
            passed += ok
            lines.append(f"| {i} | {name} | {desc} | {'PASS' if ok else 'FAIL'} |")
    # input validation goes through the same server
    code, _ = post(base, {"text": "x" * 2001})
    total += 1; passed += code == 400
    lines.append(f"| {len(SCENARIOS) + 1} | Email over 2,000 characters | rejected with a clear error | {'PASS' if code == 400 else 'FAIL'} |")
    code, _ = post(base, {"text": "   "})
    total += 1; passed += code == 400
    lines.append(f"| {len(SCENARIOS) + 2} | Empty email | rejected with a clear error | {'PASS' if code == 400 else 'FAIL'} |")
    lines += ["", f"**{passed} of {total} checks passed** ({skipped} partner checks skipped).", ""]
    text = "\n".join(lines)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Written to {a.out}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
