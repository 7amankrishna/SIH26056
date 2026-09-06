"""Deterministic demo dataset for APIx.

This module builds a realistic, fully offline, reproducible airfare dataset
that mirrors the shape of real collection data flowing through the pipeline:

    source -> collection -> raw storage -> normalization -> quality -> index

Nothing here depends on live web-scraping. The data is generated on startup
from a fixed seed, so every run produces the same numbers — exactly what a
demo needs. The shape (fields, routes, airlines, lead-times, quality flags)
is designed so that a genuine scraper / adapter can later write into the same
canonical fare model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

from .config import settings

# --------------------------------------------------------------------------- #
# Reference data (routes, airlines, sources, lead-times)
# --------------------------------------------------------------------------- #

# Route basket. ``weight`` is a PROVISIONAL traffic weight used to aggregate
# route indices into the headline APIx index. These are placeholders derived
# from typical Indian domestic traffic patterns and are explicitly identified
# as provisional so that DGCA-derived weights can replace them later.
# Each entry: key -> (origin, destination, base_fare_inr, weight, distance_km, cities)
ROUTES: dict[str, dict] = {
    "DEL-BOM": {"origin": "DEL", "destination": "BOM", "base_fare": 4650, "weight": 0.072, "distance": 1150, "origin_city": "Delhi", "destination_city": "Mumbai"},
    "BOM-DEL": {"origin": "BOM", "destination": "DEL", "base_fare": 4750, "weight": 0.070, "distance": 1150, "origin_city": "Mumbai", "destination_city": "Delhi"},
    "DEL-BLR": {"origin": "DEL", "destination": "BLR", "base_fare": 5250, "weight": 0.060, "distance": 1740, "origin_city": "Delhi", "destination_city": "Bengaluru"},
    "BOM-BLR": {"origin": "BOM", "destination": "BLR", "base_fare": 5650, "weight": 0.055, "distance": 980, "origin_city": "Mumbai", "destination_city": "Bengaluru"},
    "DEL-CCU": {"origin": "DEL", "destination": "CCU", "base_fare": 5800, "weight": 0.045, "distance": 1320, "origin_city": "Delhi", "destination_city": "Kolkata"},
    "MAA-DEL": {"origin": "MAA", "destination": "DEL", "base_fare": 6100, "weight": 0.042, "distance": 1730, "origin_city": "Chennai", "destination_city": "Delhi"},
    "DEL-HYD": {"origin": "DEL", "destination": "HYD", "base_fare": 5000, "weight": 0.050, "distance": 1530, "origin_city": "Delhi", "destination_city": "Hyderabad"},
    "BOM-MAA": {"origin": "BOM", "destination": "MAA", "base_fare": 5400, "weight": 0.038, "distance": 1020, "origin_city": "Mumbai", "destination_city": "Chennai"},
    "BLR-HYD": {"origin": "BLR", "destination": "HYD", "base_fare": 3350, "weight": 0.046, "distance": 480, "origin_city": "Bengaluru", "destination_city": "Hyderabad"},
    "HYD-BLR": {"origin": "HYD", "destination": "BLR", "base_fare": 3300, "weight": 0.044, "distance": 480, "origin_city": "Hyderabad", "destination_city": "Bengaluru"},
    "BLR-DEL": {"origin": "BLR", "destination": "DEL", "base_fare": 5450, "weight": 0.056, "distance": 1740, "origin_city": "Bengaluru", "destination_city": "Delhi"},
    "DEL-GOA": {"origin": "DEL", "destination": "GOI", "base_fare": 5250, "weight": 0.030, "distance": 1810, "origin_city": "Delhi", "destination_city": "Goa"},
    "BOM-GOA": {"origin": "BOM", "destination": "GOI", "base_fare": 4950, "weight": 0.034, "distance": 480, "origin_city": "Mumbai", "destination_city": "Goa"},
    "MAA-BLR": {"origin": "MAA", "destination": "BLR", "base_fare": 3150, "weight": 0.040, "distance": 290, "origin_city": "Chennai", "destination_city": "Bengaluru"},
    "BLR-MAA": {"origin": "BLR", "destination": "MAA", "base_fare": 3100, "weight": 0.039, "distance": 290, "origin_city": "Bengaluru", "destination_city": "Chennai"},
    "DEL-AMD": {"origin": "DEL", "destination": "AMD", "base_fare": 4850, "weight": 0.028, "distance": 930, "origin_city": "Delhi", "destination_city": "Ahmedabad"},
    "CCU-DEL": {"origin": "CCU", "destination": "DEL", "base_fare": 5900, "weight": 0.043, "distance": 1320, "origin_city": "Kolkata", "destination_city": "Delhi"},
    "BOM-HYD": {"origin": "BOM", "destination": "HYD", "base_fare": 4300, "weight": 0.036, "distance": 640, "origin_city": "Mumbai", "destination_city": "Hyderabad"},
    "HYD-BOM": {"origin": "HYD", "destination": "BOM", "base_fare": 4400, "weight": 0.035, "distance": 640, "origin_city": "Hyderabad", "destination_city": "Mumbai"},
    "DEL-COK": {"origin": "DEL", "destination": "COK", "base_fare": 6450, "weight": 0.024, "distance": 2350, "origin_city": "Delhi", "destination_city": "Kochi"},
    "BOM-COK": {"origin": "BOM", "destination": "COK", "base_fare": 6150, "weight": 0.022, "distance": 1220, "origin_city": "Mumbai", "destination_city": "Kochi"},
    "CCU-BOM": {"origin": "CCU", "destination": "BOM", "base_fare": 6000, "weight": 0.026, "distance": 1660, "origin_city": "Kolkata", "destination_city": "Mumbai"},
    "DEL-JAI": {"origin": "DEL", "destination": "JAI", "base_fare": 3900, "weight": 0.027, "distance": 270, "origin_city": "Delhi", "destination_city": "Jaipur"},
    "BOM-JAI": {"origin": "BOM", "destination": "JAI", "base_fare": 4150, "weight": 0.022, "distance": 820, "origin_city": "Mumbai", "destination_city": "Jaipur"},
}

# Airline catalogue. ``factor`` is the relative price positioning used by the
# demo generator (a stand-in for a real airline observation model).
# ``alliance`` is purely descriptive for the airline analysis screen.
AIRLINES: dict[str, dict] = {
    "6E": {"name": "IndiGo", "factor": 1.00, "alliance": "Low-cost", "hub": "DEL"},
    "AI": {"name": "Air India", "factor": 1.16, "alliance": "Full-service", "hub": "DEL"},
    "SG": {"name": "SpiceJet", "factor": 0.92, "alliance": "Low-cost", "hub": "DEL"},
    "UK": {"name": "Vistara", "factor": 1.22, "alliance": "Full-service", "hub": "DEL"},
    "G8": {"name": "Go First", "factor": 0.88, "alliance": "Low-cost", "hub": "BOM"},
    "QP": {"name": "Akasa Air", "factor": 0.95, "alliance": "Low-cost", "hub": "BOM"},
    "I5": {"name": "AirAsia India", "factor": 0.90, "alliance": "Low-cost", "hub": "BLR"},
}

# Which airlines serve which route (rough, realistic). Route keys as above.
ROUTE_AIRLINES: dict[str, list[str]] = {
    "DEL-BOM": ["6E", "AI", "UK", "SG"],
    "BOM-DEL": ["6E", "AI", "UK", "SG"],
    "DEL-BLR": ["6E", "AI", "UK", "I5"],
    "BOM-BLR": ["6E", "AI", "QP", "I5"],
    "DEL-CCU": ["6E", "AI", "SG"],
    "MAA-DEL": ["6E", "AI", "UK", "I5"],
    "DEL-HYD": ["6E", "AI", "SG", "I5"],
    "BOM-MAA": ["6E", "AI", "UK"],
    "BLR-HYD": ["6E", "I5", "AI", "QP"],
    "HYD-BLR": ["6E", "I5", "AI", "QP"],
    "BLR-DEL": ["6E", "AI", "UK", "I5"],
    "DEL-GOA": ["6E", "AI", "SG", "QP"],
    "BOM-GOA": ["6E", "SG", "UK", "QP"],
    "MAA-BLR": ["6E", "AI", "I5"],
    "BLR-MAA": ["6E", "AI", "I5"],
    "DEL-AMD": ["6E", "AI", "SG"],
    "CCU-DEL": ["6E", "AI", "SG"],
    "BOM-HYD": ["6E", "AI", "UK", "QP"],
    "HYD-BOM": ["6E", "AI", "UK", "QP"],
    "DEL-COK": ["6E", "AI", "UK"],
    "BOM-COK": ["6E", "AI", "I5"],
    "CCU-BOM": ["6E", "AI", "SG", "QP"],
    "DEL-JAI": ["6E", "AI", "SG"],
    "BOM-JAI": ["6E", "AI", "QP"],
}

# Sources feeding the pipeline. ``status`` mirrors the collection monitor:
#   healthy  -> actively collecting (mock, deterministic payloads)
#   degraded -> collecting but with intermittent failures
#   disabled -> stopped (compliance / policy / paused) — NEVER presented as live
#   ready    -> configured but not yet live (no data emitted)
# ``adapter`` names the collection adapter class pattern in the real engine.
SOURCES: dict[str, dict] = {
    "mock": {
        "id": "mock",
        "name": "Mock Source",
        "type": "synthetic",
        "status": "healthy",
        "adapter": "MockAdapter",
        "compliance": "authorized",
        "base_capacity": 38200,
    },
    "ota_a": {
        "id": "ota_a",
        "name": "Mock OTA A",
        "type": "ota",
        "status": "healthy",
        "adapter": "OtaAdapterA",
        "compliance": "authorized",
        "base_capacity": 14100,
    },
    "ota_b": {
        "id": "ota_b",
        "name": "Mock OTA B",
        "type": "ota",
        "status": "healthy",
        "adapter": "OtaAdapterB",
        "compliance": "authorized",
        "base_capacity": 11800,
    },
    "airline_direct": {
        "id": "airline_direct",
        "name": "Mock Airline Direct",
        "type": "airline",
        "status": "healthy",
        "adapter": "AirlineDirectAdapter",
        "compliance": "authorized",
        "base_capacity": 7400,
    },
    "ota_c": {
        "id": "ota_c",
        "name": "Mock OTA C",
        "type": "ota",
        "status": "degraded",
        "adapter": "OtaAdapterC",
        "compliance": "authorized",
        "base_capacity": 6900,
    },
    "ixigo": {
        "id": "ixigo",
        "name": "Ixigo",
        "type": "ota",
        "status": "disabled",
        "adapter": "IxigoAdapter",
        "compliance": "policy_gated",
        "base_capacity": 0,
    },
    "ota_d": {
        "id": "ota_d",
        "name": "Mock OTA D (Planned)",
        "type": "ota",
        "status": "ready",
        "adapter": "OtaAdapterD",
        "compliance": "authorized",
        "base_capacity": 0,
    },
}

# Active sources that actually emit observations in the demo.
ACTIVE_SOURCE_IDS = ["mock", "ota_a", "ota_b", "airline_direct", "ota_c"]

# Advancing-booking lead times measured in days.
LEAD_TIMES = [1, 3, 7, 15, 30, 45]

# Lead-time price multiplier (T+1 most expensive -> T+45 least expensive).
LEAD_FACTOR = {1: 1.46, 3: 1.36, 7: 1.22, 15: 1.10, 30: 1.02, 45: 1.00}


# --------------------------------------------------------------------------- #
# Observation model (canonical fare)
# --------------------------------------------------------------------------- #

@dataclass
class Observation:
    observation_id: str
    source: str
    origin: str
    destination: str
    route: str
    departure_date: str            # YYYY-MM-DD of the quoted flight
    collection_date: str           # YYYY-MM-DD when the fare was observed
    collection_timestamp: str      # ISO datetime of the observation
    airline: str
    flight_number: Optional[str]
    cabin: str
    fare_class: Optional[str]
    lead_time_days: int
    base_fare: float
    taxes: float
    fees: float
    total_fare: float
    currency: str
    availability: str
    seats_remaining: Optional[int]
    raw_payload_reference: str
    fingerprint: str
    quality_status: str            # VALID | SUSPICIOUS | INVALID | DUPLICATE | SOLD_OUT | STALE | MISSING
    quality_score: float
    exclusion_reason: Optional[str]

    def as_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "source": self.source,
            "origin": self.origin,
            "destination": self.destination,
            "route": self.route,
            "departure_date": self.departure_date,
            "collection_date": self.collection_date,
            "collection_timestamp": self.collection_timestamp,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "cabin": self.cabin,
            "fare_class": self.fare_class,
            "lead_time_days": self.lead_time_days,
            "base_fare": round(self.base_fare, 2),
            "taxes": round(self.taxes, 2),
            "fees": round(self.fees, 2),
            "total_fare": round(self.total_fare, 2),
            "currency": self.currency,
            "availability": self.availability,
            "seats_remaining": self.seats_remaining,
            "raw_payload_reference": self.raw_payload_reference,
            "fingerprint": self.fingerprint,
            "quality_status": self.quality_status,
            "quality_score": round(self.quality_score, 2),
            "exclusion_reason": self.exclusion_reason,
        }


# --------------------------------------------------------------------------- #
# Deterministic pseudo-random helpers
# --------------------------------------------------------------------------- #

def _hash_seed(*parts: object) -> int:
    """Derive a stable integer seed from arbitrary string parts."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8"))
    return int.from_bytes(h.digest()[:8], "big")


