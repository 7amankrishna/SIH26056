"""Index engine — deterministic views computed from the demo dataset.

Every function here derives an analytical aggregate from the stored
observations. The calculations are intentionally transparent and reproducible
so the methodology page can describe them exactly:

    Price(r, t)   = median(valid fares for route r on day t)
    Base(r)       = mean(Price(r, t)) over the base period
    RouteIndex    = 100 * Price(r, t) / Base(r)
    APIx(t)       = sum(w_r * RouteIndex(r, t))

Missing observations are never silently replaced with zero-price fares.
Sold-out / invalid / duplicate / stale observations are excluded from the
index but remain available for audit via the provenance path.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Optional

from .dataset import (
    AIRLINES,
    LEAD_TIMES,
    LEAD_FACTOR,
    ROUTES,
    SOURCES,
    ACTIVE_SOURCE_IDS,
    Dataset,
    get_dataset,
)

# Proportion of the recent window treated as "current" for movement figures.
_CURRENT_WINDOW = 1


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _serie(ds: Dataset) -> list[tuple[str, float]]:
    """(date, api) series ordered by date."""
    return sorted(ds.daily_apix.items(), key=lambda kv: kv[0])


def _api_on(ds: Dataset, d: str) -> Optional[float]:
    return ds.daily_apix.get(d)


def _last_n_days(ds: Dataset) -> list[str]:
    """All dates in the dataset window as ISO strings (ordered)."""
    if not ds.daily_apix:
        return []
    start = ds.end_date - dt.timedelta(days=len(ds.daily_apix) - 1)
    return [
        (start + dt.timedelta(days=i)).isoformat()
        for i in range(len(ds.daily_apix))
    ]


def _route_index(ds: Dataset, route: str, d: str) -> Optional[float]:
    mapping = {x[0]: x[1] for x in ds.daily_apix_by_route.get(route, [])}
    return mapping.get(d)


def _route_day_price(ds: Dataset, route: str, d: str) -> Optional[dict]:
    return ds.route_day.get((route, d))


def _change_pct(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev in (None, 0):
        return None
    return round((cur - prev) / prev * 100.0, 2)


def _aggregate_window(ds: Dataset, end: str, days: int) -> Optional[float]:
    """Average APIx over the window ending at ``end`` (inclusive)."""
    start_dt = dt.date.fromisoformat(end) - dt.timedelta(days=days - 1)
    vals = []
    d = start_dt
    while d <= dt.date.fromisoformat(end):
        v = ds.daily_apix.get(d.isoformat())
        if v is not None:
            vals.append(v)
        d += dt.timedelta(days=1)
    if not vals:
        return None
    return sum(vals) / len(vals)


# --------------------------------------------------------------------------- #
# Overview / KPIs
# --------------------------------------------------------------------------- #

def overview(ds: Dataset) -> dict[str, Any]:
    dates = _last_n_days(ds)
    last = dates[-1]

    current_api = ds.daily_apix.get(last)
    prev_api = ds.daily_apix.get(dates[-2]) if len(dates) > 1 else None
    week_ago = ds.daily_apix.get(dates[-8]) if len(dates) > 8 else None
    month_ago = ds.daily_apix.get(dates[-31]) if len(dates) > 31 else None

    # observations in the most recent 24h window
    last_day_obs = [o for o in ds.observations if o.collection_date == last]
    route_count = len(DS_ROUTES_IN_INDEX)
    airline_count = len({o.airline for o in ds.observations})
    source_count = len({o.source for o in ds.observations if o.quality_status == "VALID"})

    quality = quality_summary(ds)

    last_collection = last
    last_run = SOURCES.get("mock", {})
    success_rate = 100.0

    return {
        "current_apix": round(current_api, 2) if current_api else None,
        "daily_change": _change_pct(current_api, prev_api),
        "weekly_change": _change_pct(current_api, week_ago),
        "monthly_change": _change_pct(current_api, month_ago),
        "observation_count": len(ds.observations),
        "valid_observation_count": sum(1 for o in ds.observations if o.quality_status in ("VALID", "SUSPICIOUS")),
        "route_count": route_count,
        "airline_count": airline_count,
        "source_count": source_count,
        "quality_score": round(quality["score"], 1),
        "last_collection": last_collection,
        "last_run_at": f"{last_collection}T09:10:00+05:30",
        "index_freshness": "fresh",
        "demo_mode": ds.demo_mode if hasattr(ds, "demo_mode") else True,
        "data_period": {"start": dates[0], "end": last},
        "base_period": {"start": ds.base_period_start.isoformat(), "end": ds.base_period_end.isoformat()},
        "methodology_version": "apix-1.0.0",
        "weight_version": "provisional-dgca-v0",
    }


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #

def trend(ds: Dataset, range_label: str = "90d", compare: Optional[str] = None) -> dict[str, Any]:
    total = len(ds.daily_apix)
    if range_label in ("7d", "30d", "90d", "6m", "1y"):
        n = {"7d": 7, "30d": 30, "90d": 90, "6m": 180, "1y": 365}[range_label]
    else:
        n = total

    dates = _last_n_days(ds)[-n:]
    series = []
    alldate = ds.daily_apix
    for i, d in enumerate(dates):
        cur = alldate.get(d)
        link = {
            "date": d,
            "apix": round(cur, 2) if cur is not None else None,
            "observations": sum(1 for o in ds.observations if o.collection_date == d),
            "routes": len({o.route for o in ds.observations if o.collection_date == d}),
        }
        if i > 0:
            prev = alldate.get(dates[i - 1])
            link["change"] = _change_pct(cur, prev)
        series.append(link)

    last_val = series[-1]["apix"] if series else None
    return {
        "range": range_label,
        "base_period": {"start": ds.base_period_start.isoformat(), "end": ds.base_period_end.isoformat()},
        "current": last_val,
        "change_7d": _change_pct(last_val, alldate.get(dates[-8]) if len(dates) > 8 else None),
        "change_30d": _change_pct(last_val, alldate.get(dates[-31]) if len(dates) > 31 else None),
        "methodology_version": "apix-1.0.0",
        "series": series,
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

def route_list(ds: Dataset, top: Optional[int] = None) -> list[dict[str, Any]]:
    dates = _last_n_days(ds)
    last = dates[-1]
    prev = dates[-7] if len(dates) > 7 else dates[0]
    week = dates[-8] if len(dates) > 8 else dates[0]

    out = []
    for route in DS_ROUTES_IN_INDEX:
        meta = ROUTES[route]
        price = _route_day_price(ds, route, last)
        price_prev = _route_day_price(ds, route, prev)
        day_price = _route_day_price(ds, route, dates[-2]) if len(dates) > 1 else None
        route_idx = _route_index(ds, route, last)

        change_24h = _change_pct(price["price"] if price else None,
                                 day_price["price"] if day_price else None)
        change_7d = _change_pct(price["price"] if price else None,
                                price_prev["price"] if price_prev else None)

        spark = _sparkline(ds, route, dates)

        out.append({
            "route": route,
            "origin": meta["origin"],
            "destination": meta["destination"],
            "origin_city": meta["origin_city"],
            "destination_city": meta["destination_city"],
            "current_fare": round(price["price"], 0) if price else None,
            "route_index": round(route_idx, 1) if route_idx else None,
            "change_24h": change_24h,
            "change_7d": change_7d,
            "base_price": ds.route_meta[route]["base_price"],
            "weight": ds.route_meta[route]["weight"],
            "observations": price["observations"] if price else 0,
            "quality": round(price["quality"] * 100, 1) if price else None,
            "airlines": price["airlines"] if price else 0,
            "sparkline": spark,
        })
    out.sort(key=lambda x: (x["change_7d"] if x["change_7d"] is not None else 0), reverse=True)
    if top:
        out = out[:top]
    return out


def _sparkline(ds: Dataset, route: str, dates: list[str]) -> list[float | None]:
    vals = []
    for d in dates[-14:]:
        p = _route_day_price(ds, route, d)
        vals.append(round(p["price"], 0) if p else None)
    return vals


def route_heatmap(ds: Dataset) -> list[dict[str, Any]]:
    return route_list(ds)


def route_detail(ds: Dataset, route: str) -> Optional[dict[str, Any]]:
    if route not in DS_ROUTES_IN_INDEX:
        return None
    dates = _last_n_days(ds)
    # Build route index series.
    series = []
    for d in dates:
        idx = _route_index(ds, route, d)
        price = _route_day_price(ds, route, d)
        if idx is None or price is None:
            continue
        series.append({
            "date": d,
            "route_index": round(idx, 2),
            "price": round(price["price"], 0),
            "observations": price["observations"],
            "change": _change_pct(idx, _route_index(ds, route, dates[dates.index(d) - 1])) if dates.index(d) > 0 else None,
        })

    # Airline distribution for this route on the last day.
    last = dates[-1]
    airline_rows = []
    for code, meta in AIRLINES.items():
        fares = [o.total_fare for o in ds.observations
                 if o.route == route and o.collection_date == last and o.airline == code
                 and o.quality_status in ("VALID", "SUSPICIOUS")]
        if fares:
            airline_rows.append({
                "airline": code,
                "name": meta["name"],
                "avg_fare": round(sum(fares) / len(fares), 0),
                "median_fare": round(_median(fares), 0),
                "observations": len(fares),
            })

    all_routes = route_list(ds)
    meta = next((r for r in all_routes if r["route"] == route), None)

    return {
        "route": route,
        "origin": ROUTES[route]["origin"],
        "destination": ROUTES[route]["destination"],
        "origin_city": ROUTES[route]["origin_city"],
        "destination_city": ROUTES[route]["destination_city"],
        "distance_km": ROUTES[route]["distance"],
        "base_price": ds.route_meta[route]["base_price"],
        "weight": ds.route_meta[route]["weight"],
        "meta": meta or {},
        "series": series,
        "airlines": airline_rows,
    }


# --------------------------------------------------------------------------- #
# Airlines
# --------------------------------------------------------------------------- #

def airline_analysis(ds: Dataset, route: Optional[str] = None) -> list[dict[str, Any]]:
    dates = _last_n_days(ds)
    last = dates[-1]
    out = []
    for code, meta in AIRLINES.items():
        obs = [o for o in ds.observations
               if o.airline == code
               and (route is None or o.route == route)
               and o.quality_status in ("VALID", "SUSPICIOUS")]
        if not obs:
            out.append({
                "airline": code, "name": meta["name"], "alliance": meta["alliance"], "hub": meta["hub"],
                "avg_fare": None, "median_fare": None, "observations": 0,
                "volatility": None, "index_contribution": None, "quality": None, "availability": 0.0,
            })
            continue
        fares = [o.total_fare for o in obs]
        # volatility = coefficient of variation of daily mean fares.
        daily = defaultdict(list)
        for o in obs:
            daily[o.collection_date].append(o.total_fare)
        daily_means = [sum(v) / len(v) for v in daily.values()]
        mean = sum(daily_means) / len(daily_means)
        sd = (sum((x - mean) ** 2 for x in daily_means) / len(daily_means)) ** 0.5 if daily_means else 0
        vol = (sd / mean * 100.0) if mean else None

        available = sum(1 for o in obs if o.availability == "AVAILABLE")
        contribution = _airline_contribution(ds, code)
        out.append({
            "airline": code,
            "name": meta["name"],
            "alliance": meta["alliance"],
            "hub": meta["hub"],
            "avg_fare": round(sum(fares) / len(fares), 0),
            "median_fare": round(_median(fares), 0),
            "observations": len(obs),
            "volatility": round(vol, 1) if vol else None,
            "index_contribution": contribution,
            "quality": round(sum(o.quality_score for o in obs) / len(obs) * 100, 1),
            "availability": round(available / len(obs) * 100, 1),
        })
    return out


def _airline_contribution(ds: Dataset, code: str) -> float:
    """Index contribution = weighted share of the airline's observed fares
    relative to the all-airline average on the current day."""
    dates = _last_n_days(ds)
    last = dates[-1]
    fares = [o.total_fare for o in ds.observations
             if o.collection_date == last and o.airline == code
             and o.quality_status in ("VALID", "SUSPICIOUS")]
    all_fares = [o.total_fare for o in ds.observations
                 if o.collection_date == last and o.quality_status in ("VALID", "SUSPICIOUS")]
    if not fares or not all_fares:
        return 0.0
    airline_avg = sum(fares) / len(fares)
    all_avg = sum(all_fares) / len(all_fares)
    on_date = _api_on(ds, last) or 0.0
    return round((airline_avg / all_avg - 1.0) * 100.0, 2)


# --------------------------------------------------------------------------- #
# Lead time
# --------------------------------------------------------------------------- #

def lead_time_analysis(
    ds: Dataset,
    route: Optional[str] = None,
    airline: Optional[str] = None,
    source: Optional[str] = None,
) -> dict[str, Any]:
    dates = _last_n_days(ds)
    last = dates[-1]
    series = []

    for lead in LEAD_TIMES:
        obs = [o for o in ds.observations
               if o.lead_time_days == lead
               and o.collection_date == last
               and o.quality_status in ("VALID", "SUSPICIOUS")
               and (route is None or o.route == route)
               and (airline is None or o.airline == airline)
               and (source is None or o.source == source)]
        if not obs:
            continue
        fares = [o.total_fare for o in obs]
        series.append({
            "lead_time_days": lead,
            "label": f"T+{lead}",
            "avg_fare": round(sum(fares) / len(fares), 0),
            "median_fare": round(_median(fares), 0),
            "observations": len(fares),
        })

    # Elasticity metric: % diff between T+1 and T+45 average.
    t1 = next((s["avg_fare"] for s in series if s["lead_time_days"] == 1), None)
    t45 = next((s["avg_fare"] for s in series if s["lead_time_days"] == 45), None)
    elasticity = None
    if t1 and t45 and t45 > 0:
        elasticity = round((t1 - t45) / t45 * 100.0, 1)

    return {
        "as_of": last,
        "series": series,
        "elasticity": elasticity,
        "insight": (
            f"Average observed fare is {elasticity}% higher at T+1 than at T+45." if elasticity is not None else None
        ),
        "routes": route,
        "airline": airline,
        "source": source,
    }


# --------------------------------------------------------------------------- #
# Fares distribution
# --------------------------------------------------------------------------- #

def fare_distribution(ds: Dataset, route: Optional[str] = None) -> dict[str, Any]:
    dates = _last_n_days(ds)
    last = dates[-1]
    obs = [o for o in ds.observations
           if o.collection_date == last
           and o.quality_status in ("VALID", "SUSPICIOUS")
           and (route is None or o.route == route)]
    fares = sorted(o.total_fare for o in obs)
    if not fares:
        return {"as_of": last, "observations": 0, "route": route}

    def pct(p: float) -> float:
        idx = int((len(fares) - 1) * p)
        return round(fares[idx], 0)

    mean = sum(fares) / len(fares)
    sd = (sum((x - mean) ** 2 for x in fares) / len(fares)) ** 0.5
    return {
        "as_of": last,
        "route": route,
        "observations": len(fares),
        "currency": "INR",
        "p10": pct(0.10),
        "p25": pct(0.25),
        "median": pct(0.50),
        "mean": round(mean, 0),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "min": round(fares[0], 0),
        "max": round(fares[-1], 0),
        "std_dev": round(sd, 0),
        "histogram": _histogram(ds, route),
    }


def _histogram(ds: Dataset, route: Optional[str]) -> list[dict[str, Any]]:
    dates = _last_n_days(ds)
    last = dates[-1]
    obs = [o.total_fare for o in ds.observations
           if o.collection_date == last and (route is None or o.route == route)
           and o.quality_status in ("VALID", "SUSPICIOUS")]
    if not obs:
        return []
    lo, hi = min(obs), max(obs)
    if hi == lo:
        hi = lo + 1
    bins = 18
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in obs:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    return [
        {"bin": f"₹{int(lo + width * i):,}", "from": int(lo + width * i), "to": int(lo + width * (i + 1)), "count": c}
        for i, c in enumerate(counts)
    ]


# --------------------------------------------------------------------------- #
# Quality
# --------------------------------------------------------------------------- #

def quality_summary(ds: Dataset) -> dict[str, Any]:
    total = len(ds.observations)
    counters: dict[str, int] = defaultdict(int)
    score_sum = 0.0
    for o in ds.observations:
        counters[o.quality_status] += 1
        score_sum += o.quality_score

    valid = counters.get("VALID", 0)
    suspicious = counters.get("SUSPICIOUS", 0)
    invalid = counters.get("INVALID", 0)
    duplicate = counters.get("DUPLICATE", 0)
    sold_out = counters.get("SOLD_OUT", 0)
    stale = counters.get("STALE", 0)

    included = valid + suspicious
    score = round((included / total) * 100.0, 1) if total else 0.0

    # Breakdown dimensions (each 0-100).
    completeness = round((included / total) * 100.0, 1) if total else 0.0
    consistency = round(100.0 - (invalid / total) * 100.0, 1) if total else 0.0
    uniqueness = round(100.0 - (duplicate / total) * 100.0, 1) if total else 0.0
    freshness = round(100.0 - (stale / total) * 100.0, 1) if total else 0.0
    # Source coverage: share of active sources producing valid data.
    coverage = round(len({o.source for o in ds.observations if o.quality_status in ("VALID", "SUSPICIOUS")}) / len(ACTIVE_SOURCE_IDS) * 100.0, 1)
    outlier_rate = round(suspicious / total * 100.0, 1) if total else 0.0
    outlier_comp = max(0.0, 100.0 - outlier_rate)

    weights = {
        "completeness": 0.30,
        "consistency": 0.20,
        "uniqueness": 0.15,
        "freshness": 0.20,
        "coverage": 0.10,
        "outlier_rate": 0.05,
    }
    blended = (
        completeness * weights["completeness"]
        + consistency * weights["consistency"]
        + uniqueness * weights["uniqueness"]
        + freshness * weights["freshness"]
        + coverage * weights["coverage"]
        + outlier_comp * weights["outlier_rate"]
    )
    return {
        "score": round(blended, 1),
        "valid": valid,
        "suspicious": suspicious,
        "invalid": invalid,
        "duplicate": duplicate,
        "sold_out": sold_out,
        "stale": stale,
        "missing": counters.get("MISSING", 0),
        "total": total,
        "included": included,
        "breakdown": {
            "completeness": completeness,
            "consistency": consistency,
            "uniqueness": uniqueness,
            "freshness": freshness,
            "coverage": coverage,
            "outlier_rate": outlier_rate,
        },
        "weighted_score": round(blended, 1),
    }


def quality_rejected(ds: Dataset) -> dict[str, Any]:
    """Drill-down into rejected / suspicious observations."""
    rejected = [o for o in ds.observations if o.quality_status not in ("VALID",)]
    rows = []
    for o in rejected[:400]:
        rows.append({
            "observation_id": o.observation_id,
            "source": o.source,
            "route": o.route,
            "departure_date": o.departure_date,
            "collection_date": o.collection_date,
            "airline": o.airline,
            "lead_time_days": o.lead_time_days,
            "total_fare": o.total_fare,
            "quality_status": o.quality_status,
            "quality_score": round(o.quality_score, 2),
            "exclusion_reason": o.exclusion_reason,
        })
    return {
        "count": len(rejected),
        "rows": rows,
        "statuses": dict(sorted((k, v) for k, v in _quality_by_status(ds).items())),
    }


def _quality_by_status(ds: Dataset) -> dict[str, int]:
    counters: dict[str, int] = defaultdict(int)
    for o in ds.observations:
        counters[o.quality_status] += 1
    return dict(counters)


# --------------------------------------------------------------------------- #
# Collection runs / monitor
# --------------------------------------------------------------------------- #

def collection_runs(ds: Dataset) -> dict[str, Any]:
    dates = _last_n_days(ds)
    last = dates[-1]

    per_source: dict[str, dict[str, Any]] = {}
    for sid, meta in SOURCES.items():
        obs = [o for o in ds.observations if o.source == sid]
        percent_valid = (sum(1 for o in obs if o.quality_status in ("VALID", "SUSPICIOUS")) / len(obs) * 100.0) if obs else 0.0
        failures = sum(1 for o in obs if o.quality_status == "INVALID")
        latency = 380 + (hash(sid) % 900) if sid in ACTIVE_SOURCE_IDS else 0
        per_source[sid] = {
            "source": sid,
            "name": meta["name"],
            "type": meta["type"],
            "status": meta["status"],
            "adapter": meta["adapter"],
            "compliance": meta["compliance"],
            "last_run": (f"{last}T09:0{ACTIVE_SOURCE_IDS.index(sid) + 1 if sid in ACTIVE_SOURCE_IDS else 0}:00+05:30") if sid in ACTIVE_SOURCE_IDS else None,
            "observations": len(obs),
            "valid_observations": sum(1 for o in obs if o.quality_status in ("VALID", "SUSPICIOUS")),
            "success_rate": round(percent_valid, 1),
            "failure_count": failures,
            "avg_latency_ms": latency if sid in ACTIVE_SOURCE_IDS else None,
            "quotes": meta["base_capacity"],
        }

    return {
        "as_of": last,
        "sources": per_source,
        "summary": {
            "active_sources": len(ACTIVE_SOURCE_IDS),
            "healthy_sources": sum(1 for s in per_source.values() if s["status"] == "healthy"),
            "degraded_sources": sum(1 for s in per_source.values() if s["status"] == "degraded"),
            "disabled_sources": sum(1 for s in per_source.values() if s["status"] == "disabled"),
            "ready_sources": sum(1 for s in per_source.values() if s["status"] == "ready"),
            "last_run": last,
            "collection_success_rate": round(sum(s["success_rate"] for s in per_source.values() if s["observations"]) / max(1, len(ACTIVE_SOURCE_IDS)), 1),
        },
    }


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #

def provenance(ds: Dataset, index_id: str) -> Optional[dict[str, Any]]:
    # index_id == a date (YYYY-MM-DD) whose APIx value we trace.
    if index_id not in ds.daily_apix:
        # Allow a route-scoped provenance string like "DEL-BOM:2026-09-06".
        if ":" in index_id:
            route, date = index_id.split(":", 1)
            return _route_provenance(ds, route, date)
        return None

    total_api = ds.daily_apix[index_id]
    route_contributions = []
    for route in DS_ROUTES_IN_INDEX:
        price = _route_day_price(ds, route, index_id)
        if price is None:
            continue
        base = ds.route_meta[route]["base_price"]
        w = ds.route_meta[route]["weight"]
        idx = 100.0 * price["price"] / base
        route_contributions.append({
            "route": route,
            "price": round(price["price"], 0),
            "base": round(base, 0),
            "weight": w,
            "index": round(idx, 2),
            "contribution": round(w * idx, 2),
            "observations": price["observations"],
            "quality": round(price["quality"] * 100, 1),
        })

    return {
        "index_date": index_id,
        "api_value": round(total_api, 2),
        "methodology_version": "apix-1.0.0",
        "weight_version": "provisional-dgca-v0",
        "route_contributions": route_contributions,
    }


def _route_provenance(ds: Dataset, route: str, date: str) -> Optional[dict[str, Any]]:
    price = _route_day_price(ds, route, date)
    if price is None:
        return None
    base = ds.route_meta[route]["base_price"]
    idx = 100.0 * price["price"] / base
    obs = [o for o in ds.observations if o.route == route and o.collection_date == date
           and o.quality_status in ("VALID", "SUSPICIOUS")]
    return {
        "index_date": date,
        "route": route,
        "route_index": round(idx, 2),
        "price": round(price["price"], 0),
        "base": round(base, 0),
        "observations": price["observations"],
        "samples": [o.as_dict() for o in obs[:40]],
        "sources": sorted({o.source for o in obs}),
        "quality": round(price["quality"] * 100, 1),
    }


# --------------------------------------------------------------------------- #
# Methodology static content
# --------------------------------------------------------------------------- #

def methodology(ds: Dataset) -> dict[str, Any]:
    return {
        "title": "APIx — Methodological Framework",
        "version": "apix-1.0.0",
        "status": "Prototype methodology — not an official CPI series.",
        "steps": [
            {"step": 1, "title": "Collect raw fare observations", "detail": "Multi-source adapters (authorized feeds / public APIs / mock) emit canonical fare observations."},
            {"step": 2, "title": "Normalize prices", "detail": "Source-specific structures are mapped to a canonical fare model (currency, components, dates, airport codes)."},
            {"step": 3, "title": "Remove duplicates", "detail": "Fingerprints + itinerary matching identify near-identical re-emissions; duplicates are excluded but retained."},
            {"step": 4, "title": "Flag statistical outliers", "detail": "Robust rules (IQR / MAD) mark suspicious observations; they are flagged, not blindly deleted."},
            {"step": 5, "title": "Calculate route representative price", "detail": "Median of included valid fares per route-day (robust to skew)."},
            {"step": 6, "title": "Normalize against the base period", "detail": "Route index = 100 * Price(r,t) / Base(r), where Base(r) is the base-period mean."},
            {"step": 7, "title": "Apply route weights", "detail": "Provisional traffic-based weights (DGCA-derivable) scale route indices into the aggregate."},
            {"step": 8, "title": "Aggregate into APIx", "detail": "Weighted sum of route indices forms the headline index."},
        ],
        "formula": "APIx(t) = Σ wᵣ × 100 × Price(r,t) / Base(r)",
        "definitions": {
            "Price(r,t)": "median of valid fares for route r collected on day t",
            "Base(r)": "mean of Price(r,t) during the base period",
            "wᵣ": "provisional route weight (Σ wᵣ = 1)",
        },
        "base_period": {"start": ds.base_period_start.isoformat(), "end": ds.base_period_end.isoformat()},
        "weight_version": "provisional-dgca-v0",
        "disclaimer": "This is a prototype statistical methodology for a SIH 2026 demonstration. It is not an official CPI series and does not represent MoSPI/NSO methodology.",
    }


def stats_overview(ds: Dataset) -> dict[str, Any]:
    """Backtest / validation metrics for the most recent period."""
    dates = _last_n_days(ds)
    # Build a "nowcast" style validation: compare recent 7-day mean vs prior 7-day mean.
    last = dates[-1]
    recent = _aggregate_window(ds, last, 7)
    prior = _aggregate_window(ds, dates[-8] if len(dates) > 8 else dates[0], 7)
    deviation = _change_pct(recent, prior)
    return {
        "as_of": last,
        "recent_mean": round(recent, 2) if recent else None,
        "prior_mean": round(prior, 2) if prior else None,
        "mean_deviation": deviation,
        "backtest": {
            "status": "demo",
            "metrics": {
                "mae": round(abs(deviation or 0.0), 2),
                "correlation": 0.0,
            },
            "note": "Benchmark series unavailable in demo mode. Metrics shown are relative to the prior-period mean.",
        },
    }


# Determine index routes at import time from a dataset-independent constant.
DS_ROUTES_IN_INDEX = list(ROUTES.keys())
