"""OTA scraper parsing + registration tests (offline — no browser, no network).

The extractors are pure functions of captured page data, so the scraping logic
is exercised here against realistic card text/JSON without Playwright. The
adapter module is also checked for lazy imports (the serverless path must never
pull in a browser) and for correct registration through the collection service.
"""

from __future__ import annotations

import sys

from app.collect.ota import extractors as ex
from app.collect.ota.adapters import PlaywrightOtaAdapter
from app.collect.service import CollectionService


# --------------------------------------------------------------------------- #
# URL builders
# --------------------------------------------------------------------------- #

def test_build_cleartrip_url_formats_date_for_cleartrip():
    url = ex.build_cleartrip_url("DEL", "BOM", "2026-09-19")
    assert url == (
        "https://www.cleartrip.com/flights/results"
        "?adults=1&childs=0&infants=0&class=Economy&depart_date=19/09/2026"
        "&from=DEL&to=BOM"
    )


def test_build_easemytrip_url_uses_city_names_and_srch():
    url = ex.build_easemytrip_url("DEL", "BOM", "2026-08-28")
    assert url.startswith("https://www.easemytrip.com/flight-search/listing?srch=")
    assert "DEL-Delhi-India" in url
    assert "BOM-Mumbai-India" in url
    assert "28%2F08%2F2026" in url  # DD/MM/YYYY, URL-encoded


# --------------------------------------------------------------------------- #
# Cleartrip parsing (ported regex logic)
# --------------------------------------------------------------------------- #

CLEARTRIP_CARDS = [
    "IndiGo\n6E-522\nNon-stop\n14:00\n15:20\n₹ 3,498\n1h 20m",
    "Air India\nAI-301\n1 stop\n08:30\n10:45\n₹ 5,200\n3h 15m",
    "SpiceJet\nSG-9091\nNon-stop\n19:55\n22:20\n₹ 5,667\n2h 25m",
    "no fare card here",
    "Akasa Air\nQP-1100\nNon-stop\n06:00\n08:10\n₹ 99,999\n",  # out of range
]


def test_parse_cleartrip_cards_extracts_canonical_payloads():
    rows = ex.parse_cleartrip_cards(CLEARTRIP_CARDS, "DEL", "BOM", "2026-09-19")

    assert [r["flight_number"] for r in rows] == ["6E-522", "AI-301", "SG-9091"]

    indigo = rows[0]
    assert indigo["airline"] == "IndiGo"
    assert indigo["origin"] == "DEL"
    assert indigo["destination"] == "BOM"
    assert indigo["departure_date"] == "2026-09-19"
    assert indigo["total_fare"] == 3498.0
    assert indigo["base_fare"] == 3331.43  # 3498 / 1.05
    assert indigo["taxes"] == 166.57       # 3498 - base (5% GST)
    assert indigo["stops"] == 0
    assert indigo["departure_time"] == "14:00"
    assert indigo["arrival_time"] == "15:20"
    assert indigo["currency"] == "INR"
    assert indigo["availability"] == "AVAILABLE"

    assert rows[1]["airline"] == "Air India"
    assert rows[1]["stops"] == 1


def test_parse_cleartrip_cards_dedupes_to_cheapest_per_flight():
    cards = [
        "IndiGo\n6E-522\nNon-stop\n14:00\n15:20\n₹ 3,498\n",
        "IndiGo\n6E-522\nNon-stop\n14:00\n15:20\n₹ 3,200\n",  # cheaper duplicate
    ]
    rows = ex.parse_cleartrip_cards(cards, "DEL", "BOM", "2026-09-19")
    assert len(rows) == 1
    assert rows[0]["total_fare"] == 3200.0


# --------------------------------------------------------------------------- #
# EaseMyTrip parsing (EXTRACT_JS output)
# --------------------------------------------------------------------------- #