def _rng(*parts: object) -> random.Random:
    return random.Random(_hash_seed(*parts))


# --------------------------------------------------------------------------- #
# Dataset builder
# --------------------------------------------------------------------------- #

@dataclass
class Dataset:
    """In-memory store of the dataset and precomputed aggregates.

    Populated either by the deterministic demo generator or by the live
    collection engine (see ``app.collect.live.build_live_dataset``). The engine
    layer only reads these fields, so both paths feed identical screens.
    """

    end_date: dt.date
    base_period_start: dt.date
    base_period_end: dt.date
    #: 'demo' | 'live' — drives the badge and the disclaimer text.
    origin: str = "demo"
    #: every collection date that has data, ascending (live data can have gaps)
    dates: list[str] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    # (route, date) -> representative price + sample metadata
    route_day: dict[tuple[str, str], dict] = field(default_factory=dict)
    # date -> APIx level
    daily_apix: dict[str, float] = field(default_factory=dict)
    # route -> list of (date, route_index) sorted by date
    daily_apix_by_route: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    # route -> base price + weight
    route_meta: dict[str, dict] = field(default_factory=dict)

    # Derived caches
    _quality_breakdown: Optional[dict] = field(default=None, repr=False)


def _build_reference_airline_factor(route: str) -> dict[str, float]:
    """Stable per-airline factor for a route (slightly jittered, deterministic)."""
    out: dict[str, float] = {}
    for code in ROUTE_AIRLINES[route]:
        base = AIRLINES[code]["factor"]
        jitter = _rng(route, code, "factor").uniform(-0.03, 0.03)
        out[code] = max(0.70, base + jitter)
    return out


