"""VM lifecycle router — all /vms endpoints.

Every endpoint is protected by the ``require_api_key`` dependency.

Sync SDK calls are offloaded to a thread pool via ``asyncio.to_thread``
so they don't block the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.dependencies import require_api_key
from app.models.vm import (
    MessageResponse,
    VMCreateRequest,
    VMListResponse,
    VMResizeRequest,
    VMResponse,
    VMSnapshotRequest,
    VMSnapshotResponse,
)
from app.services.openstack_service import OpenStackVMService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/vms",
    tags=["Virtual Machines"],
    dependencies=[Depends(require_api_key)],
)

# Module-level service instance (stateless — safe to share across requests)
_svc = OpenStackVMService()


# ---------------------------------------------------------------------------
# Helper to run sync SDK calls off the event loop
# ---------------------------------------------------------------------------


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------------------
# List & detail
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=VMListResponse,
    summary="List virtual machines",
    description=(
        "Return all VMs visible to the authenticated project. "
        "Optionally filter by `status` (e.g. `ACTIVE`, `SHUTOFF`) or a name substring."
    ),
)
async def list_vms(
    status: Annotated[
        str | None,
        Query(description="Filter by OpenStack server status (e.g. ACTIVE, SHUTOFF)"),
    ] = None,
    name: Annotated[
        str | None,
        Query(description="Filter by name substring"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Maximum number of results to return"),
    ] = 100,
) -> VMListResponse:
    vms = await _run(_svc.list_vms, status=status, name=name, limit=limit)
    return VMListResponse(items=vms, total=len(vms))


@router.get(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Get a virtual machine",
    description="Return detailed information for a single VM identified by its UUID.",
)
async def get_vm(vm_id: str) -> VMResponse:
    return await _run(_svc.get_vm, vm_id)


# ---------------------------------------------------------------------------
# Create & delete
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=VMResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a virtual machine",
    description=(
        "Boot a new VM using the specified flavor and image. "
        "The VM will be in **BUILD** state initially; poll `GET /vms/{vm_id}` "
        "until it reaches **ACTIVE**."
    ),
)
async def create_vm(body: VMCreateRequest) -> VMResponse:
    return await _run(
        _svc.create_vm,
        name=body.name,
        flavor_id=body.flavor_id,
        image_id=body.image_id,
        network_id=body.network_id,
        key_name=body.key_name,
        security_groups=body.security_groups,
        user_data=body.user_data,
        availability_zone=body.availability_zone,
        metadata=body.metadata,
    )


@router.delete(
    "/{vm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a virtual machine",
    description="Terminate and permanently delete a VM. This action is **irreversible**.",
)
async def delete_vm(vm_id: str) -> None:
    await _run(_svc.delete_vm, vm_id)


# ---------------------------------------------------------------------------
# Power operations
# ---------------------------------------------------------------------------


@router.post(
    "/{vm_id}/start",
    response_model=MessageResponse,
    summary="Start a virtual machine",
    description="Power on a VM that is in **SHUTOFF** or **STOPPED** state.",
)
async def start_vm(vm_id: str) -> MessageResponse:
    await _run(_svc.start_vm, vm_id)
    return MessageResponse(message="Start request accepted", vm_id=vm_id)


@router.post(
    "/{vm_id}/stop",
    response_model=MessageResponse,
    summary="Stop a virtual machine",
    description=(
        "Send an ACPI shutdown signal to a running VM. "
        "The VM will transition to **SHUTOFF** once the guest OS completes shutdown."
    ),
)
async def stop_vm(vm_id: str) -> MessageResponse:
    await _run(_svc.stop_vm, vm_id)
    return MessageResponse(message="Stop request accepted", vm_id=vm_id)


@router.post(
    "/{vm_id}/reboot",
    response_model=MessageResponse,
    summary="Reboot a virtual machine",
    description=(
        "Reboot a VM. By default performs a **soft** (graceful) reboot. "
        "Pass `hard=true` for an unclean reset (equivalent to a power cycle)."
    ),
)
async def reboot_vm(
    vm_id: str,
    hard: Annotated[
        bool,
        Query(description="If true, perform a hard (unclean) reboot"),
    ] = False,
) -> MessageResponse:
    await _run(_svc.reboot_vm, vm_id, hard=hard)
    reboot_type = "Hard reboot" if hard else "Soft reboot"
    return MessageResponse(message=f"{reboot_type} request accepted", vm_id=vm_id)


# ---------------------------------------------------------------------------
# Resize
# ---------------------------------------------------------------------------


@router.post(
    "/{vm_id}/resize",
    response_model=MessageResponse,
    summary="Resize a virtual machine",
    description=(
        "Change a VM's flavor (CPU/RAM/disk). The VM moves to **VERIFY_RESIZE** state. "
        "Call `POST /vms/{vm_id}/resize/confirm` to accept or "
        "`POST /vms/{vm_id}/resize/revert` to roll back."
    ),
)
async def resize_vm(vm_id: str, body: VMResizeRequest) -> MessageResponse:
    await _run(_svc.resize_vm, vm_id, body.flavor_id)
    return MessageResponse(message="Resize request accepted", vm_id=vm_id)


@router.post(
    "/{vm_id}/resize/confirm",
    response_model=MessageResponse,
    summary="Confirm a pending resize",
    description="Confirm a resize that is in **VERIFY_RESIZE** state, moving the VM to **ACTIVE**.",
)
async def confirm_resize(vm_id: str) -> MessageResponse:
    await _run(_svc.confirm_resize_vm, vm_id)
    return MessageResponse(message="Resize confirmed", vm_id=vm_id)


@router.post(
    "/{vm_id}/resize/revert",
    response_model=MessageResponse,
    summary="Revert a pending resize",
    description="Revert a resize that is in **VERIFY_RESIZE** state, restoring the original flavor.",
)
async def revert_resize(vm_id: str) -> MessageResponse:
    await _run(_svc.revert_resize_vm, vm_id)
    return MessageResponse(message="Resize reverted", vm_id=vm_id)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@router.post(
    "/{vm_id}/snapshot",
    response_model=VMSnapshotResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Snapshot a virtual machine",
    description=(
        "Create a Glance image snapshot of a VM's root disk. "
        "Returns **202 Accepted** immediately; the image transitions asynchronously "
        "through `queued → saving → active`."
    ),
)
async def snapshot_vm(vm_id: str, body: VMSnapshotRequest) -> VMSnapshotResponse:
    return await _run(_svc.snapshot_vm, vm_id, body.snapshot_name)
