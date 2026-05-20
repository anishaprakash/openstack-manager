"""Pydantic schemas for VM request/response models."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, IPvAnyAddress


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class VMStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BUILD = "BUILD"
    REBUILD = "REBUILD"
    STOPPED = "STOPPED"
    SHUTOFF = "SHUTOFF"
    SUSPENDED = "SUSPENDED"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    DELETED = "DELETED"
    UNKNOWN = "UNKNOWN"


class PowerAction(StrEnum):
    START = "start"
    STOP = "stop"
    REBOOT = "reboot"
    HARD_REBOOT = "hard_reboot"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class VMCreateRequest(BaseModel):
    """Payload to create a new virtual machine."""

    name: Annotated[str, Field(min_length=1, max_length=255, examples=["web-server-01"])]
    flavor_id: Annotated[str, Field(examples=["m1.small"])]
    image_id: Annotated[str, Field(examples=["ubuntu-22.04"])]
    network_id: Annotated[str, Field(examples=["public-net"])]
    key_name: str | None = Field(
        default=None, description="SSH key pair name to inject into the instance"
    )
    security_groups: list[str] = Field(
        default_factory=lambda: ["default"],
        description="List of security group names",
    )
    user_data: str | None = Field(
        default=None,
        description="Cloud-init user data script (plain text, NOT base64-encoded)",
    )
    availability_zone: str | None = Field(
        default=None, description="Nova availability zone, e.g. 'nova' or 'az-1'"
    )
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary key-value metadata attached to the VM"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "web-server-01",
                    "flavor_id": "m1.small",
                    "image_id": "3a4d2c1b-0000-4000-8000-aabbccddeeff",
                    "network_id": "public-net",
                    "key_name": "my-keypair",
                    "security_groups": ["default", "web"],
                    "metadata": {"env": "prod", "team": "platform"},
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class VMAddresses(BaseModel):
    """Network address details for a VM."""

    network_name: str
    ip_address: str
    ip_version: int = 4
    mac_address: str | None = None
    type: str | None = None  # "fixed" | "floating"


class VMResponse(BaseModel):
    """Full representation of a virtual machine."""

    id: str = Field(description="OpenStack UUID of the server")
    name: str
    status: VMStatus
    flavor_id: str
    image_id: str | None
    addresses: list[VMAddresses] = Field(default_factory=list)
    key_name: str | None = None
    security_groups: list[str] = Field(default_factory=list)
    availability_zone: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    host: str | None = Field(default=None, description="Compute host (hypervisor)")
    task_state: str | None = None
    power_state: int | None = None

    model_config = {"from_attributes": True}


class VMListResponse(BaseModel):
    """Paginated list of virtual machines."""

    items: list[VMResponse]
    total: int


class MessageResponse(BaseModel):
    """Generic acknowledgement message."""

    message: str
    vm_id: str