def build_dataset() -> Dataset:
    """Generate the deterministic demo dataset for ``settings.demo_history_days``.

    Returns a fully-populated :class:`Dataset` ready for the API layer.
    """
    days = settings.demo_history_days
    end = dt.date(2026, 9, 6)  # "today" in the demo timeline
    start = end - dt.timedelta(days=days - 1)

    # Robust "today" anchor: use UTC date if it is within a sane range, else the
    # demo anchor. The demo anchor keeps the dataset stable for screenshots.
    today = dt.date.today()
    if start <= today <= end:
        end = today
        start = end - dt.timedelta(days=days - 1)

    # Base period = the first 7 days of the window.
    base_start = start
    base_end = start + dt.timedelta(days=6)

    ds = Dataset(
        end_date=end,
        base_period_start=base_start,
        base_period_end=base_end,
    )

    # Pre-compute per-route reference price level trend.
    route_trend = {r: _rng(r, "trend").uniform(0.0006, 0.0018) for r in ROUTES}
    route_vol = {r: _rng(r, "vol").uniform(0.03, 0.10) for r in ROUTES}

    # Anomalous spike windows per route (to make the story interesting).
    # (route, day_offset_from_end, multiplier). Magnitudes are kept modest so
    # the headline index stays in a realistic band while route-level anomalies
    # remain clearly visible.
    spike_events = {
        "DEL-BOM": [(-3, 0.14), (-12, 0.10)],
        "BOM-DEL": [(-4, 0.12)],
        "DEL-BLR": [(-6, 0.11), (-40, 0.08)],
        "BLR-DEL": [(-9, 0.10)],
        "MAA-DEL": [(-20, 0.09)],
        "DEL-CCU": [(-15, 0.10)],
        "DEL-GOA": [(-14, 0.20), (-5, 0.13)],
        "BOM-GOA": [(-16, 0.18)],
    }

    obs_list: list[Observation] = []
    seq = 0

    # Build the daily calendar once.
    day_index = 0
    current = start
    while current <= end:
        day_offset = day_index  # 0..days-1
        date_str = current.isoformat()

        for route in ROUTES:
            meta = ROUTES[route]
            airlines = ROUTE_AIRLINES[route]
            air_factor = _build_reference_airline_factor(route)

            # A per-route seasonal multiplier (mild weekend effect + annual wave).
            dow = current.weekday()
            weekend_boost = 1.015 if dow in (4, 5) else 1.0  # Fri/Sat departures
            seasonal = 1.0 + 0.06 * ((day_offset / days) - 0.5)

            # Anomalous spike for this route/day.
            spike_mult = 1.0
            for (off, mult) in spike_events.get(route, []):
                if day_index - off >= 0 and day_index - off < days:
                    # Only apply on the matching date
                    pass
            # Determine a route-level total day multiplier including spikes.
            day_spike = 1.0
            for (off, mult) in spike_events.get(route, []):
                # offset is negative relative to end; convert to absolute day index
                abs_off = (days - 1) + off
                if abs_off == day_index:
                    day_spike = 1.0 + mult

            for airline in airlines:
                af = air_factor[airline]
                for lead in LEAD_TIMES:
                    lf = LEAD_FACTOR[lead]
                    # deterministic per-cell noise
                    r = _rng(route, date_str, airline, lead)
                    noise = r.uniform(-0.06, 0.06)
                    # price level grows with time (inflation) + route-specific trend
                    trend_component = (1.0 + route_trend[route] * day_offset)

                    representative = (
                        meta["base_fare"]
                        * af
                        * lf
                        * weekend_boost
                        * seasonal
                        * trend_component
                        * (1.0 + noise)
                        * day_spike
                    )

                    # Occasionally a route goes through an "outlier" cell
                    # (e.g. a last-seat fare) that the quality engine flags.
                    outlier_p = r.random()
                    is_outlier = outlier_p < 0.045
                    if is_outlier:
                        representative *= r.uniform(1.25, 1.55)

                    # Lead-time-dependent volatility: short lead-times move more.
                    vol_component = route_vol[route] * (1.0 + (7 - lead) / 45.0 * 0.4)

                    # Emit a canonical observation from a primary source, then a
                    # second source observation for a subset (to model multi-source
                    # duplication / discrepancy).
                    primary = ACTIVE_SOURCE_IDS[seq % len(ACTIVE_SOURCE_IDS)]
                    secondary = ACTIVE_SOURCE_IDS[(seq + 2) % len(ACTIVE_SOURCE_IDS)]

                    primary_obs = _make_observation(
                        ds, route, current, date_str, day_offset, airline, lead,
                        representative, vol_component, primary, seq, is_outlier, r,
                    )
                    obs_list.append(primary_obs)
                    seq += 1

                    # Second source observation for ~55% of cells.
                    if r.random() < 0.55:
                        # Different source quotes a slightly different (but close) fare.
                        src_representative = representative * (1.0 + r.uniform(-0.05, 0.05))
                        dup = r.random() < 0.10
                        sec_obs = _make_observation(
                            ds, route, current, date_str, day_offset, airline, lead,
                            src_representative, vol_component, secondary, seq, is_outlier, r,
                            is_duplicate_of=primary_obs,
                        )
                        obs_list.append(sec_obs)
                        seq += 1

        current += dt.timedelta(days=1)
        day_index += 1

    ds.observations = obs_list
    _finalize_aggregates(ds, start, end, base_start, base_end)
    return ds


