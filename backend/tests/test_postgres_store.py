"""PostgreSQL store integration test (opt-in).

The SQLite store is what the offline and Vercel demos run on; PostgreSQL is an
opt-in for durable history. They share one code path with a small SQL translation layer
(``Store._connect``). This test exercises that layer against a *real* PostgreSQL
so a schema or translation regression cannot ship unnoticed.

It is skipped unless ``APIX_TEST_DATABASE_URL`` points at a scratch database,
because the suite must stay runnable with no services:

    APIX_TEST_DATABASE_URL=postgresql://user:pass@host:5432/apix_test \
        python -m pytest tests/test_postgres_store.py

The database is treated as disposable: every run drops and recreates the tables
from ``db/supabase_schema.sql`` — the same file a Supabase user pastes into the
SQL editor — which also proves the shipped schema and the app's own
``CREATE TABLE IF NOT EXISTS`` bootstrap agree.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

import app.collect.store as store_module
from app.collect.store import Store

DATABASE_URL = os.environ.get("APIX_TEST_DATABASE_URL", "").strip()
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "db" / "supabase_schema.sql"

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set APIX_TEST_DATABASE_URL to a scratch PostgreSQL database to run this",
)


@pytest.fixture()
def pg_store(monkeypatch):
    """A store on a real PostgreSQL, schema freshly applied from the shipped file."""
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DROP TABLE IF EXISTS public.observations, public.raw_payloads, "
            "public.collection_runs, public.apix_state, public.schema_meta CASCADE"
        )
        cur.execute(SCHEMA_FILE.read_text())
    conn.close()

    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", "0")
    previous = store_module._store
    store_module._store = None
    store = Store()  # also runs the app's own IF NOT EXISTS bootstrap on top
    try:
        yield store
    finally:
        store_module._store = previous


def _observation(observation_id: str, *, total_fare: float = 4800.0, status: str = "VALID") -> dict:
    today = dt.date.today().isoformat()
    return {
        "observation_id": observation_id,
        "source": "capture",
        "origin": "DEL",
        "destination": "BOM",
        "route": "DEL-BOM",
        "departure_date": today,
        "collection_date": today,
        "collection_timestamp": f"{today}T09:00:00+05:30",
        "airline": "6E",
        "flight_number": "6E501",
        "cabin": "ECONOMY",
        "fare_class": "M",
        "lead_time_days": 7,
        "base_fare": round(total_fare * 0.78, 2),
        "taxes": round(total_fare * 0.16, 2),
        "fees": round(total_fare * 0.06, 2),
        "total_fare": total_fare,
        "currency": "INR",
        "availability": "AVAILABLE",
        "seats_remaining": 9,
        "raw_payload_reference": "sha-1",
        "fingerprint": f"fp-{observation_id}",
        "quality_status": status,
        "quality_score": 0.95,
        "exclusion_reason": None,
    }


def test_shipped_schema_matches_the_app_bootstrap(pg_store):
    """db/supabase_schema.sql and the app's own DDL describe the same tables."""
    assert pg_store.backend == "postgresql"
    assert pg_store.available is True
    assert pg_store.durable is True
    assert pg_store.ephemeral is False

    counts = pg_store.counts()
    assert counts["available"] is True
    assert counts["db_path"] == "postgresql"
    assert counts["observations"] == 0

    # The app's bootstrap (CREATE … IF NOT EXISTS) ran on top of the shipped file
    # without conflicting: every index the code expects exists, exactly once.
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexname, count(*) FROM pg_indexes WHERE schemaname = 'public' "
                "GROUP BY indexname HAVING count(*) > 1"
            )
            assert cur.fetchall() == []
            cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            names = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert {
        "ix_obs_day", "ix_obs_route_date", "ix_obs_fp_day", "ix_obs_source",
        "ix_runs_started", "ix_runs_source_started", "ix_raw_run", "ix_raw_source",
    } <= names


