"""The live scraper on a request-scoped (serverless) runtime.

Regression cover for the failure that took the deployed demo's scraper down
while every other screen kept working normally:

* the store refused to construct without ``DATABASE_URL`` in production, and the
  exception escaped as a bare ``500 Internal Server Error`` on ``/api/health``,
  ``/api/data-source`` and every ``/api/collect/*`` endpoint;
* even with storage, a sweep was queued on a background loop that a serverless
  platform freezes the moment the response is returned — so "switch to scraped
  data" never actually produced any data.

The end-to-end cases run the app in a subprocess with the platform's environment
set *before* import, because ``Settings`` reads the environment once at import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

#: Environment of a Vercel-style deployment: request-scoped, no durable disk,
#: offline capture source so no credentials or network are needed.
SERVERLESS_ENV = {
    "VERCEL": "1",
    "DATABASE_URL": None,
    "APIX_IGNORE_DATABASE_URL": None,
    "APIX_DATA_MODE": None,
    "APIX_COLLECTOR_ENABLED": None,
    "APIX_COLLECTOR_SOURCES": "fixture",
    "APIX_MIN_REQUEST_GAP_SECONDS": "0",
}


def _run(script: str, env: dict[str, "str | None"]) -> dict:
    """Run a snippet against the real app and return the JSON it prints.

    A ``None`` value removes the variable from the child environment, so import
    time defaults can be observed.
    """
    full_env = os.environ.copy()
    full_env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(BACKEND_ROOT)])
    for key, value in env.items():
        if value is None:
            full_env.pop(key, None)
        else:
            full_env[key] = value
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(BACKEND_ROOT),
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    marker = "@@JSON@@"
    assert marker in result.stdout, result.stdout + result.stderr
    return json.loads(result.stdout.split(marker, 1)[1].strip().splitlines()[0])


SETTINGS_SCRIPT = '''
import json
from app.config import settings
print("@@JSON@@")
print(json.dumps({
    "request_scoped_runtime": settings.request_scoped_runtime,
    "collector_enabled": settings.collector_enabled,
    "data_dir": str(settings.data_dir),
}))
'''

SCRAPER_FLOW = '''
import json
from fastapi.testclient import TestClient
from app.config import settings
from api.index import app


def call(client, method, path, **kwargs):
    r = getattr(client, method)(path, **kwargs)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return {"code": r.status_code, "body": body}


out = {"settings": {
    "request_scoped_runtime": settings.request_scoped_runtime,
    "collector_enabled": settings.collector_enabled,
    "data_dir": str(settings.data_dir),
}}
with TestClient(app, raise_server_exceptions=False) as c:
    out["health"] = call(c, "get", "/api/health")
    out["status"] = call(c, "get", "/api/collect/status")
    out["source"] = call(c, "get", "/api/data-source")
    out["switch"] = call(c, "post", "/api/data-source", json={"mode": "live"})
    out["sweep"] = call(c, "post", "/api/collect/sweep", json={})
    out["overview"] = call(c, "get", "/api/overview")
    out["fares"] = call(c, "get", "/api/collect/fares")
    out["runs"] = call(c, "get", "/api/collect/runs")
    out["payloads"] = call(c, "get", "/api/collect/payloads")
    out["collection_runs"] = call(c, "get", "/api/collection-runs")
print("@@JSON@@")
print(json.dumps(out))
'''


# --------------------------------------------------------------------------- #
# Deployed (serverless) runtime: the scraper has to work in-request
# --------------------------------------------------------------------------- #


def test_serverless_defaults_point_the_store_at_tmp_and_drop_the_loop():
    out = _run(
        SETTINGS_SCRIPT,
        {**SERVERLESS_ENV, "APIX_DATA_DIR": None, "APIX_COLLECTOR_ENABLED": None},
    )
    # /tmp is the only writable path on Vercel, and a background loop cannot
    # survive between invocations — so it stays off unless explicitly requested.
    assert out["request_scoped_runtime"] is True
    assert out["collector_enabled"] is False
    assert out["data_dir"] == "/tmp/apix-data"


def test_live_scraper_works_end_to_end_on_a_serverless_runtime(tmp_path):
    out = _run(
        SCRAPER_FLOW,
        {
            **SERVERLESS_ENV,
            "APIX_DATA_DIR": str(tmp_path / "store"),
            "DATABASE_URL": None,
        },
    )

    # Nothing 500s — the scraper's endpoints answer even before any data exists.
    assert out["health"]["code"] == 200, out["health"]
    assert out["status"]["code"] == 200, out["status"]
    assert out["source"]["code"] == 200, out["source"]
    health = out["health"]["body"]
    assert health["store_available"] is True
    assert health["store_backend"] == "sqlite"
    assert health["collector_running"] is False
    status = out["status"]["body"]
    assert status["request_scoped_sweeps"] is True
    assert status["store"]["ephemeral"] is True  # labelled, never silent
    assert status["store"]["durable"] is False
    assert status["store"]["ignores_database_url"] is False
    assert "DATABASE_URL" in (health["store_note"] or "")

    # Switching to scraped data collects *inside* the request that asked for it.
    assert out["switch"]["code"] == 200, out["switch"]
    switch = out["switch"]["body"]
    assert switch["effective_mode"] == "live"
    assert switch["has_live_data"] is True
    assert switch["store"]["observations"] > 0
    assert "first sweep collected" in switch["note"]

    # …and the whole dashboard then serves what was scraped.
    assert out["overview"]["code"] == 200
    assert out["overview"]["body"]["data_origin"] == "live"
    # Two sweeps have landed by now (the mode switch and the manual one).
    assert out["overview"]["body"]["observation_count"] == out["fares"]["body"]["total"]
    assert out["overview"]["body"]["observation_count"] >= switch["store"]["observations"]
    assert out["collection_runs"]["code"] == 200

    # A second sweep runs synchronously too, and the audit trail is complete.
    assert out["sweep"]["code"] == 200, out["sweep"]
    sweep = out["sweep"]["body"]
    assert sweep["synchronous"] is True
    assert sweep["observations"] > 0
    assert out["fares"]["body"]["count"] > 0
    assert out["runs"]["body"]["count"] >= 2
    assert out["runs"]["body"]["runs"][0]["status"] == "success"
    assert out["payloads"]["body"]["count"] > 0


def test_full_basket_is_scraped_when_the_source_costs_no_wall_clock_time(tmp_path):
    """Offline captures pay no politeness gap, so they must not be truncated."""
    out = _run(SCRAPER_FLOW, {**SERVERLESS_ENV, "APIX_DATA_DIR": str(tmp_path / "store")})

    assert out["status"]["body"]["request_sweep_query_cap"] is None
    assert out["status"]["body"]["queries_per_sweep"] == 72  # 24 basket routes x 3 lead times
    assert out["sweep"]["body"]["note"] is None
    assert out["runs"]["body"]["runs"][0]["queries"] == 72


# --------------------------------------------------------------------------- #
# Sweep sizing: a request-scoped sweep must fit the platform's request budget
# --------------------------------------------------------------------------- #


def _service_with_gap(gap: float, *, background: bool = False):
    from app.collect.service import CollectionService

    svc = CollectionService.__new__(CollectionService)
    svc.adapters = {"slow": SimpleNamespace(politeness=SimpleNamespace(min_gap=gap))}
    svc._task = SimpleNamespace(done=lambda: False) if background else None
    return svc


def test_request_sweep_cap_follows_the_source_politeness_gap(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "request_sweep_budget_seconds", 20.0)
    monkeypatch.setattr(settings, "min_seconds_between_requests", 2.0)

    # A background loop can take its time: never truncate.
    assert _service_with_gap(2.0, background=True).request_sweep_query_cap() is None
    # In-process sources cost no wall-clock time: never truncate either.
    assert _service_with_gap(0.0).request_sweep_query_cap() is None
    # A real HTTP source at 2s/request must fit the 20s budget: 10 queries.
    assert _service_with_gap(2.0).request_sweep_query_cap() == 10


def test_round_robin_cap_keeps_every_route_in_scope():
    """A shortened sweep widens coverage instead of scraping one route 10 times."""
    from app.collect.service import CollectionService, _cap_queries_round_robin
    from app.config import settings

    svc = CollectionService.__new__(CollectionService)
    all_queries = CollectionService.build_queries(svc)
    assert len(all_queries) == len(settings.sweep_lead_times) * 24

    capped = _cap_queries_round_robin(all_queries, 24)
    assert len(capped) == 24
    assert len({q.route for q in capped}) == 24  # every route still represented
    assert {q.lead_time_days for q in capped} == {min(settings.sweep_lead_times)}

    assert _cap_queries_round_robin(all_queries, None) == all_queries
    assert _cap_queries_round_robin(all_queries, 10_000) == all_queries


# --------------------------------------------------------------------------- #
# A database that is misconfigured or unreachable must not take the API down
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "database_url",
    [
        "https://github.com/7amankrishna/SIH26056",  # not a database address
        "sqlite:///tmp/nope.sqlite3",  # rejected at configuration time
        "postgresql://user:pass@127.0.0.1:1/none",  # valid, but nothing is listening
    ],
)
def test_explicit_database_opt_in_still_fails_closed_without_500s(tmp_path, database_url):
    out = _run(
        SCRAPER_FLOW,
        {
            **SERVERLESS_ENV,
            "APIX_DATA_DIR": str(tmp_path / "store"),
            "DATABASE_URL": database_url,
            "APIX_IGNORE_DATABASE_URL": "0",
            "APIX_DB_CONNECT_TIMEOUT_SECONDS": "1",
        },
    )

    # The analytical dashboard is untouched either way…
    assert out["health"]["code"] == 200, out["health"]
    assert out["health"]["body"]["store_available"] is False
    assert out["overview"]["code"] == 200
    assert out["overview"]["body"]["data_origin"] == "demo"

    if not database_url.startswith("postgresql:"):
        # Refused at configuration time: the store degrades to empty-but-honest,
        # and switching to scraped data is a 503 that says why.
        assert out["status"]["code"] == 200, out["status"]
        store = out["status"]["body"]["store"]
        assert store["available"] is False
        assert store["backend"] == "unavailable"
        assert "PostgreSQL" in (store["unavailable_reason"] or "")
        assert out["fares"]["code"] == 200
        assert out["fares"]["body"]["count"] == 0
        assert out["switch"]["code"] == 503, out["switch"]
        assert "collection store is unavailable" in out["switch"]["body"]["detail"].lower()
    else:
        # A configured database that cannot be reached is exposed as an
        # unavailable capability in status, while the action that needs it is a
        # clear 503 — never an opaque Internal Server Error.
        assert out["status"]["code"] == 200, out["status"]
        store = out["status"]["body"]["store"]
        assert store["available"] is False
        assert store["backend"] == "postgresql"
        assert "could not be reached" in (store["unavailable_reason"] or "")
        assert out["switch"]["code"] == 503, out["switch"]
