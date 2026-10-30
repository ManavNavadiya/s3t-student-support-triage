"""
triage.py - the public entry point.

    from s3t import Triage

    triage = Triage()                                  # loads the model once
    result = triage.predict("I can't log in and my quiz is due today")
    result.category.label, result.category.confidence
    result.human_review.required
    result.model_dump()                                # plain dict, JSON-ready
    results = triage.predict_batch(["...", "..."])     # faster than a loop
"""
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from .classifier import Predictions, load_bundle
from .config import (DEFAULT_REVIEW_THRESHOLD, DEFAULT_URGENCY_REVIEW_THRESHOLD, DISCLAIMER,
                     HIGH_CONFIDENCE, MAX_BATCH, MODELS_DIR, THRESHOLD_FILE_NAME, __version__)
from .extraction import extract
from .rules import apply_rules
from .schemas import (Entities, Meta, Review, ScoredLabel, TriageRequest, TriageResult)

TextOrRequest = Union[str, TriageRequest]


def load_thresholds(model_name: str, models_dir: Path) -> Tuple[float, float, str]:
    """(category threshold, urgency threshold, source) - calibrated file if present."""
    f = Path(models_dir) / THRESHOLD_FILE_NAME
    if f.exists():
        try:
            entry = json.loads(f.read_text()).get(model_name)
            if entry:
                return float(entry["category"]), float(entry["urgency"]), "calibrated"
        except (ValueError, KeyError, TypeError):
            pass
    return DEFAULT_REVIEW_THRESHOLD, DEFAULT_URGENCY_REVIEW_THRESHOLD, "default"


def _scored(labels: List[str], probs: np.ndarray, final_label: str) -> ScoredLabel:
    order = np.argsort(probs)[::-1]
    top = int(order[0])
    margin = float(probs[order[0]] - probs[order[1]]) if len(order) > 1 else float(probs[top])
    return ScoredLabel(
        label=final_label, model_label=labels[top], adjusted_by_rules=final_label != labels[top],
        confidence=round(float(probs[top]), 4), margin=round(margin, 4),
        probabilities={l: round(float(p), 4) for l, p in zip(labels, probs)})


class Triage:
    """Load once, call many times. Safe to share between threads."""

    def __init__(self, model: str = "auto", models_dir: Optional[Union[str, Path]] = None,
                 thresholds: Optional[Tuple[float, float]] = None,
                 extended_crisis: bool = True):
        """
        model            'auto' | 'baseline' | 'sbert' | 'sbert+tfidf'.
                         'auto' = hybrid, or the baseline (with a warning in meta.warnings).
        models_dir       folder with the .joblib files (default: packaged ones).
        thresholds       (category, urgency) confidence below which a human must review.
                         Default: calibrated file if present, else (0.40, 0.0).
                         An urgency threshold of 0.0 means the urgency score is not a review
                         trigger; High urgency is still reviewed by rule R4.
        extended_crisis  True = also detect indirect crisis phrasing (recommended).
        """
        self.models_dir = Path(models_dir or MODELS_DIR)
        self._bundle, self._warnings = load_bundle(model, self.models_dir)
        self.model_name = self._bundle.name
        self.extended_crisis = extended_crisis
        if thresholds is not None:
            self.cat_threshold, self.urg_threshold = map(float, thresholds)
            self.thresholds_source = "user"
        else:
            self.cat_threshold, self.urg_threshold, self.thresholds_source = \
                load_thresholds(self.model_name, self.models_dir)
        if self.thresholds_source == "default":
            self._warnings.append(
                f"Using the default category review threshold ({DEFAULT_REVIEW_THRESHOLD}). Run "
                f"`python -m s3t calibrate` to choose one from cross-validation.")

    # ------------------------------------------------------------------ info
    def info(self) -> Dict:
        return {
            "asset_version": __version__, "model": self.model_name,
            "encoder": self._bundle.encoder,
            "categories": self._bundle.models["category"].classes_.tolist(),
            "urgency_levels": self._bundle.models["urgency"].classes_.tolist(),
            "review_thresholds": {"category": self.cat_threshold, "urgency": self.urg_threshold},
            "thresholds_source": self.thresholds_source,
            "extended_crisis_lexicon": self.extended_crisis,
            "warnings": list(self._warnings),
        }

    # ------------------------------------------------------------------ predict
    def predict(self, text: TextOrRequest, id: Optional[str] = None) -> TriageResult:
        req = text if isinstance(text, TriageRequest) else TriageRequest(text=text, id=id)
        return self._run([req])[0]

    def predict_batch(self, texts: Iterable[TextOrRequest],
                      ids: Optional[Sequence[Optional[str]]] = None) -> List[TriageResult]:
        items = list(texts)
        if not items:
            return []
        if len(items) > MAX_BATCH:
            raise ValueError(f"batch of {len(items)} exceeds MAX_BATCH={MAX_BATCH}; "
                             f"split it into chunks")
        if ids is not None and len(ids) != len(items):
            raise ValueError("ids must have the same length as texts")
        reqs = [t if isinstance(t, TriageRequest)
                else TriageRequest(text=t, id=(ids[i] if ids is not None else None))
                for i, t in enumerate(items)]
        return self._run(reqs)

    # ------------------------------------------------------------------ internals
    def _run(self, reqs: List[TriageRequest]) -> List[TriageResult]:
        preds: Predictions = self._bundle.predict([r.text for r in reqs])
        meta = Meta(asset_version=__version__, model=self.model_name,
                    encoder=self._bundle.encoder,
                    review_thresholds={"category": self.cat_threshold,
                                       "urgency": self.urg_threshold},
                    thresholds_source=self.thresholds_source,
                    extended_crisis_lexicon=self.extended_crisis,
                    warnings=list(self._warnings))
        out = []
        for i, req in enumerate(reqs):
            cp, up = preds.cat_p[i], preds.urg_p[i]
            cat_label = preds.cat_labels[int(cp.argmax())]
            urg_label = preds.urg_labels[int(up.argmax())]
            info = extract(req.text, self.extended_crisis)
            r = apply_rules(cat_label, urg_label, float(cp.max()), float(up.max()), info,
                            self.cat_threshold, self.urg_threshold)
            cat_conf, urg_conf = float(cp.max()), float(up.max())
            if (cat_conf < self.cat_threshold or urg_conf < self.urg_threshold):
                band = "low"
            elif cat_conf >= HIGH_CONFIDENCE:
                band = "high"
            else:
                band = "medium"
            out.append(TriageResult(
                id=req.id,
                category=_scored(preds.cat_labels, cp, cat_label),
                urgency=_scored(preds.urg_labels, up, r["urgency"]),
                confidence_band=band,
                recommended_action=r["action"],
                entities=Entities(courses=info["courses"], deadlines=info["deadlines"],
                                  blockers=info["blockers"]),
                emotions=info["emotions"],
                crisis_detected=info["crisis_detected"],
                crisis_matches=info["crisis_matches"],
                human_review=Review(required=r["review_required"], reasons=r["review_reasons"]),
                rules_applied=r["rules_applied"],
                disclaimer=DISCLAIMER, meta=meta))
        return out