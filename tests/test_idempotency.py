"""Idempotent POST /query: Idempotency-Key replay, fresh calls, concurrency.

The pipeline execution count is observed through the registry's
``hvac_queries_total`` counter, so a replay is proven by the counter NOT
moving, not just by response equality.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from hvac_copilot.serve.app import create_app
from hvac_copilot.serve.idempotency import IdempotencyStore

QUESTION = {"question": "What does fault code E04 mean?", "unit_model": "X200"}


@pytest.fixture()
def app(service):
    return create_app(service=service)


def _queries_total(service) -> float:
    return service.metrics.counter("hvac_queries_total")


def test_same_key_same_body_replays(service, app):
    async def scenario() -> tuple[bool, bool, str, str, float, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = _queries_total(service)
            first = await client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "op-1"})
            middle = _queries_total(service)
            replay = await client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "op-1"})
            after = _queries_total(service)
            return (
                "x-idempotent-replay" not in first.headers,
                replay.headers.get("x-idempotent-replay") == "true",
                first.text,
                replay.text,
                middle - before,
                after - middle,
            )

    (
        first_is_fresh,
        replayed,
        first_text,
        replay_text,
        first_delta,
        replay_delta,
    ) = asyncio.run(scenario())
    assert first_is_fresh
    assert replayed, "second identical call must carry X-Idempotent-Replay: true"
    assert first_text == replay_text, "replayed body must match the stored response"
    assert first_delta == 1.0 and replay_delta == 0.0, "replay must not re-execute the pipeline"


def test_different_key_same_body_executes_fresh(service, app):
    async def scenario() -> tuple[str, str, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = _queries_total(service)
            one = await client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "op-a"})
            two = await client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "op-b"})
            return one.text, two.text, _queries_total(service) - before

    one_text, two_text, delta = asyncio.run(scenario())
    assert delta == 2.0, "different idempotency keys must execute independently"
    # neither is a replay (fresh executions differ in trace.correlation_id)
    assert '"cache_hit"' in one_text and '"cache_hit"' in two_text


def test_no_key_bypasses_store(service, app):
    async def scenario() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = _queries_total(service)
            for _ in range(2):
                r = await client.post("/v1/query", json=QUESTION)
                assert r.status_code == 200
                assert "x-idempotent-replay" not in r.headers
            return _queries_total(service) - before

    assert asyncio.run(scenario()) == 2.0


def test_same_key_different_body_executes_fresh(service, app):
    other = {"question": "clean the condenser coil", "unit_model": "V9"}

    async def scenario() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = _queries_total(service)
            await client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "op-1"})
            r = await client.post("/v1/query", json=other, headers={"Idempotency-Key": "op-1"})
            assert r.status_code == 200
            assert r.headers.get("x-idempotent-replay") != "true"
            return _queries_total(service) - before

    # digest = sha256(key + body): same key with a different body is a new op
    assert asyncio.run(scenario()) == 2.0


def test_concurrent_duplicates_execute_once(service, app):
    async def scenario() -> tuple[list[httpx.Response], float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = _queries_total(service)
            responses = await asyncio.gather(
                *[
                    client.post("/v1/query", json=QUESTION, headers={"Idempotency-Key": "race-1"})
                    for _ in range(3)
                ]
            )
            return responses, _queries_total(service) - before

    responses, delta = asyncio.run(scenario())
    assert all(r.status_code == 200 for r in responses)
    assert delta == 1.0, "concurrent duplicates must serialize into a single execution"
    replays = [r for r in responses if r.headers.get("x-idempotent-replay") == "true"]
    assert len(replays) == 2


def test_store_lru_and_ttl_bounds():
    store = IdempotencyStore(max_entries=3, ttl_seconds=3600)
    for i in range(5):
        store.put(f"digest-{i}", 200, b"{}", [])
    assert store.get("digest-0") is None  # evicted (LRU over 3 entries)
    assert store.get("digest-4") is not None

    short_ttl = IdempotencyStore(max_entries=8, ttl_seconds=0.0)
    short_ttl.put("d", 200, b"{}", [])
    assert short_ttl.get("d") is None  # TTL 0 -> immediately expired
