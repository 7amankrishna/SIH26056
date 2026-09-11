"""Pure parsing for the OTA scrapers (no browser here).

Each site has a URL builder and a parser that turns its rendered page into a
list of canonical fare payloads. The parsers are deterministic functions of
plain data (a page's text / a JS-extracted card list), so they can be unit
tested against captured fixtures and reused unchanged by the async adapter and
the sync CLI.

Canonical payload keys (superset of the engine's canonical fare model):

    offer_id, origin, destination, departure_date, airline, flight_number,
    cabin, fare_class, currency, base_fare, taxes, fees, total_fare,
    availability, seats_remaining, stops,
    departure_time, arrival_time, duration, source_label, scraped_at, raw

Anything the canonical model does not store in a column (times, duration, the
raw card) still lives in the payload, which the engine archives verbatim for
provenance.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

# IATA code -> full city name, as required by EaseMyTrip's URL scheme.
CITY_NAMES = {
    "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bangalore", "HYD": "Hyderabad",
    "PNQ": "Pune", "CCU": "Kolkata", "AMD": "Ahmedabad", "MAA": "Chennai",
    "GOI": "Goa", "GAU": "Guwahati", "SXR": "Srinagar",
}

# IATA prefix -> airline name (as used in the ankit scraper).
IATA_AIRLINES = {
    "6E": "IndiGo", "IX": "Air India Express", "AI": "Air India",
    "QP": "Akasa Air", "SG": "SpiceJet", "UK": "Vistara", "I5": "AIX Connect",
    "9I": "Alliance Air", "S5": "Star Air",
}

KNOWN_AIRLINE_NAMES = [
    "IndiGo", "Air India", "Akasa Air", "SpiceJet", "Vistara",
    "Air India Express", "Alliance Air", "Star Air",
]

# Only keep the N cheapest flights per search for EaseMyTrip — cuts data volume
# and avoids storing near-duplicate fare-bundle variants of the same flight.
LIMIT_PER_SEARCH = 20

# One browser round-trip extracts every EaseMyTrip card (ported from ankit).
EASEMYTRIP_EXTRACT_JS = """
() => {
    const cards = document.querySelectorAll('div.nw_listing_bx_tp');
    const results = [];
    cards.forEach(card => {
        const airlineEl = card.querySelector('h6.ft_13.ft_500');
        const flightCodeEl = card.querySelector('span.ft_13');
        const h4s = card.querySelectorAll('h4');
        const tmLcSpans = card.querySelectorAll('.tm_lc span');
        const durationEl = card.querySelector('p.ft_13');
        const stopsEl = card.querySelector('span.ft_11.gryclr');
        const priceEl = card.querySelector('h4[id^="spnPrice"]');
        const seatsEl = card.querySelector('div.seatlft');

        if (!priceEl || h4s.length < 2) return;  // skip malformed cards

        results.push({
            airline: airlineEl ? airlineEl.innerText.trim() : null,
            flight_code: flightCodeEl ? flightCodeEl.innerText.trim() : null,
            departure_time: h4s[0] ? h4s[0].innerText.trim() : null,
            arrival_time: h4s[1] ? h4s[1].innerText.trim() : null,
            origin_city: tmLcSpans[0] ? tmLcSpans[0].innerText.trim() : null,
            dest_city: tmLcSpans[2] ? tmLcSpans[2].innerText.trim() : null,
            duration: durationEl ? durationEl.innerText.trim() : null,
            stops: stopsEl ? stopsEl.innerText.trim() : null,
            price_text: priceEl.innerText.trim(),
            seats_left: seatsEl ? seatsEl.innerText.trim() : null,
        });
    });
    return results;
}
"""


def build_cleartrip_url(origin: str, destination: str, travel_date: str) -> str:
    """Results URL for a one-way economy search on Cleartrip.

    ``travel_date`` is ``YYYY-MM-DD``; Cleartrip wants ``DD/MM/YYYY``.
    """
    ct_date = datetime.strptime(travel_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    return (
        "https://www.cleartrip.com/flights/results"
        f"?adults=1&childs=0&infants=0&class=Economy&depart_date={ct_date}"
        f"&from={origin}&to={destination}"
    )


def build_easemytrip_url(origin: str, destination: str, travel_date: str) -> str:
    """Results URL for EaseMyTrip's listing page.

    The ``srch`` parameter format was confirmed from a real manual search:
    ``srch=DEL-Delhi-India|BOM-Mumbai-India|28/08/2026``.
    """
    date_str = datetime.strptime(travel_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    origin_city = CITY_NAMES.get(origin, origin)
    dest_city = CITY_NAMES.get(destination, destination)
    srch = f"{origin}-{origin_city}-India|{destination}-{dest_city}-India|{date_str}"
    return (
        "https://www.easemytrip.com/flight-search/listing"
        f"?srch={quote(srch, safe='')}"
        "&px=1-0-0&cbn=0&ar=undefined&isow=true&isdm=true"
        "&lang=en-us&IsDoubleSeat=false&CCODE=IN&curr=INR&apptype=B2C"
    )


def _airline_from_code(flight_code: str) -> str:
    prefix = (flight_code or "").split("-", 1)[0].strip().upper()
    return IATA_AIRLINES.get(prefix, "Unknown")


def _airline_name_from_text(text: str, flight_code: str) -> str:
    """Resolve an airline name: exact IATA code first, then name scan."""
    if flight_code and flight_code != "Unknown":
        return _airline_from_code(flight_code)
    lowered = text.lower()
    for name in KNOWN_AIRLINE_NAMES:
        if name.lower() in lowered:
            return name
    return "Unknown"


def _split_fare(fare: float) -> tuple[float, float]:
    """ankit's GST split: base = fare/1.05, GST = fare - base (5% GST)."""
    base = round(fare / 1.05, 2)
    gst = round(fare - base, 2)
    return base, gst