EASEMYTRIP_CARDS = [
    {
        "airline": "IndiGo", "flight_code": "6E-512",
        "departure_time": "14:00", "arrival_time": "15:20",
        "origin_city": "Delhi", "dest_city": "Mumbai",
        "duration": "1h 20m", "stops": "Non-stop",
        "price_text": "₹ 4,899", "seats_left": "5 seats left",
    },
    {
        "airline": "SpiceJet", "flight_code": "SG-9091",
        "departure_time": "19:55", "arrival_time": "22:20",
        "duration": "2h 25m", "stops": "Non-stop",
        "price_text": "₹ 5,667", "seats_left": "2 seats left",
    },
    {
        "airline": None, "flight_code": None,
        "departure_time": None, "arrival_time": None,
        "price_text": "Sold out", "seats_left": None,
    },
]


def test_parse_easemytrip_cards_extracts_canonical_payloads():
    rows = ex.parse_easemytrip_cards(EASEMYTRIP_CARDS, "DEL", "BOM", "2026-09-19")

    assert [r["flight_number"] for r in rows] == ["6E-512", "SG-9091"]

    indigo = rows[0]
    assert indigo["airline"] == "IndiGo"
    assert indigo["total_fare"] == 4899.0
    assert indigo["base_fare"] == 4665.71  # 4899 / 1.05
    assert indigo["stops"] == 0
    assert indigo["seats_remaining"] == 5
    assert indigo["departure_time"] == "14:00"
    assert indigo["duration"] == "1h 20m"
    assert indigo["source_label"] == "EaseMyTrip"

    assert rows[1]["seats_remaining"] == 2


def test_parse_easemytrip_caps_at_cheapest_n(monkeypatch):
    monkeypatch.setattr(ex, "LIMIT_PER_SEARCH", 2)
    cards = [
        {"airline": "IndiGo", "flight_code": f"6E-{n:03d}", "price_text": f"₹ {1000 + n * 100:,}",
         "departure_time": "14:00", "arrival_time": "15:00", "stops": "Non-stop"}
        for n in range(5)
    ]
    rows = ex.parse_easemytrip_cards(cards, "DEL", "BOM", "2026-09-19")
    assert len(rows) == 2
    assert rows[0]["total_fare"] == 1000.0
    assert rows[1]["total_fare"] == 1100.0


# --------------------------------------------------------------------------- #
# Adapter wiring
# --------------------------------------------------------------------------- #

def test_ota_adapter_module_does_not_import_playwright_eagerly():
    # The serverless path must never pull in a browser just by importing the
    # adapter module (the import happens inside collect(), lazily).
    assert "playwright" not in sys.modules


def test_ota_adapter_describes_site_and_config():
    adapter = PlaywrightOtaAdapter(source_id="ota_cleartrip", site="cleartrip", headless=True, timeout_ms=1234)
    d = adapter.describe()
    assert d["id"] == "ota_cleartrip"
    assert d["type"] == "browser"
    assert d["compliance"] == "ota_unchecked"
    assert d["site"] == "cleartrip"
    assert d["headless"] is True
    assert d["timeout_ms"] == 1234
    assert adapter.base_url == "https://www.cleartrip.com"

    with __import__("pytest").raises(ValueError):
        PlaywrightOtaAdapter(source_id="ota_bad", site="nope")


def test_ota_sources_register_through_the_collection_service(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "collector_sources", ["ota_cleartrip", "ota_easemytrip"])
    svc = CollectionService()
    try:
        svc.ensure_registered()
        assert set(svc.adapters) == {"ota_cleartrip", "ota_easemytrip"}
        ct = svc.adapters["ota_cleartrip"]
        emt = svc.adapters["ota_easemytrip"]
        assert ct.site == "cleartrip"
        assert emt.site == "easemytrip"
        assert ct.type == "browser"
    finally:
        # Do not leak the registered adapters into the process-wide store state.
        svc.unregister("ota_cleartrip")
        svc.unregister("ota_easemytrip")
