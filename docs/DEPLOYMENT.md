# Deployment

## Option A — Vercel (recommended for a public demo)

APIx deploys to Vercel as a **single serverless function** that serves both the
FastAPI backend and the built React SPA from one origin. Vercel's Python/FastAPI
runtime runs the ASGI app natively (no `uvicorn`, no Mangum wrapper needed) and
promotes the `frontend/dist` assets to the CDN.

### Files that make Vercel work

| File | Purpose |
| --- | --- |
| `api/index.py` | Vercel entrypoint — re-exports the FastAPI `app` from `backend/app`. |
| `pyproject.toml` | `[tool.vercel] entrypoint = "api.index:app"` — removes discovery ambiguity. |
| `vercel.json` | `installCommand` + `buildCommand` build `frontend/dist`; function `maxDuration: 10`. |
| `requirements.txt` (root) | Python runtime dependencies for the function. |

### How the single function serves everything

- `/api/*` → the FastAPI router (backend).
- `/docs`, `/redoc`, `/openapi.json` → FastAPI's documentation.
- `/`, `/routes`, any SPA route → the built `frontend/dist/index.html` (deep-link
  fallback), with `/assets/*` served via a StaticFiles mount promoted to the CDN.
- Unknown `/api/*` paths → `404` (never shadowed by the SPA fallback).

### Deploy

1. Push the repo to GitHub.
2. In Vercel: **New Project → Import** the repo. Vercel auto-detects Python/FastAPI
   via `api/index.py` + root `requirements.txt`, uses the `vercel.json`
   build/install commands, and deploys.
3. The dashboard and the API are at the same URL. OpenAPI docs at `/docs`.

> **Optional:** set `APIX_DEMO_DAYS` and `APIX_DEMO_MODE` as Vercel environment
> variables (Project → Settings → Environment Variables) to change the demo
> window. They default to `90` and `1`.

### Local preview of the Vercel function

```bash
cd frontend && npm install && npm run build   # produce frontend/dist
cd .. && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # from backend/
```

or, to exercise the exact Vercel entrypoint:

```bash
python -c "import sys; sys.path.insert(0,'api'); import index; import uvicorn; uvicorn.run(index.app, host='0.0.0.0', port=8000)"
```

Then open `http://localhost:8000/` — the same single origin serves the SPA, the
API (`/api/*`) and `/docs`.

---

## Option B — Docker Compose (offline demo)

```bash
docker compose up --build
```

Two services:

| Service | Build | Exposed |
| --- | --- | --- |
| `backend` | `backend/Dockerfile` → `python:3.11-slim` + uvicorn | `0.0.0.0:8000` |
| `frontend` | `frontend/Dockerfile` → Node build → Nginx static | `0.0.0.0:8080` |

- Dashboard: <http://localhost:8080>
- API root: <http://localhost:8000/api/overview>
- OpenAPI docs: <http://localhost:8000/docs>

Nginx serves the frontend build, falls back to `index.html` for client-side
routing, and proxies `/api`, `/docs` and `/openapi.json` to the `backend`
service. This is the fully-offline option for a jury room with no internet.

---

## Development (no Docker, no Vercel)

Backend:

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://localhost:5173` and proxies `/api` to the backend at
`http://localhost:8000` by default. Override with `VITE_API_TARGET`.

---

## Collection engine (persistence matters)

The collector writes to `APIX_DATA_DIR` (default `backend/data/`). Two deployment
consequences are worth knowing before a demo:

- **Serverless filesystems are ephemeral and usually read-only.** On Vercel, set
  `APIX_DATA_DIR=/tmp/apix-data` so SQLite can write, and treat collected data as
  per-instance and per-deploy (if the configured directory is read-only the store
  falls back to `/tmp/apix-data` on its own and logs that it did). For durable
  storage set `DATABASE_URL` to a managed Postgres — see
  [Moving to PostgreSQL](#moving-to-postgresql).
- **The store initialises lazily.** Nothing touches the database at import time:
  the first request that needs it creates the schema. A bad `DATABASE_URL` (the
  classic slip is pasting the repo's GitHub URL) therefore no longer crashes the
  function — `/api/health`, the docs and the demo dataset keep working, and the
  routes that need the store answer `503 {"error": "database_misconfigured"}`
  with a message that says exactly what to fix.
- **The toggle is server state, not browser state.** If a reproducible demo number
  matters, pin it with `APIX_DATA_MODE=demo`; otherwise a live mode left on by an
  earlier run will serve a thin, correctly-labelled-but-different index.
- **A background loop does not suit a request-scoped runtime.** On Vercel, set
  `APIX_COLLECTOR_ENABLED=0` and trigger sweeps from an external scheduler
  (cron/GitHub Action) with `POST /api/collect/sweep`; the endpoint is the same
  code path as the internal loop.

## Environment variables

Backend (prefix `APIX_`):

- `APIX_DEMO_MODE` — default `1`. `0` switches the demo generator off for a real
  data path (not yet implemented).
- `APIX_DEMO_DAYS` — default `90`. Number of days the deterministic dataset spans.

Frontend:

- `VITE_API_TARGET` — dev proxy target (default `http://localhost:8000`).

## Moving to PostgreSQL

The store (`backend/app/collect/store.py`) speaks SQLite by default and Postgres
when `DATABASE_URL` is set — same tables, same code path. Use a managed Postgres
(e.g. Neon or Supabase) since Vercel Functions have no persistent local
filesystem.

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

Rules of the road:

- The value must be a PostgreSQL DSN (`postgresql://…`, `postgres://…` or libpq
  `host=… dbname=…` form). Anything else — a GitHub URL, a MySQL/SQLite URL, an
  empty scheme — is rejected with a clear `RuntimeError` **before** it reaches
  `psycopg2`; on Vercel a host is mandatory.
- The driver is `psycopg2-binary==2.9.10`, pinned in both `api/requirements.txt`
  (what Vercel installs) and `backend/requirements.txt` (Docker / local).
- Connections use a `connect_timeout` of 10 s unless the DSN sets its own
  (override with `APIX_PG_CONNECT_TIMEOUT_SECONDS`), so an unreachable database
  fails fast instead of hanging a request until the function times out.
- Unset `DATABASE_URL` to fall back to SQLite.

## Production notes

- No secrets are committed. `.env` files and credentials are git-ignored.
- The API is intentionally unauthenticated in the demo build; production should
  gate `/api/*` behind an auth/reverse-proxy layer and lock CORS to trusted
  origins.
