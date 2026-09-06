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

## Step 10 — the data-source toggle (30 s, this is the memorable one)

This is the moment to show that the pipeline is real rather than a mock-up.

1. Point the **Scraper / Demo data** switch (top-right) at **Scraper**. The whole
   dashboard re-renders off the SQLite store — same endpoints, same methodology,
   collected numbers. The header badge flips to `LIVE · SCRAPED DATA`.
2. Open **Live Feed (Scraper)**. Show the raw payloads tab: that is the bytes the
   source returned, verbatim, next to the canonical observation it produced.
3. Hit **Run sweep now** and watch the run log gain a row with query/request/
   observation/failure counts.
4. Click the **Collection rules** tab. It prints the enforced politeness values and
   the explicit list of techniques that are *not* implemented — CAPTCHA handling,
   UA/TLS-fingerprint rotation, `Sec-Fetch-*` forgery, stealth-browser patches.
   Say this out loud: *"the collector is real, and it is deliberately unable to
   evade a source that blocks it. If a source says no, the monitor shows blocked."*
5. Flip back to **Demo data** to finish on the reproducible 90-day story.

Be ready for the obvious question — *"can it just scrape Google Flights?"* The
answer is in [Scraping / collection policy](SCRAPING_POLICY.md): no, and here is
the substitute (Amadeus self-service API, licensed feeds, permissioned pages),
with the same pipeline and the same audit trail. Rehearse that answer; a judge who
asks it is testing whether you thought about it.

### On the deployed (Vercel) URL

The same story works on a public deployment. Vercel has no process lifetime for a
background loop, so the collector runs the sweep **inside** the request: point the
switch at **Scraper** and the toggle returns after the first sweep has landed,
with the observations already on screen. The Live Feed shows a
**sweeps run in-request** chip and an amber **Ephemeral collection store
(serverless /tmp)** banner — say it out loud, it is a property of the platform,
not a broken scraper: collected history resets on a cold start or redeploy unless
`APIX_IGNORE_DATABASE_URL=0` is set and `DATABASE_URL` points at a PostgreSQL
database. By default Vercel ignores `DATABASE_URL`, so a leftover value does not
stop a demo sweep.

A live store only has the days it has collected. APIx is rebased to 100 against
its own base period, so a one-day live index is a flat line *by construction* —
the dashboard says so in the amber banner. That is the honest behaviour; do not
let it look like a bug by presenting it before the banner appears.
