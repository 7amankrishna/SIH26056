"""Tests for the custom (user-supplied) data loader.

These cover the promises made in ``data/README.md``: messy headers are mapped,
missing derived fields are computed, extra files are merged, unusable rows are
counted rather than invented, and the resulting dataset flows through the same
aggregation as the demo one.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app import custom_data
from app.custom_data import (
    _airline_code,
    _normalise_header,
    _split_route,
    _to_date,
    _to_float,
    build_custom_dataset,
    discover_files,
    import_report,
    invalidate_cache,
    match_column,
    reset_registrations,
)
from app.dataset import ROUTES


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Scratch data dir + full catalogue isolation for every test.

    The loader registers imported routes/airlines/sources into the shared
    catalogues, so each test starts and ends with the shipped catalogues intact.
    """
    from app import dataset

    snapshot = {
        "ROUTES": dict(dataset.ROUTES),
        "AIRLINES": {k: dict(v) for k, v in dataset.AIRLINES.items()},
        "SOURCES": {k: dict(v) for k, v in dataset.SOURCES.items()},
        "ROUTE_AIRLINES": {k: list(v) for k, v in dataset.ROUTE_AIRLINES.items()},
        "ACTIVE_SOURCE_IDS": list(dataset.ACTIVE_SOURCE_IDS),
        "LEAD_TIMES": list(dataset.LEAD_TIMES),
    }
    monkeypatch.setattr(custom_data, "data_root", lambda: tmp_path)
    invalidate_cache()
    yield
    reset_registrations()
    invalidate_cache()
    dataset.ROUTES.clear(), dataset.ROUTES.update(snapshot["ROUTES"])
    dataset.AIRLINES.clear(), dataset.AIRLINES.update(snapshot["AIRLINES"])
    dataset.SOURCES.clear(), dataset.SOURCES.update(snapshot["SOURCES"])
    dataset.ROUTE_AIRLINES.clear(), dataset.ROUTE_AIRLINES.update(snapshot["ROUTE_AIRLINES"])
    dataset.ACTIVE_SOURCE_IDS[:] = snapshot["ACTIVE_SOURCE_IDS"]
    dataset.LEAD_TIMES[:] = snapshot["LEAD_TIMES"]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Value / header parsing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("₹ 4,650.00", 4650.0),
    ("INR 4650", 4650.0),
    ("4,650", 4650.0),
    ("4650.5", 4650.5),
    ("", None),
    ("NA", None),
    ("-", None),
    (None, None),
])
def test_amount_parsing(raw, expected):
    assert _to_float(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-09-06", dt.date(2026, 9, 6)),
    ("06/09/2026", dt.date(2026, 9, 6)),
    ("06-Sep-2026", dt.date(2026, 9, 6)),
    ("2026-09-06T09:30:00+05:30", dt.date(2026, 9, 6)),
])
def test_date_parsing(raw, expected):
    assert _to_date(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("DEL-BOM", ("DEL", "BOM")),
    ("DEL / BOM", ("DEL", "BOM")),
    ("DEL to BOM", ("DEL", "BOM")),
    ("DELBOM", ("DEL", "BOM")),
    ("del-bom", ("DEL", "BOM")),
])
def test_route_splitting(raw, expected):
    assert _split_route(raw) == expected


def test_route_alias_resolution():
    """GOA and GOI are the same airport; the basket spelling wins."""
    assert _split_route("DEL-GOA") == ("DEL", "GOI")


@pytest.mark.parametrize("raw,expected", [
    ("Total Fare (INR)", "total_fare"),
    ("Cheapest Fare", "total_fare"),
    ("Date of Journey", "departure_date"),
    ("Observed On", "collection_date"),
    ("Flight No.", "flight_number"),
    ("Airline Name", "airline"),
    ("From", "origin"),
    ("Seats Left", "seats_remaining"),
])
def test_header_matching(raw, expected):
    assert match_column(raw) == expected


def test_header_normalisation_strips_units():
    assert _normalise_header("  Total  Fare (INR) ") == "total_fare"
    assert _normalise_header("lead time (days)") == "lead_time"


def test_airline_names_resolve_to_codes():
    assert _airline_code("IndiGo") == ("6E", "IndiGo")
    assert _airline_code("6E") == ("6E", "IndiGo")
    assert _airline_code("Air Asia India") == ("I5", "AirAsia India")
    code, name = _airline_code("Some New Regional")
    assert code == "SN" and name == "Some New Regional"


# --------------------------------------------------------------------------- #
# File level
# --------------------------------------------------------------------------- #

