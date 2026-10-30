"""
classifier.py - loads a model (baseline / sbert / sbert+tfidf) and returns probabilities.

    bundle = load_bundle("sbert+tfidf")
    preds  = bundle.predict(["I can't log in to Canvas"])
    preds.cat_p      # (n, 5) probabilities, columns ordered as preds.cat_labels
"""
import importlib.util
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import joblib
import numpy as np

from .config import MODELS_DIR, MODEL_NAMES, DEFAULT_MODEL, FALLBACK_MODEL
from .models import embed, load_encoder, proba_from_embeddings
from .preprocess import stem_text

TASKS = ("category", "urgency")


@dataclass
class Predictions:
    cat_labels: List[str]
    cat_p: np.ndarray
    urg_labels: List[str]
    urg_p: np.ndarray


def files_present(name: str, models_dir: Path) -> bool:
    return all((Path(models_dir) / f"{name}_{t}.joblib").exists() for t in TASKS)


def deps_present(name: str) -> bool:
    if name == "baseline":
        return True
    return importlib.util.find_spec("sentence_transformers") is not None


def available_models(models_dir: Optional[Path] = None) -> List[str]:
    """Models whose files exist AND whose dependencies are installed."""
    d = Path(models_dir or MODELS_DIR)
    return [n for n in MODEL_NAMES if files_present(n, d) and deps_present(n)]


class Bundle:
    def __init__(self, name: str, models_dir: Path):
        if name not in MODEL_NAMES:
            raise ValueError(f"Unknown model '{name}'. Choose from {MODEL_NAMES}.")
        if not files_present(name, models_dir):
            raise FileNotFoundError(f"Model files '{name}_category.joblib' / "
                                    f"'{name}_urgency.joblib' not found in {models_dir}")
        if not deps_present(name):
            raise RuntimeError(f"Model '{name}' needs sentence-transformers: "
                               f"pip install 's3t[sbert]'")
        self.name = name
        self.warnings: List[str] = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.models = {t: joblib.load(Path(models_dir) / f"{name}_{t}.joblib") for t in TASKS}
        for w in caught:    # e.g. scikit-learn version differs from the one used for training
            if "version" in str(w.message).lower():
                self.warnings.append(str(w.message).splitlines()[0][:200])
        self.encoder = (None if name == "baseline"
                        else self.models["category"].encoder_name)

    def warmup(self):
        """Load the encoder now (so a missing download fails at start-up, not on request 1)."""
        if self.encoder:
            load_encoder(self.encoder)

    def predict(self, texts) -> Predictions:
        texts = list(texts)
        cat, urg = self.models["category"], self.models["urgency"]
        if self.name == "baseline":
            stemmed = [stem_text(t) for t in texts]
            cat_p, urg_p = cat.predict_proba(stemmed), urg.predict_proba(stemmed)
        else:
            emb = embed(texts, self.encoder)      # one encode serves both tasks
            cat_p = proba_from_embeddings(cat, emb, texts)
            urg_p = proba_from_embeddings(urg, emb, texts)
        return Predictions(list(map(str, cat.classes_)), cat_p,
                           list(map(str, urg.classes_)), urg_p)


def load_bundle(name: str = "auto", models_dir: Optional[Path] = None):
    """Returns (bundle, warnings). `auto` = hybrid if usable, else baseline (with a warning);
    an explicit name never falls back silently."""
    d = Path(models_dir or MODELS_DIR)
    if name != "auto":
        b = Bundle(name, d)
        b.warmup()
        return b, list(b.warnings)

    problems = []
    if not files_present(DEFAULT_MODEL, d):
        problems.append(f"{DEFAULT_MODEL} model files not found")
    elif not deps_present(DEFAULT_MODEL):
        problems.append("sentence-transformers not installed")
    else:
        try:
            b = Bundle(DEFAULT_MODEL, d)
            b.warmup()
            return b, list(b.warnings)
        except Exception as e:     # e.g. no internet for the one-off encoder download
            problems.append(f"{DEFAULT_MODEL} could not be loaded: {e}")
    b = Bundle(FALLBACK_MODEL, d)
    msg = (f"WARNING: fell back to the TF-IDF '{FALLBACK_MODEL}' model ({'; '.join(problems)}). "
           f"It is clearly weaker on category (Week 5: macro-F1 0.588 vs 0.859).")
    return b, [msg] + list(b.warnings)
