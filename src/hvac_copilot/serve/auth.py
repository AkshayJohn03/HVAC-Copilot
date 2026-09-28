"""API-key authentication for the serving surface.

Keys are supplied via the ``HVAC_API_KEYS`` environment variable as a
comma-separated list of RAW keys. Only SHA-256 hashes are ever stored or
compared (hash-at-ingest); raw keys are never logged and never echoed back.
The class exists separately from the middleware so the hashing/comparison
policy is unit-testable without an ASGI stack.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re

logger = logging.getLogger("hvac_copilot.serve.auth")

# Routes that require an API key (legacy and /v1 forms); health/metrics exempt.
PROTECTED_PATH = re.compile(r"^/(?:v1/)?(?:query|ingest)(?:/stream)?$")
GENERIC_401 = {"detail": "Unauthorized: missing or invalid API key."}


def hash_key(raw: str) -> str:
    """SHA-256 of one raw key, hex-encoded. The only form kept at rest."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class APIKeyAuth:
    """Hold-at-rest key hashes; verify presented keys in constant time.

    ``raw_keys`` comes from ``HVAC_API_KEYS`` (comma-separated raw keys).
    When unset/empty the authenticator is DISABLED (open service) and a
    startup warning is emitted — the pre-auth behavior stays backward
    compatible. When set, every protected route requires ``X-API-Key``.
    """

    def __init__(self, raw_keys: str | None) -> None:
        self.enabled = bool(raw_keys and raw_keys.strip())
        if not self.enabled:
            self._hashes: frozenset[str] = frozenset()
            logger.warning(
                "HVAC_API_KEYS is not set — API-key auth is DISABLED. "
                "Set it (comma-separated keys) before exposing the service."
            )
            return
        keys = [k.strip() for k in raw_keys.split(",")]
        self._hashes = frozenset(hash_key(k) for k in keys if k)
        logger.warning(
            "API-key auth ENABLED with %d key(s); only SHA-256 hashes are stored.", len(self._hashes)
        )

    def verify(self, presented: str | None) -> bool:
        """True iff the presented key matches one enrolled key (constant-time)."""
        if presented is None or not self.enabled:
            return not self.enabled
        return any(hmac.compare_digest(hash_key(presented), h) for h in self._hashes)


class APIKeyMiddleware:
    """Pure-ASGI middleware enforcing ``X-API-Key`` on protected routes.

    Mounted so it runs before idempotency: unauthorized requests are
    rejected with a generic 401 and never reach (or get cached by) the
    application.
    """

    def __init__(self, app, auth: APIKeyAuth) -> None:
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.auth.enabled:
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not PROTECTED_PATH.match(path):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if not self.auth.verify(headers.get("x-api-key")):
            response = _json_response(GENERIC_401, 401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _json_response(payload: dict, status_code: int):
    # Local import avoids a module-level Starlette dependency in tests of the
    # pure policy class; the middleware is always used inside a FastAPI app.
    from fastapi.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code)


__all__ = ["APIKeyAuth", "APIKeyMiddleware", "GENERIC_401", "hash_key"]
