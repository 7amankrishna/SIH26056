# APIx — Real-Time Airfare Price Index for India

> **SIH26056 · MoSPI — Data Informatics & Innovation Division (DIID)**
> High-frequency airfare intelligence for CPI augmentation.

APIx is an end-to-end platform that demonstrates how high-frequency online
airfare observations are **collected → cleaned → validated → indexed →
visualized → audited → exposed** through an API. It is built to be understood,
trusted and audited by a statistical reviewer (MoSPI / NSO / RBI) — not to look
like a generic admin panel.

**Observe → Validate → Normalize → Aggregate → Explain → Audit.** That is the
product.

---

## What works today (demo-ready)

The entire system runs **fully offline and deterministically** from a built-in
synthetic dataset generator, so you get a populated, realistic dashboard with
`docker compose up --build` — no live scraping required.

Alongside it, `backend/app/collect/` is a **working collection engine**: a
scheduled background loop that fetches from configured sources, parses and
normalizes responses into the canonical fare model, runs the quality gate, and
persists everything (including the payload bytes as received) to SQLite. Both
paths feed the same index layer, which is what lets the dashboard switch between
them with one toggle.

Collection sources are **authorized channels only** — a permissioned fare API
(Amadeus self-service), config-driven JSON/HTML fetchers for hosts whose terms
permit automation, and a bundled offline capture for demos. The engine implements
no CAPTCHA handling, no bot-detection evasion and no access-control
circumvention; see [Scraping / collection policy](docs/SCRAPING_POLICY.md), which
includes why a Google-Flights scrape is specifically out of scope and what to
point the same pipeline at instead.

| Layer | Status |
| --- | --- |
| Dashboard (React + TypeScript + Tailwind + Recharts) | ✅ polished, API-backed |
| REST API (FastAPI + Pydantic) | ✅ typed & documented |
| Index engine (route/airline/lead-time/aggregate APIx) | ✅ deterministic |
| Quality engine (VALID / SUSPICIOUS / DUPLICATE / INVALID / SOLD_OUT / STALE) | ✅ auditable |
| Deterministic demo dataset (24 routes · 6 airlines · 5 active sources · 90 days) | ✅ |
| Background collection engine (scheduled sweeps → normalize → quality gate → SQLite) | ✅ |
| In-request sweeps on serverless (Vercel) + ephemeral/durable store labelling | ✅ |
| **Demo ↔ Scraper toggle** on every screen (server-side, persisted) | ✅ |
| Raw-payload archive + "as collected" Live Feed screen | ✅ |
| Backtests / validation metrics | ✅ |
| Docker Compose | ✅ |

## Quick start

### Deploy to Vercel (recommended for a public demo)

APIx deploys to Vercel as a **single serverless function** that serves both the
FastAPI backend and the built React SPA from one origin. No `uvicorn`/Mangum
wrapper is required — Vercel runs the ASGI app natively.

1. Push the repo to GitHub.
2. In Vercel: **New Project → Import** the repo. Vercel auto-detects Python/FastAPI
   via `api/index.py` + root `requirements.txt`, uses the `vercel.json` commands
   to build `frontend/dist`, and deploys.
3. The dashboard and the API share one URL.

The scraper works on Vercel with no configuration at all (a clearly-labelled
temporary store under `/tmp`). To make collected history survive a cold start or
a redeploy, add one environment variable — `DATABASE_URL` — pointing at a free
Supabase PostgreSQL database, and paste
[`db/supabase_schema.sql`](db/supabase_schema.sql) into Supabase's SQL editor.
Step-by-step, without a terminal: [Setup guide](docs/SETUP_GUIDE.md).

