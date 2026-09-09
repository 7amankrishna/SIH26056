# Custom data — replacing the demo dataset with your own

The shipped demo dataset is synthetic: a fixed-seed generator that runs at
startup so every deployment looks identical. This document describes the seam
that lets **real fare data** take its place without touching the index engine,
the API contract or a single screen.

Implementation: [`backend/app/custom_data.py`](../backend/app/custom_data.py).
Quick reference for the file formats: [`data/README.md`](../data/README.md).

---

## 1. How it works

```
data/*.csv|json|jsonl                    ← you drop these in
        │
        ▼  app.custom_data
  discover → read → map columns → coerce → derive → assess quality → register
        │
        ▼  app.dataset.Observation          (the same canonical model)
  dataset._finalize_aggregates(...)         (the same aggregation as demo/live)
        │
        ▼
  Dataset(origin="custom")  ──► engine ──► /api/* ──► dashboard
```

Because the imported rows are turned into the same `Observation` objects and
aggregated by the same function that backs the demo and live paths, **every
screen works unchanged**: overview KPIs, index trend, route table, heatmap,
airline comparison, lead-time curve, fare distribution, quality breakdown,
rejected-rows audit, provenance drill-down and the collection monitor.

### Precedence

| Priority | Origin | Condition |
| --- | --- | --- |
| 1 | `live` | Live mode selected **and** the collection store has observations |
| 2 | `custom` | `data/` (or `APIX_CUSTOM_DATA_DIR`) contains at least one usable fare file |
| 3 | `demo` | otherwise |

Live falls through to custom/demo rather than rendering an empty dashboard.
Set `APIX_CUSTOM_DATA=0` or `APIX_DATA_MODE=demo` to force the synthetic store.

### Caching

The loader builds once and then only rebuilds when the *file signature* changes
(paths + `st_mtime_ns` + size + `config.json`). Dropping in a file — or editing
one — therefore shows up on the next request, with no restart. `POST
/api/data/reload` forces a rescan.

---

## 2. What is derived for you

| Missing in your file | Derived as |
| --- | --- |
| `route` | `ORIGIN-DEST` from `origin` + `destination` (airport aliases resolved: `GOA` → `GOI`, `Bombay` → `BOM`) |
| `lead_time_days` | `departure_date − collection_date` (in days, floored at 0) |
| `departure_date` | `collection_date + lead_time_days` |
| fare components | `total_fare` split 78 / 16 / 6 into base / taxes / fees |
| `total_fare` | `base_fare + taxes + fees` |
| `airline` | name → IATA code (`IndiGo` → `6E`); unknown names get a stable derived code and are added to the catalogue |
| `cabin`, `currency` | `ECONOMY`, `INR` |
| `source` | the file name (override with `default_source`) |
| `observation_id` | `<file-stem>-<row number>` |
| `fingerprint` | the same hash the pipeline uses everywhere else |
| `quality_status` | assessed — see below |

### Quality assessment (only for rows that don't carry a status)

| Rule | Result |
| --- | --- |
| fare ≤ 0 | `INVALID` — `flag:non_positive_fare` |
| `SOLD_OUT` availability or 0 seats | `SOLD_OUT` — `flag:sold_out` |
| identical source + route + date + departure + airline + flight + class + fare already seen | `DUPLICATE` — `flag:duplicate_fingerprint` |
| ≥ 2.2× or ≤ 0.40× the route-day median fare | `SUSPICIOUS` — `flag:statistical_outlier` |
| otherwise | `VALID` |

Duplicates are only flagged *within* one source on one day: two different
sources quoting the same flight is normal, not a duplicate. Outliers are
**flagged, never deleted** — the same policy as the rest of the pipeline.

Rows with no usable date, route or fare are **skipped and counted** (never
guessed); the per-file counts and reasons are in `/api/data/files`.

---

## 3. Route registration and weights

Imported routes are registered into the same catalogue the engine reads.

* A route already in the shipped 24-route basket keeps its metadata and weight.
* A new route gets an entry built from the data: origin/destination from the key,
  city names from the built-in IATA table (or your `origin_city`/`destination_city`
  columns), distance from your `distance` column if present.
* Weights, in order of preference:
  1. `weight` column in `routes.csv`;
  2. `route_weights` in `data/config.json`;
  3. otherwise proportional to the route's share of observations, reported
     honestly as `weight_version = provisional-observation-share-v1`.
* Lead times present in the data widen the lead-time ladder, so the T+ curve
  shows the buckets you actually have.
* Sources found in the data are registered so the Collection Monitor shows real
  per-source counts instead of the synthetic ones — and only those, so the
  import is never padded with built-in sources that emitted nothing.
* Everything registered is **rolled back before the next build**, so deleting a
  file removes its routes instead of leaving them in the basket.

---

## 4. Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `APIX_CUSTOM_DATA_DIR` | `<repo>/data` | directory scanned for your files |
| `APIX_CUSTOM_DATA` | `1` | `0` disables the loader entirely |
| `APIX_DATA_MODE` | `""` | `demo` pins the source to the synthetic dataset |

`data/config.json` (all keys optional):

```json
{
  "column_map": { "date of journey": "departure_date", "cheapest fare": "total_fare" },
  "date_format": "%d/%m/%Y",
  "currency": "INR",
  "default_source": "my_export",
  "route_weights": { "DEL-BOM": 0.08 },
  "include": ["fares_*.csv"],
  "exclude": ["*_draft.csv"]
}
```

Reference tables (optional, recognised by file name): `routes.csv`,
`airlines.csv`, `sources.csv`. Files and directories starting with `_` are
skipped, which is how `data/_templates/` stays out of the way.

---

## 5. Operating it

```bash
cd backend
python -m app.custom_data                            # report on the data directory
python -m app.custom_data ../data/my.csv             # validate one file before trusting it
python -m app.custom_data --import ~/Downloads/x.xlsx   # copy an export in, then validate it
python -m app.custom_data --import ~/Downloads/x.csv --as fares_2026_09.csv
```

`--import` never overwrites: importing the same file twice lands it as
`x_1.xlsx`. The rows are then flagged `DUPLICATE` (same source + route + date +
airline + flight + fare), so a repeat import cannot double the index.

`.xlsx` / `.xlsm` need the optional `openpyxl` package (in
`backend/requirements.txt`); without it the file is skipped with an explicit
"convert to CSV" message rather than failing silently.

```bash
curl -s localhost:8000/api/data/files | jq '.totals, .files[].mapped'
curl -s -X POST localhost:8000/api/data/reload   # force a rescan
```

The dashboard badge reads `YOUR DATA · N files` while custom data is served, and
the header shows a one-line banner with the import notes (provisional weights,
skipped rows, newly registered routes) until dismissed.

---

## 6. Honest limitations

* **Weights are not traffic weights.** Without `routes.csv` they are observation
  shares, labelled `provisional-observation-share-v1` in the API.
* **Base period is the first collected days.** With a short export the index
  hovers near 100 by construction — the same caveat as a young live store.
* **One currency.** Values are assumed INR; a `currency` column is carried but
  no FX conversion happens.
* **Serverless is read-only.** On Vercel the files must ship with the build
  (`vercel.json` includes `data/**`, and `.vercelignore` re-includes it after its
  blanket `*.csv` rule); the loader only ever reads them.
* **No interpolation.** Missing route-days stay missing rather than being filled
  in; the index simply has gaps.
* **Quality rules are statistical, not adjudicated.** A fare flagged
  `SUSPICIOUS` is a fare worth reviewing, not a proven error.
