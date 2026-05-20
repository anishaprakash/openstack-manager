"""Tests for main.py endpoints and helpers not covered elsewhere."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.exceptions import OpenStackConnectionError
from app.main import app, custom_openapi


@pytest.fixture()
def bare_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestRootEndpoint:
    def test_root_returns_message(self, bare_client):
        resp = bare_client.get("/")
        assert resp.status_code == 200
        assert "OpenStack VM Manager" in resp.json()["message"]


class TestCustomOpenAPI:
    def test_schema_has_security_scheme(self):
        app.openapi_schema = None  # force regeneration
        schema = custom_openapi()
        assert "ApiKeyAuth" in schema["components"]["securitySchemes"]

    def test_schema_cached_on_second_call(self):
        app.openapi_schema = None
        first = custom_openapi()
        second = custom_openapi()
        assert first is second

    def test_all_paths_have_security(self):
        app.openapi_schema = None
        schema = custom_openapi()
        for path_item in schema["paths"].values():
            for operation in path_item.values():
                assert any("ApiKeyAuth" in s for s in operation.get("security", []))


class TestOpenStackConnectionErrorHandler:
    def test_returns_503(self, client):
        with patch("app.routers.vms._svc.list_vms", side_effect=OpenStackConnectionError("down")):
            from tests.conftest import AUTH_HEADERS
            resp = client.get("/api/v1/vms", headers=AUTH_HEADERS)
        assert resp.status_code == 503
        assert resp.json()["detail"] == "OpenStack cloud is unreachable"


class TestDevEntrypoint:
    def test_main_calls_uvicorn(self):
        from app._dev import main
        with patch("uvicorn.run") as mock_run:
            main()
        mock_run.assert_called_once_with(
            "app.main:app", host="0.0.0.0", port=8000, reload=True
        )
