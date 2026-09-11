# Integration Plan — Port the `ankit70808` OTA scraper into APIx

> Status: **IMPLEMENTED + TESTED** · Target: `arena/01a08e19-sih26056`
> Source studied: [`ankit70808/Airfare-Price-Index`](https://github.com/ankit70808/Airfare-Price-Index) (`cleartrip_scraper.py`, `easemytrip_scraper.py`, `backend/src/services/scrape.service.js`)

This document was a plan first; the implementation described in §6 has since
been built and tested (see §10 for exactly what landed). It is kept here as the
design record.

---

## 1. What the ankit scraper actually is

Two **standalone Python scripts** (not a library), driven by `playwright.async_api`
(async Playwright) + `playwright-stealth` + `pandas`:

| Piece | `cleartrip_scraper.py` | `easemytrip_scraper.py` |
| --- | --- | --- |
| Entry | `scrape_cleartrip(browser, origin, dest, travel_date)` | `scrape_easemytrip(browser, origin, dest, travel_date)` |
| Target URL | `https://www.cleartrip.com/flights/results?adults=1&…&depart_date=DD/MM/YYYY&from=X&to=Y` | `https://www.easemytrip.com/flight-search/listing?srch=X-City-India\|Y-City-India\|DD/MM/YYYY&…` |
| Parsing | iterate **all `div`s**, regex the `innerText` (times, `₹` price, flight code `6E-522`, stops) | single `page.evaluate(EXTRACT_JS)` that reads `div.nw_listing_bx_tp` cards and returns structured JSON |
| Post-process | drop malformed, `base = fare/1.05`, `gst = fare − base`, dedupe on `(Origin,Dest,Flight_code,Travel_date)`, keep cheapest-first | same, plus keep **20 cheapest** per search (`LIMIT_PER_SEARCH`) |
| Basket | 20 DGCA routes × T+1,7,15,30,45 | 10 routes × T+1,7,15,30,45 |
| Browser lifecycle | **one** browser, **new context per search**, random UA, `headless=False` | same |
| Output | CSV (13 cols) | CSV (16 cols) |

Output schema (what a row looks like):

```
Origin, Destination, Airline_name, Flight_code, Stops, Travel_date,
Departure_time, Arrival_time, Fare, Base price, GST, Currency,
Scraped_at time, Source                       # Cleartrip
… + Duration, Seats_left                      # EaseMyTrip (extra)
```

The repo also ships a **Node/Express trigger**: `POST /api/…/scrape/trigger`
spawns the Python script via `child_process.spawn` and guards re-entry with an
`isScrapeRunning` flag.

### Its real strengths (worth porting)
1. **URL-first navigation.** No form-filling/clicking — it constructs the exact
   results URL. Fragile to URL-format drift, but cheap and repeatable.
2. **EaseMyTrip `EXTRACT_JS`.** One `evaluate()` round-trip extracts every card
   (the comment notes the old version did 1200+ Playwright calls; this is the
   correct fix).
3. **Proven output.** Committed CSVs (1,216 Cleartrip rows / 944 EaseMyTrip rows)
   prove the path works end-to-end, at least from the author's IP/date.

### Its weaknesses (fix during port)
1. **No robots.txt / ToS gate.** It fetches consumer OTAs with no permission check.
2. **Evasion stack:** `playwright-stealth`, rotating browser UAs, "bypass
   bot-detection" comments. **This directly violates APIx's `docs/SCRAPING_POLICY.md`.**
3. **Fixed `wait_for_timeout`** instead of waiting for the results element —
   flaky and slower than needed.
4. **`headless=False`** — won't run in Docker/CI/serverless.
5. **Latent bug:** the Node trigger passes `--origin/--destination`, but the
   Python scripts ignore `argv` and always run the hard-coded basket.
6. **No provenance** — the raw page/response bytes are not archived, so an
   auditor cannot re-derive a fare.

---

## 2. What APIx already has (why the port is mostly "map fields")

Your collection engine is **source-agnostic**. Everything after an adapter is
reused unchanged:

```
SourceAdapter.collect(query) → RawBatch[RawOffer(payload)]
        → normalize_offer() → quality gate (VALID/SUSPICIOUS/DUPLICATE/…)
        → store (observations + raw_payloads + collection_runs)
        → index engine → REST API → dashboard (Demo ↔ Scraper toggle)
```

Relevant existing pieces:

| APIx piece | Where | What it gives us |
| --- | --- | --- |
| `SourceAdapter` contract | `backend/app/collect/base.py` | `async collect(Query) -> RawBatch`; `RawOffer.payload` is the canonical fare dict |
| Canonical payload fields | `adapters_http.py` `_to_raw_offer` / `_block_to_payload` | `origin, destination, departure_date, airline, flight_number, cabin, fare_class, currency, base_fare, taxes, fees, total_fare, availability, seats_remaining, stops` |
| `Query` | `base.py` | `origin, destination, departure_date, lead_time_days, cabin, adults, currency` |
| `normalize_offer` | `collect/normalize.py` | canonical observation + quality flag, fingerprint, lead-time derivation |
| Store | `collect/store.py` | `observations` (25 canonical cols), `raw_payloads` (verbatim archive), `collection_runs` (honest run log) |
| `Politeness` | `collect/transport.py` | per-host min gap, retries/backoff, per-sweep request ceiling |
| `RobotsGate` | `collect/robots.py` | robots.txt check, fail-closed |
| `AllowListTransport` | `collect/transport.py` | host pinning (adapter can only hit its own host) |
| Source registry | `collect/service.py::_build` | `APIX_COLLECTOR_SOURCES` env → adapter instance |
| Sweep loop | `collect/service.py` | scheduled/manual sweeps, circuit breaker, demo↔live toggle |
| Route basket | `dataset.py::ROUTES` + `config.sweep_routes` | the 24-route basket APIx already uses |
| Lead times | `config.sweep_lead_times` (default `1,7,30`; `dataset.LEAD_TIMES = 1,3,7,15,30,45`) | matches ankit's T+1,7,15,30,45 set |

**What is missing:** a Playwright-based adapter. APIx's current adapters use
`urllib` (plain HTTP), so JS-rendered OTA pages need a browser. Playwright is
**not** in `requirements.txt` today.

---

## 3. Two integration paths

### Path A — Native Playwright adapter (recommended)
Port the *parsing* from ankit into a new `PlaywrightOtaAdapter` that implements
`SourceAdapter`. The ankit code becomes the "guts" of `collect()`; APIx keeps
politeness, robots gate, provenance archive, quality gate, index, API, and the
Demo ↔ Scraper toggle.

- ✅ Full pipeline: scraped fares feed the index/API/dashboard with provenance.
- ✅ One sweep = one run-log row; blocks trip the existing circuit breaker.
- ✅ `POST /api/collect/sweep` and the dashboard "Collect now" button work.
- ✅ Survives in Docker (headless browser image).
- ❌ More work (new module + tests + dependency).

### Path B — Scrape to CSV, import via the "bring your own data" path
Run the ankit scripts (or a cleaned copy) as a **cron/subprocess** that writes
CSV, then drop the CSV into `data/` (or `python -m app.custom_data --import`).

- ✅ Fastest; zero engine changes; the custom-data loader already maps columns.
- ❌ Bypasses provenance, quality gate, circuit breaker, and the live toggle.
- ❌ Two pipelines to operate; scraped data isn't "live" in the engine sense.

**Recommendation: Path A**, with Path B as the short-term bridge while A is built
(Step 1 below is genuinely useful standalone).

---

## 4. Policy gate — decide BEFORE writing the adapter

APIx's `docs/SCRAPING_POLICY.md` hard-rules conflict with the ankit scraper's
evasion stack. To integrate honestly, the port must:

1. **Drop** `playwright-stealth`, UA rotation, and `headless=False`. Use APIx's
   self-identifying `User-Agent` (already in `settings.user_agent`).
2. **Add the `RobotsGate`** before each host (like `HttpJsonAdapter._allowed`).
3. **Reclassify the sources** via `COMPLIANCE_LABELS`. Cleartrip / EaseMyTrip
   are consumer OTAs; their ToS likely prohibit automated access. Until written
   permission exists, the adapter should ship as `policy_gated` (emits no data)
   or be **disabled by default**, enabled only with an explicit env flag.

> Decision for you: do we (a) mark these `policy_gated` and keep the adapter
> off by default, (b) enable them behind `APIX_OTA_ENABLED=1` accepting the ToS
> risk for a hackathon demo, or (c) restrict to the **Amadeus**/authorized path
> already in the repo? The plan below assumes (b) but is written so (a) costs
> one line.

---

## 5. Recommended target architecture (Path A)

```
backend/app/collect/adapters_playwright.py        (NEW)
├── PlaywrightOtaAdapter(SourceAdapter)
│     id/name per OTA, type="browser", requires_robots_gate=True
│     compliance = "policy_gated" (until operator opts in)
│     async collect(query):
│        1. robots gate  (RobotsGate, fail-closed)          ← APIx
│        2. politeness.wait_turn(host)                       ← APIx
│        3. launch/reuse browser (async_playwright, headless=True)
│        4. build results URL for (origin, dest, departure_date)
│        5. goto → wait_for_selector (NOT fixed sleep)       ← fixed ankit flakiness
│        6. run site-specific extractor:
│             cleartrip → regex innerText            (ported)
│             easemytrip → EXTRACT_JS evaluate       (ported)
│        7. map each card → canonical payload dict   ← the real work
│        8. _guard_against_denial() on a bot-wall    ← APIx (no evasion)
│        9. return RawBatch(query, offers=[RawOffer(payload=…, source, url, …)])
│
│   helpers: build_cleartrip_url(), build_easemytrip_url(), parse_*()
└── (register in service._build for source ids "ota_cleartrip", "ota_easemytrip")

Field mapping (anki → APIx canonical payload):
  Origin             → origin            (upper)
  Destination        → destination       (upper)
  Airline name       → airline           (via existing _norm_airline → "6E" etc.)
  Flight_code        → flight_number
  Stops              → stops             (int; "Non-stop" → 0)
  Travel_date        → departure_date
  Fare               → total_fare
  Base price         → base_fare
  GST                → taxes
  Currency           → currency
  Departure/Arrival  → kept inside payload (archived verbatim; not a canonical col)
  Scraped_at time    → fetched_at / collection timestamp (APIx provides)
  Source             → adapter id
  Seats_left         → seats_remaining
  Duration           → payload only
```

Config (`config.py` additions):

```
APIX_COLLECTOR_SOURCES=fixture,ota_cleartrip,ota_easemytrip
APIX_OTA_ENABLED=0|1                      # master gate (default 0)
APIX_PLAYWRIGHT_HEADLESS=1
APIX_PLAYWRIGHT_TIMEOUT_MS=60000
```

Dependency: add `playwright` to `backend/requirements.txt` + `docker-compose`
(Chromium + deps). Keep it isolated from the Vercel/serverless path (Step 3).

---

## 6. Step-by-step implementation plan

Each step is independently shippable and verifiable. Stop points are marked.

### Step 0 — Snapshot & dependency audit ✅-able
- Baseline `git status`; add `playwright` to `backend/requirements.txt`
  (dev/local only, not the Vercel bundle).
- Verify a headless Chromium runs in this sandbox (`python -m playwright install chromium`).

**Verify:** `python -c "from playwright.sync_api import sync_playwright"` works.

### Step 1 — Standalone "scrape-to-CSV" CLI (Path B bridge, ~half a day)
- Copy the two ankit scripts into `backend/app/collect/ota/` **minus** the
  evasion (no stealth, no UA rotation, `headless=True`, `wait_for_selector`).
- Add a real `argparse` CLI: `--routes DEL-BOM,BLR-DEL`, `--lead-times 1,7,30`,
  `--source cleartrip|easemytrip`, `--out data/ota_YYYYMMDD.csv`.
- Fix the ankit `--origin/--destination`-ignored bug by actually honoring args.
- Emit the **same CSV schema** ankit uses, so Path B import works unchanged.

**Verify:** run against one route/date; confirm CSV rows + that a bot-wall is
detected and reported (not "solved").

### Step 2 — Adapter skeleton registered in the engine (~half a day)
- Create `backend/app/collect/adapters_playwright.py` with `PlaywrightOtaAdapter`
  implementing `collect()` and `health_check()`; wire it into `service._build`
  behind the source ids `ota_cleartrip` / `ota_easemytrip`.
- `collect()` calls the Step-1 extractors but returns `RawBatch` (no CSV).
- Add `APIX_OTA_ENABLED` gate + `compliance="policy_gated"`.

**Verify:** `POST /api/collect/sources` lists both OTAs as `policy_gated`;
`POST /api/collect/sweep?source=ota_cleartrip` records a `blocked`/`disabled`
run honestly when the gate is off.

### Step 3 — Field mapping + canonical payload (~half a day)
- Implement the field table above; reuse `_norm_airline` and `_money`/`_int_or_none`
  from `adapters_http.py` so parsing is consistent.
- Archive the raw card JSON verbatim in `RawOffer.payload` extras (times/duration).
- Port `EXTRACT_JS` for EaseMyTrip and the regex pass for Cleartrip, refactored
  into `extract_cleartrip_cards(page)` / `extract_easemytrip_cards(page)`.

**Verify:** unit tests with saved HTML/JSON fixtures (capture real page dumps in
Step 1 as test fixtures) → correct canonical payloads, no network in tests.

### Step 4 — Robustness & policy wiring (~half a day)
- `wait_for_selector` per OTA (not fixed sleeps), timeouts, retry via politeness.
- `_guard_against_denial` on interstitial pages → `CollectionError("blocked")`.
- Ensure `robots` + `allow-list` transport semantics apply (host pinning).
- Circuit breaker integration (already in the sweep loop — just confirm).

**Verify:** force a fake bot-wall fixture → run is `blocked`; force timeout →
run is `failed`; neither is recorded `healthy`.

### Step 5 — Docker + runtime (~quarter a day)
- Extend `backend/Dockerfile` to install Playwright + Chromium deps.
- Pin the browser to a persisted volume if cache-warmth matters.
- Guard the serverless path: adapter imports `playwright` lazily so Vercel never
  needs the browser.

**Verify:** `docker compose up --build` → sweep `ota_cleartrip` for one route →
data appears in the dashboard under live mode.

### Step 6 — Wire into the UX & docs (~quarter a day)
- Confirm the existing Demo ↔ Scraper toggle, `Collect now`, `/collect/runs`,
  `/collect/payloads` show the OTA sources.
- Add a `docs/SCRAPING_POLICY.md` note (OTA case study: "why these are
  `policy_gated` by default"), mirroring the Google-Flights section.

**Verify:** full loop — toggle live → Collect now → fare appears in Overview →
raw payload visible in the audit view → toggle back to demo.

---

## 7. Run commands (target end-state)

```bash
# 1. install browser once (local / docker build)
python -m playwright install chromium

# 2. enable the OTA adapters
export APIX_COLLECTOR_SOURCES=fixture,ota_cleartrip,ota_easemytrip
export APIX_OTA_ENABLED=1
export APIX_DATA_MODE=live
export APIX_SWEEP_LEAD_TIMES=1,7,30

# 3. run the backend + frontend, then either:
curl -X POST localhost:8000/api/collect/sweep          # one sweep now
# or use the dashboard "Collect now" button
```

---

## 8. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| IP block mid-demo (same risk ankit had) | circuit breaker + `blocked` run logging; low frequency; don't demo the live path as the primary flow |
| Selector/URL drift on Cleartrip/EaseMyTrip | fixtures + `wait_for_selector`; keep Path B CLI so a re-capture re-seeds the demo |
| Policy/ToS exposure | ship `policy_gated`/disabled by default; `APIX_OTA_ENABLED` is an explicit opt-in; document in `SCRAPING_POLICY.md` |
| Playwright bloats Vercel bundle | lazy import; browser only in Docker/VM; serverless keeps using fixtures/Amadeus |
| Slow sweeps (browser + politeness gap) | default lead times `1,7,30`; per-sweep request ceiling; background loop in Docker |

---

## 9. Decision needed before Step 1

1. **Path A, Path B, or A with B as a bridge?** (Recommended: A, with Step 1 as the bridge.)
2. **Policy posture:** `policy_gated` (off by default) vs `APIX_OTA_ENABLED=1` opt-in vs Amadeus-only.
3. **Scope of OTAs:** Cleartrip + EaseMyTrip (as in ankit), or just one first?
4. **Where to run it:** Docker/VM only, or also attempt serverless?

> **Resolution (per operator):** ignore the policy gate, build it, test it, and
> store collected data in the project's Supabase (PostgreSQL) database. §10
> records what was shipped under that instruction.

---

## 10. What has been implemented

### Supabase (PostgreSQL) storage — the collection target
APIx stores collected data in **Supabase**, which is hosted PostgreSQL. This was
already the repo's durable-store path (`DATABASE_URL=postgres://…` → psycopg2);
the OTA scrapers write into the same three tables the rest of the engine uses:

- `db/supabase_schema.sql` — the full idempotent schema (paste into the Supabase
  **SQL Editor** once). Five tables, the analytical indexes, table/column
  comments, and RLS enabled with a single `postgres`-role policy so the data is
  not reachable through Supabase's public REST API.
- `DATABASE_URL` — set it to the Supabase connection string (Project Settings →
  Database → Connection string; the **Session pooler** / **Direct connection**
  on port 5432, or the **Transaction pooler** on 6543 with `?sslmode=require`).
  `APIX_IGNORE_DATABASE_URL` must be `0`/unset.
- The backend bootstraps the same tables on first connection, so running the
  schema file is optional-but-recommended; `test_postgres_store.py` (opt-in via
  `APIX_TEST_DATABASE_URL`) proves the shipped schema and the app's DDL agree.
- `.env.example` added (Supabase URL template + OTA/collector vars);
  `docker-compose.supabase.yml` runs backend + frontend with the OTA scrapers,
  reading `DATABASE_URL` from `.env` (no database container — Supabase is hosted).

### OTA scrapers (`backend/app/collect/ota/`)
- `extractors.py` — faithful, browser-free port of the ankit parsing: URL
  builders (`build_cleartrip_url`, `build_easemytrip_url`), the EaseMyTrip
  `EXTRACT_JS`, and pure parsers (`parse_cleartrip_cards`,
  `parse_easemytrip_cards`) that emit the engine's canonical payload shape
  (fare → `base_fare` = fare/1.05, `taxes` = 5% GST, airline/flight/stops/times).
- `adapters.py` — `PlaywrightOtaAdapter(SourceAdapter)` registered as
  `ota_cleartrip` / `ota_easemytrip`; lazy Playwright import (serverless stays
  lean); headless by default; bot-wall pages recorded `blocked`.
- `cli.py` — `python -m app.collect.ota.cli --source cleartrip --routes …
  --lead-times … --out …`, honours its arguments (fixes ankit's ignored-argv bug)
  and writes ankit-schema CSVs usable by the custom-data import path.
- `service.py::_build` registers the two sources; `config.py` adds
  `APIX_OTA_HEADLESS` / `APIX_OTA_TIMEOUT_MS`. `playwright==1.62.0` in
  `backend/requirements.txt`.

### Tests
- `tests/test_ota_extractors.py` — URL builders, Cleartrip/EaseMyTrip parsing
  against captured card fixtures, dedupe/cheapest-N, lazy-import check, and
  collection-service registration.
- `tests/test_postgres_store.py` (existing, opt-in) — verifies the Supabase
  path: the shipped schema, CRUD round-trips, duplicate handling, date-window
  queries and reset against a real PostgreSQL.
- Full backend suite: **209 passed, 5 skipped**.

### Run it
```bash
# Docker: backend (OTA scrapers + Chromium) + frontend → Supabase
cp .env.example .env        # set DATABASE_URL to your Supabase connection string
docker compose -f docker-compose.supabase.yml up --build

# or locally
export DATABASE_URL=postgresql://postgres.<REF>:<PASSWORD>@db.<REF>.supabase.co:5432/postgres
export APIX_COLLECTOR_SOURCES=ota_cleartrip,ota_easemytrip
export APIX_DATA_MODE=live
python -m playwright install chromium
cd backend && uvicorn app.main:app --reload
curl -X POST localhost:8000/api/collect/sweep
```

### Sandbox note
This workspace's network egress is allow-listed to PyPI + GitHub only, so a live
Supabase round-trip, Docker, and the Playwright Chromium CDN could not be
provisioned here. The scraper's parsing is fully covered by fixture tests, and
the Supabase/Postgres store path is covered by the repo's existing opt-in
`APIX_TEST_DATABASE_URL` integration test — point it at your Supabase project to
verify end-to-end before the first real sweep.
