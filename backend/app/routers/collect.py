"""Collection-engine endpoints: the scraper control surface + raw feed.

These are what the dashboard's demo/scraper toggle and the "Live Feed" screen
talk to. Note the split of responsibilities:

* mode (which data the *index* serves) lives here, not in the frontend;
* a sweep is fire-and-forget async — the UI polls ``/collect/status``;
* ``/collect/payloads`` returns the stored payload *exactly as collected*,
  which is the "display it as it is" requirement, kept separate from the
  normalized/quality-filtered view on purpose.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..collect import collection_service
from ..collect.headers import NOT_IMPLEMENTED, SENT_FIELDS
from ..collect.service import DEMO, LIVE
from ..config import settings
from ..dataset import get_dataset
from .. import schemas

router = APIRouter(tags=["Collection"])


class ModeBody(BaseModel):
    mode: str = Field(..., description=f"'{LIVE}' to serve scraped data, '{DEMO}' for the synthetic store.")


class SweepBody(BaseModel):
    sources: Optional[list[str]] = Field(None, description="Restrict the sweep to these source ids.")
    routes: Optional[list[str]] = Field(None, description="Restrict to these route keys, e.g. DEL-BOM.")
    lead_times: Optional[list[int]] = Field(None, description="Override the scheduled lead-time ladder.")
    wait: bool = Field(False, description="If true, block until the sweep finishes and return its result.")


# --------------------------------------------------------------------------- #
# Data-source mode (the toggle)
# --------------------------------------------------------------------------- #


@router.get("/data-source", response_model=schemas.DataSourceState)
def get_data_source() -> dict:
    """Which dataset the dashboard is currently served from."""
    ds = get_dataset()
    return {
        "mode": collection_service.mode,
        "effective_mode": ds.origin,
        "has_live_data": collection_service.has_live_data,
        "collector_enabled": settings.collector_enabled,
        "background_running": collection_service.background_running,
        "store": collection_service.store.counts(),
        "sources": [s["id"] for s in collection_service.status()["sources"]],
    }


@router.post("/data-source", response_model=schemas.DataSourceState)
async def set_data_source(body: ModeBody) -> dict:
    """Flip the whole dashboard between scraped data and the demo dataset."""
    try:
        result = collection_service.set_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "locked" in str(exc) else 422, detail=str(exc)) from exc

    # Switching to live with an empty store would show nothing; collect once so
    # the toggle produces an immediately meaningful screen instead of a spinner.
    if body.mode.lower() == LIVE and not collection_service.has_live_data and collection_service.adapters:
        collection_service.start_sweep(trigger="mode-switch")
        result["note"] = "Live mode selected — a first sweep is running; the screens fill as it lands."
    ds = get_dataset()
    state = collection_service.status()
    return {
        **result,
        "effective_mode": ds.origin,
        "has_live_data": collection_service.has_live_data,
        "collector_enabled": settings.collector_enabled,
        "background_running": collection_service.background_running,
        "store": state["store"],
        "sources": [s["id"] for s in state["sources"]],
    }


# --------------------------------------------------------------------------- #
# Collection control
# --------------------------------------------------------------------------- #


@router.get("/collect/status")
def collect_status() -> dict:
    return collection_service.status()


@router.get("/collect/policy")
def collect_policy() -> dict:
    """The rules the engine enforces, straight from the code."""
    return {
        "policy_document": "docs/SCRAPING_POLICY.md",
        "sent_headers": list(SENT_FIELDS),
        "not_implemented": list(NOT_IMPLEMENTED),
        "politeness": {
            "user_agent": settings.user_agent,
            "min_seconds_between_requests": settings.min_seconds_between_requests,
            "max_retries": settings.max_retries,
            "backoff_base_seconds": settings.backoff_base_seconds,
            "max_requests_per_sweep": settings.max_requests_per_sweep,
            "robots_txt": "checked per host; fail closed" if settings.refuse_when_robots_unreadable else "checked per host; fail open",
            "circuit_breaker": {
                "threshold": settings.circuit_breaker_threshold,
                "cooldown_seconds": settings.circuit_breaker_cooldown_seconds,
            },
        },
        "sources": [a.describe() for a in collection_service.adapters.values()],
    }


@router.post("/collect/sweep")
async def run_sweep(body: Optional[SweepBody] = None) -> dict:
    """Run a collection sweep now (the dashboard's "Collect now" button).

    Returns immediately with the run id unless ``wait`` is set, in which case the
    full result is returned — handy for tests and small manual checks.
    """
    body = body or SweepBody()
    if not collection_service.adapters:
        raise HTTPException(
            status_code=409,
            detail=(
                "No collection adapter is enabled. Set APIX_COLLECTOR_SOURCES "
                "(e.g. 'fixture' for the offline capture, 'amadeus' for the "
                "permissioned API) and restart."
            ),
        )

    if body.lead_times:
        # Scoped to this request only — the scheduled sweep keeps its own ladder.
        settings.sweep_lead_times = [int(x) for x in body.lead_times if int(x) > 0]

    if body.wait:
        result = await collection_service.run_sweep(
            source_ids=body.sources, trigger="manual", routes=body.routes
        )
        return result.as_dict()

    collection_service.start_sweep(source_ids=body.sources, trigger="manual", routes=body.routes)
    return {
        "accepted": True,
        "detail": "sweep scheduled in the background; poll /api/collect/status or /api/collect/runs",
    }


@router.get("/collect/runs")
def collect_runs(limit: int = Query(20, ge=1, le=200), source: Optional[str] = Query(None)) -> dict:
    """The run log — including blocked/failed runs, which are never hidden."""
    runs = collection_service.store.recent_runs(limit=limit, source=source)
    return {"count": len(runs), "runs": runs}


@router.get("/collect/payloads")
def collect_payloads(
    limit: int = Query(50, ge=1, le=500),
    source: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
) -> dict:
    """Raw payloads exactly as collected, newest first (audit / 'as it is' view)."""
    rows = collection_service.store.recent_payloads(limit=limit, source=source, run_id=run_id)
    return {"count": len(rows), "rows": rows}


@router.get("/collect/fares")
def collect_fares(
    limit: int = Query(100, ge=1, le=1000),
    route: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> dict:
    """Normalized observations collected by the scraper, newest first."""
    rows = collection_service.store.all_observations()
    if route:
        rows = [r for r in rows if r["route"] == route.upper()]
    if status:
        rows = [r for r in rows if r["quality_status"] == status.upper()]
    rows.sort(key=lambda r: (r.get("collection_timestamp") or "", r.get("id") or 0), reverse=True)
    return {"count": len(rows), "total": len(rows), "rows": rows[:limit]}


@router.get("/collect/sources")
def collect_sources() -> dict:
    return {
        "sources": collection_service.status()["sources"],
        "registered": sorted(collection_service.adapters.keys()),
        "requested_in_config": settings.collector_sources,
    }


@router.post("/collect/sources/{source_id}/test")
async def test_source(source_id: str) -> dict:
    """Cheap probe: can we reach this source *as permitted* right now?"""
    try:
        return await collection_service.test_connection(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' is not registered.")


@router.delete("/collect/store")
def clear_store(confirm: bool = Query(False)) -> dict:
    """Wipe collected data. Requires ?confirm=true so it cannot fire by accident."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Pass ?confirm=true to delete all collected data.")
    collection_service.store.reset()
    from ..dataset import invalidate_live_cache

    invalidate_live_cache()
    return {"cleared": True, "store": collection_service.store.counts()}
