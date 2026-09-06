"""Raw payload -> canonical observation, with the quality gate applied.

The collector never trusts a source. Every offer goes through the same
validation the demo generator's output goes through, so a live observation and a
synthetic one are indistinguishable downstream. That is the whole reason the
index layer could stay source-agnostic.

Quality statuses (shared with the demo pipeline):
    VALID        passed every check; enters the index
    SUSPICIOUS   price deviates hard from the route's recent level; kept for
                 display, excluded from the index
    DUPLICATE    same itinerary fingerprint already stored for this day
    INVALID        structurally broken (missing fields, non-positive fare,
                 departure before the collection date, foreign currency)
    SOLD_OUT   source reported no seats
    STALE      payload carried a cached/older timestamp than the sweep
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ..dataset import ROUTES
from .base import Query, RawOffer

#: deviation from the route's recent median fare above which an observation is
#: treated as a statistical outlier rather than a real market move.
OUTLIER_ABS = 0.45
OUTLIER_ROBUST_MAD = 6.0

STALE_HOURS = 20.0
KNOWN_CURRENCIES = {"INR"}


@dataclass
class QualityContext:
    """Everything needed to judge an observation against what we already hold.

    ``route_medians`` maps route -> recent representative fare (from the store).
    ``seen_fingerprints`` holds fingerprints already stored for this collection
    day, so a re-sweep does not double-count the same itinerary.
    """

    route_medians: dict[str, float]
    seen_fingerprints: set[str]
    collection_date: str
    collection_timestamp: str
    #: unique per sweep. Observation ids embed it, so a second collection of the
    #: same day is stored as a new observation instead of being silently dropped
    #: by the UNIQUE constraint — while true repeats are still caught by
    #: ``seen_fingerprints`` below and flagged DUPLICATE.
    batch_tag: str = ""

    @staticmethod
    def build(
        collection_date: str,
        route_medians: dict[str, float],
        seen: Iterable[str],
        batch_tag: str = "",
    ) -> "QualityContext":
        return QualityContext(
            route_medians=dict(route_medians),
            seen_fingerprints=set(seen),
            collection_date=collection_date,
            collection_timestamp=f"{collection_date}T{dt.datetime.now().strftime('%H:%M:%S')}+05:30",
            batch_tag=batch_tag,
        )


def fingerprint(source: str, route: str, dep: str, airline: str, flight: Any, cls: Any, total: float) -> str:
    payload = f"{source}|{route}|{dep}|{airline}|{flight}|{cls}|{round(total, 0)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _route_key(origin: str, destination: str) -> str:
    return f"{origin}-{destination}"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_offer(offer: RawOffer, query: Query, ctx: QualityContext, seq: int) -> dict[str, Any]:
    """Return a canonical observation dict (ready for the store) + status."""
    p = offer.payload or {}
    origin = str(p.get("origin") or query.origin).upper()
    destination = str(p.get("destination") or query.destination).upper()
    route = _route_key(origin, destination)
    currency = str(p.get("currency") or "INR").upper()

    total = _as_float(p.get("total_fare"))
    base = _as_float(p.get("base_fare")) or total
    taxes = _as_float(p.get("taxes"))
    fees = _as_float(p.get("fees"))

    dep_raw = str(p.get("departure_date") or query.departure_date.isoformat())[:10]
    try:
        dep_date = dt.date.fromisoformat(dep_raw)
    except ValueError:
        dep_date = query.departure_date
    collect_date = dt.date.fromisoformat(ctx.collection_date)
    lead = (dep_date - collect_date).days

    availability = str(p.get("availability") or "AVAILABLE").upper()
    seats = p.get("seats_remaining")
    seats = int(seats) if isinstance(seats, (int, float)) else None
    if seats == 0:
        availability = "SOLD_OUT"

    fp = fingerprint(
        offer.source, route, dep_date.isoformat(), str(p.get("airline") or "NA"),
        p.get("flight_number"), p.get("fare_class"), total,
    )

    obs: dict[str, Any] = {
        "observation_id": f"live-{offer.source}-{ctx.collection_date}-{ctx.batch_tag}-{seq:06d}",
        "source": offer.source,
        "origin": origin,
        "destination": destination,
        "route": route,
        "departure_date": dep_date.isoformat(),
        "collection_date": ctx.collection_date,
        "collection_timestamp": offer.fetched_at or ctx.collection_timestamp,
        "airline": str(p.get("airline") or "NA").upper(),
        "flight_number": p.get("flight_number"),
        "cabin": str(p.get("cabin") or "ECONOMY").upper(),
        "fare_class": p.get("fare_class") or None,
        "lead_time_days": lead,
        "base_fare": round(base, 2),
        "taxes": round(taxes, 2),
        "fees": round(fees, 2),
        "total_fare": round(total, 2),
        "currency": currency,
        "availability": availability,
        "seats_remaining": seats,
        "raw_payload_reference": offer.url or f"raw:{offer.source}:{ctx.collection_date}:{route}:{seq}",
        "fingerprint": fp,
        "in_basket": route in ROUTES,
    }

    obs["quality_status"], obs["exclusion_reason"] = _assess(obs, fp, ctx)
    obs["quality_score"] = _quality_score(obs["quality_status"])
    return obs


def _assess(obs: dict[str, Any], fp: str, ctx: QualityContext) -> tuple[str, Optional[str]]:
    # --- structural ------------------------------------------------------- #
    if not obs["origin"] or not obs["destination"] or obs["origin"] == obs["destination"]:
        return "INVALID", "flag:malformed_route"
    if obs["currency"] not in KNOWN_CURRENCIES:
        return "INVALID", f"flag:unsupported_currency:{obs['currency']}"
    if obs["lead_time_days"] < 0:
        return "INVALID", "flag:departure_before_collection"

    # --- market state, checked *before* the fare sanity rules --------------
    # A sold-out offer legitimately has no price, so "price missing" here is a
    # market fact, not a collection defect. Classifying it INVALID would inflate
    # the failure rate on the quality screen and hide real parse errors in it.
    if obs["availability"] == "SOLD_OUT" or obs["seats_remaining"] == 0:
        return "SOLD_OUT", "flag:sold_out"
    if obs["total_fare"] <= 0:
        return "INVALID", "flag:non_positive_fare"
    if obs["total_fare"] > 500_000:
        return "INVALID", "flag:implausible_fare_magnitude"
    # base + components should reconcile with the total, loosely
    components = obs["base_fare"] + obs["taxes"] + obs["fees"]
    if obs["base_fare"] > 0 and components > obs["total_fare"] * 1.6:
        return "SUSPICIOUS", "flag:fare_components_inconsistent"

    # --- freshness -------------------------------------------------------- #
    if _is_stale(obs["collection_timestamp"]):
        return "STALE", "flag:stale_cached_fare"

    # --- duplication ------------------------------------------------------ #
    if fp in ctx.seen_fingerprints:
        return "DUPLICATE", "flag:duplicate_fingerprint"

    # --- outlier vs the route's own recent level -------------------------- #
    ref = ctx.route_medians.get(obs["route"])
    if ref:
        deviation = abs(obs["total_fare"] - ref) / ref
        if deviation > OUTLIER_ABS:
            return "SUSPICIOUS", f"flag:statistical_outlier(dev={deviation:.2f},ref={ref:.0f})"

    return "VALID", None


def _is_stale(ts: str) -> bool:
    if not ts:
        return False
    try:
        parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = dt.datetime.now(parsed.tzinfo)
    return (now - parsed).total_seconds() > STALE_HOURS * 3600.0


def _quality_score(status: str) -> float:
    return {
        "VALID": 0.99,
        "SUSPICIOUS": 0.55,
        "DUPLICATE": 0.5,
        "INVALID": 0.05,
        "SOLD_OUT": 0.4,
        "STALE": 0.35,
    }.get(status, 0.3)


def dedupe_within_batch(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Second pass: mark repeats inside one batch before they hit the store."""
    seen = set()
    for obs in observations:
        fp = obs["fingerprint"]
        if fp in seen and obs["quality_status"] == "VALID":
            obs["quality_status"] = "DUPLICATE"
            obs["exclusion_reason"] = "flag:duplicate_fingerprint_in_batch"
            obs["quality_score"] = _quality_score("DUPLICATE")
        seen.add(fp)
    return observations


def robust_level(values: list[float]) -> Optional[float]:
    """Median, guarded against an all-outlier batch. Used to seed route levels."""
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
