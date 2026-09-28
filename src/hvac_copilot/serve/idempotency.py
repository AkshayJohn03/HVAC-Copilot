"""Idempotent POST /query via the ``Idempotency-Key`` header.

Store: ``sha256(key + request body)`` -> cached JSON response, LRU-bounded
(512 entries) with a 1h TTL. Concurrent duplicates of the same key+body are
serialized behind a per-digest ``asyncio.Lock``: the second caller waits,
re-checks the store, and receives the stored response flagged with
``X-Idempotent-Replay: true`` instead of re-executing the pipeline.

Requests WITHOUT the header bypass the store entirely (keyed idempotency:
the client opts in per logical operation).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict

MAX_ENTRIES = 512
TTL_SECONDS = 3600.0
REPLAY_HEADER = "X-Idempotent-Replay"

# Only POST /query participates (legacy and /v1 forms).
IDEMPOTENT_PATHS = {"/query", "/v1/query"}


class IdempotencyStore:
    """LRU + TTL cache of completed responses, keyed by request digest."""

    def __init__(self, max_entries: int = MAX_ENTRIES, ttl_seconds: float = TTL_SECONDS) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, int, bytes, list[tuple[str, str]]]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def digest(idempotency_key: str, body: bytes) -> str:
        """Stable digest of (key, body); raw key/body never stored or logged."""
        h = hashlib.sha256()
        h.update(idempotency_key.encode("utf-8"))
        h.update(b"\x00")
        h.update(body)
        return h.hexdigest()

    def lock_for(self, digest: str) -> asyncio.Lock:
        """One lock per digest so concurrent duplicates serialize."""
        lock = self._locks.get(digest)
        if lock is None:
            lock = self._locks[digest] = asyncio.Lock()
        return lock

    def get(self, digest: str) -> tuple[int, bytes, list[tuple[str, str]]] | None:
        entry = self._entries.get(digest)
        if entry is None:
            return None
        stored_at, status, body, headers = entry
        if time.monotonic() - stored_at >= self._ttl:
            del self._entries[digest]
            return None
        self._entries.move_to_end(digest)
        return status, body, headers

    def put(self, digest: str, status: int, body: bytes, headers: list[tuple[str, str]]) -> None:
        self._entries[digest] = (time.monotonic(), status, body, headers)
        self._entries.move_to_end(digest)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


class IdempotencyMiddleware:
    """Pure-ASGI middleware: replays stored responses for duplicate idempotent calls.

    Mounted inside auth and inside the body-size limiter (which provides a
    replayable ``receive``), so the request body is read once here and
    re-injected for the application.
    """

    def __init__(self, app, store: IdempotencyStore) -> None:
        self.app = app
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method", "").upper() != "POST":
            return await self.app(scope, receive, send)
        if scope.get("path", "") not in IDEMPOTENT_PATHS:
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        idem_key = headers.get("idempotency-key")
        if not idem_key:
            return await self.app(scope, receive, send)

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return

        digest = self.store.digest(idem_key, bytes(body))
        replayed = {"done": False}

        async def replay_receive():
            # First consumer gets the buffered body; after that, disconnect.
            if not replayed["done"]:
                replayed["done"] = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        async with self.store.lock_for(digest):
            cached = self.store.get(digest)
            if cached is not None:
                status, cached_body, cached_headers = cached
                await _send_stored(send, status, cached_body, cached_headers)
                return
            captured: dict = {}
            await self.app(
                scope,
                replay_receive,
                _capture_send(send, captured),
            )
            if 200 <= captured.get("status", 500) < 300:
                self.store.put(digest, captured["status"], captured["body"], captured["headers"])


async def _send_stored(send, status: int, body: bytes, headers: list[tuple[str, str]]) -> None:
    out_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers]
    out_headers.append((b"x-idempotent-replay", b"true"))
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": out_headers,
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _capture_send(send, captured: dict):
    async def wrapped(message) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = [
                (k.decode("latin-1"), v.decode("latin-1")) for k, v in message.get("headers", [])
            ]
        elif message["type"] == "http.response.body":
            captured["body"] = captured.get("body", b"") + message.get("body", b"")
        await send(message)

    return wrapped


__all__ = [
    "IDEMPOTENT_PATHS",
    "IdempotencyMiddleware",
    "IdempotencyStore",
    "REPLAY_HEADER",
]
