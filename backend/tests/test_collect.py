"""Collection-engine tests: scraping pipeline, policy gates, storage, toggle.

These run with no network at all — every test drives the real fetch/parse/
normalize/quality/store path through an in-process transport, which is exactly
how the offline demo works too.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.collect.adapters_http import HttpHtmlAdapter, HttpJsonAdapter
from app.collect.base import Query, RawBatch, RawOffer, SourceAdapter
from app.collect.normalize import QualityContext, dedupe_within_batch, normalize_offer
from app.collect.robots import RobotsGate
from app.collect.service import CollectionService
from app.collect.store import Store
from app.collect.transport import (
    AllowListTransport,
    CallableTransport,
    CollectionError,
    HttpResponse,
    Politeness,
)
# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def offer_payload(**kw):
    p = {
        "origin": "DEL", "destination": "BOM", "departure_date": "2026-09-19",
        "airline": "6E", "flight_number": "6E501", "cabin": "ECONOMY",
        "fare_class": "E", "currency": "INR", "base_fare": 3700.0, "taxes": 770.0,
        "fees": 290.0, "total_fare": 4800.0, "availability": "AVAILABLE",
        "seats_remaining": 9, "offer_id": "O1",
    }
    p.update(kw)
    return p


def make_query(lead=7):
    today = dt.date.today()
    return Query(origin="DEL", destination="BOM", departure_date=today + dt.timedelta(days=lead), lead_time_days=lead)


def scripted_transport(responses):
    """CallableTransport serving queued (status, body) or exceptions per call."""
    queue = list(responses)

    def handler(url: str):
        if not queue:
            raise AssertionError(f"unexpected extra request to {url}")
        nxt = queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if isinstance(nxt, HttpResponse):
            return nxt
        status, body = nxt
        return HttpResponse(url=url, status_code=status, body=body if isinstance(body, bytes) else json.dumps(body).encode())

    return CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=0))


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


@pytest.fixture
def service(store):
    svc = CollectionService.__new__(CollectionService)
    svc.store = store
    svc.adapters = {}
    svc.breakers = {}
    svc.transport = None
    svc._task = None
    svc._sweep_lock = __import__("asyncio").Lock()
    svc._current = None
    svc._last_sweep_error = None
    svc._sweep_seq = 0
    svc._registered = True
    svc._tasks = []
    return svc


class StubAdapter(SourceAdapter):
    """A source that returns what the test says it returns."""

    id = "stub"
    name = "Stub Source"
    type = "synthetic"
    compliance = "authorized"
    requires_robots_gate = False

    def __init__(self, outcomes):
        super().__init__()
        self.outcomes = list(outcomes)
        self.calls: list[Query] = []

    async def collect(self, query):
        self.calls.append(query)
        nxt = self.outcomes.pop(0) if self.outcomes else RawBatch(query=query)
        if isinstance(nxt, Exception):
            raise nxt
        nxt.query = query
        return nxt


def batch(offers):
    return RawBatch(
        query=make_query(),
        offers=[
            RawOffer(payload=op, source="stub", url="https://stub.invalid/v1/fares",
                     http_status=200, fetched_at=dt.datetime.now().isoformat(), latency_ms=120)
            for op in offers
        ],
    )


# --------------------------------------------------------------------------- #
# normalizer + quality gate
# --------------------------------------------------------------------------- #

def test_normalize_maps_canonical_fields():
    ctx = QualityContext.build(dt.date.today().isoformat(), {}, [])
    q = make_query()
    obs = normalize_offer(
        RawOffer(payload=offer_payload(), source="stub", url="u://x", fetched_at="2026-09-06T10:00:00+05:30"),
        q, ctx, seq=0,
    )
    assert obs["route"] == "DEL-BOM"
    assert obs["quality_status"] == "VALID"
    assert obs["total_fare"] == 4800.0
    assert obs["currency"] == "INR"
    assert obs["fingerprint"] and obs["raw_payload_reference"] == "u://x"


@pytest.mark.parametrize(
    "payload,expected_status",
    [
        ({"total_fare": 0}, "INVALID"),
        ({"total_fare": -5}, "INVALID"),
        ({"currency": "USD"}, "INVALID"),
        ({"availability": "SOLD_OUT"}, "SOLD_OUT"),
        ({"seats_remaining": 0}, "SOLD_OUT"),
        ({"origin": "DEL", "destination": "DEL"}, "INVALID"),
        ({"total_fare": 9_000_000}, "INVALID"),
    ],
)
def test_quality_gate_flags_bad_offers(payload, expected_status):
    ctx = QualityContext.build(dt.date.today().isoformat(), {}, [])
    obs = normalize_offer(
        RawOffer(payload=offer_payload(**payload), source="stub", url="u", fetched_at="2026-09-06T10:00:00+05:30"),
        make_query(), ctx, seq=0,
    )
    assert obs["quality_status"] == expected_status
    assert obs["exclusion_reason"]


def test_duplicate_fingerprint_is_flagged_not_indexed():
    today = dt.date.today().isoformat()
    fp = normalize_offer(
        RawOffer(payload=offer_payload(), source="stub", url="u", fetched_at=f"{today}T10:00:00+05:30"),
        make_query(), QualityContext.build(today, {}, []), 0,
    )["fingerprint"]
    ctx = QualityContext.build(today, {}, [fp])
    second = normalize_offer(
        RawOffer(payload=offer_payload(), source="stub", url="u", fetched_at=f"{today}T10:05:00+05:30"),
        make_query(), ctx, 1,
    )
    assert second["quality_status"] == "DUPLICATE"


def test_outlier_vs_route_level_is_suspicious():
    today = dt.date.today().isoformat()
    ctx = QualityContext.build(today, {"DEL-BOM": 4000.0}, [])
    obs = normalize_offer(
        RawOffer(payload=offer_payload(total_fare=8000.0), source="stub", url="u", fetched_at=f"{today}T10:00:00+05:30"),
        make_query(), ctx, 0,
    )
    assert obs["quality_status"] == "SUSPICIOUS"
    assert "statistical_outlier" in obs["exclusion_reason"]


def test_in_batch_dedupe_keeps_first():
    today = dt.date.today().isoformat()
    ctx = QualityContext.build(today, {}, [])
    q = make_query()
    rows = [
        normalize_offer(RawOffer(payload=offer_payload(), source="stub", url="u", fetched_at=f"{today}T10:00:00+05:30"), q, ctx, i)
        for i in range(3)
    ]
    out = dedupe_within_batch(rows)
    assert [o["quality_status"] for o in out] == ["VALID", "DUPLICATE", "DUPLICATE"]


def test_departure_before_collection_is_invalid():
    today = dt.date.today().isoformat()
    ctx = QualityContext.build(today, {}, [])
    q = Query(origin="DEL", destination="BOM", departure_date=dt.date.today() - dt.timedelta(days=3), lead_time_days=-3)
    obs = normalize_offer(
        RawOffer(payload=offer_payload(departure_date=q.departure_date.isoformat()), source="stub", url="u",
                 fetched_at=f"{today}T10:00:00+05:30"), q, ctx, 0,
    )
    assert obs["quality_status"] == "INVALID"
    assert "departure_before_collection" in obs["exclusion_reason"]


# --------------------------------------------------------------------------- #
# transport: politeness, retries, honest blocking
# --------------------------------------------------------------------------- #

def test_rate_limit_retries_then_raises(store):
    transport = scripted_transport([(429, b"", ), (429, b""), (429, b"")])
    transport.politeness.max_retries = 2
    transport.politeness.backoff_base = 0.001
    with pytest.raises(CollectionError) as exc:
        import asyncio

        asyncio.run(transport.get("https://stub.invalid/x"))
    assert exc.value.kind == "rate_limited"
    assert transport.politeness.retries == 2


def test_forbidden_is_blocked_not_retried():
    calls = []

    def handler(url):
        calls.append(url)
        return HttpResponse(url=url, status_code=403, body=b"nope")

    transport = CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=5))
    import asyncio

    with pytest.raises(CollectionError) as exc:
        asyncio.run(transport.get("https://stub.invalid/x"))
    assert exc.value.kind == "blocked"
    assert len(calls) == 1  # never retried: denial means stop


def test_per_sweep_request_ceiling_stops_politely():
    transport = scripted_transport([(200, {"offers": []})] * 10)
    transport.max_requests = 2
    import asyncio

    async def run():
        await transport.get("https://stub.invalid/1")
        await transport.get("https://stub.invalid/2")
        with pytest.raises(CollectionError) as exc:
            await transport.get("https://stub.invalid/3")
        return exc.value

    err = asyncio.run(run())
    # its own kind, so it never counts as a source failure against the breaker
    assert err.kind == "ceiling"
    assert "ceiling" in str(err)


def test_allowlist_blocks_unapproved_host():
    import asyncio

    inner = scripted_transport([(200, {"ok": True})])
    transport = AllowListTransport(["stub.invalid"], inner)
    with pytest.raises(CollectionError) as exc:
        asyncio.run(transport.get("https://evil.example/x"))
    assert exc.value.kind == "robots_denied"
    assert "allow-list" in str(exc.value)


# --------------------------------------------------------------------------- #
# robots gate + bot-wall handling
# --------------------------------------------------------------------------- #

def test_robots_disallow_prevents_request():
    import asyncio

    requested = []

    def handler(url):
        requested.append(url)
        if url.endswith("/robots.txt"):
            return HttpResponse(url=url, status_code=200, body=b"User-agent: *\nDisallow: /\n")
        return HttpResponse(url=url, status_code=200, body=b'{"offers":[]}')

    transport = CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=0))
    gate = RobotsGate()
    verdict = asyncio.run(gate.check(transport, "https://target.invalid/fares"))
    assert verdict.allowed is False
    assert "disallows" in verdict.reason
    assert requested == ["https://target.invalid/robots.txt"]  # nothing else touched


def test_robots_allow_and_crawl_delay_is_honoured():
    import asyncio

    def handler(url):
        if url.endswith("/robots.txt"):
            return HttpResponse(url=url, status_code=200, body=b"User-agent: *\nAllow: /fares\nCrawl-delay: 11\n")
        return HttpResponse(url=url, status_code=200, body=b'{"offers":[]}')

    transport = CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=0))
    verdict = asyncio.run(RobotsGate().check(transport, "https://target.invalid/fares?x=1"))
    assert verdict.allowed is True
    assert verdict.crawl_delay == 11.0


def test_robots_unreadable_fails_closed():
    import asyncio

    def handler(url):
        raise CollectionError("no egress", "network")

    transport = CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=0))
    verdict = asyncio.run(RobotsGate().check(transport, "https://target.invalid/fares"))
    assert verdict.allowed is False
    assert "failing closed" in verdict.reason


def test_bot_wall_interstitial_is_reported_as_blocked():
    import asyncio

    html = b"<html><head><title>Access</title></head><body>Our systems have detected unusual traffic from your network.</body></html>"
    adapter = HttpJsonAdapter(
        source_id="wall", name="Bot-walled source",
        url_template="https://wall.invalid/fares?origin={origin}&destination={destination}&departureDate={departure_date}",
        offers_path="offers",
    )
    adapter.bind_transport(scripted_transport([(200, html)]))
    adapter.robots_gate = RobotsGate()

    async def allowed(*a, **k):
        return None

    adapter._allowed = allowed  # authorized channel: gate not applicable here
    with pytest.raises(CollectionError) as exc:
        asyncio.run(adapter.collect(make_query()))
    assert exc.value.kind == "blocked"
    assert "no evasion attempted" in str(exc.value)


def test_generic_adapter_refuses_when_robots_denies():
    import asyncio

    def handler(url):
        return HttpResponse(url=url, status_code=200, body=b"User-agent: *\nDisallow: /\n")

    adapter = HttpJsonAdapter(
        source_id="gated", name="Gated",
        url_template="https://gated.invalid/fares?origin={origin}&destination={destination}&departureDate={departure_date}",
        offers_path="offers", compliance="robots_permitted",
    )
    adapter.bind_transport(CallableTransport(handler, politeness=Politeness(min_gap=0.0, max_retries=0)))
    with pytest.raises(CollectionError) as exc:
        asyncio.run(adapter.collect(make_query()))
    assert exc.value.kind == "robots_denied"


# --------------------------------------------------------------------------- #
# generic HTML adapter really parses markup
# --------------------------------------------------------------------------- #

def test_html_adapter_extracts_offers_from_markup():
    import asyncio

    page = """
    <html><body><table class="fares">
      <div class="offer"><span class="flight">6E501</span><span class="carrier">IndiGo</span>
           <span class="price">₹4,899</span><span class="cls">E</span></div>
      <div class="offer"><span class="flight">AI863</span><span class="carrier">Air India</span>
           <span class="price">₹6,120</span><span class="cls">B</span></div>
    </table></body></html>
    """
    adapter = HttpHtmlAdapter(
        source_id="htmlsrc", name="Public HTML prices",
        url_template="https://prices.invalid/del-bom/{departure_date}",
        offer_selector="div.offer",
        field_selectors={"flight_number": "span.flight", "airline": "span.carrier", "total": "span.price", "fare_class": "span.cls"},
        compliance="authorized",
    )
    adapter.bind_transport(scripted_transport([(200, page.encode())]))
    adapter.robots_gate = RobotsGate()
    adapter._allowed = lambda transport, url: asyncio.sleep(0)

    async def allowed(*a, **k):
        return None

    adapter._allowed = allowed
    batch = asyncio.run(adapter.collect(make_query()))
    assert len(batch.offers) == 2
    first = batch.offers[0].payload
    assert first["total_fare"] == 4899.0
    assert first["airline"] == "6E"
    assert first["flight_number"] == "6E501"


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def test_store_roundtrip_and_persistence(tmp_path):
    st = Store(tmp_path / "s.sqlite3")
    st.begin_run("run-a", "stub", "manual")
    st.insert_observations("run-a", [dict(
        observation_id="o-1", source="stub", origin="DEL", destination="BOM", route="DEL-BOM",
        departure_date="2026-09-19", collection_date="2026-09-06", collection_timestamp="2026-09-06T10:00:00+05:30",
        airline="6E", flight_number="6E501", cabin="ECONOMY", fare_class="E", lead_time_days=13,
        base_fare=3700.0, taxes=770.0, fees=290.0, total_fare=4800.0, currency="INR",
        availability="AVAILABLE", seats_remaining=9, raw_payload_reference="u", fingerprint="fp1",
        quality_status="VALID", quality_score=0.99, exclusion_reason=None, in_basket=1,
    )])
    st.finish_run("run-a", status="success", queries=1, requests=1, observations=1, valid_observations=1)
    st.set_state("data_mode", "live")

    again = Store(tmp_path / "s.sqlite3")  # a fresh process sees the same state
    assert again.counts()["observations"] == 1
    assert again.get_state("data_mode") == "live"
    assert again.fingerprints_for_day("2026-09-06") == {"fp1"}
    assert again.route_median_levels("2026-09-06")["DEL-BOM"] == 4800.0


def test_store_keeps_raw_payload_verbatim(tmp_path):
    from app.collect.base import RawOffer as RO

    st = Store(tmp_path / "s2.sqlite3")
    st.begin_run("r", "stub", "manual")
    payload = {"weird": "field", "nested": {"a": [1, 2]}, "total_fare": 1.0}
    st.add_raw_payloads("r", [RO(payload=payload, source="stub", url="u://x", http_status=200, fetched_at="t", latency_ms=5, query={"k": 1})])
    row = st.recent_payloads(1)[0]
    assert row["payload"] == payload          # untouched, incl. unknown fields
    assert row["url"] == "u://x"
    assert row["query"] == {"k": 1}


def test_blocked_run_is_recorded_not_hidden(tmp_path):
    st = Store(tmp_path / "s3.sqlite3")
    st.begin_run("rb", "stub", "scheduled")
    st.finish_run("rb", status="blocked", error_kind="blocked", detail="403 refused", queries=4, requests=4, failures=4)
    run = st.last_run(source="stub")
    assert run["status"] == "blocked"
    assert run["error_kind"] == "blocked"


# --------------------------------------------------------------------------- #
# service: sweep, circuit breaker, toggle
# --------------------------------------------------------------------------- #

def test_sweep_stores_observations_and_run(service):
    service.adapters = {"stub": StubAdapter([batch([offer_payload(), offer_payload(total_fare=5100.0, offer_id="O2")])])}
    import asyncio

    result = asyncio.run(service.run_sweep(routes=["DEL-BOM"]))
    assert result.observations == 2
    assert result.per_source["stub"]["status"] == "success"
    counts = service.store.counts()
    assert counts["observations"] == 2
    assert counts["raw_payloads"] == 2
    assert counts["runs"] == 1


def test_blocked_source_opens_breaker_and_stops_requesting(service):
    adapter = StubAdapter([CollectionError("403 refused", "blocked")])
    service.adapters = {"stub": adapter}
    import asyncio

    result = asyncio.run(service.run_sweep(routes=["DEL-BOM", "BOM-DEL"]))
    assert result.per_source["stub"]["status"] == "blocked"
    # STOP_AND_BACKOFF: the sweep must not keep hammering after a denial.
    assert len(adapter.calls) == 1
    assert service.breakers["stub"].open is True

    # Next sweep: breaker open -> zero requests, still recorded as blocked.
    calls_before = len(adapter.calls)
    second = asyncio.run(service.run_sweep(routes=["DEL-BOM"]))
    assert len(adapter.calls) == calls_before
    assert second.per_source["stub"]["status"] == "blocked"
    assert "circuit breaker open" in second.per_source["stub"]["detail"]
    assert service.store.last_run(source="stub")["status"] == "blocked"


def test_request_ceiling_does_not_trip_breaker(service):
    """A self-imposed politeness cap is not a source failure."""

    class CappedAdapter(StubAdapter):
        async def collect(self, query):
            await __import__("asyncio").sleep(0)
            raise CollectionError("per-sweep request ceiling (1) reached", "ceiling")

    svc = service
    svc.adapters = {"stub": CappedAdapter([])}
    import asyncio

    result = asyncio.run(svc.run_sweep(routes=["DEL-BOM", "BOM-DEL", "DEL-BLR"]))
    stats = result.per_source["stub"]
    assert stats["status"] == "partial"
    assert stats["failures"] == 0
    assert stats["ceiling_hit"] is True
    assert "ceiling" in stats["detail"]
    # the breaker must stay closed and the source stay usable next sweep
    assert svc.breakers["stub"].open is False
    assert svc.breakers["stub"].failures == 0


def test_partial_sweep_reports_failures(service):
    adapter = StubAdapter([
        batch([offer_payload()]),
        CollectionError("timeout contacting stub", "timeout", retryable=True),
        batch([offer_payload(total_fare=5000.0, offer_id="O2")]),
    ])
    service.adapters = {"stub": adapter}
    import asyncio

    result = asyncio.run(service.run_sweep(routes=["DEL-BOM", "BOM-DEL", "DEL-BLR"]))
    stats = result.per_source["stub"]
    assert stats["status"] == "partial"
    assert stats["failures"] == 1
    assert stats["observations"] == 2
    assert service.store.last_run(source="stub")["status"] == "partial"


def test_mode_toggle_persists_and_selects_dataset(service, monkeypatch):
    assert service.mode == "demo"
    service.store.set_state("data_mode", "live")
    assert service.mode == "live"
    with pytest.raises(ValueError):
        service.set_mode("google-flights")
    out = service.set_mode("live")
    assert out["effective_mode"] == "demo"  # live requested, store empty -> honest fallback
    assert "empty" in out["note"]

    service.adapters = {"stub": StubAdapter([batch([offer_payload()])])}
    import asyncio

    asyncio.run(service.run_sweep(routes=["DEL-BOM"]))
    assert service.set_mode("live")["effective_mode"] == "live"


def test_monitor_view_exposes_compliance_and_recent_runs(service):
    service.adapters = {"stub": StubAdapter([batch([offer_payload()])])}
    import asyncio

    asyncio.run(service.run_sweep(routes=["DEL-BOM"]))
    view = service.collection_runs_view()
    row = view["sources"]["stub"]
    assert row["status"] == "healthy"
    assert row["observations"] == 1
    assert row["compliance"] == "authorized"
    assert row["recent_runs"][0]["status"] == "success"
    assert view["summary"]["healthy_sources"] == 1


def test_queries_respect_route_scope_and_lead_times(service, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sweep_lead_times", [1, 3])
    monkeypatch.setattr(settings, "sweep_routes", [])
    qs = service.build_queries(routes=["DEL-BOM"])
    assert len(qs) == 2
    assert {q.route for q in qs} == {"DEL-BOM"}
    assert sorted(q.lead_time_days for q in qs) == [1, 3]
    assert all(q.departure_date >= dt.date.today() for q in qs)


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #

def test_api_toggle_and_raw_feed(store, monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient

    from app import dataset as ds_mod
    from app.routers import collect as collect_router

    svc = CollectionService.__new__(CollectionService)
    svc.store = store
    svc.adapters = {"stub": StubAdapter([batch([offer_payload()]), batch([offer_payload(total_fare=5200.0, offer_id="O2")])])}
    svc.breakers = {}
    svc.transport = None
    svc._task = None
    svc._sweep_lock = asyncio.Lock()
    svc._current = None
    svc._last_sweep_error = None
    svc._sweep_seq = 0
    svc._registered = True
    svc._tasks = []

    monkeypatch.setattr(collect_router, "collection_service", svc)
    from app.collect import service as svc_mod
    from app.collect import store as store_mod

    monkeypatch.setattr(svc_mod, "collection_service", svc)
    # `live.py` / `live_signature()` read the process-wide store singleton, so the
    # whole read path has to see the same test database the collector wrote to.
    monkeypatch.setattr(store_mod, "_store", store)
    monkeypatch.setattr(ds_mod, "_dataset", None)
    monkeypatch.setattr(ds_mod, "_live_dataset", None)
    monkeypatch.setattr(ds_mod, "_live_signature", None)

    from app.main import app

    with TestClient(app) as client:
        pol = client.get("/api/collect/policy").json()
        assert any("CAPTCHA" in x for x in pol["not_implemented"])
        assert any("sec-ch-ua" in x.lower() for x in pol["not_implemented"])

        bad = client.post("/api/data-source", json={"mode": "scrape-me"})
        assert bad.status_code == 422

        sweep = client.post("/api/collect/sweep", json={"wait": True, "routes": ["DEL-BOM"], "lead_times": [7]}).json()
        assert sweep["observations"] >= 1

        state = client.post("/api/data-source", json={"mode": "live"}).json()
        assert state["effective_mode"] == "live"

        overview = client.get("/api/overview").json()
        assert overview["data_origin"] == "live"
        assert overview["demo_mode"] is False

        raw = client.get("/api/collect/payloads").json()
        assert raw["count"] >= 1
        assert "total_fare" in raw["rows"][0]["payload"]

        fares = client.get("/api/collect/fares").json()
        assert fares["rows"][0]["route"] == "DEL-BOM"

        runs = client.get("/api/collect/runs").json()
        assert runs["runs"][0]["source"] == "stub"

        health = client.get("/api/health").json()
        assert health["data_origin"] == "live"

        assert client.post("/api/data-source", json={"mode": "demo"}).json()["effective_mode"] == "demo"
        assert client.get("/api/overview").json()["data_origin"] == "demo"

        client.delete("/api/collect/store")  # needs confirm
        assert client.delete("/api/collect/store?confirm=true").json()["cleared"] is True


def test_sweep_without_adapters_is_not_silently_successful(store, monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient

    from app.routers import collect as collect_router

    svc = CollectionService.__new__(CollectionService)
    svc.store = store
    svc.adapters = {}
    svc.breakers = {}
    svc.transport = None
    svc._task = None
    svc._sweep_lock = asyncio.Lock()
    svc._current = None
    svc._last_sweep_error = None
    svc._sweep_seq = 0
    svc._registered = True
    svc._tasks = []

    monkeypatch.setattr(collect_router, "collection_service", svc)
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/collect/sweep", json={"wait": True})
        assert r.status_code == 409
        assert "APIX_COLLECTOR_SOURCES" in r.json()["detail"]
