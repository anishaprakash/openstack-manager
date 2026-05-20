"""Pytest fixtures shared across the test suite.

Strategy
--------
We do NOT talk to a real OpenStack cloud in tests.  Instead, we patch
``OpenStackVMService`` at the router level so every SDK call is replaced
by a ``MagicMock``.  This keeps tests fast, hermetic, and runnable with
no credentials.

The ``VALID_API_KEY`` constant mirrors the default in ``Settings`` so the
TestClient can pass auth without touching env variables.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.dependencies as _deps
from app.main import app
from app.models.vm import VMAddresses, VMResponse, VMStatus

VALID_API_KEY = "test-key"
AUTH_HEADERS = {"X-API-Key": VALID_API_KEY}


# ---------------------------------------------------------------------------
# Canonical fixture VM
# ---------------------------------------------------------------------------

FIXTURE_VM = VMResponse(
    id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    name="web-server-01",
    status=VMStatus.ACTIVE,
    flavor_id="m1.small",
    image_id="11111111-2222-3333-4444-555555555555",
    addresses=[
        VMAddresses(
            network_name="public",
            ip_address="192.168.1.10",
            ip_version=4,
            type="fixed",
        )
    ],
    key_name="my-keypair",
    security_groups=["default"],
    availability_zone="nova",
    metadata={"env": "test"},
    created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
)

# ---------------------------------------------------------------------------
# Mock service fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _override_api_key(monkeypatch):
    """Force settings.api_key to VALID_API_KEY for every test."""
    monkeypatch.setattr(_deps.settings, "api_key", VALID_API_KEY)


@pytest.fixture()
def mock_svc() -> MagicMock:
    """Patch the module-level ``_svc`` instance inside the vms router."""
    with patch("app.routers.vms._svc") as mock:
        # Default return values — individual tests can override as needed
        mock.list_vms.return_value = [FIXTURE_VM]
        mock.get_vm.return_value = FIXTURE_VM
        mock.create_vm.return_value = FIXTURE_VM
        mock.delete_vm.return_value = None
        mock.start_vm.return_value = None
        mock.stop_vm.return_value = None
        mock.reboot_vm.return_value = None
        yield mock


@pytest.fixture()
def client(mock_svc) -> TestClient:
    """HTTP test client with the mock service already wired in."""
    return TestClient(app, raise_server_exceptions=True)
