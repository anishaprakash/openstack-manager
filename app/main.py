"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload

With Docker:
    docker compose up
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import settings
from app.exceptions import register_exception_handlers
from app.routers import vms

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "A production-ready REST API for managing the **full lifecycle** of "
        "OpenStack virtual machines.  \n\n"
        "All endpoints require an `X-API-Key` header for authentication.\n\n"
        "## VM Lifecycle\n"
        "```\n"
        "CREATE → BUILD → ACTIVE ⟷ SHUTOFF\n"
        "                  ↓\n"
        "              VERIFY_RESIZE\n"
        "                  ↓\n"
        "           confirm / revert\n"
        "```\n"
    ),
    contact={
        "name": "Ranjith",
        "email": "ranjithsinghu@gmail.com",
    },
    license_info={"name": "MIT"},
    openapi_tags=[
        {
            "name": "Virtual Machines",
            "description": "Full lifecycle operations: create, list, get, start, stop, reboot, resize, snapshot, delete.",
        },
        {
            "name": "Health",
            "description": "Liveness and readiness checks.",
        },
    ],
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

register_exception_handlers(app)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(vms.router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Health endpoints (no auth required)
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health() -> dict:
    """Returns 200 OK when the application process is running."""
    return {"status": "ok", "version": settings.app_version}


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "OpenStack VM Manager — see /docs for the API reference"}


# ---------------------------------------------------------------------------
# Custom OpenAPI schema (adds security scheme)
# ---------------------------------------------------------------------------


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    # Register ApiKey security scheme so Swagger UI shows the "Authorize" button
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }

    # Apply globally so every operation shows the lock icon
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            operation.setdefault("security", []).append({"ApiKeyAuth": []})

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
