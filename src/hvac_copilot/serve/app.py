"""FastAPI surface (v1 + legacy aliases).

- POST /v1/query          : grounded answer JSON (citations, trace, timings)
- GET  /v1/query/stream   : SSE stream (meta -> token* -> done)
- POST /v1/ingest         : (re)ingest the corpus, reports incremental stats
- GET  /v1/health         : liveness + index summary
- GET  /v1/metrics        : Prometheus text format

The unversioned legacy paths (``/query``, ``/ingest``, ...) keep working for
one release and are stamped with ``Deprecation: true`` / ``Sunset`` headers
on every response (see serve.middleware.DeprecatedPathMiddleware).

Cross-cutting behavior (outermost first on the request path):

- correlation id   : inbound ``X-Correlation-ID`` or generated uuid4, echoed
  on every response and attached to ``answer.trace["correlation_id"]``.
- API-key auth     : ``X-API-Key`` required on /query* and /ingest when
  ``HVAC_API_KEYS`` is set (disabled with a warning otherwise).
- request limits   : question bodies > 8 KiB rejected with 413; ``top_k`` > 50
  rejected with 422.
- idempotency      : ``Idempotency-Key`` on POST /query replays the stored
  response with ``X-Idempotent-Replay: true`` (LRU 512, TTL 1h).

The app is ASGI-tested: tests drive it through httpx's ASGITransport, so the
suite never opens a socket.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from hvac_copilot.config import Settings
from hvac_copilot.serve.auth import APIKeyAuth, APIKeyMiddleware
from hvac_copilot.serve.idempotency import IdempotencyMiddleware, IdempotencyStore
from hvac_copilot.serve.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    DeprecatedPathMiddleware,
)
from hvac_copilot.service import HVACCopilot

MAX_QUESTION_BYTES = 8 * 1024  # 8 KiB question-body cap -> 413
MAX_TOP_K = 50  # top_k above this -> 422
# Body reads happen on POST /query (idempotency hash + size limit).
SIZE_LIMITED_PATHS = {"/query", "/v1/query"}


class QueryRequest(BaseModel):
    # Byte-level cap (>8 KiB) is enforced by BodySizeLimitMiddleware with 413;
    # the char cap here is the defensive backstop for non-413 paths.
    question: str = Field(min_length=1, max_length=2000)
    unit_model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=MAX_TOP_K)
    safety: bool | None = None  # metadata filter override (None = no filter)
    mode: str = "hybrid"


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(service: HVACCopilot | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    copilot = service or HVACCopilot(settings)
    auth = APIKeyAuth(settings.api_keys)
    idempotency = IdempotencyStore()

    app = FastAPI(
        title="HVAC-Copilot",
        description="Grounded RAG assistant for HVAC field technicians",
        version="0.1.0",
    )

    # Request path order = reverse of registration below:
    # correlation -> deprecation stamp -> auth -> body limit -> idempotency -> routes.
    app.add_middleware(IdempotencyMiddleware, store=idempotency)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_QUESTION_BYTES, protected_paths=SIZE_LIMITED_PATHS)
    app.add_middleware(APIKeyMiddleware, auth=auth)
    app.add_middleware(DeprecatedPathMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    async def query(request: Request, body: QueryRequest) -> JSONResponse:
        answer = await copilot.ask(
            body.question,
            unit_model=body.unit_model,
            top_k=body.top_k,
            safety=body.safety,
            mode=body.mode,
        )
        payload = answer.model_dump()
        payload.setdefault("trace", {})["correlation_id"] = request.scope["correlation_id"]
        return JSONResponse(payload)

    async def query_stream(question: str, unit_model: str | None = None, top_k: int | None = None):
        async def event_source():
            try:
                async for event in copilot.ask_stream(question, unit_model=unit_model, top_k=top_k):
                    yield _sse(event["event"], event["data"])
            except Exception as exc:  # defensive: stream must end with an error event
                yield _sse("error", {"message": str(exc)})

        return StreamingResponse(event_source(), media_type="text/event-stream")

    async def ingest() -> JSONResponse:
        stats = copilot.ingest()
        return JSONResponse(stats.__dict__)

    async def health() -> JSONResponse:
        return JSONResponse(copilot.health())

    async def metrics() -> StreamingResponse:
        return StreamingResponse(iter([copilot.metrics.render()]), media_type="text/plain; version=0.0.4")

    # v1 is canonical; legacy root paths are registered on the same handlers
    # and deprecation-stamped by DeprecatedPathMiddleware for one release.
    app.post("/v1/query")(query)
    app.post("/query")(query)
    app.get("/v1/query/stream")(query_stream)
    app.get("/query/stream")(query_stream)
    app.post("/v1/ingest")(ingest)
    app.post("/ingest")(ingest)
    app.get("/v1/health")(health)
    app.get("/health")(health)
    app.get("/v1/metrics")(metrics)
    app.get("/metrics")(metrics)

    return app


def main() -> None:  # pragma: no cover - manual run helper
    import uvicorn

    uvicorn.run("hvac_copilot.serve.app:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["MAX_QUESTION_BYTES", "MAX_TOP_K", "QueryRequest", "create_app"]
