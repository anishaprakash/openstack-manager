"""Tests for all VM lifecycle endpoints."""

from __future__ import annotations

import pytest

from app.exceptions import VMNotFoundError, VMOperationError
from tests.conftest import AUTH_HEADERS, FIXTURE_VM

VM_ID = FIXTURE_VM.id
BASE = "/api/v1/vms"


# ---------------------------------------------------------------------------
# List VMs
# ---------------------------------------------------------------------------


class TestListVMs:
    def test_returns_200_with_items(self, client, mock_svc):
        resp = client.get(BASE, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == VM_ID

    def test_passes_filters_to_service(self, client, mock_svc):
        mock_svc.list_vms.return_value = []
        resp = client.get(BASE, params={"status": "ACTIVE", "name": "web", "limit": 50}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        mock_svc.list_vms.assert_called_once_with(status="ACTIVE", name="web", limit=50)

    def test_empty_list(self, client, mock_svc):
        mock_svc.list_vms.return_value = []
        resp = client.get(BASE, headers=AUTH_HEADERS)
        assert resp.json() == {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Get VM
# ---------------------------------------------------------------------------


class TestGetVM:
    def test_returns_vm(self, client, mock_svc):
        resp = client.get(f"{BASE}/{VM_ID}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["id"] == VM_ID
        assert resp.json()["name"] == "web-server-01"

    def test_not_found_returns_404(self, client, mock_svc):
        mock_svc.get_vm.side_effect = VMNotFoundError("bad-id")
        resp = client.get(f"{BASE}/bad-id", headers=AUTH_HEADERS)
        assert resp.status_code == 404
        assert "bad-id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Create VM
# ---------------------------------------------------------------------------


class TestCreateVM:
    PAYLOAD = {
        "name": "web-server-01",
        "flavor_id": "m1.small",
        "image_id": "11111111-2222-3333-4444-555555555555",
        "network_id": "public-net",
    }

    def test_creates_vm_returns_201(self, client, mock_svc):
        resp = client.post(BASE, json=self.PAYLOAD, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        assert resp.json()["id"] == VM_ID

    def test_service_called_with_correct_args(self, client, mock_svc):
        client.post(BASE, json=self.PAYLOAD, headers=AUTH_HEADERS)
        mock_svc.create_vm.assert_called_once_with(
            name="web-server-01",
            flavor_id="m1.small",
            image_id="11111111-2222-3333-4444-555555555555",
            network_id="public-net",
            key_name=None,
            security_groups=["default"],
            user_data=None,
            availability_zone=None,
            metadata={},
        )

    def test_missing_required_field_returns_422(self, client, mock_svc):
        bad = {k: v for k, v in self.PAYLOAD.items() if k != "image_id"}
        resp = client.post(BASE, json=bad, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    def test_operation_error_propagates(self, client, mock_svc):
        mock_svc.create_vm.side_effect = VMOperationError("quota exceeded", status_code=422)
        resp = client.post(BASE, json=self.PAYLOAD, headers=AUTH_HEADERS)
        assert resp.status_code == 422
        assert "quota exceeded" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Delete VM
# ---------------------------------------------------------------------------


class TestDeleteVM:
    def test_delete_returns_204(self, client, mock_svc):
        resp = client.delete(f"{BASE}/{VM_ID}", headers=AUTH_HEADERS)
        assert resp.status_code == 204
        assert resp.content == b""

    def test_not_found_returns_404(self, client, mock_svc):
        mock_svc.delete_vm.side_effect = VMNotFoundError(VM_ID)
        resp = client.delete(f"{BASE}/{VM_ID}", headers=AUTH_HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Power operations
# ---------------------------------------------------------------------------


class TestPowerOps:
    @pytest.mark.parametrize("action", ["start", "stop"])
    def test_action_returns_200(self, client, mock_svc, action):
        resp = client.post(f"{BASE}/{VM_ID}/{action}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["vm_id"] == VM_ID

    def test_reboot_soft(self, client, mock_svc):
        resp = client.post(f"{BASE}/{VM_ID}/reboot", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        mock_svc.reboot_vm.assert_called_once_with(VM_ID, hard=False)

    def test_reboot_hard(self, client, mock_svc):
        resp = client.post(f"{BASE}/{VM_ID}/reboot", params={"hard": "true"}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        mock_svc.reboot_vm.assert_called_once_with(VM_ID, hard=True)

    def test_start_not_found(self, client, mock_svc):
        mock_svc.start_vm.side_effect = VMNotFoundError(VM_ID)
        resp = client.post(f"{BASE}/{VM_ID}/start", headers=AUTH_HEADERS)
        assert resp.status_code == 404


