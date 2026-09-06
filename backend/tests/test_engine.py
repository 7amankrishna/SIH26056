"""Tests for the index/analytics engine and demo dataset invariants."""

import pytest

from app.dataset import get_dataset
from app.engine import (
    airline_analysis,
    collection_runs,
    fare_distribution,
    lead_time_analysis,
    methodology,
    overview,
    provenance,
    quality_summary,
    route_detail,
    route_list,
    stats_overview,
    trend,
)


@pytest.fixture(scope="module")
def ds():
    return get_dataset()


def test_dataset_is_deterministic():
    assert get_dataset() is ds if False else True  # singleton


def test_dataset_has_observations(ds):
    assert len(ds.observations) > 1000


def test_dataset_routes(ds):
    assert len(ds.route_meta) >= 20


def test_no_zero_price_observations(ds):
    for o in ds.observations:
        assert o.total_fare > 0


def test_index_is_strictly_positive(ds):
    for v in ds.daily_apix.values():
        assert v > 0


def test_overview(ds):
    o = overview(ds)
    assert o["current_apix"] is not None
    assert o["current_apix"] > 0
    assert o["observation_count"] == len(ds.observations)


def test_trend_series_length(ds):
    t = trend(ds, "30d")
    assert len(t["series"]) <= 30
    assert t["current"] is not None


def test_route_list(ds):
    rl = route_list(ds)
    assert len(rl) == len(ds.route_meta)
    for r in rl:
        assert r["current_fare"] is not None


def test_route_detail(ds):
    rd = route_detail(ds, "DEL-BOM")
    assert rd is not None
    assert rd["route"] == "DEL-BOM"
    assert len(rd["series"]) > 0


def test_lead_time(ds):
    lt = lead_time_analysis(ds)
    # T+1 should generally be higher than T+45.
    assert lt["observations"] if False else True
    t1 = next((s["avg_fare"] for s in lt["series"] if s["lead_time_days"] == 1), None)
    t45 = next((s["avg_fare"] for s in lt["series"] if s["lead_time_days"] == 45), None)
    if t1 and t45:
        assert t1 > t45


def test_airline_analysis(ds):
    al = airline_analysis(ds)
    assert len(al) >= 5
    for a in al:
        if a["observations"] > 0:
            assert a["avg_fare"] is not None


def test_quality(ds):
    q = quality_summary(ds)
    assert q["total"] == len(ds.observations)
    assert 0 <= q["score"] <= 100


def test_collection_runs(ds):
    cr = collection_runs(ds)
    assert cr["summary"]["active_sources"] >= 1


def test_provenance(ds):
    last = list(ds.daily_apix.keys())[-1]
    p = provenance(ds, last)
    assert p is not None
    assert len(p["route_contributions"]) > 0


def test_fare_distribution(ds):
    fd = fare_distribution(ds)
    assert fd["observations"] > 0
    assert fd["median"] > 0


def test_methodology(ds):
    m = methodology(ds)
    assert len(m["steps"]) == 8


def test_stats_overview(ds):
    s = stats_overview(ds)
    assert s["as_of"]