def _make_observation(
    ds: Dataset,
    route: str,
    date: dt.date,
    date_str: str,
    day_offset: int,
    airline: str,
    lead: int,
    representative: float,
    vol_component: float,
    source_id: str,
    seq: int,
    is_outlier: bool,
    rng: random.Random,
    is_duplicate_of: Optional[Observation] = None,
) -> Observation:
    meta = ROUTES[route]

    # Split headline fare into components.
    total = representative
    base = total * 0.78
    taxes = total * 0.16
    fees = total * 0.06

    departure = date + dt.timedelta(days=lead)
    departure_str = departure.isoformat()

    # Collection time of day (deterministic per source).
    hour = 8 + (seq % 9)
    minute = (seq * 7) % 60
    ts = f"{date_str}T{hour:02d}:{minute:02d}:00+05:30"

    flight_number = f"{airline}{100 + (seq % 880):03d}"
    fare_class = rng.choice(["E", "E", "E", "L", "M", "V", "K", "B"])

    # Determine quality status.
    status = "VALID"
    exclusion = None
    if is_outlier:
        status = "SUSPICIOUS"
        exclusion = "flag:statistical_outlier"
    elif rng.random() < 0.012:
        status = "INVALID"
        exclusion = "flag:invalid_payload"
    elif rng.random() < 0.008:
        status = "SOLD_OUT"
        availability = "SOLD_OUT"
        seats = 0
        status = "SOLD_OUT"
        exclusion = "flag:sold_out"
        base = total * 0.7
    elif rng.random() < 0.015:
        status = "STALE"
        exclusion = "flag:stale_cached_fare"
    else:
        availability = rng.choice(["AVAILABLE", "AVAILABLE", "AVAILABLE", "LIMITED"])
        seats = rng.randint(1, 9) if availability == "LIMITED" else rng.randint(9, 40)

    availability = "AVAILABLE"
    if status != "SOLD_OUT":
        availability = rng.choice(["AVAILABLE", "AVAILABLE", "AVAILABLE", "LIMITED"])
        seats = rng.randint(1, 9) if availability == "LIMITED" else rng.randint(9, 40)
    else:
        availability = "SOLD_OUT"
        seats = 0

    # Duplicate handling: an observation that is a near-identical re-emission of
    # an already-collected canonical fare from a different source.
    if is_duplicate_of is not None and status == "VALID" and rng.random() < 0.10:
        status = "DUPLICATE"
        exclusion = "flag:duplicate_fingerprint"
        # A duplicate keeps its own total but is not used in the index.

    quality_score = _quality_score(status, rng)

    return Observation(
        observation_id=f"obs-{seq:07d}",
        source=source_id,
        origin=meta["origin"],
        destination=meta["destination"],
        route=route,
        departure_date=departure_str,
        collection_date=date_str,
        collection_timestamp=ts,
        airline=airline,
        flight_number=flight_number,
        cabin="ECONOMY",
        fare_class=fare_class,
        lead_time_days=lead,
        base_fare=round(base, 2),
        taxes=round(taxes, 2),
        fees=round(fees, 2),
        total_fare=round(total, 2),
        currency="INR",
        availability=availability,
        seats_remaining=seats,
        raw_payload_reference=f"raw:{source_id}:{date_str}:{route}:{airline}:{lead}:{seq}",
        fingerprint=_fingerprint(source_id, route, departure_str, airline, flight_number, fare_class, total),
        quality_status=status,
        quality_score=quality_score,
        exclusion_reason=exclusion,
    )


