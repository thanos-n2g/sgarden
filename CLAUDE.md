# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SGarden is a FastAPI REST API for inventory/product management backed by MongoDB. The Python source lives entirely under `python/`.

## Build & Run Commands

All commands run from the `python/` directory:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (default port 4000, with auto-reload)
uvicorn main:app --host 0.0.0.0 --port 4000 --reload

# Or via the entry point
python main.py
```

Interactive API docs are available at `http://localhost:4000/docs` (Swagger UI).

## Testing

Tests live in `python/tests/` and use **pytest + pytest-asyncio + httpx**.

```bash
# Install test dependencies (one-time)
pip install -r requirements-test.txt

# Run all tests
python3 -m pytest tests/ -v
```

Tests run without a real MongoDB instance — `products_collection` is replaced by an in-memory mock that applies the same filter logic (`$or`, `$gte`/`$lte`, regex) that the route builds. The lifespan hooks (`init_indexes`, `seed_data`) are also patched out.

`pytest.ini` sets `asyncio_mode = auto` so async test functions and fixtures need no extra decorators.

## Environment Configuration

Copy `.env.sample` to `.env` at the repo root. The app reads these environment variables (with defaults):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `mongodb://localhost:27017/sgarden` | MongoDB connection URI |
| `PORT` | `4000` | HTTP server port |
| `SERVER_SECRET` | `sgarden-secret-key` | JWT signing secret |
| `JWT_EXPIRATION_HOURS` | `24` | Token validity in hours |

## Architecture

### Layer structure

```
routes/ → security/ → database.py → MongoDB
```

- **routes/**: `auth.py`, `products.py`, `users.py` — endpoint handlers; thin, delegate DB calls directly (no service layer yet)
- **security/jwt_handler.py**: JWT creation/validation; FastAPI dependencies `get_current_user()` and `get_optional_user()` for route protection
- **database.py**: Motor (`AsyncIOMotorClient`) connection, collection handles, and index initialization
- **models/**: Pydantic v2 schemas for request/response shapes; keep these as the single source of truth for data contracts
- **seed.py**: Seeds 2 test users and 15 products on startup (only if collections are empty)
- **config.py**: Pydantic Settings — all configuration loaded from environment here

### Startup sequence

`main.py` uses a lifespan context manager that runs `init_indexes()` then `seed_data()` before accepting requests.

### Authentication

Bearer JWT auth via HTTPBearer. Token payload contains `sub` (user_id), `username`, `role`. Public endpoints:

- `POST /api/auth/**`
- `GET /api/health`
- `GET /api/products/**`
- `/api/users/system/**`, `/api/users/hash`

### Data seeding test credentials

- `admin` / `admin123` (role: admin)
- `user` / `user1234` (role: user)

### API surface

| Prefix | Responsibility |
|---|---|
| `POST /api/auth/` | Register, login — returns JWT |
| `/api/products/` | CRUD, search, stats |
| `/api/users/` | User management |
| `GET /api/health` | Liveness check |
