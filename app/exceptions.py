"""Custom exceptions and FastAPI exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class VMNotFoundError(Exception):
    def __init__(self, vm_id: str):
        self.vm_id = vm_id
        super().__init__(f"VM '{vm_id}' not found")


class VMOperationError(Exception):
    """Raised when an OpenStack operation fails."""

    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


class OpenStackConnectionError(Exception):
    """Raised when the SDK cannot connect to the OpenStack cloud."""


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VMNotFoundError)
    async def vm_not_found_handler(request: Request, exc: VMNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "vm_id": exc.vm_id},
        )

    @app.exception_handler(VMOperationError)
    async def vm_operation_handler(request: Request, exc: VMOperationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc)},
        )

    @app.exception_handler(OpenStackConnectionError)
    async def openstack_connection_handler(
        request: Request, exc: OpenStackConnectionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "OpenStack cloud is unreachable", "error": str(exc)},
        )
