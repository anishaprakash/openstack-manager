"""Tests for API key authentication."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import AUTH_HEADERS


@pytest.fixture()
def bare_client() -> TestClient:
    """Client without mock_svc — only auth behaviour is tested."""
    return TestClient(app, raise_server_exceptions=False)


class TestAPIKeyAuth:
    def test_missing_key_returns_401(self, bare_client):
        resp = bare_client.get("/api/v1/vms")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, bare_client):
        resp = bare_client.get("/api/v1/vms", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_valid_key_passes_auth(self, client):
        # client fixture has the correct API key set; service is mocked
        resp = client.get("/api/v1/vms", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_health_endpoint_needs_no_auth(self, bare_client):
        resp = bare_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
