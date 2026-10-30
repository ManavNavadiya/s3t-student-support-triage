"""
api.py - HTTP service (FastAPI) around the Triage class.

    uvicorn s3t.api:app --port 8000          # or:  python -m s3t serve
    open http://localhost:8000/docs          # interactive documentation

Endpoints
    GET  /health            liveness + which model is loaded
    GET  /v1/info           model, labels, thresholds, warnings
    POST /v1/triage         {"text": "...", "id": "optional"}      -> TriageResult
    POST /v1/triage/batch   {"items": [{"text": "..."}, ...]}      -> BatchResponse

Privacy: message text is never logged or echoed back (only your optional `id`).
Optional protection: set S3T_API_KEY and send it as the X-API-Key header.
"""
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from .config import SCHEMA_VERSION, __version__
from .schemas import (BatchRequest, BatchResponse, HealthResponse, TriageRequest,
                      TriageResult)
from .triage import Triage


def create_app(model: str = None) -> FastAPI:
    model = model or os.environ.get("S3T_MODEL", "auto")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.triage = Triage(model=model)       # loaded once at start-up
        yield

    app = FastAPI(title="S3T Student Support Triage", version=__version__,
                  description="Advisory triage of student messages: category, urgency, "
                              "confidence, extracted details and a human-review flag. "
                              "A staff member always makes the final decision.",
                  lifespan=lifespan)

    def check_key(x_api_key: str = Header(default=None)):
        key = os.environ.get("S3T_API_KEY")
        if key and not (x_api_key and secrets.compare_digest(x_api_key, key)):
            raise HTTPException(status_code=401, detail="Missing or wrong X-API-Key")

    @app.get("/health", response_model=HealthResponse)
    def health():
        t = app.state.triage
        return HealthResponse(status="ok", model=t.model_name, asset_version=__version__,
                              schema_version=SCHEMA_VERSION)

    @app.get("/v1/info", dependencies=[Depends(check_key)])
    def info():
        return app.state.triage.info()

    @app.post("/v1/triage", response_model=TriageResult, dependencies=[Depends(check_key)])
    def triage_one(req: TriageRequest):
        return app.state.triage.predict(req)

    @app.post("/v1/triage/batch", response_model=BatchResponse,
              dependencies=[Depends(check_key)])
    def triage_batch(req: BatchRequest):
        results = app.state.triage.predict_batch(req.items)
        return BatchResponse(count=len(results), results=results)

    return app


app = create_app()
