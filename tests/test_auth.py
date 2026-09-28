"""API-key auth: enforced when HVAC_API_KEYS is set, disabled (with warning) otherwise.

Each test builds its own app after adjusting the environment, so the
monkeypatched env var is picked up by the Settings constructed inside
create_app.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from hvac_copilot.serve.app import create_app
from hvac_copilot.serve.auth import APIKeyAuth, hash_key


def _client(service, **kwargs):
    return TestClient(create_app(service=service, **kwargs))


def test_auth_disabled_by_default(service, monkeypatch):
    monkeypatch.delenv("HVAC_API_KEYS", raising=False)
    client = _client(service)
    r = client.post(
        "/v1/query", json={"question": "What does fault code E04 mean?", "unit_model": "X200"}
    )
    assert r.status_code == 200
    assert client.get("/v1/health").status_code == 200


def test_auth_missing_key_returns_401(service, monkeypatch):
    monkeypatch.setenv("HVAC_API_KEYS", "secret-a,secret-b")
    client = _client(service)
    r = client.post(
        "/v1/query", json={"question": "What does fault code E04 mean?", "unit_model": "X200"}
    )
    assert r.status_code == 401
    # generic message: no detail about which key failed or how many exist
    assert r.json()["detail"] == "Unauthorized: missing or invalid API key."


def test_auth_wrong_key_returns_401(service, monkeypatch):
    monkeypatch.setenv("HVAC_API_KEYS", "secret-a,secret-b")
    client = _client(service)
    r = client.post(
        "/v1/query",
        json={"question": "What does fault code E04 mean?", "unit_model": "X200"},
        headers={"X-API-Key": "not-a-key"},
    )
    assert r.status_code == 401


def test_auth_valid_key_returns_200(service, monkeypatch):
    monkeypatch.setenv("HVAC_API_KEYS", "secret-a,secret-b")
    client = _client(service)
    for key in ("secret-a", "secret-b"):
        r = client.post(
            "/v1/query",
            json={"question": "What does fault code E04 mean?", "unit_model": "X200"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 200


def test_auth_protects_legacy_and_ingest_exempts_health_metrics(service, monkeypatch):
    monkeypatch.setenv("HVAC_API_KEYS", "secret-a")
    client = _client(service)
    assert client.post("/query", json={"question": "check the coil"}).status_code == 401
    assert client.post("/v1/ingest").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/v1/metrics").status_code == 200
    ok = client.post(
        "/v1/query",
        json={"question": "check the coil"},
        headers={"X-API-Key": "secret-a"},
    )
    assert ok.status_code == 200


def test_auth_stores_only_sha256_hashes():
    auth = APIKeyAuth("secret-a, secret-b")
    assert auth.enabled
    assert auth._hashes == frozenset({hash_key("secret-a"), hash_key("secret-b")})
    assert auth.verify("secret-a") and auth.verify("secret-b")
    assert not auth.verify("secret-c") and not auth.verify(None)
    # at rest: hashes only — raw keys are nowhere in the object's repr
    assert "secret-a" not in repr(auth) and "secret-b" not in repr(auth)


def test_auth_blank_value_disables():
    assert not APIKeyAuth(None).enabled
    assert not APIKeyAuth("").enabled
    assert not APIKeyAuth("   ").enabled
