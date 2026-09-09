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

## UI / design system

The dashboard is a token-driven design system (`docs/UI_AUDIT.md` has the full
audit): every color is a CSS variable surfaced as a Tailwind token, so the whole
app re-themes by flipping one class.

- **Dark mode** — toggle in the header, `system` default, persisted, OS-synced,
  no flash on load (pre-paint inline script); charts, heatmap, tooltips and
  code panes all adapt. Surfaces: `#0a0a0b` page → `#141417` cards → `#1c1c20`
  elevated; never pure black.
- **WCAG AA verified in both themes** — text, chips, buttons, heatmap cells and
  tooltips were checked numerically against the shipped token values.
- **Heatmap tooltip** — portal-rendered and `position: fixed`, so it can never
  be clipped by the matrix scroll container; solid dark-glass surface with
  backdrop blur in both themes.
- **Skeleton loaders** for every async view (charts, tables, stats), consistent
  button/segment control system, visible `:focus-visible` rings, reduced-motion
  support, per-route document titles, self-hosted Inter Variable (offline-safe).

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
| Dashboard (React + TypeScript + Tailwind + Recharts) | ✅ polished, API-backed, dark mode |
| REST API (FastAPI + Pydantic) | ✅ typed & documented |
| Index engine (route/airline/lead-time/aggregate APIx) | ✅ deterministic |
| Quality engine (VALID / SUSPICIOUS / DUPLICATE / INVALID / SOLD_OUT / STALE) | ✅ auditable |
| Deterministic demo dataset (24 routes · 6 airlines · 5 active sources · 90 days) | ✅ |
| **Bring your own data** — upload CSV/Excel/JSON from the dashboard (or drop files in `data/`): replaces the demo data, merges additively | ✅ |
| Background collection engine (scheduled sweeps → normalize → quality gate → SQLite) | ✅ |
| In-request sweeps on serverless (Vercel) + ephemeral/durable store labelling | ✅ |
| **Demo ↔ Scraper toggle** on every screen (server-side, persisted) | ✅ |
| Raw-payload archive + collection audit endpoints | ✅ |
| Backtests / validation metrics | ✅ |
| Docker Compose | ✅ |

## Using your own data

The demo dataset is a stand-in. To put **your** fares on the dashboard, drop your
export into [`data/`](data/README.md) — CSV, TSV, JSON or JSONL, any column
names you like (`Cheapest Fare (INR)`, `Date of Journey`, `From`/`To`, … are all
recognised). Nothing else changes: no code, no restart, and **adding another file
merges its rows in**, so growing the dataset is a file drop.

**From the dashboard:** **Import Data** → drop the file on the box.
It uploads, parses and reports back (rows, column mapping, rejected rows), and
you can delete files from the same screen.

**From disk or a shell** (same result, useful for large files or automation):

```bash
cp my_fares.csv data/                              # the dashboard now serves your data
cd backend && python -m app.custom_data            # per-file report: rows, mapping, rejects
cd backend && python -m app.custom_data --import ~/Downloads/export.xlsx
```

The dashboard switches its badge from `DEMO DATA` to `YOUR DATA`; the Overview,
Index, Routes, Airlines and Lead Time views read the imported observations, and
`GET /api/data/files` reports exactly which files
fed each number, how columns were mapped and which rows were rejected and why.
Missing fields (route, lead time, fare components, quality flags) are derived;
unusable rows are counted, never invented. Full contract:
[`docs/CUSTOM_DATA.md`](docs/CUSTOM_DATA.md), quick reference:
[`data/README.md`](data/README.md).

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

Files that make this work: `api/index.py` (re-exports the FastAPI `app`),
`pyproject.toml` (`[tool.vercel] entrypoint`), `vercel.json`
(install/build commands + function `maxDuration`), and root `requirements.txt`.
See [Deployment](docs/DEPLOYMENT.md#option-a--vercel-recommended-for-a-public-demo).

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

## Data sources, in priority order

| Priority | Origin | Source | Badge |
| --- | --- | --- | --- |
| 1 | `live` | what the collection engine scraped (SQLite/Postgres) | `LIVE · SCRAPED DATA` |
| 2 | `custom` | your files in `data/` (`APIX_CUSTOM_DATA_DIR`) | `YOUR DATA` |
| 3 | `demo` | the deterministic synthetic generator | `DEMO DATA` |

Every response carries `data_origin`, so an API consumer — or an auditor — can
always tell which of the three they are looking at.

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
6. **Import Data** — upload and validate CSV/Excel/JSON exports, inspect
   storage diagnostics, and upsert data into the configured database.
7. **Methodology** — the standalone statistical framework with rendered LaTex
   estimators, inclusion rules, base-period definition and prototype disclaimer.
8. **API / Data Access** — the documented, typed REST contract, including
   quality, provenance and collection audit endpoints for technical reviewers.

## Documentation

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
