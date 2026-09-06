"""APIx data API endpoints.

Every route returns validated Pydantic models (see ``schemas``). The endpoints
are grouped to mirror the dashboard screens: overview, index, routes, airlines,
lead-time, distribution, quality, collection, methodology and provenance.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..dataset import get_dataset
from ..engine import (
    airline_analysis,
    collection_runs,
    fare_distribution,
    lead_time_analysis,
    methodology,
    overview,
    provenance,
    quality_rejected,
    quality_summary,
    route_detail,
    route_heatmap,
    route_list,
    stats_overview,
    trend,
)
from .. import schemas

router = APIRouter(tags=["APIx"])


@router.get("/overview", response_model=schemas.Overview)
def get_overview() -> dict:
    return overview(get_dataset())


@router.get("/index", response_model=schemas.Overview)
def get_index() -> dict:
    """Current index value + movement (same envelope as overview)."""
    return overview(get_dataset())


@router.get("/index/trend", response_model=schemas.Trend)
def get_index_trend(
    range: str = Query("90d", description="7d | 30d | 90d | 6m | 1y"),
    compare: Optional[str] = Query(None, description="Optional comparison series"),
) -> dict:
    return trend(get_dataset(), range_label=range, compare=compare)


@router.get("/index/route/{route}", response_model=schemas.RouteDetail)
def get_route_index(route: str) -> dict:
    result = route_detail(get_dataset(), route.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Route index unavailable — no valid observations for {route.upper()}.")
    return result


@router.get("/index/airline/{airline}", response_model=schemas.AirlineList)
def get_airline_index(airline: str) -> dict:
    rows = airline_analysis(get_dataset(), route=None)
    filtered = [r for r in rows if r["airline"] == airline.upper()]
    return {"airlines": filtered}


@router.get("/index/lead-time", response_model=schemas.LeadTime)
def get_index_lead_time(
    route: Optional[str] = Query(None),
    airline: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
) -> dict:
    return lead_time_analysis(get_dataset(), route=route, airline=airline, source=source)


@router.get("/routes", response_model=schemas.RouteList)
def get_routes(top: Optional[int] = Query(None, description="Limit to the top N by 7-day movement")) -> dict:
    return {"routes": route_list(get_dataset(), top=top)}


@router.get("/routes/heatmap", response_model=schemas.RouteHeatmap)
def get_route_heatmap() -> dict:
    return {"routes": route_heatmap(get_dataset())}


@router.get("/airlines", response_model=schemas.AirlineList)
def get_airlines(route: Optional[str] = Query(None)) -> dict:
    return {"airlines": airline_analysis(get_dataset(), route=route)}


@router.get("/fares/distribution", response_model=schemas.FareDistribution)
def get_fare_distribution(route: Optional[str] = Query(None)) -> dict:
    return fare_distribution(get_dataset(), route=route)


@router.get("/fares")
def get_fares(
    route: Optional[str] = Query(None),
    airline: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Recent canonical fare observations (for an auditor / drill-down)."""
    ds = get_dataset()
    rows = [o.as_dict() for o in ds.observations
            if (route is None or o.route == route)
            and (airline is None or o.airline == airline)]
    rows.sort(key=lambda r: r["collection_timestamp"], reverse=True)
    return {"count": len(rows), "rows": rows[:limit]}


@router.get("/quality", response_model=schemas.Quality)
def get_quality() -> dict:
    return quality_summary(get_dataset())


@router.get("/quality/rejected", response_model=schemas.Rejected)
def get_quality_rejected() -> dict:
    return quality_rejected(get_dataset())


@router.get("/collection-runs", response_model=schemas.CollectionRuns)
def get_collection_runs() -> dict:
    return collection_runs(get_dataset())


@router.get("/methodology", response_model=schemas.Methodology)
def get_methodology() -> dict:
    return methodology(get_dataset())


@router.get("/provenance/{index_id}", response_model=schemas.Provenance)
def get_provenance(index_id: str) -> dict:
    result = provenance(get_dataset(), index_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No index value or route provenance found for '{index_id}'.")
    return result


@router.get("/stats/overview", response_model=schemas.StatsOverview)
def get_stats_overview() -> dict:
    return stats_overview(get_dataset())
