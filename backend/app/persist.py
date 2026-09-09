"""Write imported observations into the durable collection store.

This is the "upload it to my database" half of the custom-data feature. The
loader turns files into canonical observations; this module puts them in the
``observations`` table of whatever store is configured — **Supabase/PostgreSQL**
in a deployed setup, SQLite locally — using ``observation_id`` as the
de-duplication key:

* a row whose ``observation_id`` is new is **inserted**;
* a row whose id already exists is **updated in place**, so re-uploading the
  same export (or a corrected version of it) can never duplicate data.

Credentials are never handled here and never logged: the store reads
``DATABASE_URL`` from the environment, exactly as the collection engine does
(see docs/DEPLOYMENT.md — ``APIX_IGNORE_DATABASE_URL=0`` on Vercel).

Once rows are in that table they are ordinary stored observations: switching the
dashboard to *live* serves the index straight out of your database.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Optional

from .dataset import Observation

#: The columns the store owns; anything else on an Observation is derived.
_STORE_FIELDS = (
    "observation_id", "source", "origin", "destination", "route", "departure_date",
    "collection_date", "collection_timestamp", "airline", "flight_number", "cabin",
    "fare_class", "lead_time_days", "base_fare", "taxes", "fees", "total_fare",
    "currency", "availability", "seats_remaining", "raw_payload_reference",
    "fingerprint", "quality_status", "quality_score", "exclusion_reason",
)


#: apix_state key holding {file label: run_id} for every import, so uploading the
#: same file again can replace exactly the rows the previous upload wrote.
IMPORT_RUNS_KEY = "import_runs"


def _slug(label: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "-", label.lower()).strip("-") or "upload"


def _run_id(label: str) -> str:
    """Unique per import call — two uploads in the same second must not collide,
    or the "replace what the last upload wrote" step would replace itself."""
    import uuid

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"import-{_slug(label)}-{stamp}-{uuid.uuid4().hex[:6]}"


def _import_runs(store: Any) -> dict:
    """{file label: run_id} of previous imports (persisted in apix_state)."""
    import json

    try:
        raw = store.get_state(IMPORT_RUNS_KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _remember_run(store: Any, label: str, run_id: str) -> None:
    import json

    runs = _import_runs(store)
    runs[label] = run_id
    try:
        store.set_state(IMPORT_RUNS_KEY, json.dumps(runs, sort_keys=True))
    except Exception:
        pass


def _rows(observations: Iterable[Observation], basket: Optional[set[str]] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obs in observations:
        row = {field: getattr(obs, field, None) for field in _STORE_FIELDS}
        row["in_basket"] = 1 if (basket is None or obs.route in basket) else 0
        out.append(row)
    return out


def database_status() -> dict[str, Any]:
    """What the dashboard is (or is not) able to persist to, and why."""
    try:
        from .collect.store import get_store
    except Exception as exc:  # pragma: no cover - import-time failure
        return {"configured": False, "available": False, "backend": "unknown",
                "reason": f"store unavailable: {type(exc).__name__}"}
    try:
        store = get_store()
        counts = store.counts()
    except Exception as exc:
        return {"configured": False, "available": False, "backend": "unknown",
                "reason": f"store unavailable: {type(exc).__name__}"}
    return {
        "configured": bool(counts.get("backend") == "postgresql" or store.available),
        "available": bool(counts.get("available")),
        "backend": counts.get("backend"),
        "durable": counts.get("durable"),
        "ephemeral": counts.get("ephemeral"),
        "ignores_database_url": counts.get("ignores_database_url"),
        "reason": counts.get("unavailable_reason"),
        "note": counts.get("note"),
        "counts": {
            "observations": counts.get("observations", 0),
            "valid_observations": counts.get("valid_observations", 0),
            "days_collected": counts.get("days_collected", 0),
            "by_status": counts.get("by_status", {}),
        },
    }


def persist_observations(
    observations: list[Observation],
    *,
    label: str = "upload",
    basket: Optional[set[str]] = None,
    record_run: bool = True,
    replace_previous: bool = True,
) -> dict[str, Any]:
    """Upsert observations into the store. Never raises for a missing database.

    ``label`` identifies *what* is being imported (normally the file name). With
    ``replace_previous`` (the default) the rows written by the previous import of
    that same label are deleted first, so re-uploading a corrected export
    replaces it instead of leaving both versions behind. Rows are additionally
    upserted on ``observation_id``, so identical data can never duplicate even
    across different files.

    Returns a report the API can hand straight to the UI::

        {"persisted": True, "backend": "postgresql", "inserted": 12,
         "updated": 3, "replaced": 0, "total": 15, "run_id": "import-…", "error": None}
    """
    if not observations:
        return {"persisted": False, "inserted": 0, "updated": 0, "replaced": 0,
                "total": 0, "error": "nothing to persist", "backend": None, "run_id": None}

    status = database_status()
    if not status.get("available"):
        return {
            "persisted": False,
            "inserted": 0, "updated": 0, "replaced": 0, "total": 0,
            "backend": status.get("backend"),
            "run_id": None,
            "error": status.get("reason")
            or "No usable collection store. Set DATABASE_URL (and APIX_IGNORE_DATABASE_URL=0 "
               "on Vercel) to persist imports to PostgreSQL — see docs/DEPLOYMENT.md.",
            "note": status.get("note"),
        }

    from .collect.store import get_store

    store = get_store()
    run_id = _run_id(label)
    rows = _rows(observations, basket=basket)
    replaced = 0

    try:
        previous = _import_runs(store).get(label) if replace_previous else None
        if record_run:
            try:
                store.begin_run(run_id, "import", trigger="import")
            except Exception:
                run_id = run_id  # an audit row is nice, not essential
        result = store.upsert_observations(rows, run_id=run_id)
        valid = sum(1 for o in observations if o.quality_status in ("VALID", "SUSPICIOUS"))
        if record_run:
            try:
                store.finish_run(
                    run_id,
                    status="success",
                    finished_at=_now_iso(),
                    observations=len(rows),
                    valid_observations=valid,
                    duplicates=sum(1 for o in observations if o.quality_status == "DUPLICATE"),
                    invalid=sum(1 for o in observations if o.quality_status == "INVALID"),
                    suspicious=sum(1 for o in observations if o.quality_status == "SUSPICIOUS"),
                )
            except Exception:
                pass
        # Order matters: upsert first (so unchanged rows are *updated*, not
        # deleted and re-created), then remove whatever the previous version of
        # this file left behind and this one did not refresh.
        if previous and previous != run_id:
            try:
                replaced = store.delete_superseded(previous, run_id)
            except Exception:
                replaced = 0
        if replace_previous:
            _remember_run(store, label, run_id)
    except Exception as exc:
        # A database failure must not lose the import: the files are already on
        # disk and the dashboard keeps serving them.
        return {
            "persisted": False,
            "inserted": 0, "updated": 0, "replaced": 0, "total": 0,
            "backend": status.get("backend"),
            "run_id": run_id,
            "error": f"{type(exc).__name__}: {exc}",
            "note": status.get("note"),
        }

    return {
        "persisted": True,
        "backend": status.get("backend"),
        "durable": status.get("durable"),
        "run_id": run_id,
        "inserted": result["inserted"],
        "updated": result["updated"],
        "replaced": replaced,
        "total": result["total"],
        "error": None,
        "note": status.get("note"),
    }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
