"""HTML page capture — a real page scrape, with no API anywhere in the path.

Why this exists: the honest criticism of a "scraper" that pulls JSON from an
endpoint is that it is *not really scraping*, it is calling an API. This module
makes the point concrete by rendering an ordinary server-side fare **page** —
nested divs, `₹4,899.00` formatted amounts, sold-out rows with an empty price,
attributes instead of fields — and running it through `HttpHtmlAdapter`: the same
selector-based extractor that would hit a permitted live target.

Nothing about the pipeline changes between this and a real website: only the
bytes on the wire. `APIX_COLLECTOR_SOURCES=fixture_html` gives you a dashboard
whose data was scraped out of markup.
"""

from __future__ import annotations

import datetime as dt
import random
import time
from typing import Any, Optional

from .adapters_http import HttpHtmlAdapter
from .adapters_sources import simulate_market
from .base import HealthStatus, Query
from .transport import CallableTransport, HttpResponse, Politeness


def render_fare_page(origin: str, destination: str, dep: dt.date, lead: int, offers: list[dict[str, Any]], stamp: str) -> str:
    """Render one results page the way a fare table is typically laid out."""
    rows: list[str] = []
    for o in offers:
        sold = o["availability"] == "SOLD_OUT"
        fc = o["fareComponents"]
        # Deliberately un-friendly: currency symbol, thousands separators, and a
        # blank price cell when sold out — exactly what a selector scraper must cope with.
        price = "" if sold else "₹{:,.2f}".format(fc["total"])
        rows.append(
            '      <div class="offer" data-offer-id="{oid}">\n'
            '        <span class="flight">{fn}</span>\n'
            '        <span class="carrier">{cn}</span>\n'
            '        <span class="dept">{date}</span>\n'
            '        <span class="cls">{cls}</span>\n'
            '        <span class="base">₹{base:,.2f}</span>\n'
            '        <span class="tax">₹{tax:,.2f}</span>\n'
            '        <span class="fee">₹{fee:,.2f}</span>\n'
            '        <span class="price">{price}</span>\n'
            '        <span class="avail">{avail}</span>\n'
            '        <span class="seats">{seats}</span>\n'
            "      </div>".format(
                oid=o["offerId"],
                fn=o["flightNumber"],
                cn=o["carrierName"],
                date=o["departureDateTime"][:10],
                cls=o["bookingClass"],
                base=fc["base"],
                tax=fc["tax"],
                fee=fc["fee"],
                price=price,
                avail=o["availability"],
                seats=0 if sold else o["seatsLeft"],
            )
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en-IN">\n'
        "<head><title>Flights {o} to {d} on {dep}</title></head>\n"
        "<body>\n"
        "  <!-- fare table rendered server-side; collected per the site's published crawler policy -->\n"
        '  <div class="page">\n'
        '    <h1 class="route">{o} &rarr; {d}</h1>\n'
        '    <p class="asof">Prices captured {stamp} &middot; lead time {lead}d</p>\n'
        '    <div class="offers">\n'
        "{rows}\n"
        "    </div>\n"
        '    <p class="disclaimer">Sample fares for demonstration.</p>\n'
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    ).format(o=origin, d=destination, dep=dep.isoformat(), stamp=stamp, lead=lead, rows="\n".join(rows))


class HtmlCaptureTransport(CallableTransport):
    """Serves the rendered page in-process; the adapter above parses it."""

    def __init__(self, sweep_seq: int, as_of: dt.date):
        super().__init__(self._handle, politeness=Politeness(min_gap=0.0, max_retries=0))
        self.sweep_seq = sweep_seq
        self.as_of = as_of
        self.requested: list[str] = []
        self.started = time.monotonic()

    def _handle(self, url: str) -> HttpResponse:
        self.requested.append(url)
        from urllib.parse import parse_qs, urlparse

        qs = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        origin = qs.get("origin", "DEL")
        destination = qs.get("destination", "BOM")
        dep = dt.date.fromisoformat(qs.get("departureDate", self.as_of.isoformat()))
        lead = int(qs.get("leadTime", (dep - self.as_of).days or 1))
        offers = simulate_market(origin, destination, dep, lead, self.sweep_seq)
        rng = random.Random(f"latency|{origin}{destination}{dep}{lead}|{self.sweep_seq}")

        page = render_fare_page(origin, destination, dep, lead, offers, self._stamp())
        return HttpResponse(
            url=url,
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8", "x-ratelimit-remaining": "999"},
            body=page.encode("utf-8"),
            elapsed_ms=int((time.monotonic() - self.started) * 1000) + rng.randint(60, 340),
        )

    @staticmethod
    def _stamp() -> str:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")


class FixtureHtmlCaptureAdapter(HttpHtmlAdapter):
    """Scrapes the in-process page with the same selectors a real table needs."""

    id = "capture_html"
    name = "Authorized Offline Page Scrape"
    type = "html_page"
    compliance = "authorized"
    requires_robots_gate = False

    def __init__(self, sweep_seq: int = 0, as_of: Optional[dt.date] = None, *, source_id: str = "capture_html"):
        super().__init__(
            source_id=source_id,
            name="Authorized Offline Page Scrape",
            url_template="https://pagecapture.apix.invalid/fares"
            "?origin={origin}&destination={destination}&departureDate={departure_date}&leadTime={lead_time_days}",
            offer_selector="div.offer",
            field_selectors={
                "offer_id": "@data-offer-id",
                "flight_number": "span.flight",
                "airline": "span.carrier",
                "departure_date": "span.dept",
                "fare_class": "span.cls",
                "base": "span.base",
                "taxes": "span.tax",
                "fees": "span.fee",
                "total": "span.price",
                "availability": "span.avail",
                "seats": "span.seats",
            },
            compliance="authorized",
        )
        self._capture_total_marker = "₹"
        self.bind_transport(HtmlCaptureTransport(sweep_seq, as_of or dt.date.today()))
        self.base_url = "in-process://pagecapture.apix.invalid"

    async def _allowed(self, transport, url: str) -> None:
        return None  # our own fixture; no third-party policy in play

    def _block_to_payload(self, v: dict[str, str], q: Query) -> dict[str, Any]:
        payload = super()._block_to_payload(v, q)
        seats = (v.get("seats") or "").strip()
        payload["seats_remaining"] = int(seats) if seats.isdigit() else None
        # An empty price cell plus SOLD_OUT is how these pages mark no availability.
        if payload["availability"] == "SOLD_OUT" or payload["total_fare"] <= 0:
            payload["availability"] = "SOLD_OUT"
            payload["total_fare"] = 0.0
        return payload

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=True,
            state="healthy",
            detail="in-process HTML page capture; exercises the HTML scraper end-to-end with no network",
            compliance=self.compliance,
            latency_ms=1,
        )
