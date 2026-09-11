"""Request-safe gating: browser scrapers must never be awaited inside a request.

Cleartrip/EaseMyTrip are Playwright scrapers that need Chromium + a long-lived
process. On a request-scoped runtime (no background loop) the old behaviour ran
the whole sweep synchronously inside the HTTP request, blew the platform's
function/gateway timeout (504) and stored nothing. These tests pin the new
contract: such sources are refused *fast* with an actionable message.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.collect.ota.adapters import PlaywrightOtaAdapter
from app.collect.service import CollectionService
from app.collect.store import Store


def _bare_service(store, adapters):
    svc = CollectionService.__new__(CollectionService)
    svc.store = store
    svc.adapters = adapters
    svc.breakers = {}
    svc.transport = None
    svc._task = None
    svc._sweep_lock = asyncio.Lock()
    svc._current = None
    svc._last_sweep_error = None
    svc._sweep_seq = 0
    svc._registered = True
    svc._tasks = []
    return svc


def test_ota_adapter_is_marked_request_unsafe():
    adapter = PlaywrightOtaAdapter(source_id="ota_cleartrip", site="cleartrip")
    assert adapter.request_safe is False
    assert adapter.cost_per_query_seconds > 0
    desc = adapter.describe()
    assert desc["request_safe"] is False
    assert desc["type"] == "browser"


def test_request_unsafe_sources_lists_browser_adapters():
    svc = CollectionService.__new__(CollectionService)
    svc.adapters = {
        "ota_cleartrip": PlaywrightOtaAdapter(source_id="ota_cleartrip", site="cleartrip"),
        "ota_easemytrip": PlaywrightOtaAdapter(source_id="ota_easemytrip", site="easemytrip"),
    }
    assert svc.request_unsafe_sources() == ["ota_cleartrip", "ota_easemytrip"]
    assert svc.request_unsafe_sources(["ota_cleartrip"]) == ["ota_cleartrip"]
    assert svc.request_unsafe_sources(["nope"]) == []


def test_request_scoped_sweep_refuses_browser_sources_fast(tmp_path, monkeypatch):
    from app.routers import collect as collect_router

    store = Store(tmp_path / "t.sqlite3")
    svc = _bare_service(store, {
        "ota_cleartrip": PlaywrightOtaAdapter(source_id="ota_cleartrip", site="cleartrip"),
    })
    monkeypatch.setattr(collect_router, "collection_service", svc)

    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/collect/sweep", json={"wait": True})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "browser scrapers" in detail
        assert "ota_cleartrip" in detail
        assert "docker compose" in detail
        # Nothing ran: the store is untouched and no run was recorded.
        assert store.counts()["observations"] == 0
        assert store.recent_runs() == []


def test_live_toggle_with_only_browser_sources_returns_a_note_not_a_hang(tmp_path, monkeypatch):
    from app import dataset as ds_mod
    from app.collect import store as store_mod
    from app.routers import collect as collect_router

    store = Store(tmp_path / "t.sqlite3")
    svc = _bare_service(store, {
        "ota_cleartrip": PlaywrightOtaAdapter(source_id="ota_cleartrip", site="cleartrip"),
        "ota_easemytrip": PlaywrightOtaAdapter(source_id="ota_easemytrip", site="easemytrip"),
    })
    monkeypatch.setattr(collect_router, "collection_service", svc)
    monkeypatch.setattr(store_mod, "_store", store)
    monkeypatch.setattr(ds_mod, "_dataset", None)
    monkeypatch.setattr(ds_mod, "_live_dataset", None)
    monkeypatch.setattr(ds_mod, "_live_signature", None)

    from app.main import app

    with TestClient(app) as client:
        state = client.post("/api/data-source", json={"mode": "live"})
        assert state.status_code == 200
        body = state.json()
        assert "browser scrapers" in (body.get("note") or "")
        assert "ota_cleartrip" in (body.get("note") or "")
        # No sweep ran inside the request: store still empty, no run log rows.
        assert body["has_live_data"] is False
        assert store.counts()["observations"] == 0
        assert store.recent_runs() == []
