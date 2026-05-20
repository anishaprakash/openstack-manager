"""Unit tests for OpenStackVMService and its helper functions.

All OpenStack SDK calls are mocked — no real cloud is needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import openstack.exceptions
import pytest

from app.exceptions import OpenStackConnectionError, VMNotFoundError, VMOperationError
from app.services.openstack_service import (
    OpenStackVMService,
    _parse_addresses,
    _parse_datetime,
    _parse_server,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_UNSET = object()


def _make_server(
    id="srv-123",
    name="test-vm",
    status="ACTIVE",
    flavor=_UNSET,
    image=_UNSET,
    addresses=_UNSET,
    security_groups=_UNSET,
    key_name="kp",
    availability_zone="nova",
    metadata=None,
    created_at="2024-01-01T00:00:00Z",
    updated_at="2024-01-02T00:00:00Z",
    hypervisor_hostname=None,
    task_state=None,
    power_state=None,
):
    data = {
        "status": status,
        "flavor": {"id": "m1.small"} if flavor is _UNSET else flavor,
        "image": {"id": "img-abc"} if image is _UNSET else image,
        "addresses": {} if addresses is _UNSET else addresses,
        "security_groups": [{"name": "default"}] if security_groups is _UNSET else security_groups,
        "key_name": key_name,
        "availability_zone": availability_zone,
        "metadata": metadata or {},
        "created_at": created_at,
        "updated_at": updated_at,
        "hypervisor_hostname": hypervisor_hostname,
        "task_state": task_state,
        "power_state": power_state,
    }
    mock = MagicMock()
    mock.id = id
    mock.name = name
    mock.get = lambda key, default=None: data.get(key, default)
    return mock


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_none_returns_none(self):
        assert _parse_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_datetime("") is None

    def test_z_suffix_parsed(self):
        result = _parse_datetime("2024-01-01T12:00:00Z")
        assert result == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_iso_with_offset_parsed(self):
        result = _parse_datetime("2024-06-15T08:30:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_invalid_string_returns_none(self):
        assert _parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# _parse_addresses
# ---------------------------------------------------------------------------


class TestParseAddresses:
    def test_empty_dict_returns_empty_list(self):
        assert _parse_addresses({}) == []

    def test_none_returns_empty_list(self):
        assert _parse_addresses(None) == []

    def test_single_address(self):
        raw = {
            "public": [
                {"addr": "10.0.0.1", "version": 4, "OS-EXT-IPS-MAC:mac_addr": "aa:bb:cc:dd:ee:ff", "OS-EXT-IPS:type": "fixed"}
            ]
        }
        result = _parse_addresses(raw)
        assert len(result) == 1
        assert result[0].network_name == "public"
        assert result[0].ip_address == "10.0.0.1"
        assert result[0].ip_version == 4
        assert result[0].mac_address == "aa:bb:cc:dd:ee:ff"
        assert result[0].type == "fixed"

    def test_multiple_networks(self):
        raw = {
            "public": [{"addr": "1.2.3.4", "version": 4}],
            "private": [{"addr": "192.168.1.1", "version": 4}],
        }
        result = _parse_addresses(raw)
        assert len(result) == 2

    def test_missing_addr_defaults_to_empty_string(self):
        raw = {"net": [{}]}
        result = _parse_addresses(raw)
        assert result[0].ip_address == ""

    def test_missing_version_defaults_to_4(self):
        raw = {"net": [{"addr": "10.0.0.1"}]}
        result = _parse_addresses(raw)
        assert result[0].ip_version == 4


# ---------------------------------------------------------------------------
# _parse_server
# ---------------------------------------------------------------------------


class TestParseServer:
    def test_active_server(self):
        vm = _parse_server(_make_server())
        assert vm.id == "srv-123"
        assert vm.name == "test-vm"
        assert vm.status.value == "ACTIVE"
        assert vm.flavor_id == "m1.small"
        assert vm.image_id == "img-abc"

    def test_unknown_status_maps_to_unknown(self):
        vm = _parse_server(_make_server(status="RETICULATING_SPLINES"))
        assert vm.status.value == "UNKNOWN"

    def test_image_non_dict_gives_none_image_id(self):
        vm = _parse_server(_make_server(image=""))
        assert vm.image_id is None

    def test_security_groups_extracted(self):
        server = _make_server(security_groups=[{"name": "default"}, {"name": "web"}])
        vm = _parse_server(server)
        assert vm.security_groups == ["default", "web"]

    def test_flavor_with_original_name(self):
        server = _make_server(flavor={"original_name": "m1.xlarge"})
        vm = _parse_server(server)
        assert vm.flavor_id == "m1.xlarge"

    def test_addresses_populated(self):
        addresses = {"public": [{"addr": "10.0.0.1", "version": 4}]}
        vm = _parse_server(_make_server(addresses=addresses))
        assert len(vm.addresses) == 1

    def test_host_from_hypervisor_hostname(self):
        server = _make_server(hypervisor_hostname="compute-01")
        vm = _parse_server(server)
        assert vm.host == "compute-01"

    def test_none_security_groups(self):
        server = _make_server(security_groups=None)
        vm = _parse_server(server)
        assert vm.security_groups == []


# ---------------------------------------------------------------------------
# OpenStackVMService._connect
# ---------------------------------------------------------------------------


class TestConnect:
    def test_returns_connection_on_success(self):
        svc = OpenStackVMService()
        with patch("app.services.openstack_service.openstack.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            conn = svc._connect()
            assert conn is mock_connect.return_value

    def test_raises_connection_error_on_exception(self):
        svc = OpenStackVMService()
        with patch("app.services.openstack_service.openstack.connect", side_effect=Exception("timeout")):
            with pytest.raises(OpenStackConnectionError, match="timeout"):
                svc._connect()


# ---------------------------------------------------------------------------
# OpenStackVMService.list_vms
# ---------------------------------------------------------------------------


class TestListVMs:
    def _svc_with_conn(self, conn):
        svc = OpenStackVMService()
        svc._connect = MagicMock(return_value=conn)
        return svc

    def test_returns_parsed_vms(self):
        conn = MagicMock()
        conn.compute.servers.return_value = [_make_server()]
        svc = self._svc_with_conn(conn)
        result = svc.list_vms()
        assert len(result) == 1
        assert result[0].id == "srv-123"

    def test_filters_passed_to_sdk(self):
        conn = MagicMock()
        conn.compute.servers.return_value = []
        svc = self._svc_with_conn(conn)
        svc.list_vms(status="active", name="web", limit=25)
        conn.compute.servers.assert_called_once_with(status="ACTIVE", name="web", limit=25)

    def test_no_filters_uses_limit_only(self):
        conn = MagicMock()
        conn.compute.servers.return_value = []
        svc = self._svc_with_conn(conn)
        svc.list_vms()
        conn.compute.servers.assert_called_once_with(limit=100)

    def test_sdk_exception_raises_vm_operation_error(self):
        conn = MagicMock()
        conn.compute.servers.side_effect = openstack.exceptions.SDKException("boom")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to list VMs"):
            svc.list_vms()


# ---------------------------------------------------------------------------
# OpenStackVMService.get_vm
# ---------------------------------------------------------------------------


class TestGetVM:
    def _svc_with_conn(self, conn):
        svc = OpenStackVMService()
        svc._connect = MagicMock(return_value=conn)
        return svc

    def test_returns_vm(self):
        conn = MagicMock()
        conn.compute.get_server.return_value = _make_server()
        svc = self._svc_with_conn(conn)
        result = svc.get_vm("srv-123")
        assert result.id == "srv-123"

    def test_none_server_raises_not_found(self):
        conn = MagicMock()
        conn.compute.get_server.return_value = None
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.get_vm("missing")

    def test_resource_not_found_raises_not_found(self):
        conn = MagicMock()
        conn.compute.get_server.side_effect = openstack.exceptions.ResourceNotFound
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.get_vm("missing")

    def test_sdk_exception_raises_operation_error(self):
        conn = MagicMock()
        conn.compute.get_server.side_effect = openstack.exceptions.SDKException("err")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to get VM"):
            svc.get_vm("srv-123")


# ---------------------------------------------------------------------------
# OpenStackVMService.create_vm
# ---------------------------------------------------------------------------


class TestCreateVM:
    def _svc_with_conn(self, conn):
        svc = OpenStackVMService()
        svc._connect = MagicMock(return_value=conn)
        return svc

    def _base_kwargs(self):
        return dict(
            name="vm-1",
            flavor_id="m1.small",
            image_id="img-abc",
            network_id="net-xyz",
        )

    def test_creates_vm_minimal(self):
        conn = MagicMock()
        conn.compute.create_server.return_value = _make_server()
        svc = self._svc_with_conn(conn)
        result = svc.create_vm(**self._base_kwargs())
        assert result.id == "srv-123"
        call_kwargs = conn.compute.create_server.call_args[1]
        assert call_kwargs["networks"] == [{"uuid": "net-xyz"}]
        assert call_kwargs["security_groups"] == [{"name": "default"}]

    def test_creates_vm_with_optional_params(self):
        conn = MagicMock()
        conn.compute.create_server.return_value = _make_server()
        svc = self._svc_with_conn(conn)
        svc.create_vm(
            **self._base_kwargs(),
            key_name="my-key",
            user_data="#!/bin/bash\necho hi",
            availability_zone="az-1",
            security_groups=["web", "db"],
            metadata={"env": "prod"},
        )
        call_kwargs = conn.compute.create_server.call_args[1]
        assert call_kwargs["key_name"] == "my-key"
        assert call_kwargs["user_data"] == "#!/bin/bash\necho hi"
        assert call_kwargs["availability_zone"] == "az-1"
        assert call_kwargs["security_groups"] == [{"name": "web"}, {"name": "db"}]

    def test_sdk_exception_raises_operation_error(self):
        conn = MagicMock()
        conn.compute.create_server.side_effect = openstack.exceptions.SDKException("quota")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to create VM"):
            svc.create_vm(**self._base_kwargs())


# ---------------------------------------------------------------------------
# OpenStackVMService.delete_vm
# ---------------------------------------------------------------------------


class TestDeleteVM:
    def _svc_with_conn(self, conn):
        svc = OpenStackVMService()
        svc._connect = MagicMock(return_value=conn)
        return svc

    def test_deletes_successfully(self):
        conn = MagicMock()
        conn.compute.get_server.return_value = _make_server()
        svc = self._svc_with_conn(conn)
        svc.delete_vm("srv-123")
        conn.compute.delete_server.assert_called_once_with("srv-123", force=False)

    def test_none_server_raises_not_found(self):
        conn = MagicMock()
        conn.compute.get_server.return_value = None
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.delete_vm("missing")

    def test_resource_not_found_raises_not_found(self):
        conn = MagicMock()
        conn.compute.get_server.side_effect = openstack.exceptions.ResourceNotFound
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.delete_vm("missing")

    def test_sdk_exception_raises_operation_error(self):
        conn = MagicMock()
        conn.compute.get_server.return_value = _make_server()
        conn.compute.delete_server.side_effect = openstack.exceptions.SDKException("err")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to delete VM"):
            svc.delete_vm("srv-123")


# ---------------------------------------------------------------------------
# OpenStackVMService power operations
# ---------------------------------------------------------------------------


class TestPowerOps:
    def _svc_with_conn(self, conn):
        svc = OpenStackVMService()
        svc._connect = MagicMock(return_value=conn)
        return svc

    def test_start_calls_sdk(self):
        conn = MagicMock()
        svc = self._svc_with_conn(conn)
        svc.start_vm("srv-123")
        conn.compute.start_server.assert_called_once_with("srv-123")

    def test_stop_calls_sdk(self):
        conn = MagicMock()
        svc = self._svc_with_conn(conn)
        svc.stop_vm("srv-123")
        conn.compute.stop_server.assert_called_once_with("srv-123")

    def test_reboot_soft(self):
        conn = MagicMock()
        svc = self._svc_with_conn(conn)
        svc.reboot_vm("srv-123", hard=False)
        conn.compute.reboot_server.assert_called_once_with("srv-123", "SOFT")

    def test_reboot_hard(self):
        conn = MagicMock()
        svc = self._svc_with_conn(conn)
        svc.reboot_vm("srv-123", hard=True)
        conn.compute.reboot_server.assert_called_once_with("srv-123", "HARD")

    def test_start_resource_not_found(self):
        conn = MagicMock()
        conn.compute.start_server.side_effect = openstack.exceptions.ResourceNotFound
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.start_vm("srv-123")

    def test_stop_sdk_exception(self):
        conn = MagicMock()
        conn.compute.stop_server.side_effect = openstack.exceptions.SDKException("err")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to stop VM"):
            svc.stop_vm("srv-123")

    def test_reboot_resource_not_found(self):
        conn = MagicMock()
        conn.compute.reboot_server.side_effect = openstack.exceptions.ResourceNotFound
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMNotFoundError):
            svc.reboot_vm("srv-123")

    def test_reboot_sdk_exception(self):
        conn = MagicMock()
        conn.compute.reboot_server.side_effect = openstack.exceptions.SDKException("err")
        svc = self._svc_with_conn(conn)
        with pytest.raises(VMOperationError, match="Failed to reboot VM"):
            svc.reboot_vm("srv-123")

    def test_server_action_unknown_action_raises(self):
        conn = MagicMock()
        svc = self._svc_with_conn(conn)
        with pytest.raises(ValueError, match="Unknown action"):
            svc._server_action("srv-123", "explode")
