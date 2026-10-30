"""Run the Group 6 pipeline on one fixed email (no browser).

    PYTHONPATH=.:.. python demo.py                         # Group 6 only
    PYTHONPATH=.:.. python demo.py --email pace
    # with partner services running (optional):
    PYTHONPATH=.:.. python demo.py --group7 http://127.0.0.1:8080 --group5 http://127.0.0.1:8002

--group5 accepts a URL, local:<Group5 folder> or off; --group7 a URL or off.
S3T is imported in-process (pip install -e . from the repository root). Use --s3t-url to call its HTTP API
instead (python -m s3t serve --port 8001).
"""
import argparse, json, urllib.request
from group5_feedback import make_group5
from pipeline import run_pipeline

EMAILS = {
    "risk": ("Dear Professor, I missed the M1 test of Natural Language Processing (CS 521) because I was unwell, "
             "and I have also not submitted some of my assignments. I am worried about failing. "
             "Could you please tell me the passing criterion for internal assessment? Is a make-up test possible?"),
    "pace": ("Hello sir, the lectures in CS 410 go way too fast and I cannot follow them. I missed the quiz last week "
             "and I have not submitted two assignments. I am worried about failing. Regards, Student"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--s3t-url"); ap.add_argument("--group7", default="off")
ap.add_argument("--group5", default="off", help="URL | local:<Group5 folder> | off")
ap.add_argument("--model", default="auto", help="S3T model: auto|baseline|sbert+tfidf")
ap.add_argument("--email", choices=sorted(EMAILS), default="risk")
a = ap.parse_args()
EMAIL = EMAILS[a.email]

if a.s3t_url:
    req = urllib.request.Request(a.s3t_url.rstrip("/") + "/v1/triage",
        data=json.dumps({"text": EMAIL, "id": "stu-001"}).encode(), headers={"Content-Type": "application/json"})
    s3t = json.load(urllib.request.urlopen(req))
else:
    from s3t import Triage
    s3t = Triage(model=a.model).predict(EMAIL, id="stu-001").model_dump()

print(json.dumps(run_pipeline(EMAIL, s3t, group5=make_group5(a.group5), group7_url=a.group7).to_dict(), indent=2))
