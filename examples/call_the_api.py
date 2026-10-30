"""Call the running HTTP service.
Start it first:  python -m s3t serve     (then run this file)
Needs only the standard library."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})   # add "X-API-Key" if set
    with urllib.request.urlopen(req) as r:
        return json.load(r)


one = post("/v1/triage", {"text": "My scholarship money has not been disbursed", "id": "ticket-7"})
print(one["category"]["label"], one["category"]["confidence"], one["human_review"])

many = post("/v1/triage/batch", {"items": [{"text": "wifi down in hostel"}, {"text": "need transcript"}]})
print(many["count"], [r["category"]["label"] for r in many["results"]])
