"""OpenStack VM lifecycle service.

Wraps ``openstacksdk`` to provide a clean, typed interface for all VM
operations consumed by the API layer.  Each public method raises only the
custom exceptions defined in ``app.exceptions``; callers never see raw SDK
exceptions.

Design notes
------------
* We use ``openstack.connect()`` with keyword arguments rather than a
  ``clouds.yaml`` file so that every credential comes from the validated
  ``Settings`` object (and therefore from environment variables / .env).
* All SDK calls are synchronous.  FastAPI's ``run_in_executor`` (via
  ``asyncio.to_thread``) can be used at the router level if you need to
  free the event-loop during long-running operations; that wiring is done
  in ``routers/vms.py``.
* The ``_parse_server`` helper normalises the raw SDK ``Server`` resource
  into our ``VMResponse`` Pydantic model, isolating all SDK-specific field
  names in one place.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import openstack
import openstack.exceptions
from openstack.compute.v2.server import Server

from app.config import settings
from app.exceptions import OpenStackConnectionError, VMNotFoundError, VMOperationError
from app.models.vm import VMAddresses, VMResponse, VMSnapshotResponse, VMStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_addresses(raw: dict[str, list[dict[str, Any]]]) -> list[VMAddresses]:
    """Convert the SDK address dict into a flat list of ``VMAddresses``."""
    result: list[VMAddresses] = []
    for network_name, addrs in (raw or {}).items():
        for addr in addrs:
            result.append(
                VMAddresses(
                    network_name=network_name,
                    ip_address=addr.get("addr", ""),
                    ip_version=addr.get("version", 4),
                    mac_address=addr.get("OS-EXT-IPS-MAC:mac_addr"),
                    type=addr.get("OS-EXT-IPS:type"),
                )
            )
    return result


def _parse_server(server: Server) -> VMResponse:
    """Map a raw SDK ``Server`` object to our ``VMResponse`` schema."""
    raw_status = (server.get("status") or "UNKNOWN").upper()
    try:
        status = VMStatus(raw_status)
    except ValueError:
        status = VMStatus.UNKNOWN

    flavor = server.get("flavor") or {}
    image = server.get("image") or {}

    security_groups: list[str] = [
        sg.get("name", "") for sg in (server.get("security_groups") or [])
    ]

    return VMResponse(
        id=server.id,
        name=server.name,
        status=status,
        flavor_id=flavor.get("id", flavor.get("original_name", "")),
        image_id=image.get("id") if isinstance(image, dict) else None,
        addresses=_parse_addresses(server.get("addresses") or {}),
        key_name=server.get("key_name"),
        security_groups=security_groups,
        availability_zone=server.get("availability_zone"),
        metadata=dict(server.get("metadata") or {}),
        created_at=_parse_datetime(server.get("created_at") or server.get("created")),
        updated_at=_parse_datetime(server.get("updated_at") or server.get("updated")),
        host=server.get("hypervisor_hostname") or server.get("OS-EXT-SRV-ATTR:host"),
        task_state=server.get("task_state") or server.get("OS-EXT-STS:task_state"),
        power_state=server.get("power_state") or server.get("OS-EXT-STS:power_state"),
    )


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class OpenStackVMService:
    """Stateless service that opens a fresh SDK connection per operation.

    Using per-call connections avoids token-expiry issues in long-running
    processes; the SDK caches the session internally for the lifetime of
    the ``Connection`` object so each instance still benefits from HTTP
    keep-alive within a single request.
    """

    def _connect(self) -> openstack.connection.Connection:
        """Return an authenticated OpenStack connection."""
        try:
            conn = openstack.connect(
                auth_url=settings.os_auth_url,
                username=settings.os_username,
                password=settings.os_password,
                project_name=settings.os_project_name,
                user_domain_name=settings.os_user_domain_name,
                project_domain_name=settings.os_project_domain_name,
                region_name=settings.os_region_name,
            )
            return conn
        except Exception as exc:
            logger.exception("Failed to connect to OpenStack: %s", exc)
            raise OpenStackConnectionError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_vms(
        self,
        status: str | None = None,
        name: str | None = None,
        limit: int = 100,
    ) -> list[VMResponse]:
        """Return all servers visible to the authenticated project."""
        conn = self._connect()
        try:
            filters: dict[str, Any] = {"limit": limit}
            if status:
                filters["status"] = status.upper()
            if name:
                filters["name"] = name
            servers = list(conn.compute.servers(**filters))
            return [_parse_server(s) for s in servers]
        except openstack.exceptions.SDKException as exc:
            logger.exception("list_vms failed: %s", exc)
            raise VMOperationError(f"Failed to list VMs: {exc}") from exc

    def get_vm(self, vm_id: str) -> VMResponse:
        """Return a single server by UUID or name."""
        conn = self._connect()
        try:
            server = conn.compute.get_server(vm_id)
            if server is None:
                raise VMNotFoundError(vm_id)
            return _parse_server(server)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except VMNotFoundError:
            raise
        except openstack.exceptions.SDKException as exc:
            logger.exception("get_vm(%s) failed: %s", vm_id, exc)
            raise VMOperationError(f"Failed to get VM '{vm_id}': {exc}") from exc

    # ------------------------------------------------------------------
    # Create / delete
    # ------------------------------------------------------------------

    def create_vm(
        self,
        name: str,
        flavor_id: str,
        image_id: str,
        network_id: str,
        key_name: str | None = None,
        security_groups: list[str] | None = None,
        user_data: str | None = None,
        availability_zone: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> VMResponse:
        """Boot a new server and return its initial representation."""
        conn = self._connect()
        try:
            kwargs: dict[str, Any] = {
                "name": name,
                "flavor_id": flavor_id,
                "image_id": image_id,
                "networks": [{"uuid": network_id}],
                "security_groups": [
                    {"name": sg} for sg in (security_groups or ["default"])
                ],
                "metadata": metadata or {},
            }
            if key_name:
                kwargs["key_name"] = key_name
            if user_data:
                kwargs["user_data"] = user_data
            if availability_zone:
                kwargs["availability_zone"] = availability_zone

            server = conn.compute.create_server(**kwargs)
            return _parse_server(server)
        except openstack.exceptions.SDKException as exc:
            logger.exception("create_vm failed: %s", exc)
            raise VMOperationError(f"Failed to create VM: {exc}", status_code=422) from exc

    def delete_vm(self, vm_id: str) -> None:
        """Terminate and delete a server."""
        conn = self._connect()
        try:
            server = conn.compute.get_server(vm_id)
            if server is None:
                raise VMNotFoundError(vm_id)
            conn.compute.delete_server(vm_id, force=False)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except VMNotFoundError:
            raise
        except openstack.exceptions.SDKException as exc:
            logger.exception("delete_vm(%s) failed: %s", vm_id, exc)
            raise VMOperationError(f"Failed to delete VM '{vm_id}': {exc}") from exc

    # ------------------------------------------------------------------
    # Power operations
    # ------------------------------------------------------------------

    def start_vm(self, vm_id: str) -> None:
        """Start a stopped or shut-off server."""
        self._server_action(vm_id, "start")

    def stop_vm(self, vm_id: str) -> None:
        """Gracefully stop a running server (ACPI shutdown)."""
        self._server_action(vm_id, "stop")

    def reboot_vm(self, vm_id: str, hard: bool = False) -> None:
        """Reboot a server.

        Args:
            vm_id: Server UUID.
            hard: If True, performs an unclean reset (equivalent to pulling
                  the power cord).  Defaults to a soft (graceful) reboot.
        """
        conn = self._connect()
        try:
            reboot_type = "HARD" if hard else "SOFT"
            conn.compute.reboot_server(vm_id, reboot_type)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            logger.exception("reboot_vm(%s) failed: %s", vm_id, exc)
            raise VMOperationError(f"Failed to reboot VM '{vm_id}': {exc}") from exc

    def _server_action(self, vm_id: str, action: str) -> None:
        """Dispatch a simple start/stop action."""
        conn = self._connect()
        try:
            if action == "start":
                conn.compute.start_server(vm_id)
            elif action == "stop":
                conn.compute.stop_server(vm_id)
            else:
                raise ValueError(f"Unknown action: {action}")
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            logger.exception("%s_vm(%s) failed: %s", action, vm_id, exc)
            raise VMOperationError(
                f"Failed to {action} VM '{vm_id}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def resize_vm(self, vm_id: str, flavor_id: str) -> None:
        """Resize a server to a different flavor.

        After Nova schedules the resize, the server moves into
        ``VERIFY_RESIZE`` state.  The caller should subsequently call
        ``confirm_resize_vm`` or ``revert_resize_vm``.
        """
        conn = self._connect()
        try:
            conn.compute.resize_server(vm_id, flavor_id)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            logger.exception("resize_vm(%s) failed: %s", vm_id, exc)
            raise VMOperationError(f"Failed to resize VM '{vm_id}': {exc}", status_code=422) from exc

    def confirm_resize_vm(self, vm_id: str) -> None:
        """Confirm a pending resize (moves server to ACTIVE)."""
        conn = self._connect()
        try:
            conn.compute.confirm_server_resize(vm_id)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            raise VMOperationError(f"Failed to confirm resize for VM '{vm_id}': {exc}") from exc

    def revert_resize_vm(self, vm_id: str) -> None:
        """Revert a pending resize (returns server to original flavor)."""
        conn = self._connect()
        try:
            conn.compute.revert_server_resize(vm_id)
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            raise VMOperationError(f"Failed to revert resize for VM '{vm_id}': {exc}") from exc

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot_vm(self, vm_id: str, snapshot_name: str) -> VMSnapshotResponse:
        """Create an image snapshot of the server's root disk.

        Returns immediately once Nova has accepted the request; the image
        moves through ``queued`` → ``saving`` → ``active`` asynchronously.
        """
        conn = self._connect()
        try:
            image_id = conn.compute.create_server_image(vm_id, name=snapshot_name)
            # create_server_image returns the image ID string in openstacksdk ≥ 1.x
            return VMSnapshotResponse(
                image_id=str(image_id),
                snapshot_name=snapshot_name,
                vm_id=vm_id,
                status="queued",
            )
        except openstack.exceptions.ResourceNotFound as exc:
            raise VMNotFoundError(vm_id) from exc
        except openstack.exceptions.SDKException as exc:
            logger.exception("snapshot_vm(%s) failed: %s", vm_id, exc)
            raise VMOperationError(
                f"Failed to snapshot VM '{vm_id}': {exc}", status_code=422
            ) from exc
