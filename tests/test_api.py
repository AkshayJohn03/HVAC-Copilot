"""ASGI service contract: /health, /query, /ingest, /metrics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hvac_copilot.serve.app import create_app


@pytest.fixture(scope="module")
def client(service):
    return TestClient(create_app(service=service))


def test_health_reports_index(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["indexed_chunks"] > 0
    assert body["fault_codes"] > 0


def test_query_endpoint_grounds_answers(client):
    r = client.post(
        "/query", json={"question": "What does fault code E04 mean?", "unit_model": "X200"}
    )
    assert r.status_code == 200
    body = r.json()
    assert "E04" in body["code_refs"]
    assert body["citations"]


def test_query_endpoint_safety_escalation(client):
    r = client.post(
        "/query",
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
    client.post("/query", json={"question": "clean the condenser coil", "unit_model": "V9"})
    text = client.get("/metrics").text
    assert "hvac_queries_total" in text
    assert "hvac_guardrail_escalations_total" in text


def test_ingest_endpoint_idempotent_stats(client):
    body = client.post("/ingest").json()
    assert body["new"] == 0 and body["updated"] == 0