Files that make this work: `api/index.py` (re-exports the FastAPI `app`),
`vercel.json` (install/build commands + function `maxDuration`), and root
`requirements.txt`.
See [Deployment](docs/DEPLOYMENT.md#option-a--vercel-recommended-for-a-public-demo).

The scraper works on Vercel as well: the runtime has no process lifetime for a
background loop, so the collector detects that and runs each sweep *inside* the
request that asks for it — flipping the dashboard to **Scraper** collects and
switches in one round trip. Without `DATABASE_URL` the store is SQLite under
`/tmp`, which the API and the Live Feed screen label **ephemeral** (per instance,
reset on cold start/redeploy); set `DATABASE_URL` to a managed PostgreSQL for
durable collection history. Storage that cannot be used at all degrades the
scraper only: `/api/health` still answers, and `POST /api/data-source` returns a
`503` that says why instead of an opaque `500`.

OpenAPI docs land at `/docs` on the deployed URL.

### Offline demo (Docker, jury room with no internet)

```bash
docker compose up --build
```

Then open:

- Dashboard: <http://localhost:8080>
- Backend API: <http://localhost:8000/api/overview>
- Interactive OpenAPI docs: <http://localhost:8000/docs>

### Development

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

The Vite dev server runs on `http://localhost:5173` and proxies `/api` to the
backend. The dashboard shows a **DEMO DATA** badge whenever synthetic data is
in use.

### Running the collection engine

```bash
cd backend
APIX_COLLECTOR_SOURCES=fixture_html \   # or: fixture (JSON capture), amadeus, http_html
APIX_MIN_REQUEST_GAP_SECONDS=0 \
.venv/bin/python -m uvicorn app.main:app --port 8000
```

On a serverless runtime (`VERCEL` set) the background loop is off by default and
`APIX_DATA_DIR` defaults to `/tmp/apix-data`, because no process survives between
requests: `POST /api/collect/sweep` then runs the sweep inside the request and
returns its result. See
[Deployment → Sweeps on a request-scoped runtime](docs/DEPLOYMENT.md#sweeps-on-a-request-scoped-runtime).

`fixture_html` is the one to show a jury: the collector fetches an HTML fare
**page** and extracts offers with CSS-ish selectors (`div.offer`, `span.price`,
`@data-offer-id`) through the same `HttpHtmlAdapter` used for real targets — so
the demo is genuinely *scraping*, not an API call, and it needs no credentials
and no network. `₹4,899.00` formatted amounts, blank price cells on sold-out
rows and attribute-carried ids are all parsed by the real code path.

Then flip the dashboard's **Scraper / Demo data** switch (top right), or drive it
from the CLI:

```bash
curl -X POST localhost:8000/api/collect/sweep -H 'content-type: application/json' \
     -d '{"wait": true, "routes": ["DEL-BOM"], "lead_times": [7, 30]}'
curl -X POST localhost:8000/api/data-source -d '{"mode":"live"}' -H 'content-type: application/json'
curl localhost:8000/api/overview | jq '{data_origin, current_apix, days_collected}'
```

### Checking a new source before you scrape it

```bash
cd backend && .venv/bin/python -m app.collect.preflight https://example.com/del-bom-fares
```

Prints the robots verdict for our user-agent, the `Crawl-delay` we would adopt,
the resulting requests/day for the configured sweep, and the questions a
`robots.txt` cannot answer (ToS clause, redistribution rights, personal data).
Same function as `GET /api/collect/preflight?url=…`. If it says denied, that is
the end of the conversation — the output lists what the engine will not do to
work around it.

The default `fixture` / `fixture_html` sources need no credentials and make no network calls, so
the whole live path — fetch → parse → normalize → quality → store → index → API —
is demonstrable in a room with no internet. Switch `APIX_COLLECTOR_SOURCES` to
`amadeus` (with `AMADEUS_CLIENT_ID`/`AMADEUS_CLIENT_SECRET`) to collect from a
permissioned API for real. Data lands in `backend/data/apix.sqlite3` (gitignored);
every sweep adds a collection day, and the index rebases against its own base
period as history accrues.

---

## Dashboard screens

1. **Overview** — executive KPIs (APIx, 24h/7d/30d movement, observations,
   coverage), the hero APIx trend chart, the India route heatmap, and the
   routes driving movement.
2. **Airfare Index** — headline trend, full route-index table, and a
   *"contribution to today's APIx"* drill-down.
3. **Routes** — route heatmap + movement table, with a per-route drill-down
   (route index series, base price, weight, airline composition).
4. **Airlines** — observed vs normalised fares, volatility, index contribution,
   availability and quality. Clearly disclaims that comparisons are *not*
   statistically controlled.
5. **Lead Time** — the advance-booking elasticity curve (T+1 → T+45) with an
   automatic insight ("Average observed fare is X% higher at T+1 than T+45").
6. **Data Quality** — overall quality score, breakdown (completeness,
   consistency, uniqueness, freshness, source coverage, outlier rate) and a
   drill-down into rejected / suspicious observations.
7. **Collection Monitor** — per-source health, success rate, latency, failures,
   circuit-breaker state and compliance. Disabled sources are never shown live.
8. **Methodology** — the 8-step framework, the actual formula, definitions and
   the *prototype* disclaimer.
9. **API / Data Access** — the documented, typed REST contract.
10. **Live Feed (Scraper)** — the collection engine's own screen: source health and
    circuit-breaker state, the run log including blocked runs, collected fares,
    raw payloads verbatim, and the enforced header/blocklist policy.

## Documentation

- [Setup guide — Vercel + Supabase, click-only](docs/SETUP_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Index methodology](docs/METHODOLOGY.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [Scraping / collection policy](docs/SCRAPING_POLICY.md)
- [Backtesting](docs/BACKTESTING.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Demo instructions](docs/DEMO.md)
- [API reference](docs/API.md)

## Testing

```bash
cd backend && . .venv/bin/activate && python -m pytest   # 68 tests incl. the collection engine
cd frontend && npm run typecheck && npm test && npm run build
```

## Honest limitations

APIx is a **prototype statistical methodology**, not an official CPI series.
See [Methodology](docs/METHODOLOGY.md) and the acknowledgment in the product for
a candid list: live-source access constraints, **provisional (DGCA-derivable)
route weights**, synthetic demo data, absent official benchmark series, and the
fact that no official CPI integration exists yet.
