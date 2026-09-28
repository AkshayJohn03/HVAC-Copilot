"""FastAPI surface.

- POST /query         : grounded answer JSON (citations, trace, timings)
- GET  /query/stream  : SSE stream (meta -> token* -> done)
- POST /ingest        : (re)ingest the corpus, reports incremental stats
- GET  /health        : liveness + index summary
- GET  /metrics       : Prometheus text format

The app is ASGI-tested: tests drive it through httpx's ASGITransport, so the
suite never opens a socket.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from hvac_copilot.config import Settings
from hvac_copilot.service import HVACCopilot


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    unit_model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    safety: bool | None = None  # metadata filter override (None = no filter)
    mode: str = "hybrid"


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(service: HVACCopilot | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    copilot = service or HVACCopilot(settings)

    app = FastAPI(
        title="HVAC-Copilot",
        description="Grounded RAG assistant for HVAC field technicians",
        version="0.1.0",
    )

    @app.post("/query")
    async def query(request: QueryRequest) -> JSONResponse:
        answer = await copilot.ask(
            request.question,
            unit_model=request.unit_model,
            top_k=request.top_k,
            safety=request.safety,
            mode=request.mode,
        )
        return JSONResponse(answer.model_dump())

    @app.get("/query/stream")
    async def query_stream(question: str, unit_model: str | None = None, top_k: int | None = None):
        async def event_source():
            try:
                async for event in copilot.ask_stream(question, unit_model=unit_model, top_k=top_k):
                    yield _sse(event["event"], event["data"])
            except Exception as exc:  # defensive: stream must end with an error event
                yield _sse("error", {"message": str(exc)})

        return StreamingResponse(event_source(), media_type="text/event-stream")

    @app.post("/ingest")
    async def ingest() -> JSONResponse:
        stats = copilot.ingest()
        return JSONResponse(stats.__dict__)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(copilot.health())

    @app.get("/metrics")
    async def metrics() -> StreamingResponse:
        return StreamingResponse(iter([copilot.metrics.render()]), media_type="text/plain; version=0.0.4")

    return app


def main() -> None:  # pragma: no cover - manual run helper
    import uvicorn

    uvicorn.run("hvac_copilot.serve.app:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["QueryRequest", "create_app"]
