"""APIx data API endpoints.

Every route returns validated Pydantic models (see ``schemas``). The endpoints
are grouped to mirror the dashboard screens: overview, index, routes, airlines,
lead-time, distribution, quality, collection, methodology and provenance.
"""

from __future__ import annotations

import logging
from typing import Any, Collection, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

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
logger = logging.getLogger(__name__)


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
    route = route.upper() if route else None
    airline = airline.upper() if airline else None
    rows = [o.as_dict() for o in ds.observations
            if (route is None or o.route == route)
            and (airline is None or o.airline == airline)]
    rows.sort(key=lambda r: r["collection_timestamp"], reverse=True)
    return {"count": len(rows), "data_origin": ds.origin, "rows": rows[:limit]}


@router.get("/quality", response_model=schemas.Quality)
def get_quality() -> dict:
    return quality_summary(get_dataset())


@router.get("/quality/rejected", response_model=schemas.Rejected)
def get_quality_rejected() -> dict:
    return quality_rejected(get_dataset())


@router.get("/collection-runs", response_model=schemas.CollectionRuns)
def get_collection_runs() -> dict:
    """Per-source health. In live mode this is the REAL run log from SQLite
    (blocked/failed runs included); in demo mode it is the synthetic monitor."""
    ds = get_dataset()
    if ds.origin == "live":
        from ..collect import collection_service

        return collection_service.collection_runs_view()
    return collection_runs(ds)


@router.get("/data/files", response_model=schemas.CustomDataReport)
def get_data_files() -> dict:
    """Provenance for imported data: which files feed the dashboard, how each
    column was mapped, how many rows were rejected and why.

    This is the audit surface for "is this my data?": it reads straight from the
    files on disk and is empty, not invented, when no files are present.
    """
    from ..custom_data import import_report

    return import_report()


@router.post("/data/reload", response_model=schemas.CustomDataReport)
def reload_data_files() -> dict:
    """Rescan the data directory now (normally unnecessary — the loader notices
    changed files on its own, but it is handy right after dropping a file in)."""
    from ..custom_data import import_report, invalidate_cache

    invalidate_cache()
    return import_report()


def _canonical_observations(dataset: Any) -> list[Any]:
    """One row per ``observation_id`` — the loader's duplicate twins dropped.

    The loader emits every copy it found and flags the later ones
    ``DUPLICATE`` / ``flag:duplicate_fingerprint``, so the *first* row for an id
    is the one carrying the real quality verdict. Rows without an id cannot be
    de-duplicated and are passed through untouched.
    """
    canonical: dict[str, Any] = {}
    unkeyed: list[Any] = []
    for obs in dataset.observations:
        if not obs.observation_id:
            unkeyed.append(obs)
        elif obs.observation_id not in canonical:
            canonical[obs.observation_id] = obs
    return list(canonical.values()) + unkeyed


def _rows_to_persist(dataset: Any, disk_names: Optional[Collection[str]] = None) -> list[Any]:
    """The rows to write to the database for the files named ``disk_names``.

    Selecting only the rows whose ``raw_payload_reference`` names the newly
    written file is wrong whenever that data already exists under another name
    (a re-upload, which lands as ``fares_1.csv``, or a file already sitting in
    the data directory). The loader flags the *second* copy ``DUPLICATE``, so
    persisting "the new file's rows" writes exactly the rows the index excludes
    and the database ends up holding data that produces an empty dashboard.
    Resolve to the canonical row per ``observation_id`` instead.

    ``disk_names=None`` means "everything the loader read".
    """
    canonical = _canonical_observations(dataset)
    if disk_names is None:
        return canonical
    names = set(disk_names)
    touched = {
        o.observation_id
        for o in dataset.observations
        if o.observation_id and any(n in (o.raw_payload_reference or "") for n in names)
    }
    return [
        o for o in canonical
        if o.observation_id in touched
        or (not o.observation_id and any(n in (o.raw_payload_reference or "") for n in names))
    ]


