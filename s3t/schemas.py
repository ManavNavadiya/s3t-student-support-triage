"""
schemas.py - the structured input and output of the asset (pydantic models).

These classes ARE the contract: the Python API, the CLI's JSON and the HTTP API all use
them, and `python -m s3t schema` prints them as JSON Schema.
Change a field => bump SCHEMA_VERSION in config.py.
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import MAX_BATCH, MAX_TEXT_CHARS, SCHEMA_VERSION


# ---------------- input ----------------
class TriageRequest(BaseModel):
    text: str = Field(..., description="The student's message.", max_length=MAX_TEXT_CHARS)
    id: Optional[str] = Field(None, description="Your own reference; echoed back unchanged. "
                              "Use this instead of sending names or student numbers.",
                              max_length=100)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty or whitespace")
        return v


class BatchRequest(BaseModel):
    items: List[TriageRequest] = Field(..., min_length=1, max_length=MAX_BATCH)


# ---------------- output ----------------
class ScoredLabel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())   # allow the field name `model_label`

    label: str = Field(..., description="Final label (for urgency: after rules R1/R2).")
    model_label: str = Field(..., description="What the classifier itself predicted.")
    adjusted_by_rules: bool = Field(..., description="True if label != model_label.")
    confidence: float = Field(..., ge=0, le=1, description="Model probability of model_label.")
    margin: float = Field(..., ge=0, le=1, description="Top probability minus second-best. "
                          "Small = the model was torn between two labels.")
    probabilities: Dict[str, float] = Field(..., description="Probability of every label (sums to 1).")


class Entities(BaseModel):
    courses: List[str]
    deadlines: List[str]
    blockers: List[str]


class Review(BaseModel):
    required: bool = Field(..., description="True = a human must look at this before any action.")
    reasons: List[Literal["crisis_language", "high_urgency",
                          "low_category_confidence", "low_urgency_confidence"]]


class Meta(BaseModel):
    schema_version: str = SCHEMA_VERSION
    asset_version: str
    model: str
    encoder: Optional[str]
    review_thresholds: Dict[str, float]
    thresholds_source: Literal["calibrated", "default", "user"]
    extended_crisis_lexicon: bool
    warnings: List[str]


class TriageResult(BaseModel):
    id: Optional[str]
    category: ScoredLabel
    urgency: ScoredLabel
    confidence_band: Literal["high", "medium", "low"] = Field(
        ..., description="low: either confidence is below its review threshold; high: not low "
                         "and category confidence >= 0.90; medium: otherwise. A rough guide, "
                         "not a probability.")
    recommended_action: str
    entities: Entities
    emotions: List[str]
    crisis_detected: bool
    crisis_matches: List[str]
    human_review: Review
    rules_applied: List[str]
    advisory_only: bool = True
    disclaimer: str
    meta: Meta


class BatchResponse(BaseModel):
    count: int
    results: List[TriageResult]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model: str
    asset_version: str
    schema_version: str