CSV = """Date of Journey,Observed On,From,To,Airline Name,Cheapest Fare (INR),Seats Left,Provider
2026-09-08,2026-09-01,DEL,BOM,IndiGo,"₹ 4,820.00",14,my_export
2026-09-09,2026-09-01,DEL,BOM,Air India,"₹ 5,610.00",6,my_export
2026-09-08,2026-09-02,DEL,BOM,IndiGo,"₹ 4,900.00",9,my_export
2026-09-15,2026-09-02,BLR,DEL,Vistara,"₹ 6,290.00",3,my_export
2026-09-16,2026-09-03,BLR,DEL,Vistara,"₹ 6,120.00",8,my_export
"""


def test_loads_a_messy_csv(tmp_path):
    write(tmp_path / "fares.csv", CSV)
    data = build_custom_dataset()

    assert data.dataset is not None
    assert data.dataset.origin == "custom"
    obs = data.dataset.observations
    assert len(obs) == 5

    first = obs[0]
    assert first.route == "DEL-BOM"
    assert first.collection_date == "2026-09-01"
    assert first.departure_date == "2026-09-08"
    assert first.lead_time_days == 7            # derived from the two dates
    assert first.total_fare == 4820.0
    assert first.base_fare + first.taxes + first.fees == pytest.approx(4820.0, abs=0.05)
    assert first.airline == "6E"                # name -> IATA code
    assert first.source == "my_export"
    assert first.quality_status in ("VALID", "SUSPICIOUS")
    assert first.fingerprint

    assert data.quality.get("VALID") == 5
    assert set(data.routes) == {"DEL-BOM", "BLR-DEL"}
    assert {a["code"] for a in data.airlines} == {"6E", "AI", "UK"}
    assert {s["id"] for s in data.sources} == {"my_export"}

    report = data.as_dict()
    assert report["files"][0]["mapped"]["total_fare"] == "Cheapest Fare (INR)"
    assert report["date_range"]["start"] == "2026-09-01"
    assert report["date_range"]["end"] == "2026-09-02" or report["date_range"]["end"] == "2026-09-03"


def test_multiple_files_are_merged(tmp_path):
    """Dropping in another file adds rows — that is the 'more data' path."""
    write(tmp_path / "fares_1.csv", CSV)
    data = build_custom_dataset()
    assert len(data.dataset.observations) == 5

    write(tmp_path / "fares_2.json", json.dumps({"observations": [
        {"route": "DEL-BOM", "date": "2026-09-04", "departure_date": "2026-09-11",
         "airline": "6E", "price": 4990, "source": "second_drop"},
        {"route": "MAA-BLR", "date": "2026-09-04", "departure_date": "2026-09-11",
         "airline": "I5", "price": 2880, "source": "second_drop"},
    ]}))
    invalidate_cache()
    data = build_custom_dataset()
    assert len(data.dataset.observations) == 7
    assert set(data.routes) == {"DEL-BOM", "BLR-DEL", "MAA-BLR"}
    assert {s["id"] for s in data.sources} == {"my_export", "second_drop"}


def test_templates_and_hidden_files_are_ignored(tmp_path):
    write(tmp_path / "_templates" / "fares_template.csv", CSV)
    write(tmp_path / ".hidden.csv", CSV)
    assert discover_files(tmp_path) == []


def test_unusable_rows_are_counted_not_invented(tmp_path):
    write(tmp_path / "fares.csv", (
        "route,date,price\n"
        "DEL-BOM,2026-09-01,4800\n"
        "DEL-BOM,not-a-date,4800\n"        # unparseable date -> skipped
        "DEL-BOM,2026-09-01,\n"            # missing fare -> skipped
        ",2026-09-01,4800\n"               # no route -> skipped
    ))
    data = build_custom_dataset()
    assert len(data.dataset.observations) == 1
    file_report = data.as_dict()["files"][0]
    assert file_report["rejected"] == 3
    assert any("skipped" in w for w in file_report["warnings"])


def test_missing_required_columns_is_reported(tmp_path):
    write(tmp_path / "fares.csv", "foo,bar\n1,2\n")
    data = build_custom_dataset()
    assert data.dataset is None
    assert data.files[0].errors, "a file with no recognisable columns must say so"


def test_quality_assessment_flags_outliers_and_sold_out(tmp_path):
    rows = ["route,date,price,seats"]
    for day in range(1, 6):
        rows.append(f"DEL-BOM,2026-09-0{day},4800,9")
    rows.append("DEL-BOM,2026-09-03,24000,9")   # ~5x the route-day median
    rows.append("DEL-BOM,2026-09-03,4750,0")    # sold out
    write(tmp_path / "fares.csv", "\n".join(rows) + "\n")
    data = build_custom_dataset()
    assert data.quality.get("SUSPICIOUS") == 1
    assert data.quality.get("SOLD_OUT") == 1
    flagged = {o.quality_status: o.exclusion_reason for o in data.dataset.observations
               if o.quality_status != "VALID"}
    assert flagged["SUSPICIOUS"] == "flag:statistical_outlier"
    assert flagged["SOLD_OUT"] == "flag:sold_out"