def _quality_score(status: str, rng: random.Random) -> float:
    base = {
        "VALID": rng.uniform(0.96, 0.999),
        "SUSPICIOUS": rng.uniform(0.45, 0.62),
        "DUPLICATE": rng.uniform(0.40, 0.58),
        "INVALID": rng.uniform(0.0, 0.2),
        "SOLD_OUT": rng.uniform(0.30, 0.5),
        "STALE": rng.uniform(0.25, 0.45),
        "MISSING": 0.0,
    }.get(status, 0.3)
    return max(0.0, min(1.0, base))


def _fingerprint(source: str, route: str, dep: str, airline: str, flight: str, cls: str, total: float) -> str:
    """Stable fingerprint for the canonical fare.

    Dimensions included: source, route, departure date, airline, flight,
    fare class and the rounded normalised fare. Different sources intentionally
    produce *different* fingerprints for the same underlying itinerary; the
    dedup logic therefore matches on itinerary + normalised fare + collection
    context rather than on fingerprint equality alone.
    """
    payload = f"{source}|{route}|{dep}|{airline}|{flight}|{cls}|{round(total, 0)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Aggregation helpers
# --------------------------------------------------------------------------- #

def _finalize_aggregates(
    ds: Dataset,
    start: dt.date,
    end: dt.date,
    base_start: dt.date,
    base_end: dt.date,
    index_routes: Optional[list[str]] = None,
) -> None:
    """Compute route-day prices, base values, per-route and aggregate indices.

    Shared by both dataset builders. ``index_routes`` lets a live dataset restrict
    the basket to routes it actually has observations for, instead of emitting
    100.0 for routes with no data.
    """
    # Routes that are "used in the index" (those with enough data).
    index_routes = list(index_routes) if index_routes is not None else list(ROUTES.keys())

    # Keep weights summing to 1 over the index routes.
    total_weight = sum(ROUTES[r]["weight"] for r in index_routes)
    weights = {r: ROUTES[r]["weight"] / total_weight for r in index_routes}

    # Group included observations (index-eligible) by (route, collection_date).
    raw_route_day: dict[tuple[str, str], list[Observation]] = {}
    for obs in ds.observations:
        if obs.quality_status in ("VALID", "SUSPICIOUS"):
            key = (obs.route, obs.collection_date)
            raw_route_day.setdefault(key, []).append(obs)

    # Representative route-day price = median of included fares.
    route_day_price: dict[tuple[str, str], float] = {}
    route_day_meta: dict[tuple[str, str], dict] = {}
    for (route, d), obs_list in raw_route_day.items():
        fares = sorted(o.total_fare for o in obs_list)
        if not fares:
            continue
        med = _median(fares)
        route_day_price[(route, d)] = med
        route_day_meta[(route, d)] = {
            "price": med,
            "observations": len(obs_list),
            "quality": round(sum(o.quality_score for o in obs_list) / len(obs_list), 4),
            "airlines": len({o.airline for o in obs_list}),
        }

    ds.route_day = {(r, d): {"price": med, **_meta} for (r, d), med in route_day_price.items()
                     for _meta in [route_day_meta[(r, d)]]}

    # Base price for each route = mean of route-day prices over base period.
    base_price: dict[str, float] = {}
    for route in index_routes:
        bvals = []
        d = base_start
        while d <= base_end:
            v = route_day_price.get((route, d.isoformat()))
            if v is not None:
                bvals.append(v)
            d += dt.timedelta(days=1)
        if bvals:
            base_price[route] = sum(bvals) / len(bvals)
        else:
            base_price[route] = ROUTES[route]["base_fare"]

    ds.route_meta = {
        r: {
            "base_price": round(base_price[r], 2),
            "weight": round(weights[r], 4),
            "raw_weight": ROUTES[r]["weight"],
        }
        for r in index_routes
    }

    # Per-day APIx.
    current = start
    route_index_by_route: dict[str, list[tuple[str, float]]] = {r: [] for r in index_routes}
    while current <= end:
        d = current.isoformat()
        # route indices for this day
        route_idx: dict[str, float] = {}
        for route in index_routes:
            price = route_day_price.get((route, d))
            if price is None:
                continue
            route_idx[route] = 100.0 * price / base_price[route]
        if route_idx:
            api = sum(weights[r] * route_idx[r] for r in route_idx)
            ds.daily_apix[d] = api
            # normalised route index (for plotting) — relative to its own base
            for r, idx in route_idx.items():
                route_index_by_route[r].append((d, round(idx, 4)))
        current += dt.timedelta(days=1)

    ds.daily_apix_by_route = route_index_by_route
    ds.dates = sorted(ds.daily_apix.keys())


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous in (None, 0):
        return None
    return round((current - previous) / previous * 100.0, 2)


