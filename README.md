# OpenStack VM Manager

[![Tests](https://github.com/anishaprakash/openstack-manager/actions/workflows/tests.yml/badge.svg)](https://github.com/anishaprakash/openstack-manager/actions/workflows/tests.yml)
[![Docker](https://github.com/anishaprakash/openstack-manager/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/anishaprakash/openstack-manager/actions/workflows/docker-publish.yml)
[![codecov](https://codecov.io/gh/anishaprakash/openstack-manager/branch/main/graph/badge.svg?token=bc8f1602-ce58-4297-8cf3-c31d8e73a6a0)](https://app.codecov.io/github/anishaprakash/openstack-manager)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)

A production-ready REST API for managing the **full lifecycle** of OpenStack virtual machines, built with **FastAPI** and **Poetry**.

---

## Features

- Full VM lifecycle: create, list, get, start, stop, reboot, resize (with confirm/revert), snapshot, delete
- Real OpenStack integration via `openstacksdk`
- API key authentication (`X-API-Key` header)
- Async endpoints (sync SDK calls offloaded via `asyncio.to_thread`)
- Rich OpenAPI / Swagger UI with security scheme pre-wired
- Docker + Docker Compose for instant local startup
- pytest test suite with coverage reporting

---

## Quick Start

### 1. Prerequisites

| Tool             | Version    |
| ---------------- | ---------- |
| Python           | ≥ 3.11     |
| Poetry           | ≥ 1.8      |
| Docker + Compose | any recent |

### 2. Install dependencies

```bash
poetry install
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your OpenStack credentials and a strong API_KEY
```

### 4. Run locally

```bash
poetry run uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.  
Click **Authorize** and enter your `API_KEY` to authenticate all requests.

### 5. Run with Docker

```bash
docker compose up --build
```

---

## API Reference

All endpoints live under `/api/v1/vms` and require the `X-API-Key` header.

| Method   | Path                              | Description                           |
| -------- | --------------------------------- | ------------------------------------- |
| `GET`    | `/api/v1/vms`                     | List VMs (filter by status, name)     |
| `POST`   | `/api/v1/vms`                     | Create a VM                           |
| `GET`    | `/api/v1/vms/{id}`                | Get VM details                        |
| `DELETE` | `/api/v1/vms/{id}`                | Delete a VM                           |
| `POST`   | `/api/v1/vms/{id}/start`          | Start a stopped VM                    |
| `POST`   | `/api/v1/vms/{id}/stop`           | Stop a running VM                     |
| `POST`   | `/api/v1/vms/{id}/reboot`         | Reboot (`?hard=true` for hard reboot) |
| `GET`    | `/health`                         | Liveness probe (no auth required)     |

### Example: Create a VM

```bash
curl -X POST http://localhost:8000/api/v1/vms \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web-server-01",
    "flavor_id": "m1.small",
    "image_id": "3a4d2c1b-0000-4000-8000-aabbccddeeff",
    "network_id": "public-net",
    "key_name": "my-keypair",
    "security_groups": ["default", "web"],
    "metadata": {"env": "prod"}
  }'
```

---

## Running Tests

```bash
poetry run pytest
```

Tests use `unittest.mock` to patch `OpenStackVMService` — no real OpenStack cluster is needed. Coverage is reported to the terminal automatically.

To run a specific file:

```bash
poetry run pytest tests/test_vms.py -v
```

---

## Project Structure

```
.
├── app/
│   ├── main.py               # FastAPI app, middleware, OpenAPI customisation
│   ├── config.py             # pydantic-settings — all config from env vars
│   ├── dependencies.py       # API key auth dependency
│   ├── exceptions.py         # Custom exceptions + FastAPI handlers
│   ├── models/
│   │   └── vm.py             # Pydantic request/response schemas
│   ├── routers/
│   │   └── vms.py            # All /vms endpoints
│   └── services/
│       └── openstack_service.py  # openstacksdk wrapper
├── tests/
│   ├── conftest.py           # Shared fixtures (mock service, TestClient)
│   ├── test_auth.py          # Authentication tests
│   └── test_vms.py           # Endpoint tests for all lifecycle operations
├── Dockerfile                # Multi-stage build (builder + runtime)
├── docker-compose.yml
├── pyproject.toml            # Poetry config, ruff, pytest
└── .env.example
```

---

## Architecture & Design Decisions

### Framework: FastAPI

FastAPI was chosen for its native async support, automatic OpenAPI generation, and tight Pydantic v2 integration. The combination eliminates entire categories of serialisation bugs and gives us interactive docs for free.

### Dependency Management: Poetry

Poetry provides deterministic installs (`poetry.lock`), clear separation of dev vs. production dependencies, and a single source of truth for project metadata.

### OpenStack Integration: openstacksdk

`openstacksdk` is the official Python SDK maintained by the OpenStack community. It normalises differences between OpenStack versions and handles token refresh internally. All SDK calls are **synchronous** and are dispatched via `asyncio.to_thread` at the router level, keeping the FastAPI event loop unblocked.

### Service Layer

`OpenStackVMService` is a stateless class that opens a fresh SDK connection per call. This sidesteps token-expiry issues common in long-running services. The class is the single integration point for OpenStack: the router never imports `openstack` directly, making the SDK swappable in tests and in future multi-cloud scenarios.

### Authentication

A simple `X-API-Key` header scheme was chosen as the minimal viable auth for a proof-of-concept. It is enforced as a FastAPI `Security` dependency so it appears correctly in the OpenAPI schema and can be tested via Swagger UI's Authorize button.

### Error Handling

Three custom exception classes (`VMNotFoundError`, `VMOperationError`, `OpenStackConnectionError`) map to HTTP 404, variable 4xx/5xx, and 503 respectively. Each has a registered FastAPI handler that returns a consistent JSON error envelope, keeping SDK internals out of API responses.

### Docker: Multi-Stage Build

The Dockerfile uses a builder stage to install Poetry + dependencies into a `.venv`, then copies only the venv and application source into the slim runtime image. This keeps the final image small (~120 MB) and free of build tooling.

---

## Configuration Reference

All configuration is read from environment variables (or `.env`).

| Variable                  | Default                    | Description                                        |
| ------------------------- | -------------------------- | -------------------------------------------------- |
| `API_KEY`                 | `changeme`                 | Secret key clients must send in `X-API-Key`        |
| `OS_AUTH_URL`             | `http://localhost:5000/v3` | Keystone endpoint                                  |
| `OS_IDENTITY_API_VERSION` | `3`                        | Keystone API version                               |
| `OS_USERNAME`             | `admin`                    | OpenStack username                                 |
| `OS_PASSWORD`             | `secret`                   | OpenStack password                                 |
| `OS_TENANT_NAME`          | `admin`                    | Project / tenant name                              |
| `OS_TENANT_ID`            | _(empty)_                  | Project UUID — takes precedence over name when set |
| `OS_USER_DOMAIN_NAME`     | `Default`                  | User domain                                        |
| `OS_PROJECT_DOMAIN_NAME`  | `Default`                  | Project domain                                     |
| `OS_REGION_NAME`          | `RegionOne`                | Nova / compute region                              |
| `APP_TITLE`               | `OpenStack VM Manager`     | API title shown in Swagger UI                      |
| `APP_VERSION`             | `0.1.0`                    | API version shown in Swagger UI                    |
| `DEBUG`                   | `false`                    | Enable debug logging                               |