def _stops_count(text: str) -> Optional[int]:
    match = re.search(r"(Non-stop|non-stop|\b\d+\s*stop)", text)
    if not match:
        return None
    if "non-stop" in match.group(1).lower():
        return 0
    return int(match.group(1).split()[0])


def _base_payload(
    *,
    origin: str,
    destination: str,
    travel_date: str,
    airline: str,
    flight_code: str,
    fare: float,
    stops: Optional[int],
    source_label: str,
    departure_time: Optional[str] = None,
    arrival_time: Optional[str] = None,
    duration: Optional[str] = None,
    seats_left: Optional[str] = None,
    raw: Any = None,
) -> dict[str, Any]:
    base, gst = _split_fare(fare)
    seats = None
    if seats_left:
        m = re.search(r"\d+", str(seats_left))
        if m:
            seats = int(m.group())
    offer_id = f"{flight_code}|{travel_date}|{departure_time or ''}"
    return {
        "offer_id": offer_id,
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_date": travel_date,
        "airline": airline,
        "flight_number": flight_code,
        "cabin": "ECONOMY",
        "fare_class": None,
        "currency": "INR",
        "base_fare": base,
        "taxes": gst,
        "fees": 0.0,
        "total_fare": fare,
        "availability": "AVAILABLE",
        "seats_remaining": seats,
        "stops": stops,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "duration": duration,
        "source_label": source_label,
        "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "raw": raw,
    }


def parse_cleartrip_cards(
    card_texts: list[str],
    origin: str,
    destination: str,
    travel_date: str,
) -> list[dict[str, Any]]:
    """Parse Cleartrip results from a list of candidate card texts.

    Ported from ankit's per-``div`` scan: a card is a candidate when it carries
    a ``₹`` price, at least two clock times, a sane fare and (ideally) a flight
    code.
    """
    rows: list[dict[str, Any]] = []
    for text in card_texts:
        if "₹" not in text:
            continue

        times = re.findall(r"\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b", text)
        if len(times) < 2:
            continue

        price_matches = re.findall(r"₹\s*([\d,]+)", text)
        if not price_matches:
            continue
        prices = [int(p.replace(",", "")) for p in price_matches]
        clean_price = float(max(prices))  # real fare > any discount line
        if clean_price < 2000 or clean_price > 50000:
            continue

        code_match = re.search(r"\b([A-Z0-9]{2})\s*[-]?\s*(\d{3,4})\b", text, re.IGNORECASE)
        if code_match:
            prefix = code_match.group(1).upper()
            flight_code = f"{prefix}-{code_match.group(2)}"
            airline = IATA_AIRLINES.get(prefix, "Unknown")
        else:
            flight_code = "Unknown"
            airline = _airline_name_from_text(text, "")

        departure_time = f"{times[0][0]}:{times[0][1]}"
        arrival_time = f"{times[1][0]}:{times[1][1]}"

        rows.append(
            _base_payload(
                origin=origin,
                destination=destination,
                travel_date=travel_date,
                airline=airline,
                flight_code=flight_code,
                fare=clean_price,
                stops=_stops_count(text),
                source_label="Cleartrip",
                departure_time=departure_time,
                arrival_time=arrival_time,
                raw=text.strip()[:500],
            )
        )
    return _dedupe_cheapest(rows)


def parse_easemytrip_cards(
    raw_cards: list[dict[str, Any]],
    origin: str,
    destination: str,
    travel_date: str,
) -> list[dict[str, Any]]:
    """Parse the card list ``EASEMYTRIP_EXTRACT_JS`` returns."""
    origin_city = CITY_NAMES.get(origin, origin)
    dest_city = CITY_NAMES.get(destination, destination)

    rows: list[dict[str, Any]] = []
    for card in raw_cards:
        try:
            price_match = re.search(r"[\d,]+", card.get("price_text") or "")
            if not price_match:
                continue
            fare = float(price_match.group().replace(",", ""))

            flight_code = card.get("flight_code") or "Unknown"
            airline = (
                _airline_from_code(flight_code)
                if flight_code != "Unknown"
                else _airline_name_from_text(card.get("airline") or "", "")
            )

            rows.append(
                _base_payload(
                    origin=origin,
                    destination=destination,
                    travel_date=travel_date,
                    airline=airline,
                    flight_code=flight_code,
                    fare=fare,
                    stops=_stops_count(card.get("stops") or ""),
                    source_label="EaseMyTrip",
                    departure_time=card.get("departure_time"),
                    arrival_time=card.get("arrival_time"),
                    duration=card.get("duration"),
                    seats_left=card.get("seats_left"),
                    raw=card,
                )
            )
        except Exception:
            continue

    if len(rows) > LIMIT_PER_SEARCH:
        rows.sort(key=lambda r: r["total_fare"])
        rows = rows[:LIMIT_PER_SEARCH]
    return _dedupe_cheapest(rows)


def _dedupe_cheapest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the cheapest row per (origin, destination, flight, travel date)."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r["total_fare"])
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (r["origin"], r["destination"], r["flight_number"], r["departure_date"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