# --------------------------------------------------------------------------- #
# Singleton store — built once at import time (FastAPI startup dependency).
# --------------------------------------------------------------------------- #

_dataset: Optional[Dataset] = None
_live_dataset: Optional[Dataset] = None
_live_signature: Optional[tuple] = None


def get_dataset() -> Dataset:
    """Return the active dataset for the current data-source mode.

    ``demo`` mode serves the deterministic synthetic store. ``live`` mode serves
    whatever the collection engine has actually stored — and rebuilds it only
    when the stored data changed (each sweep bumps the signature). If live mode
    has no data yet we fall back to demo and say so, rather than rendering an
    empty dashboard with no explanation.
    """
    global _dataset, _live_dataset, _live_signature

    try:  # lazy import: the collector imports this module, not vice versa
        from .collect.service import collection_service

        mode = collection_service.mode
    except Exception:
        mode = "demo"

    if mode == "live":
        from .live import live_signature, build_live_dataset

        sig = live_signature()
        if sig is not None and (_live_dataset is None or _live_signature != sig):
            _live_dataset = build_live_dataset()
        if _live_dataset is not None and _live_dataset.observations:
            return _live_dataset

    if _dataset is None:
        _dataset = build_dataset()
    return _dataset


def dataset_mode() -> str:
    """'live' only when live mode is selected AND data exists, else 'demo'."""
    return get_dataset().origin


def invalidate_live_cache() -> None:
    """Force the live view to be rebuilt on the next request."""
    global _live_dataset, _live_signature
    _live_dataset = None
    _live_signature = None
