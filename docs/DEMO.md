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
7. **Import and persistence** — Import Data page; show the upload-storage
   diagnostic, database status, and idempotent Push to database / Push demo data actions.
8. **Index methodology** — Methodology page; rendered LaTex estimators,
   inclusion rules, base-period settings and the prototype disclaimer.
9. **Provenance drill-down** — Airfare Index → "Contribution to today's APIx";
    each route links to its detail. Every index value traces back to
    observations, source and raw payload.

## What the jury can do

- Change the hero chart range (7D/30D/90D/6M/1Y).
- Filter globally by route, airline or source (URL-synced).
- Drill into any route and see its index series and airline mix.
- Inspect file-level mapping, skipped rows and safe storage diagnostics.
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
2. Trigger one collection sweep through the header scraper control (or
   `POST /api/collect/sweep`) and inspect the resulting run through the documented API.
3. Explain the enforced politeness policy: CAPTCHA handling, UA/TLS-fingerprint
   rotation, `Sec-Fetch-*` forgery and stealth-browser patches are not implemented.
   Say this out loud: *"the collector is real, and it deliberately stops when a
   source says no."*
4. Flip back to **Demo data** to finish on the reproducible 90-day story.

Be ready for the obvious question — *"can it just scrape Google Flights?"* The
answer is in [Scraping / collection policy](SCRAPING_POLICY.md): no, and here is
the substitute (Amadeus self-service API, licensed feeds, permissioned pages),
with the same pipeline and the same audit trail. Rehearse that answer; a judge who
asks it is testing whether you thought about it.

### On the deployed (Vercel) URL

The same story works on a public deployment. Vercel has no process lifetime for a
background loop, so the collector runs the sweep **inside** the request: point the
switch at **Scraper** and the toggle returns after the first sweep has landed,
with the observations already on screen. Without a configured PostgreSQL URL,
the store is an **ephemeral collection store (serverless /tmp)** — collected history
resets on a cold start or redeploy. Configure `DATABASE_URL` for PostgreSQL and
leave `APIX_IGNORE_DATABASE_URL` unset (or `0`) for durable history.

A live store only has the days it has collected. APIx is rebased to 100 against
its own base period, so a one-day live index is a flat line *by construction* —
the dashboard says so in the amber banner. That is the honest behaviour; do not
let it look like a bug by presenting it before the banner appears.
