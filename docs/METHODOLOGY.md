# Index Methodology (APIx)

> **⚠️ Prototype methodology — not an official CPI series.** APIx demonstrates
> *how* high-frequency airfare observations could be transformed into a
> statistical index for CPI augmentation. It does not represent MoSPI/NSO
> methodology and is not an official CPI series.

## The 8 steps

1. **Collect raw fare observations** — multi-source adapters (authorized feeds,
   public APIs, or mock/synthetic data) emit canonical fare observations.
2. **Normalize prices** — source-specific structures are mapped to a canonical
   fare model (currency, fare components, dates, airport & airline codes).
3. **Remove duplicates** — fingerprints and itinerary matching identify
   near-identical re-emissions; duplicates are excluded but retained for audit.
4. **Flag statistical outliers** — robust rules mark suspicious observations.
   They are **flagged, not blindly deleted**. Raw provenance is preserved.
5. **Calculate the route representative price** — the **median** of included
   valid fares for each route-day (robust to the skew in airfare data).
6. **Normalize against the base period** — each route is indexed against its own
   base-period price.
7. **Apply route weights** — provisional traffic-based weights scale route
   indices into the aggregate.
8. **Aggregate into APIx** — a weighted sum of route indices.

## The formula

```
Price(r, t) = median( valid fares for route r collected on day t )
Base(r)      = mean of Price(r, t) over the base period
RouteIndex   = 100 × Price(r, t) / Base(r)
APIx(t)      = Σ wᵣ × 100 × Price(r, t) / Base(r)     with  Σ wᵣ = 1
```

Where:

- `Price(r,t)` is the representative (median) price for route `r` on day `t`.
- `Base(r)` is the mean route price over the base period (the first 7 days of
  the demo window).
- `wᵣ` is the provisional route weight. Weights are **provisional** and
  identified as `provisional-dgca-v0`; they are intentionally designed so that
  DGCA-derived traffic weights can replace the placeholders later.

## Robustness & honest handling

- **Median, not mean.** Airfare distributions are right-skewed; the median far
  better represents a route-day price. Percentiles (P10/P25/P50/P75/P90) are
  shown in the UI precisely because a simple mean is misleading.
- **Minimum sample.** A route-day is only included in the index when it has a
  non-empty set of valid observations. Insufficient-sample handling means the
  index simply omits that route-day rather than fabricating a value.
- **Missing ≠ zero.** Missing observations are never silently converted into
  zero-price observations.
- **Sold-out is explicit.** Sold-out fares are represented with a distinct
  `SOLD_OUT` status and an `exclusion_reason`, never folded into the index.
- **Outliers are flagged.** `SUSPICIOUS` observations remain available for audit
  (see the quality/audit endpoints) instead of being deleted.
- **Every index result carries** its `methodology_version`, `weight_version`,
  sample sizes, excluded counts and a quality score, so the calculation can be
  reproduced.

## Base period

Configurable via the demo generator. Default window is 90 days ending on the
demo "today"; the base period is the first 7 days. `Base = 100` is shown as a
reference line on the headline index chart.

## Versioning

- `methodology_version`: `apix-1.0.0`
- `weight_version`: `provisional-dgca-v0`

## What APIx is *not*

- Not an official CPI series.
- Not a replacement for MoSPI/NSO transport-component indices.
- Not a statistically validated inflation measure — it is a *demonstration* of a
  defensible, transparent methodology with realistic data.
