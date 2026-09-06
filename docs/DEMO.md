# Demo Guide

The demo is designed for a 3–5 minute SIH jury presentation, entirely offline
and deterministic.

## Run it

```bash
docker compose up --build
```

Open <http://localhost:8080>. A **DEMO DATA** badge is shown whenever the
synthetic dataset is in use.

## Presentation story

**Raw fares → trusted observations → statistical index → economic insight.**

1. **Current APIx** — Overview page KPI (e.g. `115.1`, up on the day/week).
2. **30-day movement** — Overview KPIs + hero trend chart with range controls.
3. **Route heatmap** — Overview (and Routes). Toggle `% Change` / `Price Level`;
   hover any cell for fare, route index, 7d/24h change, observation count and
   quality.
4. **Most inflationary routes** — Overview "Routes with Largest Price Movement"
   and the Route Index table.
5. **Lead-time elasticity** — Lead Time page. T+1 is far more expensive than
   T+45; the insight line quantifies it ("Average observed fare is X% higher at
   T+1 than T+45"). Apply route/airline filters.
6. **Airline comparison** — Airlines page; observed vs normalized metrics with a
   clear statistical disclaimer.
7. **Data quality** — Data Quality page; quality score, breakdown, and a real
   drill-down into rejected/suspicious observations.
8. **Collection pipeline** — Collection Monitor; per-source health, latency,
   failures, circuit-breaker state and compliance. Demonstrates that a disabled
   source is never shown as live.
9. **Index methodology** — Methodology page; 8-step framework, the actual
   formula, definitions and the prototype disclaimer.
10. **Provenance drill-down** — Airfare Index → "Contribution to today's APIx";
    each route links to its detail. Every index value traces back to
    observations, source and raw payload.

## What the jury can do

- Change the hero chart range (7D/30D/90D/6M/1Y).
- Filter globally by route, airline or source (URL-synced).
- Drill into any route and see its index series and airline mix.
- Inspect exactly which observations were rejected and why.
- Read the OpenAPI docs and hit any endpoint with a real JSON response.

## What to emphasize (and what to be honest about)

Emphasize **transparency and auditability** — this is the product. Be honest
that the data is synthetic, weights are provisional, and there is no official
benchmark or CPI integration yet. That honesty is a feature, not a weakness.
