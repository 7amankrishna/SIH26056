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
`docker compose up --build` — no live scraping required. The pipeline is
engineered so a genuine scraper / source adapter can later write into the same
canonical fare model.

| Layer | Status |
| --- | --- |
| Dashboard (React + TypeScript + Tailwind + Recharts) | ✅ polished, API-backed |
| REST API (FastAPI + Pydantic) | ✅ typed & documented |
| Index engine (route/airline/lead-time/aggregate APIx) | ✅ deterministic |
| Quality engine (VALID / SUSPICIOUS / DUPLICATE / INVALID / SOLD_OUT / STALE) | ✅ auditable |
| Deterministic demo dataset (24 routes · 6 airlines · 5 active sources · 90 days) | ✅ |
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
cd backend && . .venv/bin/activate && python -m pytest
cd frontend && npm run typecheck && npm run build
```

## Honest limitations

APIx is a **prototype statistical methodology**, not an official CPI series.
See [Methodology](docs/METHODOLOGY.md) and the acknowledgment in the product for
a candid list: live-source access constraints, **provisional (DGCA-derivable)
route weights**, synthetic demo data, absent official benchmark series, and the
fact that no official CPI integration exists yet.
