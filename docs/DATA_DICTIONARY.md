# Data Dictionary

## Canonical fare observation

Each observation is the normalized, quality-assessed result of one collected
fare. Optional fields remain nullable; the system never invents data that is
unavailable.

| Field | Type | Description |
| --- | --- | --- |
| `observation_id` | string | Unique observation identifier. |
| `source` | string | Collection source (e.g. `mock`, `ota_a`, `airline_direct`). |
| `origin` / `destination` | string | IATA airport codes. |
| `route` | string | `ORIGIN-DEST` (e.g. `DEL-BOM`). |
| `departure_date` | string | `YYYY-MM-DD` of the quoted flight. |
| `collection_date` | string | `YYYY-MM-DD` when the fare was observed. |
| `collection_timestamp` | string | ISO datetime of the observation. |
| `airline` | string | Airline code (e.g. `6E`, `AI`). |
| `flight_number` | string\|null | Flight number if available. |
| `cabin` | string | Cabin (e.g. `ECONOMY`). |
| `fare_class` | string\|null | Fare class / booking class if available. |
| `lead_time_days` | integer | Days between collection and departure. |
| `base_fare` | float | Base fare (INR). |
| `taxes` | float | Taxes (INR). |
| `fees` | float | Fees / convenience charges (INR). |
| `total_fare` | float | Base + taxes + fees (INR). |
| `currency` | string | Currency (`INR`). |
| `availability` | string | `AVAILABLE`, `LIMITED` or `SOLD_OUT`. |
| `seats_remaining` | integer\|null | Seats left, if available. |
| `raw_payload_reference` | string | Pointer to the stored raw payload (provenance). |
| `fingerprint` | string | Deduplication fingerprint. |
| `quality_status` | string | `VALID`, `SUSPICIOUS`, `DUPLICATE`, `INVALID`, `SOLD_OUT`, `STALE`, `MISSING`. |
| `quality_score` | float | 0–1 quality score. |
| `exclusion_reason` | string\|null | Why the observation was excluded (audit). |

## Quality statuses

| Status | Meaning | Used in index? |
| --- | --- | --- |
| `VALID` | Passed all checks. | ✅ |
| `SUSPICIOUS` | Statistical outlier / anomaly flag. | ✅ (kept for audit) |
| `DUPLICATE` | Near-identical re-emission of a collected fare. | ❌ |
| `INVALID` | Failed payload / parsing checks. | ❌ |
| `SOLD_OUT` | Fare sold out (no available seats). | ❌ |
| `STALE` | Cached / stale fare too old to be trusted. | ❌ |
| `MISSING` | Expected field absent. | ❌ |

## Routes & weights

`routes` are the 24-route index basket with **provisional** weights. Each route
carries `base_fare`, `weight`, distance and origin/destination city. Weights are
identified as `provisional-dgca-v0` and are designed to be replaceable by
DGCA-derived traffic weights.

## Sources

Sources carry `status` (`healthy`, `degraded`, `disabled`, `ready`), an adapter
name and a `compliance` label. `disabled` and `ready` sources emit no data and
are never presented as live in the UI.

## Index outputs

- **APIx** — headline weighted index (base = 100).
- **Route index** — per-route index.
- **Route contribution** — `wᵣ × route index` (the weighted amount a route
  contributes to the headline).
- **Airline metrics** — observed avg/median fare, volatility (coefficient of
  variation of daily mean fares), index contribution, availability, quality.
- **Lead-time** — avg/median fare bucketed by days-to-departure (T+1 … T+45).
