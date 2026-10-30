# S3T asset - interface reference (schema version 1.0)

The same objects are used by the Python module, the CLI (`--file` output is one JSON per line) and
the HTTP API. `python -m s3t schema` prints the exact JSON Schema; `/docs` on a running service shows
it interactively.

## Python

| Call | Returns | Notes |
|---|---|---|
| `Triage(model="auto", models_dir=None, thresholds=None, extended_crisis=True)` | `Triage` | Loads models once. `thresholds=(category, urgency)` overrides. |
| `.predict(text_or_request, id=None)` | `TriageResult` | `ValueError` (pydantic `ValidationError`) for empty / blank / non-string / over 2000 characters. |
| `.predict_batch(texts, ids=None)` | `list[TriageResult]` | 1-100 items per call; `[]` for empty input; one encoder pass for the batch. |
| `.info()` | `dict` | model, encoder, labels, thresholds and their source, warnings. |

Safe to share one `Triage` object between threads.

## HTTP

| Method and path | Body | Response | Errors |
|---|---|---|---|
| `GET /health` | - | `{status, model, asset_version, schema_version}` | - |
| `GET /v1/info` | - | same as `Triage.info()` | 401 |
| `POST /v1/triage` | `{"text": str, "id": str?}` | `TriageResult` | 401, 422 |
| `POST /v1/triage/batch` | `{"items": [{"text", "id"?}, ...]}` (1-100) | `{"count": n, "results": [TriageResult]}` | 401, 422 |

401 only when `S3T_API_KEY` is set. 422 = invalid input (empty text, text over 2000 characters, empty or
oversized batch). Message text is never logged or echoed; send your own `id` to match results to inputs.

## Input: `TriageRequest`

| Field | Type | Rules |
|---|---|---|
| `text` | string | required, trimmed, 1-2000 characters |
| `id` | string or null | optional, max 100 characters, returned unchanged |

## Output: `TriageResult`

| Field | Type | Meaning |
|---|---|---|
| `id` | string or null | your reference |
| `category` | ScoredLabel | one of Academic Difficulty, Mental Health & Wellbeing, Financial Aid, Administrative, Technical Support |
| `urgency` | ScoredLabel | Low, Medium, High (final, after rules) |
| `confidence_band` | high / medium / low | rough guide, see below |
| `recommended_action` | string | which team; prefixed `PRIORITY:` for High; `IMMEDIATE:` for crisis language |
| `entities` | `{courses[], deadlines[], blockers[]}` | rule-based extraction |
| `emotions` | string[] | anxiety, stress, sadness, hopelessness, isolation, desperation |
| `crisis_detected`, `crisis_matches` | bool, string[] | crisis lexicon hit and the matched phrases |
| `human_review` | `{required: bool, reasons: [...]}` | reasons: `crisis_language`, `high_urgency`, `low_category_confidence`, `low_urgency_confidence` |
| `rules_applied` | string[] | human-readable log of rules R1-R3 that fired |
| `advisory_only`, `disclaimer` | true, string | always present |
| `meta` | Meta | `schema_version`, `asset_version`, `model`, `encoder`, `review_thresholds`, `thresholds_source` (`calibrated`/`default`/`user`), `extended_crisis_lexicon`, `warnings[]` |

### `ScoredLabel`

| Field | Meaning |
|---|---|
| `label` | final label (urgency: after rules R1/R2) |
| `model_label` | the classifier's own top choice |
| `adjusted_by_rules` | `label != model_label` |
| `confidence` | probability of `model_label`, 0-1 |
| `margin` | top probability minus second-best |
| `probabilities` | every label's probability (sums to 1, rounded to 4 decimals) |

### Rules
- **R1** crisis language: urgency becomes High, action becomes the crisis action, review required.
- **R2** deadline today / tonight / tomorrow / in an hour: urgency up one level (not when already High or crisis).
- **R3** category or urgency confidence below its threshold: review required. The default urgency threshold is `0.0`, so by default only category confidence triggers R3 (the urgency score is not informative; see README section 4).
- **R4** final urgency High: review required.

### Confidence band
`low`: category confidence below the category threshold or urgency confidence below the urgency threshold.
`high`: not low, and category confidence >= 0.90 (urgency confidence is not required to reach 0.90: in the Week 6 calibration 99% of training messages had urgency confidence below 0.70). `medium`: everything else. It is a triage convenience, not a probability.

## Versioning
`meta.schema_version` changes when a field is added, removed or changes meaning (currently `1.0`).
`meta.asset_version` is the package version (currently `1.0.0`). Models are replaced by dropping new
`<name>_category.joblib` / `<name>_urgency.joblib` files into the models folder and re-running
`python -m s3t verify` and `python -m s3t calibrate`.