# Architecture

APIx is a two-service application connected by a documented JSON API. It is
built to be **deterministic, auditable and reproducible** in an offline demo,
while leaving a clean seam for real collection adapters.

## High-level flow

```
   Source
     ↓
  Collection        (adapters: search() + health_check())
     ↓
  Raw storage       (raw_payload_reference → provenance)
     ↓
  Normalization     (source structures → canonical fare model)
     ↓
  Quality engine    (VALID/SUSPICIOUS/DUPLICATE/INVALID/SOLD_OUT/STALE)
     ↓
  PostgreSQL        (canonical observations — in this demo, an in-memory store)
     ↓
  Index engine      (route price → route index → weighted APIx)
     ↓
  FastAPI           (typed Pydantic responses)
     ↓
  React dashboard   (Overview · Index · Routes · Airlines · Lead Time · Import · Methodology · API)
```

## Services

### `backend/` — FastAPI

- **`app/dataset.py`** — deterministic synthetic dataset generator. Builds a
  realistic 90-day window of canonical fare observations for 24 Indian routes,
  6 airlines and 5 active sources. The exact same dataset is produced on every
  run (seeded hashing). It mirrors the shape of real collection output so a real
  scraper can be swapped in.
- **`app/engine.py`** — the index / analytics engine. All aggregate views
  (overview KPIs, trend, route indices, airline analysis, lead-time elasticity,
  quality, collection runs, provenance, backtest stats) are derived here from
  the observation store.
- **`app/schemas.py`** — strongly typed Pydantic response models. Database /
  session objects are never exposed directly.
- **`app/routers/api.py`** — the REST endpoints.
- **`app/config.py`** — environment-driven settings (`APIX_*`).
- **`tests/`** — pytest suite for the engine and API contract.

> The demo uses an in-memory observation store. The engine is written against a
> simple object interface, so moving to PostgreSQL only requires implementing a
> store that returns the same shapes (see [Deployment](DEPLOYMENT.md)).

### `frontend/` — React SPA

- **`src/lib/api.ts`** — typed API client (always `/api`, no hard-coded origins).
- **`src/lib/types.ts`** — TS mirrors of the Pydantic models.
- **`src/hooks/useApi.ts`** — React Query wrappers (central query logic).
- **`src/hooks/useFilters.tsx`** — global filter state synced to the URL.
- **`src/components/`** — reusable shell, KPI cards, badges, data-state
  boundaries, chart cards, sparklines and the route heatmap.
- **`src/pages/`** — one screen per dashboard view.

Vite dev-server proxies `/api` → backend. In Docker, Nginx proxies `/api` and
`/docs` → the `backend` service and serves the static build with client-side
routing fallback.

On **Vercel**, the whole app ships as a single serverless function. `api/index.py`
re-exports the FastAPI `app`; Vercel's Python runtime runs it natively. The same
function serves `/api/*`, `/docs`, and the built SPA (with deep-link fallback),
and `/assets/*` is promoted to the CDN. See
[Deployment](DEPLOYMENT.md#option-a--vercel-recommended-for-a-public-demo).

## Key design decisions

- **One source of truth.** Every dashboard visualisation is backed by a real
  API endpoint; there are no hard-coded dashboard values.
- **No black-box math.** The index formula, methodology version and weight
  version are returned in every relevant response and explained on the
  Methodology page.
- **Provenance everywhere.** Each index value can be traced to route
  contributions, route-day prices, canonical observations, source and raw
  payload reference.
- **Uncertainty is shown.** The quality score, dismissed/suspicious counts and
  a drill-down are part of the UI, not an afterthought.
- **Compliance by design.** Collection adapters respect robots/rate limits; if a
  source blocks automated collection the adapter enters `STOP_AND_BACKOFF`. No
  CAPTCHA/auth/anti-bot circumvention is implemented.

## Data states

Every component handles loading, empty, error, partial and stale/demo states via
a shared `DataBoundary` component with helpful, non-blank messages.
