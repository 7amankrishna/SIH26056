"""Persisting imported data to the durable store (Supabase/PostgreSQL in prod).

These tests run against the SQLite backend because that is what is available in
CI, but they exercise the same store methods and the same SQL shape the
PostgreSQL path uses — the store translates placeholders and the upsert clause.
The PostgreSQL-specific behaviour is covered by tests/test_postgres_store.py,
which is skipped unless APIX_TEST_DATABASE_URL is set.

The property under test is the one the user asked for: **uploading the same data
twice must not duplicate it.**
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# A throwaway store, isolated from any developer's SQLite file.
os.environ.setdefault("APIX_COLLECTOR_SOURCES", "")
os.environ["APIX_DATA_DIR"] = tempfile.mkdtemp(prefix="apix-persist-tests-")
os.environ["APIX_CUSTOM_DATA_DIR"] = tempfile.mkdtemp(prefix="apix-persist-custom-")


@pytest.fixture()
def store():
    from app.collect.store import get_store

    s = get_store()
    assert s.available, f"test store unavailable: {s.unavailable_reason}"
    s.reset()
    yield s
    s.reset()


def _row(observation_id: str, total: float = 4800.0, route: str = "DEL-BOM") -> dict:
    origin, _, destination = route.partition("-")
    return {
        "observation_id": observation_id,
        "source": "test",
        "origin": origin,
        "destination": destination,
        "route": route,
        "departure_date": "2026-09-08",
        "collection_date": "2026-09-01",
        "collection_timestamp": "2026-09-01T09:00:00+05:30",
        "airline": "6E",
        "flight_number": "6E101",
        "cabin": "ECONOMY",
        "fare_class": "E",
        "lead_time_days": 7,
        "base_fare": total * 0.78,
        "taxes": total * 0.16,
        "fees": total * 0.06,
        "total_fare": total,
        "currency": "INR",
        "availability": "AVAILABLE",
        "seats_remaining": 9,
        "raw_payload_reference": "file:test.csv:1",
        "fingerprint": "fp",
        "quality_status": "VALID",
        "quality_score": 0.99,
        "exclusion_reason": None,
    }


def count(store) -> int:
    return store.counts()["observations"]


# --------------------------------------------------------------------------- #
# Store level: upsert by observation_id
# --------------------------------------------------------------------------- #

def test_upsert_inserts_new_rows(store):
    result = store.upsert_observations([_row("A"), _row("B")], run_id="import-1")
    assert result == {"inserted": 2, "updated": 0, "total": 2}
    assert count(store) == 2


def test_upsert_updates_instead_of_duplicating(store):
    store.upsert_observations([_row("A")], run_id="import-1")
    result = store.upsert_observations([_row("A", total=5100.0)], run_id="import-2")
    assert result == {"inserted": 0, "updated": 1, "total": 1}
    assert count(store) == 1, "an existing id must not create a second row"
    stored = store.all_observations()[0]
    assert stored["total_fare"] == 5100.0, "the update must actually be applied"


def test_upsert_collapses_duplicate_ids_inside_one_batch(store):
    result = store.upsert_observations([_row("A"), _row("A"), _row("A")], run_id="import-1")
    assert result["total"] == 1
    assert count(store) == 1


def test_upsert_ignores_rows_without_an_id(store):
    row = _row("A")
    row["observation_id"] = None
    result = store.upsert_observations([row], run_id="import-1")
    assert result["total"] == 0
    assert count(store) == 0


def test_delete_run_observations(store):
    store.upsert_observations([_row("A"), _row("B")], run_id="import-1")
    store.upsert_observations([_row("C")], run_id="import-2")
    assert store.delete_run_observations("import-1") == 2
    assert count(store) == 1


# --------------------------------------------------------------------------- #
# persist.py: the helper the endpoints call
# --------------------------------------------------------------------------- #

def _observation(observation_id: str, total: float = 4800.0):
    from app.dataset import Observation

    values = _row(observation_id, total=total)
    values.pop("raw_payload_reference")
    return Observation(raw_payload_reference="file:test.csv:1", **values)


def test_persist_reports_insert_then_update(store):
    from app.persist import persist_observations

    first = persist_observations([_observation("A"), _observation("B")], label="test")
    assert first["persisted"] is True
    assert first["inserted"] == 2 and first["updated"] == 0
    assert count(store) == 2

    second = persist_observations([_observation("A"), _observation("B")], label="test")
    assert second["inserted"] == 0 and second["updated"] == 2
    assert count(store) == 2, "persisting the same rows twice must not duplicate"


def test_persist_replaces_the_previous_import_of_the_same_file(store):
    """A re-uploaded export replaces what that export contributed."""
    from app.persist import persist_observations

    persist_observations([_observation("A")], label="fares.csv")
    assert count(store) == 1

    # Same file, one fare corrected: a *different* id, so a plain upsert would
    # leave two rows behind. Replacement removes the superseded one.
    report = persist_observations([_observation("A-fixed")], label="fares.csv")
    assert report["replaced"] == 1
    assert count(store) == 1


def test_persist_keeps_other_files_rows(store):
    from app.persist import persist_observations

    persist_observations([_observation("A")], label="fares.csv")
    persist_observations([_observation("B")], label="other.csv")
    persist_observations([_observation("A2")], label="fares.csv")
    assert count(store) == 2, "only the re-uploaded file's rows are replaced"


def test_persist_without_observations_is_a_no_op(store):
    from app.persist import persist_observations

    report = persist_observations([], label="empty")
    assert report["persisted"] is False
    assert count(store) == 0


def test_persist_records_an_import_run(store):
    from app.persist import persist_observations

    report = persist_observations([_observation("A")], label="fares.csv")
    runs = store.recent_runs(limit=10)
    assert any(r["run_id"] == report["run_id"] and r["trigger"] == "import" for r in runs)


def test_database_status_never_exposes_the_dsn(store):
    from app.persist import database_status

    status = database_status()
    assert status["available"] is True
    blob = repr(status)
    assert "postgres://" not in blob and "password" not in blob.lower()


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _upload(client, name="fares.csv", content=b"route,date,price\nDEL-BOM,2026-09-01,4800\n"):
    return client.post("/api/data/upload", files=[("files", (name, content, "text/csv"))])


def test_database_endpoint(client):
    body = client.get("/api/data/database").json()
    assert body["available"] is True
    assert "counts" in body
    assert "DATABASE_URL" not in repr(body)


def test_upload_persists_and_reupload_updates(client):
    first = _upload(client).json()
    assert first["persistence"]["persisted"] is True
    assert first["persistence"]["inserted"] == 1

    second = _upload(client).json()
    assert second["persistence"]["inserted"] == 0
    assert second["persistence"]["updated"] + second["persistence"]["replaced"] >= 1

    after = client.get("/api/data/database").json()["counts"]["observations"]
    assert after == 1, "the same row uploaded twice must exist once"


def test_persist_endpoint_pushes_loaded_files(client):
    body = client.post("/api/data/persist").json()
    assert body["persisted"] is True
    assert body["total"] >= 1


def test_persist_demo_endpoint_seeds_the_store_without_an_uploaded_file(client):
    """The built-in demo seed bypasses the browser-upload filesystem entirely."""
    before = client.get("/api/data/database").json()["counts"]["observations"]
    r = client.post("/api/data/persist-demo")
    assert r.status_code == 200
    report = r.json()
    assert report["persisted"] is True
    assert report["total"] > 1_000
    after = client.get("/api/data/database").json()["counts"]["observations"]
    assert after >= before + report["inserted"]


def test_persist_endpoint_without_data_is_404(client, monkeypatch):
    import app.custom_data as custom_data

    monkeypatch.setattr(custom_data, "get_custom_dataset", lambda: None)
    r = client.post("/api/data/persist")
    assert r.status_code == 404
