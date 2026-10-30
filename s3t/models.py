"""
models.py - the Week 4 Sentence-Transformer classifier, inference side only.

    raw text -> sentence embedding (384 numbers) [+ TF-IDF features if hybrid]
             -> Logistic Regression -> class probabilities

Training code stays in the Week 4 / Week 5 folders. This file only has to be able to
LOAD the saved `*.joblib` files, which were pickled with the class living in a module
called `sbert_model`. We register this module under that name (see the bottom) so
the old pickles load without being re-trained or edited.
"""
import hashlib
import os
import sys
import threading
import types

import numpy as np
from scipy.sparse import csr_matrix, hstack

from .config import SBERT_NAME
from .preprocess import stem_text

DEBUG_ENCODER = "debug-hash"      # offline stand-in used only by code smoke tests
_ENCODERS = {}
_LOCK = threading.Lock()


def resolve_encoder(name: str) -> str:
    """S3T_ENCODER (name or local folder) overrides the name stored in the pickle."""
    return name if name == DEBUG_ENCODER else os.environ.get("S3T_ENCODER", name)


def load_encoder(name: str):
    """Load (once) and return the SentenceTransformer. Raises a clear error if the
    package or the model files are missing."""
    name = resolve_encoder(name)
    with _LOCK:
        if name not in _ENCODERS:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers is not installed. Run: pip install "
                    "'s3t[sbert]'  (or use model='baseline')") from e
            try:
                _ENCODERS[name] = SentenceTransformer(name)
            except Exception as e:      # network / path problems
                raise RuntimeError(
                    f"Could not load the sentence encoder '{name}'. On the first run it is "
                    f"downloaded (~90 MB), so internet is needed once. For an offline machine, "
                    f"download it elsewhere and set S3T_ENCODER to the local folder.") from e
    return _ENCODERS[name]


def embed(texts, encoder_name: str, cache_dir=None) -> np.ndarray:
    """Texts -> (n, dim) L2-normalised embeddings. `cache_dir` (optional) stores results
    on disk; it is only used by the calibration tool, never by normal inference."""
    texts = list(texts)
    name = resolve_encoder(encoder_name)
    cache_file = None
    if cache_dir is not None:
        key = hashlib.sha1((name + "\n" + "\n".join(texts)).encode()).hexdigest()[:16]
        cache_file = os.path.join(str(cache_dir), f"{key}.npy")
        if os.path.exists(cache_file):
            return np.load(cache_file)

    if name == DEBUG_ENCODER:
        from sklearn.feature_extraction.text import HashingVectorizer
        X = HashingVectorizer(n_features=384, norm="l2", alternate_sign=False) \
            .transform(texts).toarray()
    else:
        enc = load_encoder(name)
        with _LOCK:    # one encode at a time: keeps the API safe under threads
            X = enc.encode(texts, batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False)
    if cache_file:
        os.makedirs(str(cache_dir), exist_ok=True)
        np.save(cache_file, X)
    return X


class SbertClassifier:
    """Embeddings (optionally + TF-IDF) -> Logistic Regression.

    Attribute names (encoder_name, hybrid, tfidf, clf, best_C, cv_macro_f1) must match
    the pickled objects. Do not rename them.
    """

    def __init__(self, encoder_name: str = SBERT_NAME, hybrid: bool = False):
        self.encoder_name = encoder_name
        self.hybrid = hybrid
        self.tfidf = None
        self.clf = None
        self.best_C = None
        self.cv_macro_f1 = None

    @property
    def classes_(self):
        return self.clf.classes_

    def _features(self, texts):
        emb = embed(texts, self.encoder_name)
        if not self.hybrid:
            return emb
        tf = self.tfidf.transform([stem_text(t) for t in texts])
        return hstack([csr_matrix(emb), tf]).tocsr()

    def predict_proba(self, texts) -> np.ndarray:
        return self.clf.predict_proba(self._features(list(texts)))


def proba_from_embeddings(model, emb: np.ndarray, texts) -> np.ndarray:
    """Probabilities for already-computed embeddings (lets one encode serve both the
    category and the urgency model). Works on any object with the SbertClassifier fields."""
    if not model.hybrid:
        return model.clf.predict_proba(emb)
    tf = model.tfidf.transform([stem_text(t) for t in texts])
    return model.clf.predict_proba(hstack([csr_matrix(emb), tf]).tocsr())


# Old pickles say "sbert_model.SbertClassifier". Provide that name (unless the Week 4
# module is already imported, in which case Python simply uses that one).
_legacy = types.ModuleType("sbert_model")
_legacy.SbertClassifier = SbertClassifier
_legacy.embed = embed
sys.modules.setdefault("sbert_model", _legacy)
