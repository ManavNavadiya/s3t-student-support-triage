"""
Fast tests. They use the TF-IDF baseline so they need neither torch nor internet.
Run:  pytest -q
(`python -m s3t verify` is the full check and also covers the hybrid model.)
"""
import json

import pytest

from s3t import Triage, TriageRequest, TriageResult
from s3t.config import CATEGORIES, MAX_BATCH, URGENCY_LEVELS
from s3t.extraction import extract, find_crisis
from s3t.rules import apply_rules


@pytest.fixture(scope="module")
def triage():
    return Triage(model="baseline")


def test_result_shape_and_probabilities(triage):
    r = triage.predict("I can't log in to Canvas and my CS101 quiz closes today")
    assert isinstance(r, TriageResult)
    assert set(r.category.probabilities) == set(CATEGORIES)
    assert set(r.urgency.probabilities) == set(URGENCY_LEVELS)
    assert abs(sum(r.category.probabilities.values()) - 1) < 2e-3
    assert r.category.confidence == max(r.category.probabilities.values())
    assert 0 <= r.category.margin <= 1
    assert r.advisory_only is True
    assert r.meta.model == "baseline"
    json.dumps(r.model_dump())


def test_batch_matches_single(triage):
    texts = ["My financial aid has not arrived.", "How do I get my transcript?"]
    batch = triage.predict_batch(texts, ids=["a", "b"])
    assert [b.id for b in batch] == ["a", "b"]
    for text, b in zip(texts, batch):
        assert triage.predict(text).category.label == b.category.label


@pytest.mark.parametrize("bad", ["", "   ", None, 5, "x" * 5000])
def test_invalid_input_rejected(triage, bad):
    with pytest.raises(ValueError):
        triage.predict(bad)


def test_batch_limits(triage):
    assert triage.predict_batch([]) == []
    with pytest.raises(ValueError):
        triage.predict_batch(["hello"] * (MAX_BATCH + 1))
    with pytest.raises(ValueError):
        triage.predict_batch(["a", "b"], ids=["only-one"])


def test_crisis_forces_high_and_review(triage):
    r = triage.predict("I want to hurt myself")
    assert r.crisis_detected and r.urgency.label == "High"
    assert r.human_review.required and "crisis_language" in r.human_review.reasons
    assert r.recommended_action.startswith("IMMEDIATE")


def test_extended_crisis_lexicon():
    assert find_crisis("I don't want to live like this anymore")
    assert find_crisis("Nobody would even notice if I disappeared")
    assert find_crisis("I don’t want to live like this")            # curly apostrophe
    assert not find_crisis("I don't want to live in the hostel any more")  # harmless
    assert not find_crisis("I don't want to live like this anymore", extended=False)
    assert find_crisis("I want to hurt myself", extended=False)


def test_rules_deadline_and_confidence():
    info = {"crisis_detected": False, "imminent_deadline": True}
    out = apply_rules("Technical Support", "Low", 0.95, 0.95, info, 0.4, 0.4)
    assert out["urgency"] == "Medium" and not out["review_required"]
    out = apply_rules("Technical Support", "Low", 0.20, 0.95, info, 0.4, 0.4)
    assert out["review_reasons"] == ["low_category_confidence"]


def test_extraction_basics():
    info = extract("My MATH 204 exam is tomorrow and there is a hold on my account")
    assert info["courses"] == ["MATH 204"]
    assert "tomorrow" in info["deadlines"] and info["imminent_deadline"]
    assert "account / registration hold" in info["blockers"]


def test_thresholds_can_be_overridden():
    t = Triage(model="baseline", thresholds=(0.99, 0.99))
    r = t.predict("hello there")
    assert r.meta.thresholds_source == "user"
    assert r.human_review.required        # nothing reaches 0.99 for such a short message


def test_text_not_echoed(triage):
    r = triage.predict("Please update my mailing address zzqx7unique", id="t1")
    assert r.id == "t1" and "zzqx7unique" not in json.dumps(r.model_dump())


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        Triage(model="nope")


# ---------------- HTTP API (skipped when fastapi / httpx are not installed) ----------------
def test_http_api(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from s3t.api import create_app
    monkeypatch.delenv("S3T_API_KEY", raising=False)
    with TestClient(create_app("baseline")) as c:
        assert c.get("/health").json()["model"] == "baseline"
        r = c.post("/v1/triage", json={"text": "wifi is down in the library", "id": "x"})
        assert r.status_code == 200 and r.json()["id"] == "x"
        assert c.post("/v1/triage", json={"text": ""}).status_code == 422
        b = c.post("/v1/triage/batch", json={"items": [{"text": "a b c"}, {"text": "d e f"}]})
        assert b.json()["count"] == 2
        assert c.post("/v1/triage/batch", json={"items": []}).status_code == 422


def test_http_api_key(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from s3t.api import create_app
    monkeypatch.setenv("S3T_API_KEY", "secret")
    with TestClient(create_app("baseline")) as c:
        assert c.post("/v1/triage", json={"text": "hello"}).status_code == 401
        assert c.post("/v1/triage", json={"text": "hello"},
                      headers={"X-API-Key": "secret"}).status_code == 200


def test_urgency_score_is_not_a_review_trigger_when_threshold_is_zero():
    info = {"crisis_detected": False, "imminent_deadline": False}
    out = apply_rules("Technical Support", "Medium", 0.99, 0.34, info, 0.4, 0.0)
    assert not out["review_required"] and out["review_reasons"] == []
    # category confidence and the High-urgency rule still trigger review
    out = apply_rules("Technical Support", "Medium", 0.30, 0.34, info, 0.4, 0.0)
    assert out["review_reasons"] == ["low_category_confidence"]
    out = apply_rules("Technical Support", "High", 0.99, 0.34, info, 0.4, 0.0)
    assert out["review_reasons"] == ["high_urgency"]


def test_default_urgency_threshold_is_zero(tmp_path):
    from s3t.triage import load_thresholds
    cat, urg, src = load_thresholds("sbert+tfidf", tmp_path)   # empty folder -> defaults
    assert (cat, urg, src) == (0.40, 0.0, "default")