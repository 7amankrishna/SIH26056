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
| `GET` | `/health` | Liveness, version, demo mode, uptime, data window. |
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

Full parameter and schema documentation is available in the OpenAPI schema at
`/openapi.json` and the interactive `/docs`.
