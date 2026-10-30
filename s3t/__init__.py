"""S3T - Student Support Triage: a reusable NLP asset.

    from s3t import Triage
    result = Triage().predict("I can't log in to Canvas and my quiz is due today")
"""
from .config import __version__, SCHEMA_VERSION
from .schemas import TriageRequest, TriageResult, BatchRequest, BatchResponse
from .triage import Triage

__all__ = ["Triage", "TriageRequest", "TriageResult", "BatchRequest", "BatchResponse",
           "__version__", "SCHEMA_VERSION"]