def test_state_run_and_observation_crud_round_trips(pg_store):
    today = dt.date.today().isoformat()

    # The dashboard toggle (apix_state) — upsert twice, second value wins.
    pg_store.set_state("data_mode", "live")
    pg_store.set_state("data_mode", "demo")
    assert pg_store.get_state("data_mode") == "demo"
    assert pg_store.get_state("missing", "fallback") == "fallback"

    # The run log, including the blocked/failed statuses the monitor shows.
    pg_store.begin_run("run-1", "capture", "manual")
    assert pg_store.last_run(source="capture")["status"] == "running"
    pg_store.finish_run(
        "run-1", status="success", detail="2 observations from 1 queries",
        queries=1, requests=1, observations=2, valid_observations=2,
        duplicates=0, invalid=0, suspicious=0, failures=0, avg_latency_ms=120,
    )
    run = pg_store.recent_runs(limit=5)[0]
    assert run["status"] == "success"
    assert run["avg_latency_ms"] == 120
    assert run["finished_at"]

    # Raw payloads verbatim + normalized observations.
    class _Offer:
        source = "capture"
        url = "https://capture.apix.invalid/v1/fares?origin=DEL"
        http_status = 200
        fetched_at = f"{today}T09:00:00+05:30"
        latency_ms = 120
        query = {"origin": "DEL", "destination": "BOM"}
        payload = {"offerId": "O1", "total_fare": 4800.0}

    assert pg_store.add_raw_payloads("run-1", [_Offer(), _Offer()]) == 2
    assert pg_store.insert_observations("run-1", [_observation("obs-1"), _observation("obs-2", total_fare=5200.0)]) == 2

    # Re-inserting the same observation_id must be ignored, not duplicated or fatal.
    assert pg_store.insert_observations("run-1", [_observation("obs-1")]) == 0

    counts = pg_store.counts()
    assert counts["observations"] == 2
    assert counts["valid_observations"] == 2
    assert counts["raw_payloads"] == 2
    assert counts["runs"] == 1
    assert counts["days_collected"] == 1
    assert counts["by_status"] == {"VALID": 2}

    rows = pg_store.all_observations()
    assert [r["observation_id"] for r in rows] == ["obs-1", "obs-2"]
    assert rows[1]["total_fare"] == 5200.0

    payloads = pg_store.recent_payloads(limit=10, source="capture")
    assert len(payloads) == 2
    assert payloads[0]["payload"]["offerId"] == "O1"
    assert payloads[0]["query"]["origin"] == "DEL"


def test_date_window_queries_translate_to_postgres(pg_store):
    """`date(col) >= date(?)` and the `- N day` window must both work on PG."""
    today = dt.date.today()
    older = (today - dt.timedelta(days=3)).isoformat()
    stale = _observation("obs-old", total_fare=3000.0)
    stale["collection_date"] = older
    stale["collection_timestamp"] = f"{older}T09:00:00+05:30"

    pg_store.begin_run("run-2", "capture", "manual")
    pg_store.insert_observations("run-2", [_observation("obs-new"), stale])

    # since=window (used by the live dataset builder)
    assert len(pg_store.all_observations(since=today.isoformat())) == 1
    assert len(pg_store.all_observations(since=older)) == 2

    # 7-day median window (used by the quality gate's outlier test)
    medians = pg_store.route_median_levels(today.isoformat(), window_days=7)
    assert medians["DEL-BOM"] == pytest.approx(3900.0)  # median of 3000 and 4800

    # Narrow window excludes the older day.
    assert pg_store.route_median_levels(today.isoformat(), window_days=1)["DEL-BOM"] == pytest.approx(4800.0)

    assert pg_store.fingerprints_for_day(today.isoformat()) == {"fp-obs-new"}
    assert pg_store.sources_seen() == ["capture"]


def test_ipv4_pinned_connection_round_trips(pg_store):
    """The ``hostaddr``-pinned URL produced by the IPv4 fallback must really work.

    A dual-stack database host plus a runtime without outbound IPv6 is dialed
    through this URL instead of the plain one, so it has to carry the hostname
    (for TLS) and still execute ordinary reads and writes.
    """
    pinned = store_module.pin_database_url_to_ipv4(DATABASE_URL)
    if pinned is None:
        pytest.skip("scratch database host publishes no IPv4 address to pin")
    assert "hostaddr=" in pinned

    pg_store._effective_url = pinned
    pg_store.set_state("data_mode", "live")
    assert pg_store.get_state("data_mode") == "live"

    pg_store.begin_run("run-pinned", "capture", "manual")
    assert pg_store.insert_observations("run-pinned", [_observation("obs-pinned")]) == 1
    counts = pg_store.counts()
    assert counts["observations"] == 1
    assert counts["valid_observations"] == 1


def test_reset_clears_every_table(pg_store):
    pg_store.set_state("data_mode", "live")
    pg_store.begin_run("run-3", "capture", "manual")
    pg_store.insert_observations("run-3", [_observation("obs-3")])

    pg_store.reset()

    assert pg_store.counts()["observations"] == 0
    assert pg_store.recent_runs() == []
    assert pg_store.get_state("data_mode") is None