def _merge_persistence(reports: list[dict]) -> Optional[dict]:
    """Combine per-file persistence reports into one summary."""
    if not reports:
        return None
    merged = {
        "persisted": any(r.get("persisted") for r in reports),
        "backend": next((r.get("backend") for r in reports if r.get("backend")), None),
        "durable": any(r.get("durable") for r in reports),
        "run_id": ", ".join(r["run_id"] for r in reports if r.get("run_id")) or None,
        "inserted": sum(r.get("inserted", 0) for r in reports),
        "updated": sum(r.get("updated", 0) for r in reports),
        "replaced": sum(r.get("replaced", 0) for r in reports),
        "total": sum(r.get("total", 0) for r in reports),
        "error": next((r.get("error") for r in reports if r.get("error")), None),
        "note": next((r.get("note") for r in reports if r.get("note")), None),
    }
    return merged


@router.get("/data/database", response_model=schemas.DatabaseStatus)
def get_data_database() -> dict:
    """Can imports be persisted right now, and what is already stored?

    Never reveals the connection string — only the backend, its health and the
    observation counts, so the UI can say "connected to Supabase" or explain
    exactly why nothing is being saved.
    """
    from ..persist import database_status

    return database_status()


@router.post("/data/persist", response_model=schemas.PersistenceReport)
def persist_data_files(file: Optional[str] = Query(
        None, description="Persist only this file's rows (default: every loaded file)")) -> dict:
    """Push the imported observations into the database (upsert by id).

    Safe to run twice: rows whose ``observation_id`` already exists are updated
    in place, so re-running after a partial failure cannot duplicate data.
    """
    from ..custom_data import get_custom_dataset
    from ..persist import persist_observations

    ds = get_custom_dataset()
    if ds is None or not ds.observations:
        raise HTTPException(status_code=404, detail="No imported data to persist — upload a file first.")
    observations = _rows_to_persist(ds, [file] if file else None)
    if file and not observations:
        raise HTTPException(status_code=404, detail=f"No rows came from '{file}'.")
    basket = set(ds.route_meta) or None
    report = persist_observations(observations, label=file or "all", basket=basket)
    if not report.get("persisted"):
        logger.warning("Imported-data persistence failed: backend=%s error=%s", report.get("backend"), report.get("error"))
    return report


@router.post("/data/persist-demo", response_model=schemas.PersistenceReport)
def persist_demo_data() -> dict:
    """Seed the configured store with the deterministic APIx demo dataset.

    This intentionally bypasses the browser-upload filesystem. It makes the
    ``Push demo data`` action work even when a serverless deployment keeps its
    bundled ``/var/task/data`` directory read-only, and it is idempotent because
    deterministic demo observations retain stable ``observation_id`` values.
    """
    from ..dataset import build_dataset
    from ..persist import persist_observations

    demo = build_dataset()
    report = persist_observations(
        demo.observations,
        label="apix-built-in-demo-v1",
        basket=set(demo.route_meta) or None,
    )
    if not report.get("persisted"):
        logger.warning("Demo-data persistence failed: backend=%s error=%s", report.get("backend"), report.get("error"))
    else:
        logger.info("Demo data persisted: total=%s backend=%s", report.get("total"), report.get("backend"))
    return report


