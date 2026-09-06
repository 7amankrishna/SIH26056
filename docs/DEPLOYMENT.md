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
  per-instance and per-deploy. For durable storage move the same three tables
  (`collection_runs`, `raw_payloads`, `observations`) to Postgres — the store is a
  thin wrapper, so this is one module.
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

The engine is written against a simple observation-store interface so a
PostgreSQL-backed store can be swapped in. Use a managed Postgres (e.g. Neon or
Supabase) since Vercel Functions have no persistent local filesystem. The
migration path:

1. Add SQLAlchemy models matching [Data Dictionary](DATA_DICTIONARY.md).
2. Implement store functions returning the same shapes the engine expects.
3. Add indexes on `collection_timestamp`, `route`, `departure_date`, `source`,
   `airline`, `lead_time_days`.
4. Store raw payloads as JSONB, never loaded in analytical queries.

## Production notes

- No secrets are committed. `.env` files and credentials are git-ignored.
- The API is intentionally unauthenticated in the demo build; production should
  gate `/api/*` behind an auth/reverse-proxy layer and lock CORS to trusted
  origins.
