# API Reference

Health check and the data API are documented automatically at `/docs`
(OpenAPI/Swagger). This page summarizes the contract for an external statistical
consumer.

## Conventions

- **Base path:** `/api`
- **Base URL (dev):** `http://localhost:8000/api`
- **Content type:** `application/json`
- **Auth:** none (demo build). Production should be gated.
- **Naming:** route parameters are uppercase IATA codes (e.g. `DEL-BOM`).
- **Versions:** every index-bearing response includes `methodology_version` and
  `weight_version` so the calculation can be reproduced.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness, version, demo mode, uptime, data window, collection-store health. Never fails because the scraper's storage is misconfigured. |
| `GET` | `/overview` | Headline KPI envelope (APIx, 24h/7d/30d movement, coverage). |
| `GET` | `/index` | Current index (same envelope as overview). |
| `GET` | `/index/trend?range=` | Time-series of APIx. `range` ∈ `7d \| 30d \| 90d \| 6m \| 1y`. |
| `GET` | `/index/route/{route}` | Route-level index, series, base, weight, airlines. |
| `GET` | `/index/airline/{airline}` | Airline index contribution. |
| `GET` | `/index/lead-time` | Lead-time elasticity. Filters: `route`, `airline`, `source`. |
| `GET` | `/routes` | All routes by 7-day movement (with sparklines). Optional `top`. |
| `GET` | `/routes/heatmap` | Same route data for the heatmap. |
| `GET` | `/airlines` | Airline comparison. Optional `route`. |
| `GET` | `/fares` | Recent canonical observations. Filters: `route`, `airline`, `limit`. |
| `GET` | `/fares/distribution` | Fare percentiles + histogram. Optional `route`. |
| `GET` | `/quality` | Quality score, breakdown, status counts. |
| `GET` | `/quality/rejected` | Rejected/suspicious observations for audit. |
| `GET` | `/collection-runs` | Per-source health and compliance. |
| `GET` | `/methodology` | Framework, formula and definitions. |
| `GET` | `/provenance/{index_id}` | Trace an index value to route contributions. |
| `GET` | `/stats/overview` | Validation / backtest summary. |
| `GET` | `/data/files` | Provenance for imported data: every file in the data directory, rows in/observations/rejects, which of your columns mapped to which canonical field, unmapped columns, warnings and errors. |
| `POST` | `/data/reload` | Rescan the data directory now (the loader normally notices changed files on its own). Returns the same report. |

### Collection engine (scraper)

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/data-source` | Which dataset the dashboard is served from (`live` scraped / `demo`), store counts + health, `request_scoped_sweeps`, registered sources. |
| `POST` | `/data-source` | `{"mode":"live"\|"demo"}` — flips the source for **every** screen; persisted so it survives a restart. Switching to `live` with an empty store collects once before answering (awaited when no background loop survives). `409` if `APIX_DATA_MODE` pins it; `503` if nothing can be persisted. |
| `GET` | `/collect/status` | Engine state: mode, scheduler, per-source health, circuit breaker, politeness settings, store totals/health, in-request sweep sizing. |
| `POST` | `/collect/sweep` | Run a collection sweep. Body: `sources`, `routes`, `lead_times`, `wait`. Returns the finished sweep (`synchronous: true`) when `wait` is set **or** when the runtime has no surviving background loop; otherwise `{"accepted": true}`. `409` when no adapter is enabled. |
| `GET` | `/collect/runs` | Run log — `success` / `partial` / `blocked` / `failed`, per-run query, request, observation and failure counts. |
| `GET` | `/collect/payloads` | **Raw responses exactly as collected** (verbatim JSON body, URL, HTTP status, latency, query). |
| `GET` | `/collect/fares` | Normalized canonical observations with quality status and exclusion reason. |
| `GET` | `/collect/sources` | Registered adapters and their compliance state. |
| `POST` | `/collect/sources/{id}/test` | Probe a source: reachable, authorized, and how long it took. |
| `GET` | `/collect/policy` | Sent headers, the enforced politeness values, and the explicit blocklist of non-implemented evasion techniques. |
| `DELETE` | `/collect/store?confirm=true` | Wipe all collected data (guarded). |

`GET /api/overview`, `/api/index/*`, `/api/routes`, `/api/airlines`,
`/api/quality` and `/api/collection-runs` are **mode-aware**: they serve the
live, custom or demo dataset (in that order of precedence) and every response
carries `data_origin` — `live`, `custom` or `demo` — so a consumer can tell which
it is looking at.

## Example response

`GET /api/index/trend?range=30d`

```json
{
  "range": "30d",
  "base_period": { "start": "2026-06-09", "end": "2026-06-15" },
  "current": 114.97,
  "change_7d": 1.37,
  "change_30d": null,
  "methodology_version": "apix-1.0.0",
  "series": [
    { "date": "2026-08-08", "apix": 110.3, "observations": 1180, "routes": 24, "change": 0.5 },
    "..."
  ]
}
```

## Error states

Errors return a safe, human-readable message rather than a bare 500. Example:

```json
{ "detail": "Route index unavailable — no valid observations for DEL-BOM." }
```

Storage problems are reported, not crashed on:

| Status | When | Body |
| --- | --- | --- |
| `503` | The collection store is unavailable (invalid `DATABASE_URL` when enabled, unwritable data dir) or the configured PostgreSQL cannot be reached. | `{"detail": "Collection store unavailable: …", "store_error": true}` |
| `200` | Same conditions, on a *read* endpoint: the store degrades to empty and says why. | `store.available: false`, `store.unavailable_reason`, `store.note` |
| `409` | No collection adapter is enabled (`APIX_COLLECTOR_SOURCES`). | `{"detail": "No collection adapter is enabled. …"}` |

Every store description carries `backend` (`sqlite` / `postgresql` /
`unavailable`), `durable`, `ephemeral`, `ignores_database_url` and a human-readable
`note`, so a consumer can tell a durable collection history from a per-instance
serverless one. Vercel defaults to `ignores_database_url: true`: the SQLite demo
works even if `DATABASE_URL` is malformed or unreachable. Set
`APIX_IGNORE_DATABASE_URL=0` to opt in to PostgreSQL; only then do database URL
validation/connection failures apply. The note never includes the URL or credentials.

Full parameter and schema documentation is available in the OpenAPI schema at
`/openapi.json` and the interactive `/docs`.