@router.post("/data/upload", response_model=schemas.UploadResponse)
async def upload_data_files(files: list[UploadFile] = File(...)) -> dict:
    """Import fare files through the browser.

    Accepts the same formats as the data directory (csv/tsv/json/jsonl/xlsx),
    writes them into it without ever overwriting an existing import, and returns
    the per-file parse report so the UI can show exactly what was understood.
    Files that cannot be accepted are listed under ``refused`` with a reason
    rather than aborting the whole upload.
    """
    from ..config import settings
    from ..custom_data import import_bytes, import_report, invalidate_cache, upload_diagnostics

    diagnostics = upload_diagnostics()
    imported: list[dict] = []
    refused: list[dict[str, str]] = []

    for upload in files:
        name = upload.filename or "upload.csv"
        try:
            payload = await upload.read()
        except Exception as exc:  # a broken part must not kill the rest
            refused.append({"name": name, "error": f"could not read upload: {exc}"})
            continue
        finally:
            await upload.close()

        if not payload:
            refused.append({"name": name, "error": "file is empty"})
            continue
        if len(payload) > settings.max_upload_bytes:
            refused.append({
                "name": name,
                "error": f"{len(payload) / 1_048_576:.1f}MB exceeds the "
                         f"{settings.max_upload_bytes / 1_048_576:.0f}MB upload limit — "
                         "copy it into the data directory instead",
            })
            continue
        try:
            target = import_bytes(name, payload)
        except ValueError as exc:
            refused.append({"name": name, "error": str(exc)})
            continue
        except OSError as exc:
            # Keep a support-quality diagnostic in the server log without
            # exposing environment variables or connection strings to clients.
            logger.warning(
                "Upload write failed: name=%s upload_dir=%s error=%s",
                name,
                diagnostics.get("upload_dir"),
                f"{type(exc).__name__}: {exc}",
            )
            hint = diagnostics.get("reason") or (
                "The deployment filesystem is read-only. Configure APIX_UPLOAD_DATA_DIR "
                "to a writable volume, or use the serverless /tmp target."
            )
            refused.append({
                "name": name,
                "error": f"could not write temporary upload: {exc}. Diagnostic: {hint}",
            })
            continue
        imported.append({
            "name": target.name,
            "original_name": name,
            "path": str(target),
            "size_bytes": len(payload),
        })

    invalidate_cache()
    report = import_report()
    by_name = {f["name"]: f for f in report.get("files", [])}

    enriched: list[dict] = []
    for item in imported:
        parsed = by_name.get(item["name"], {})
        enriched.append({
            **item,
            "rows": parsed.get("rows", 0),
            "observations": parsed.get("observations", 0),
            "rejected": parsed.get("rejected", 0),
            "mapped": parsed.get("mapped", {}),
            "unmapped": parsed.get("unmapped", []),
            "warnings": parsed.get("warnings", []),
            "errors": parsed.get("errors", []),
        })

    # Persist to the durable store (Supabase/PostgreSQL when configured):
    # upsert on observation_id, so re-uploading the same rows updates them
    # instead of duplicating them. A database failure never loses the import —
    # the files are already on disk and keep serving the dashboard.
    persistence = None
    if imported:
        from ..custom_data import get_custom_dataset
        from ..persist import persist_observations

        ds = get_custom_dataset()
        names = {item["name"] for item in imported}
        fresh = _rows_to_persist(ds, names)
        if fresh:
            # Group by the name the user uploaded under: re-uploading "fares.csv"
            # (which lands as fares_1.csv) must replace what it wrote last time.
            by_label: dict[str, list] = {}
            for item in imported:
                by_label.setdefault(item["original_name"], []).append(item["name"])
            reports = []
            for label, disk_names in by_label.items():
                rows = _rows_to_persist(ds, disk_names)
                if rows:
                    reports.append(persist_observations(
                        rows, label=label, basket=set(ds.route_meta) if ds else None,
                    ))
            persistence = _merge_persistence(reports)

    return {
        "imported": enriched,
        "refused": refused,
        "persistence": persistence,
        "report": report,
        "diagnostics": upload_diagnostics(),
    }


@router.delete("/data/files/{name}", response_model=schemas.CustomDataReport)
def delete_data_file(name: str) -> dict:
    """Remove one imported file and rescan (the dashboard's Import screen)."""
    from ..custom_data import import_report, invalidate_cache, remove_file

    try:
        remove_file(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"could not delete {name}: {exc}")
    invalidate_cache()
    return import_report()


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