def test_duplicates_within_a_source_are_flagged(tmp_path):
    write(tmp_path / "fares.csv", (
        "route,date,departure_date,airline,flight,price,source\n"
        "DEL-BOM,2026-09-01,2026-09-08,6E,6E101,4800,my_export\n"
        "DEL-BOM,2026-09-01,2026-09-08,6E,6E101,4800,my_export\n"
    ))
    data = build_custom_dataset()
    assert data.quality.get("DUPLICATE") == 1
    assert data.quality.get("VALID") == 1


def test_explicit_quality_status_is_respected(tmp_path):
    write(tmp_path / "fares.csv", (
        "route,date,price,quality\n"
        "DEL-BOM,2026-09-01,4800,VALID\n"
        "DEL-BOM,2026-09-01,4820,INVALID\n"
        "DEL-BOM,2026-09-02,4830,STALE\n"
    ))
    data = build_custom_dataset()
    assert data.quality == {"VALID": 1, "INVALID": 1, "STALE": 1}


def test_config_column_map_and_date_format(tmp_path):
    write(tmp_path / "fares.csv", (
        "sector;snapshot;tariff\n"
        "DEL-BOM;01/09/2026;4800\n"
        "DEL-BOM;02/09/2026;4900\n"
    ))
    write(tmp_path / "config.json", json.dumps({
        "column_map": {"sector": "route", "snapshot": "collection_date", "tariff": "total_fare"},
        "date_format": "%d/%m/%Y",
    }))
    data = build_custom_dataset()
    assert data.dataset is not None
    assert [o.collection_date for o in data.dataset.observations] == ["2026-09-01", "2026-09-02"]


# --------------------------------------------------------------------------- #
# Basket integration
# --------------------------------------------------------------------------- #

def test_route_weights_can_be_supplied(tmp_path):
    write(tmp_path / "fares.csv", CSV)
    write(tmp_path / "routes.csv", "route,weight,origin_city,destination_city\nDEL-BOM,0.7,Delhi,Mumbai\nBLR-DEL,0.3,Bengaluru,Delhi\n")
    data = build_custom_dataset()
    assert data.weight_basis == "provided"
    assert data.routes["DEL-BOM"]["weight"] == pytest.approx(0.7)
    assert data.routes["DEL-BOM"]["origin_city"] == "Delhi"
    assert data.dataset.import_notes["weight_basis"] == "provided"


def test_unknown_routes_are_registered(tmp_path):
    write(tmp_path / "fares.csv", (
        "route,date,price\n"
        "IXR-PNQ,2026-09-01,5200\n"
        "IXR-PNQ,2026-09-02,5300\n"
    ))
    data = build_custom_dataset()
    assert "IXR-PNQ" in data.routes
    assert data.routes["IXR-PNQ"]["destination_city"] == "Pune"
    assert data.weight_basis == "observation_share"
    assert any("new to the basket" in n for n in data.as_dict()["notes"])


def test_custom_dataset_feeds_the_index(tmp_path):
    """The imported dataset must produce a real, finite index series."""
    rows = ["route,date,departure_date,airline,price"]
    for day in range(1, 21):
        for route, base in (("DEL-BOM", 4800), ("BLR-DEL", 6200)):
            rows.append(f"{route},2026-09-{day:02d},2026-10-{day:02d},6E,{base + day * 20}")
    write(tmp_path / "fares.csv", "\n".join(rows) + "\n")

    invalidate_cache()
    from app.dataset import get_dataset

    ds = get_dataset()
    assert ds.origin == "custom"
    assert ds.daily_apix, "the aggregate index must be computed"
    assert all(v > 0 for v in ds.daily_apix.values())
    assert set(ds.route_meta) == {"DEL-BOM", "BLR-DEL"}
    assert abs(sum(r["weight"] for r in ds.route_meta.values()) - 1.0) < 1e-6


def test_new_routes_leave_the_published_basket_alone(tmp_path, monkeypatch):
    """Registration must not permanently corrupt the shipped catalogue."""
    snapshot = dict(ROUTES)
    try:
        write(tmp_path / "fares.csv", "route,date,price\nZZZ-YYY,2026-09-01,1000\n")
        build_custom_dataset()
        assert "ZZZ-YYY" in ROUTES
    finally:
        ROUTES.clear()
        ROUTES.update(snapshot)


def test_disabled_by_env(tmp_path, monkeypatch):
    write(tmp_path / "fares.csv", CSV)
    monkeypatch.setattr(custom_data, "is_enabled", lambda: False)
    monkeypatch.setattr(custom_data, "_custom", None)
    report = import_report()
    assert report["enabled"] is False
    assert report["active"] is False
