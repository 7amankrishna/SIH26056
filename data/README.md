# Your data goes here

Any file you drop in this folder replaces the synthetic demo dataset on the
dashboard. Nothing else has to change — no code, no restart. Add another file
and its rows are merged in, so **more data = one more file**.

```
data/
├── fares_2026_09.csv      ← fare observations (as many files as you like)
├── fares_2026_10.csv
├── routes.csv             ← optional: route weights / cities / distances
├── airlines.csv           ← optional: airline names
├── sources.csv            ← optional: source names
├── config.json            ← optional: column mapping, date format, …
└── _templates/            ← starting points (ignored by the loader: copy out)
```

### Importing an attached export

```bash
cd backend
python -m app.custom_data --import ~/Downloads/my_fares.xlsx
python -m app.custom_data --import ~/Downloads/export.csv --as fares_2026_09.csv
```

That copies the file into this folder (never overwriting — a second import of
the same file becomes `my_fares_1.xlsx`), then prints the parse report.

## 1. Fare files (required)

Accepted: `.csv` `.tsv` `.txt` `.json` `.jsonl` `.ndjson` `.xlsx` `.xlsm`
(comma/tab/semicolon/pipe delimited CSVs are sniffed automatically; the first
worksheet of an Excel workbook is read, real date cells included — that needs
`pip install openpyxl`). Sub-folders are scanned too. Files or folders whose
name starts with `_` are skipped.

Only three things are needed per row — **when** the fare was seen, **which
route**, and **how much**. Everything else is optional and derived when missing:

| You must have | Accepted column names (case/space/`_` insensitive) |
| --- | --- |
| a date | `collection_date`, `date`, `observed_on`, `snapshot_date`, `timestamp`, … |
| a route | `route` (`DEL-BOM`, `DEL/BOM`, `DEL to BOM`) **or** both `origin` + `destination` |
| a fare | `total_fare`, `price`, `fare`, `amount`, … **or** `base_fare` + `taxes` + `fees` |

Optional columns that are used when present: `departure_date`, `lead_time_days`,
`airline`, `flight_number`, `cabin`, `fare_class`, `source`, `currency`,
`availability`, `seats_remaining`, `quality_status`, `observation_id`,
`origin_city`, `destination_city`, `distance`. Unrecognised columns are ignored
(and listed under `unmapped` in the report, so you can see what was dropped).

**Column names not matching?** Don't rename anything — map them in `config.json`:

```json
{ "column_map": { "date of journey": "departure_date", "cheapest fare": "total_fare" } }
```

**Dates** are parsed from `2026-09-06`, `06/09/2026`, `06-Sep-2026`, `06 Sep 2026`,
`Sep 06, 2026`, ISO timestamps, … If your file is ambiguous, pin it:
`{ "date_format": "%d/%m/%Y" }`.

**Fares** may carry currency symbols and thousands separators — `₹ 4,650.00`,
`INR 4650`, `4650.00` all work.

**Re-importing the same rows is safe**: identical source + route + date +
airline + flight + fare is flagged `DUPLICATE` and excluded from the index
(kept for audit), so a file that arrives twice does not double the index.

### What the loader fills in for you

* `route` from origin/destination, `lead_time_days` from `departure_date − collection_date`
* fare components from a headline fare (78/16/6 base/tax/fee) or the total from components
* flight-level fingerprint, observation ids, `ECONOMY` cabin, `INR` currency
* **quality**: rows that arrive without a `quality_status` are assessed —
  sold-out rows become `SOLD_OUT`, exact re-emissions from the same source on the
  same day become `DUPLICATE`, fares far from their route-day median become
  `SUSPICIOUS` (flagged, never deleted), non-positive fares become `INVALID`.
  A `quality_status` column in your file always wins.

Rows missing a usable date, route or fare are **skipped and counted** (never
guessed) — see `/api/data/files` or `python -m app.custom_data` for the reasons.

## 2. Reference files (optional)

| File | Columns | Why |
| --- | --- | --- |
| `routes.csv` | `route` (or `origin`,`destination`), `weight`, `base_fare`, `distance`, `origin_city`, `destination_city` | Set the index weights (they must sum to ~1) and the city labels |
| `airlines.csv` | `airline` (code), `name`, `alliance`, `hub` | Prettier airline names |
| `sources.csv` | `source` (id), `name`, `type`, `status`, `compliance` | Prettier source names on the Collection Monitor |

Routes in your data that are **not** in the shipped 24-route basket are
registered automatically. If you do not supply weights, each route is weighted by
its share of observations — the dashboard labels this
`provisional-observation-share-v1` so nobody mistakes it for a traffic weight.

## 3. `config.json` (optional)

```json
{
  "column_map": { "date of journey": "departure_date" },
  "date_format": "%d/%m/%Y",
  "currency": "INR",
  "default_source": "my_export",
  "route_weights": { "DEL-BOM": 0.08, "BOM-DEL": 0.07 },
  "include": ["fares_*.csv"],
  "exclude": ["*_draft.csv"]
}
```

## 4. Check it before you open the dashboard

```bash
cd backend
python -m app.custom_data                 # report on ../data
python -m app.custom_data ../data/my.csv  # validate a single file
```

…or, with the API running: `GET /api/data/files` (per-file rows, mapped columns,
skipped rows, warnings) and `POST /api/data/reload` to force a rescan.

## 5. Switching back

Move the files out of this folder (or set `APIX_CUSTOM_DATA=0`, or
`APIX_DATA_MODE=demo`) and the deterministic demo dataset serves again. In live
mode, scraped data always wins over both.
