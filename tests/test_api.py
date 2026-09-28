"""ASGI service contract (v1): /v1/health, /v1/query, /v1/ingest, /v1/metrics.

Also covers the hardening surface: legacy-path deprecation headers,
correlation ids, and request limits (8 KiB body -> 413, top_k > 50 -> 422).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hvac_copilot.serve.app import create_app


@pytest.fixture(scope="module")
def client(service):
    return TestClient(create_app(service=service))


def test_health_reports_index(client):
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"
    assert body["indexed_chunks"] > 0
    assert body["fault_codes"] > 0


def test_query_endpoint_grounds_answers(client):
    r = client.post(
        "/v1/query", json={"question": "What does fault code E04 mean?", "unit_model": "X200"}
    )
    assert r.status_code == 200
    body = r.json()
    assert "E04" in body["code_refs"]
    assert body["citations"]


def test_query_endpoint_safety_escalation(client):
    r = client.post(
        "/v1/query",
        json={
            "question": "How do I recharge the refrigerant?",
            "unit_model": "X200",
            "safety": False,
        },
    )
    body = r.json()
    assert body["escalation"] is True
    assert "certified" in body["answer"].lower()


def test_metrics_prometheus_format(client):
    client.post("/v1/query", json={"question": "clean the condenser coil", "unit_model": "V9"})
    text = client.get("/v1/metrics").text
    assert "hvac_queries_total" in text
    assert "hvac_guardrail_escalations_total" in text


def test_ingest_endpoint_idempotent_stats(client):
    body = client.post("/v1/ingest").json()
    assert body["new"] == 0 and body["updated"] == 0


# -- versioning: legacy aliases still work, stamped deprecated -----------------


def test_legacy_alias_works_with_deprecation_headers(client):
    r = client.post(
        "/query", json={"question": "What does fault code E04 mean?", "unit_model": "X200"}
    )
    assert r.status_code == 200
    assert r.headers["deprecation"] == "true"
    assert "sunset" in r.headers

    legacy_health = client.get("/health")
    assert legacy_health.status_code == 200
    assert legacy_health.headers["deprecation"] == "true"


def test_v1_paths_not_marked_deprecated(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert "deprecation" not in r.headers
    assert "sunset" not in r.headers


# -- correlation ids -----------------------------------------------------------


def test_correlation_id_echoed_and_traced(client):
    r = client.post(
        "/v1/query",
        json={"question": "What does fault code E04 mean?", "unit_model": "X200"},
        headers={"X-Correlation-ID": "cid-test-123"},
    )
    assert r.status_code == 200
    assert r.headers["x-correlation-id"] == "cid-test-123"
    assert r.json()["trace"]["correlation_id"] == "cid-test-123"


def test_correlation_id_generated_when_absent(client):
    r = client.post("/v1/query", json={"question": "clean the condenser coil", "unit_model": "V9"})
    assert r.status_code == 200
    generated = r.headers["x-correlation-id"]
    assert generated and generated != "cid-test-123"
    assert r.json()["trace"]["correlation_id"] == generated


# -- request limits -------------------------------------------------------------


def test_oversized_question_body_rejected_413(client):
    r = client.post(
        "/v1/query",
        json={"question": "x" * (8 * 1024 + 1), "unit_model": "X200"},
    )
    assert r.status_code == 413


def test_top_k_above_50_rejected_422(client):
    r = client.post(
        "/v1/query",
        json={"question": "What does fault code E04 mean?", "unit_model": "X200", "top_k": 51},
    )
    assert r.status_code == 422
