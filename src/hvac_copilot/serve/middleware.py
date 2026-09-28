"""Cross-cutting HTTP middleware (pure ASGI, no BaseHTTPMiddleware).

- CorrelationIdMiddleware : inbound ``X-Correlation-ID`` or generated uuid4,
  echoed on every response; handlers read it from ``scope["correlation_id"]``.
- BodySizeLimitMiddleware : rejects request bodies above ``max_bytes`` (413)
  on the configured paths; the buffered body is re-injected downstream.
- DeprecatedPathMiddleware: stamps legacy (pre-/v1) paths with
  ``Deprecation`` / ``Sunset`` headers for one release.

Pure-ASGI wrappers are used deliberately: they never buffer or transform
streaming responses (SSE) and each one is a few lines a reviewer can audit.
"""

from __future__ import annotations

import uuid

CORRELATION_HEADER = "X-Correlation-ID"
DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
# One release of grace for legacy paths before removal (RFC 8594 HTTP-date).
SUNSET_DATE = "Wed, 30 Sep 2026 00:00:00 GMT"

# Legacy (unversioned) equivalents of the /v1 routes.
LEGACY_PATHS = {"/query", "/query/stream", "/ingest", "/health", "/metrics"}


class CorrelationIdMiddleware:
    """Attach a correlation id to every request/response pair."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        correlation_id = headers.get("x-correlation-id") or uuid.uuid4().hex
        # Bound hostile/inordinately long client ids.
        correlation_id = correlation_id[:128]
        scope["correlation_id"] = correlation_id
        await self.app(scope, receive, _header_injecting_send(send, CORRELATION_HEADER, correlation_id))


class BodySizeLimitMiddleware:
    """Reject bodies larger than ``max_bytes`` on protected paths with 413.

    The body is drained (bounded by the limit + one drain pass) and handed
    to the inner app through a replayable ``receive`` so exactly-one-consumer
    ASGI semantics are preserved for downstream middleware.
    """

    def __init__(self, app, max_bytes: int, protected_paths: set[str]) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.protected_paths = protected_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "") not in self.protected_paths:
            return await self.app(scope, receive, send)
        if scope.get("method", "").upper() not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)

        body = bytearray()
        too_large = False
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if len(body) > self.max_bytes:
                    too_large = True
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return

        if too_large:
            response = _json_response(
                {"detail": f"Request body exceeds {self.max_bytes} bytes."}, 413
            )
            await response(scope, receive, send)
            return

        replayed = {"done": False}

        async def replay_receive():
            if not replayed["done"]:
                replayed["done"] = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


class DeprecatedPathMiddleware:
    """Stamp ``Deprecation``/``Sunset`` headers on legacy (pre-versioned) paths."""

    def __init__(self, app, legacy_paths: set[str] = LEGACY_PATHS) -> None:
        self.app = app
        self.legacy_paths = legacy_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "") not in self.legacy_paths:
            return await self.app(scope, receive, send)
        headers = [(DEPRECATION_HEADER.lower(), b"true"), (SUNSET_HEADER.lower(), SUNSET_DATE.encode())]
        await self.app(scope, receive, _header_appending_send(send, headers))


def _header_injecting_send(send, name: str, value: str):
    target = name.lower().encode("latin-1")

    async def wrapped(message) -> None:
        if message["type"] == "http.response.start":
            raw_headers = [(k, v) for k, v in message.get("headers", []) if k != target]
            raw_headers.append((target, value.encode("latin-1")))
            message = {**message, "headers": raw_headers}
        await send(message)

    return wrapped


def _header_appending_send(send, extra: list[tuple[str, bytes]]):
    encoded = [(k.encode("latin-1"), v) for k, v in extra]

    async def wrapped(message) -> None:
        if message["type"] == "http.response.start":
            message = {**message, "headers": [*message.get("headers", []), *encoded]}
        await send(message)

    return wrapped


def _json_response(payload: dict, status_code: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code)


__all__ = [
    "CORRELATION_HEADER",
    "DEPRECATION_HEADER",
    "LEGACY_PATHS",
    "BodySizeLimitMiddleware",
    "CorrelationIdMiddleware",
    "DeprecatedPathMiddleware",
    "SUNSET_DATE",
    "SUNSET_HEADER",
]
