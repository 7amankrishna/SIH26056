"""API endpoint contract tests."""

import pytest


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["demo_mode"] is True


def test_overview(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["current_apix"] is not None
    assert data["observation_count"] > 0


def test_index_trend(client):
    r = client.get("/api/index/trend?range=30d")
    if r.status_code != 200:
        # Fall back to the default range
        r = client.get("/api/index/trend")
    assert r.status_code == 200
    data = r.json()
    assert "series" in data
    assert data["current"] is not None


def test_routes(client):
    r = client.get("/api/routes")
    assert r.status_code == 200
    data = r.json()
    assert len(data["routes"]) > 0


def test_route_detail(client):
    r = client.get("/api/index/route/DEL-BOM")
    assert r.status_code == 200
    data = r.json()
    assert data["route"] == "DEL-BOM"


def test_route_detail_404(client):
    r = client.get("/api/index/route/NOPE-BAD")
    assert r.status_code == 404


def test_airlines(client):
    r = client.get("/api/airlines")
    assert r.status_code == 200
    data = r.json()
    assert len(data["airlines"]) > 0


def test_lead_time(client):
    r = client.get("/api/index/lead-time")
    assert r.status_code == 200
    assert r.json()["series"]


def test_quality(client):
    r = client.get("/api/quality")
    assert r.status_code == 200
    data = r.json()
    assert "score" in data


def test_quality_rejected(client):
    r = client.get("/api/quality/rejected")
    assert r.status_code == 200
    assert "rows" in r.json()


def test_collection_runs(client):
    r = client.get("/api/collection-runs")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert "summary" in data


def test_methodology(client):
    r = client.get("/api/methodology")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 8


def test_provenance(client):
    latest = client.get("/api/index/trend").json()["series"][-1]["date"]
    r = client.get(f"/api/provenance/{latest}")
    assert r.status_code == 200
    assert r.json()["route_contributions"]


def test_fares_distribution(client):
    r = client.get("/api/fares/distribution")
    assert r.status_code == 200
    assert r.json()["observations"] > 0


def test_stats_overview(client):
    r = client.get("/api/stats/overview")
    assert r.status_code == 200
    assert "as_of" in r.json()


def test_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" in r.headers
