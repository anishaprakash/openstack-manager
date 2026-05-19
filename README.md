# OpenStack VM Manager

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

| Tool | Version |
|------|---------|
| Python | ≥ 3.11 |
| Poetry | ≥ 1.8 |
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

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/vms` | List VMs (filter by status, name) |
| `POST` | `/api/v1/vms` | Create a VM |
| `GET` | `/api/v1/vms/{id}` | Get VM details |
| `DELETE` | `/api/v1/vms/{id}` | Delete a VM |
| `POST` | `/api/v1/vms/{id}/start` | Start a stopped VM |
| `POST` | `/api/v1/vms/{id}/stop` | Stop a running VM |
| `POST` | `/api/v1/vms/{id}/reboot` | Reboot (`?hard=true` for hard reboot) |
| `POST` | `/api/v1/vms/{id}/resize` | Resize to a new flavor |
| `POST` | `/api/v1/vms/{id}/resize/confirm` | Confirm pending resize |
| `POST` | `/api/v1/vms/{id}/resize/revert` | Revert pending resize |
| `POST` | `/api/v1/vms/{id}/snapshot` | Create a Glance image snapshot |
| `GET` | `/health` | Liveness probe (no auth required) |

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

### Example: Snapshot a VM

```bash
curl -X POST http://localhost:8000/api/v1/vms/<vm-id>/snapshot \
  -H "X-API-Key: changeme" \
  -H "Content-Type: application/json" \
  -d '{"snapshot_name": "web-server-01-snap-2024"}'
```

---

## Running Tests

```bash
poetry run pytest
```

Tests use `unittest.mock` to patch `OpenStackVMService` — no real OpenStack cluster is needed.  Coverage is reported to the terminal automatically.

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

FastAPI was chosen for its native async support, automatic OpenAPI generation, and tight Pydantic v2 integration.  The combination eliminates entire categories of serialisation bugs and gives us interactive docs for free.

### Dependency Management: Poetry

Poetry provides deterministic installs (`poetry.lock`), clear separation of dev vs. production dependencies, and a single source of truth for project metadata.

### OpenStack Integration: openstacksdk

`openstacksdk` is the official Python SDK maintained by the OpenStack community.  It normalises differences between OpenStack versions and handles token refresh internally.  All SDK calls are **synchronous** and are dispatched via `asyncio.to_thread` at the router level, keeping the FastAPI event loop unblocked.

### Service Layer

`OpenStackVMService` is a stateless class that opens a fresh SDK connection per call.  This sidesteps token-expiry issues common in long-running services.  The class is the single integration point for OpenStack: the router never imports `openstack` directly, making the SDK swappable in tests and in future multi-cloud scenarios.

### Authentication

A simple `X-API-Key` header scheme was chosen as the minimal viable auth for a proof-of-concept.  It is enforced as a FastAPI `Security` dependency so it appears correctly in the OpenAPI schema and can be tested via Swagger UI's Authorize button.

### Error Handling

Three custom exception classes (`VMNotFoundError`, `VMOperationError`, `OpenStackConnectionError`) map to HTTP 404, variable 4xx/5xx, and 503 respectively.  Each has a registered FastAPI handler that returns a consistent JSON error envelope, keeping SDK internals out of API responses.

### Docker: Multi-Stage Build

The Dockerfile uses a builder stage to install Poetry + dependencies into a `.venv`, then copies only the venv and application source into the slim runtime image.  This keeps the final image small (~120 MB) and free of build tooling.

---

## Configuration Reference

All configuration is read from environment variables (or `.env`).

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `changeme` | Secret key clients must send in `X-API-Key` |
| `OS_AUTH_URL` | `http://localhost:5000/v3` | Keystone endpoint |
| `OS_USERNAME` | `admin` | OpenStack username |
| `OS_PASSWORD` | `secret` | OpenStack password |
| `OS_PROJECT_NAME` | `admin` | Project / tenant name |
| `OS_USER_DOMAIN_NAME` | `Default` | User domain |
| `OS_PROJECT_DOMAIN_NAME` | `Default` | Project domain |
| `OS_REGION_NAME` | `RegionOne` | Nova region |
| `DEBUG` | `false` | Enable debug logging |

---

## Roadmap / Backlog

Items below are scoped beyond the initial timebox but represent the natural next steps for a production service.

### Short Term (next sprint)
- **Token caching** — reuse SDK connections across requests within a TTL window to reduce auth round-trips
- **Pagination cursors** — replace `limit`-only pagination with OpenStack marker-based cursors for large fleets
- **`GET /vms/{id}/console`** — return a noVNC / SPICE console URL
- **Floating IP management** — attach/detach public IPs as a sub-resource (`/vms/{id}/floating-ips`)
- **Prometheus `/metrics` endpoint** — expose request latency, error rate, and VM counts via `prometheus-fastapi-instrumentator`

### Medium Term
- **JWT / OAuth2 authentication** — replace API key with short-lived tokens (Keycloak or Dex)
- **Multi-cloud adapter pattern** — introduce a `BaseVMService` interface so AWS EC2 or GCP Compute Engine backends can be plugged in alongside OpenStack
- **Background task queue** — use Celery + Redis to track long-running operations (resize, snapshot) and expose a `GET /tasks/{task_id}` status endpoint
- **Rate limiting** — per-key request throttling via `slowapi`
- **Audit log** — append-only log of every mutation with actor, timestamp, and before/after state

### Long Term
- **Kubernetes operator** — expose VM management as a Kubernetes CRD so platform teams can manage VMs declaratively alongside their workloads
- **Terraform provider** — wrap the API as a Terraform provider for IaC adoption
- **WebSocket console streaming** — real-time serial console over WebSocket
- **Cost & quota dashboard** — aggregate flavor pricing and project quota utilisation
