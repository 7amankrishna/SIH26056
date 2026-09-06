"""Build a :class:`Dataset` from what the collector has actually stored.

This is the seam that makes the toggle honest: the *same* aggregation code that
backs the demo (`dataset._finalize_aggregates`) runs over real observations, so
every existing screen — index, routes, airlines, lead time, quality, provenance —
works on live data without a single special case in the engine.

Consequences of a young live store, handled explicitly:
* Only routes with observations enter the index (no phantom 100.0s).
* The base period is the first collected day(s); until more history accrues the
  APIx hovers around 100 by construction. The dashboard says so.
* Observations outside the basket are kept in the store and shown in the raw
  feed, but they cannot enter an index that has no weight for them.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from .dataset import Dataset, Observation, ROUTES, _finalize_aggregates
from .collect.store import get_store


def live_signature() -> Optional[tuple]:
    """Cheap fingerprint of the live store; changes whenever data is appended."""
    try:
        store = get_store()
        c = store.counts()
    except Exception:
        return None
    if not c["observations"]:
        return None
    return (c["observations"], c["runs"], c["valid_observations"], c["days_collected"])


def build_live_dataset(history_days: int = 90) -> Dataset:
    """Materialize the stored observations as a Dataset for the engine layer."""
    store = get_store()
    today = dt.date.today()
    start_window = today - dt.timedelta(days=max(1, history_days) - 1)

    rows = store.all_observations(since=start_window.isoformat())
    observations: list[Observation] = []
    for r in rows:
        observations.append(
            Observation(
                observation_id=str(r.get("observation_id") or ""),
                source=str(r.get("source") or "live"),
                origin=str(r.get("origin") or ""),
                destination=str(r.get("destination") or ""),
                route=str(r.get("route") or ""),
                departure_date=str(r.get("departure_date") or ""),
                collection_date=str(r.get("collection_date") or today.isoformat()),
                collection_timestamp=str(r.get("collection_timestamp") or ""),
                airline=str(r.get("airline") or "NA"),
                flight_number=r.get("flight_number"),
                cabin=str(r.get("cabin") or "ECONOMY"),
                fare_class=r.get("fare_class"),
                lead_time_days=int(r.get("lead_time_days") or 0),
                base_fare=float(r.get("base_fare") or 0.0),
                taxes=float(r.get("taxes") or 0.0),
                fees=float(r.get("fees") or 0.0),
                total_fare=float(r.get("total_fare") or 0.0),
                currency=str(r.get("currency") or "INR"),
                availability=str(r.get("availability") or "AVAILABLE"),
                seats_remaining=(int(r["seats_remaining"]) if r.get("seats_remaining") is not None else None),
                raw_payload_reference=str(r.get("raw_payload_reference") or ""),
                fingerprint=str(r.get("fingerprint") or ""),
                quality_status=str(r.get("quality_status") or "VALID"),
                quality_score=float(r.get("quality_score") or 0.0),
                exclusion_reason=r.get("exclusion_reason"),
            )
        )

    dates = sorted({o.collection_date for o in observations})
    if not dates:
        dates = [today.isoformat()]
    start = dt.date.fromisoformat(dates[0])
    end = dt.date.fromisoformat(dates[-1])

    # Base period: first up-to-7 collected days (index is relative to it).
    base_end = min(end, start + dt.timedelta(days=6))

    # Restrict the index basket to routes that actually have index-eligible data.
    eligible = {
        o.route
        for o in observations
        if o.quality_status in ("VALID", "SUSPICIOUS") and o.route in ROUTES
    }
    index_routes = [r for r in ROUTES if r in eligible] or [r for r in ROUTES][:1]

    ds = Dataset(
        end_date=end,
        base_period_start=start,
        base_period_end=base_end,
        origin="live",
    )
    ds.observations = observations
    _finalize_aggregates(ds, start, end, start, base_end, index_routes=index_routes)
    return ds
