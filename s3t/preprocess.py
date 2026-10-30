"""
preprocess.py - text cleaning used by the TF-IDF part of the models (from Week 2).

Must stay identical to the training-time version, otherwise the saved TF-IDF
vocabularies no longer match. Do not "improve" it without retraining.
"""
import re
from nltk.stem import PorterStemmer

_stemmer = PorterStemmer()


def clean_text(text: str) -> str:
    """Lowercase, keep letters/numbers only, squash extra spaces."""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stem_text(text: str) -> str:
    """Clean + Porter-stem every word (e.g. 'struggling' -> 'struggl')."""
    return " ".join(_stemmer.stem(w) for w in clean_text(text).split())
