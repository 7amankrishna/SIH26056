"""End-to-end pipeline test.

Verifies the full flow that the dashboard depends on:

    demo data -> collection -> normalization -> quality -> store -> index
    -> API -> response contract

This is not a browser test, but it exercises the entire backend contract that
the React dashboard consumes, so the dashboard can be assumed to render against
real API data.
"""


def test_full_pipeline_via_api(client):
    # 1. Health / data window
    h = client.get("/api/health").json()
    assert h["status"] == "ok"

    # 2. Index value
    ov = client.get("/api/overview").json()
    assert ov["current_apix"] > 0
    assert ov["observation_count"] > 0

    # 3. Trend series feeds the hero chart
    trend = client.get("/api/index/trend?range=90d").json()
    assert len(trend["series"]) > 0
    assert all(p["apix"] is not None and p["apix"] > 0 for p in trend["series"])

    # 4. Route heatmap + route table
    heatmap = client.get("/api/routes/heatmap").json()["routes"]
    assert len(heatmap) > 0
    assert all(r["current_fare"] is not None for r in heatmap)

    # 5. Lead-time elasticity
    lt = client.get("/api/index/lead-time").json()
    assert lt["series"]
    assert any(s["lead_time_days"] == 1 for s in lt["series"])

    # 6. Airlines
    airlines = client.get("/api/airlines").json()["airlines"]
    assert len(airlines) > 0

    # 7. Quality + rejected drill-down
    quality = client.get("/api/quality").json()
    assert 0 <= quality["score"] <= 100
    rejected = client.get("/api/quality/rejected").json()
    assert "rows" in rejected

    # 8. Collection-status audit API
    runs = client.get("/api/collection-runs").json()
    assert runs["summary"]["active_sources"] >= 1

    # 9. Provenance trace from the latest index value
    latest = trend["series"][-1]["date"]
    prov = client.get(f"/api/provenance/{latest}").json()
    assert prov["api_value"] == ov["current_apix"] or abs(prov["api_value"] - ov["current_apix"]) < 1.0
    assert prov["route_contributions"]
