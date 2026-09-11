# Deployment

## Option A — Vercel (recommended for a public demo)

APIx deploys to Vercel as a **single serverless function** that serves both the
FastAPI backend and the built React SPA from one origin. Vercel's Python/FastAPI
runtime runs the ASGI app natively (no `uvicorn`, no Mangum wrapper needed) and
promotes the `frontend/dist` assets to the CDN.

The collection engine works there too — see
[Collection engine (persistence matters)](#collection-engine-persistence-matters)
for how sweeps run inside a request and where the store lives.

### Files that make Vercel work

| File | Purpose |
| --- | --- |
| `api/index.py` | Vercel entrypoint — re-exports the FastAPI `app` from `backend/app`. |
| `vercel.json` | `installCommand` + `buildCommand` build `frontend/dist`; function `maxDuration: 60` so an in-request sweep can finish. |
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

The collector writes to `APIX_DATA_DIR` (default `backend/data/`, and
`/tmp/apix-data` automatically on a serverless runtime). Three deployment
consequences are worth knowing before a demo:

- **Serverless filesystems are read-only except `/tmp`, and `/tmp` is
  per-instance.** The store detects a hosted runtime (`VERCEL`, `VERCEL_ENV`,
  `AWS_LAMBDA_FUNCTION_NAME`, …) and uses SQLite under `/tmp/apix-data` when no
  database is configured; it is labelled *ephemeral* in every API response.
  The bundled `/var/task/data` directory remains readable for sample files, but
  browser uploads are staged in `/tmp/apix-data/imports` so they never fail with
  `Errno 30`. A configured `DATABASE_URL` is honoured on Vercel and selects the
  durable PostgreSQL store (Neon/Supabase). The same three tables
  (`collection_runs`, `raw_payloads`, `observations`) are created there, and the
  store reports `durable: true`. Set `APIX_IGNORE_DATABASE_URL=1` only to force
  the temporary SQLite demo despite a configured URL.
- **Storage problems degrade the scraper, never the dashboard.** If no database
  can be used at all (an invalid `DATABASE_URL` when explicitly enabled, or an
  unwritable SQLite path), the store
  switches to an explicitly *unavailable* state: reads answer empty, writes are
  no-ops, `/api/health` still returns `200` with `store_available: false`, the
  collection endpoints explain themselves, and `POST /api/data-source` with
  `{"mode":"live"}` returns `503` with the reason instead of an opaque `500`. A
  valid-but-unreachable PostgreSQL, when enabled, is a `503` on the scraper's own
  endpoints only — an opted-in durable database never silently falls back to SQLite.
- **The toggle is server state, not browser state.** If a reproducible demo number
  matters, pin it with `APIX_DATA_MODE=demo`; otherwise a live mode left on by an
  earlier run will serve a thin, correctly-labelled-but-different index.

When `APIX_IGNORE_DATABASE_URL=1`, the URL is ignored **before** validation or
connection, which is useful for an intentionally offline temporary-store demo.
Otherwise a configured URL is validated and used on every platform. The API
reports `store.ignores_database_url` and a safe explanatory note (never the
connection string). Existing PostgreSQL data is left untouched; switching
backends does not migrate collection history.

### "I set `DATABASE_URL` and it still is not working"

Start with the one endpoint that says the truth — it never returns the
connection string, only what the backend decided and why:

```bash
curl https://<your-app>/api/data/database
```

`backend`, `available`, `reason` and `note` identify every case below. The known
ones, in the order they are worth checking:

| What you see | Cause | Fix |
| --- | --- | --- |
| `backend: "sqlite"`, `ephemeral: true` | `DATABASE_URL` is not set *in the environment the function runs in*. On Vercel an env var added after a deployment only applies to the **next** deployment. | Set it under Project → Settings → Environment Variables for Production (and Preview), then redeploy. |
| `note: "DATABASE_URL is ignored…"` | `APIX_IGNORE_DATABASE_URL=1` is set. | Remove it (or set `0`) and redeploy. |
| `reason: …unreadable port…` / `…truncated…` | The password contains `@`, `:`, `/`, `#` pasted raw, which ends the URL early. | Percent-encode the password (`@`→`%40`, `:`→`%3A`, `/`→`%2F`). Copy the provider's *URI* string and change only the password. |
| `note: "Ignored unsupported DATABASE_URL parameter(s): pgbouncer"` | Supabase's pooler URL ends with `?pgbouncer=true&connect_timeout=15`. `libpq` rejects parameters it does not know, so this used to disable the store outright; the hint is now dropped and reported. | Nothing to do — but the session/direct (port 5432) URL is preferable for a serverless backend. |
| `reason: …could not be reached…` | Host/port unreachable, project paused, or the password is wrong. The message now carries the driver's own detail (credentials redacted). Transient failures are retried every `APIX_DB_RETRY_SECONDS` (default 15) instead of disabling the store for the process lifetime. | Check the host resolves from the platform, the project is active, and `sslmode=require` is accepted. |
| `available: true` but the dashboard is empty in live mode | The rows are in the database but excluded from the index — see `counts.by_status`. Rows flagged `DUPLICATE`/`INVALID` never enter an index. | Check the import report; re-upload a corrected file (an upload of data that already exists is now stored as the canonical rows, not as duplicate-flagged twins). |
| Inserts fail with `new row violates row-level security policy`, or reads return 0 rows | RLS is on and the policy does not name the role the backend logs in as. Supabase connection strings use `postgres.<project-ref>`, not `postgres`. | Re-run `db/supabase_schema.sql`; it creates one policy per backend role (`postgres` and any `postgres.*`), leaving `anon`/`authenticated` blocked. |

Two details that make failures easy to misread:

- `POST /api/data/upload` returns **200 even when persistence fails** — the file
  is safely on disk and still serves the dashboard. Read `persistence.error` in
  the response (the Import screen shows it) rather than the status code.
- `psycopg2-binary` must be installed in the deployment (`api/requirements.txt`
  and `backend/requirements.txt` both pin it). Without it a valid
  `DATABASE_URL` is refused with an explicit configuration error.

### Sweeps on a request-scoped runtime

A background `asyncio` loop does not survive between invocations on Vercel — the
process is frozen the moment a response is returned, so a "sweep queued, poll
later" answer would never produce any data. The collector therefore detects that
it has no surviving loop and runs the sweep **inside the request**:

- `POST /api/collect/sweep` returns the finished sweep (`synchronous: true`)
  instead of `{"accepted": true}`;
- `POST /api/data-source {"mode":"live"}` awaits the first sweep, so the toggle
  lands on real observations in one round trip;
- the dashboard's **Collect now** / **Run sweep now** buttons await the result and
  refresh every screen when it lands.

So that a polite sweep cannot outrun the platform's function timeout
(`maxDuration: 60` in `vercel.json`), an in-request sweep is sized to
`APIX_REQUEST_SWEEP_BUDGET_SECONDS` ÷ the source's politeness gap, and the queries
it drops are chosen round-robin so *every* basket route stays in scope. The
response says when this happened (`note`), and `/api/collect/status` reports
`request_scoped_sweeps` and `request_sweep_query_cap`. Offline captures make no
network call and pay no gap, so they are never truncated — the full 24-route ×
3-lead-time basket lands in tens of milliseconds.

For continuous collection on a hosted deployment, point an external scheduler
(Vercel Cron, a GitHub Action) at `POST /api/collect/sweep` — the same code path
the internal loop uses — or run the backend somewhere with a real process
lifetime (Docker, a VM) and leave `APIX_COLLECTOR_ENABLED=1`.

## Environment variables

Backend (prefix `APIX_`):

- `APIX_DEMO_MODE` — default `1`. `0` switches the demo generator off for a real
  data path (not yet implemented).
- `APIX_DEMO_DAYS` — default `90`. Number of days the deterministic dataset spans.
- `APIX_DATA_DIR` — where the SQLite store lives. Defaults to `backend/data/`
  locally and `/tmp/apix-data` on a serverless runtime.
- `APIX_CUSTOM_DATA_DIR` — operator-managed directory scanned for fare files
  (CSV/JSON/JSONL). Defaults to `<repo>/data`. Any usable file there replaces the
  synthetic demo dataset; see `docs/CUSTOM_DATA.md`. On Vercel it may remain a
  bundled, read-only path; browser uploads are automatically staged separately.
- `APIX_UPLOAD_DATA_DIR` — writable landing directory for browser uploads. When
  omitted, local writable custom-data directories are reused; Vercel defaults to
  `/tmp/apix-data/imports`. Point this to a mounted shared volume on a VM/container
  if uploaded files themselves must survive restarts.
- `APIX_CUSTOM_DATA` — default `1`. `0` disables custom-data loading.
- Uploaded/imported rows are upserted into the same `observations` table the
  collector uses, matched on `observation_id` (see `docs/CUSTOM_DATA.md`). Set
  `DATABASE_URL` for that to be Supabase; it is honoured on Vercel unless
  `APIX_IGNORE_DATABASE_URL=1`. The Import screen also exposes **Push demo data**
  (`POST /api/data/persist-demo`) for an idempotent database seed.
- `APIX_DATA_MODE` — `demo` pins the dashboard to the synthetic dataset (custom
  files are ignored), `live` pins it to scraped data.
- `APIX_IGNORE_DATABASE_URL` — default `0` on every platform. `1` / `true` /
  `yes` / `on` intentionally select SQLite without reading or connecting to
  `DATABASE_URL`; `0` / `false` / `no` / `off` (or unset) honour the PostgreSQL
  setting when a URL is provided.
- `DATABASE_URL` — PostgreSQL URL or keyword DSN (on Supabase use the
  **Transaction pooler** URI, port 6543, with `?sslmode=require`). Used only when
  `APIX_IGNORE_DATABASE_URL` is off. In that mode an invalid value is refused
  rather than silently downgraded to SQLite; unset/blank still selects SQLite.
  Schema: [`db/supabase_schema.sql`](../db/supabase_schema.sql).
- `APIX_COLLECTOR_ENABLED` — default `1` locally, `0` on a serverless runtime
  (there is no process to keep a loop alive).
- `APIX_COLLECTOR_SOURCES` — default `fixture` (offline capture). Also
  `fixture_html`, `amadeus`, `http_json`, `http_html`.
- `APIX_REQUEST_SWEEP_BUDGET_SECONDS` — default `45`. Wall-clock budget for a
  sweep that has to finish inside one request; keep it under `maxDuration`.
- `APIX_DB_CONNECT_TIMEOUT_SECONDS` — default `5`.
- `APIX_DATA_MODE` — pin the dashboard to `demo` or `live` (the toggle then reports
  itself locked).

Frontend:

- `VITE_API_TARGET` — dev proxy target (default `http://localhost:8000`).

## Moving to PostgreSQL

The store already speaks PostgreSQL: set `DATABASE_URL` (managed Neon or
Supabase works well with Vercel), ensure `APIX_IGNORE_DATABASE_URL` is unset or
`0`, then redeploy.
The same three tables are created there, with the
SQLite date/idiom differences translated in one place (`Store._connect`).
`GET /api/collect/status` then reports `store.durable: true` and the ephemeral
warning disappears from the dashboard.

[`db/supabase_schema.sql`](../db/supabase_schema.sql) is the whole schema in one
idempotent file — paste it into the Supabase **SQL Editor** and press *Run*. It
creates the five tables, the indexes the analytical queries use, table/column
comments, and enables row-level security with a single policy for the `postgres`
role the backend connects as (so the tables are not reachable through Supabase's
public REST API with an anonymous key). The backend can also bootstrap the tables
itself on first boot; running the file first is simply the explicit, reviewed
path, and the two agree. Full click-through instructions, the exact Vercel
environment variables and a message-by-message troubleshooting table:
[Setup guide](SETUP_GUIDE.md).

Verified against a real PostgreSQL by `backend/tests/test_postgres_store.py`
(opt-in: set `APIX_TEST_DATABASE_URL` to a scratch database and it applies that
same schema file, then round-trips state, runs, raw payloads, observations,
duplicate handling, the date-window queries and reset).

If you outgrow that thin wrapper:

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
