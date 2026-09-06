"""Concrete collection sources.

``AmadeusAdapter``
    The recommended live source. Amadeus for Developers exposes an official,
    self-service **Flight Offers Search** REST API with a free test tier — i.e.
    a *permissioned* channel, which is what policy rule 3 asks for ("prefer
    authorized channels: licensed feeds, public APIs, permissioned access").
    Prices in the test environment are sample data; production credentials return
    real offers. Either way the shape of the data is identical, so the pipeline
    is exercised end-to-end for real.

``FixtureCaptureAdapter``
    An authorized *local* capture of OTA-shaped JSON served in-process. Needs no
    credentials and no network, so the whole live path (fetch -> parse ->
    normalize -> quality -> SQLite -> index -> API -> dashboard) is demonstrable
    offline. It is always labelled synthetic in the UI.

Neither adapter circumvents an access control. That is a hard design constraint:
see ``docs/SCRAPING_POLICY.md``.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import random
import time
from typing import Any, Optional

from ..config import settings
from ..dataset import AIRLINES, LEAD_FACTOR, ROUTE_AIRLINES, ROUTES
from .base import HealthStatus, Query, RawBatch, RawOffer
from .adapters_http import HttpJsonAdapter
from .transport import CallableTransport, CollectionError, HttpResponse, Politeness

# --------------------------------------------------------------------------- #
# Amadeus (permissioned official API)
# --------------------------------------------------------------------------- #


class AmadeusAdapter(HttpJsonAdapter):
    """Flight Offers Search against a keyed Amadeus self-service account."""

    id = "amadeus"
    name = "Amadeus Self-Test API"
    type = "json_api"
    compliance = "authorized"
    requires_robots_gate = False  # authenticated API, not a crawl
    requires_credentials = True

    def __init__(self, base_url: Optional[str] = None, *, source_id: str = "amadeus", name: Optional[str] = None):
        super().__init__(
            source_id=source_id,
            name=name or "Amadeus Self-Test API",
            url_template=f"{base_url or settings.amadeus_base_url}/v2/shopping/flight-offers"
            "?originLocationCode={origin}&destinationLocationCode={destination}"
            "&departureDate={departure_date}&adults=1&currencyCode={currency}&max=10",
            offers_path="data",
            compliance="authorized",
        )
        self.base_url = base_url or settings.amadeus_base_url
        self._token: Optional[str] = None
        self._token_until = 0.0

    # -- auth ------------------------------------------------------------- #
    async def _auth(self) -> str:
        if self._token and time.time() < self._token_until - 30:
            return self._token
        if not settings.amadeus_client_id or not settings.amadeus_client_secret:
            raise CollectionError(
                "Amadeus credentials not configured (set AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET)",
                "blocked",
            )
        creds = base64.b64encode(f"{settings.amadeus_client_id}:{settings.amadeus_client_secret}".encode()).decode()
        resp = await self.transport.post_form(
            f"{self.base_url}/v1/security/oauth2/token",
            {"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {creds}"},
        )
        doc = resp.json()
        token = doc.get("access_token")
        if not token:
            raise CollectionError(f"Amadeus token response carried no access_token: {doc.get('error_description', doc)}", "parse")
        self._token = str(token)
        self._token_until = time.time() + float(doc.get("expires_in", 1500))
        return self._token

    async def _authorized_get(self, url: str) -> HttpResponse:
        token = await self._auth()
        return await self.transport.get(url, accept="application/json", headers={"Authorization": f"Bearer {token}"})

    async def _allowed(self, transport, url: str) -> None:  # authorized channel: no robots gate
        return None

    # -- collection -------------------------------------------------------- #
    async def collect(self, query: Query) -> RawBatch:
        url = self._url_for(query)
        resp = await self._authorized_get(url)
        try:
            doc = resp.json()
        except Exception as exc:
            raise CollectionError(f"Amadeus returned a non-JSON body: {exc}", "parse") from exc
        if "errors" in doc:
            first = (doc["errors"] or [{}])[0]
            status = int(first.get("code") or 0)
            detail = str(first.get("detail") or first.get("title") or "unknown error")
            kind = "blocked" if status in (401, 403, 429) else "parse"
            raise CollectionError(f"Amadeus error {status}: {detail}", kind, status=status or None)

        data = doc.get("data") or []
        carriers = (doc.get("dictionaries") or {}).get("carriers") or {}
        batch = RawBatch(query=query, request_count=1)
        for offer in data:
            batch.offers.append(self._offer(offer, query, url, resp, carriers))
        if not batch.offers:
            batch.note = "Amadeus returned no offers for this date (no availability, not an error)"
        return batch

    def _offer(self, offer: dict[str, Any], q: Query, url: str, resp, carriers: dict[str, str]) -> RawOffer:
        price = offer.get("price") or {}
        itineraries = offer.get("itineraries") or [{}]
        segs = itineraries[0].get("segments") or [{}]
        first_seg = segs[0]
        carrier = first_seg.get("carrierCode") or ""
        total = float(price.get("grandTotal") or price.get("total") or 0)
        base = float(price.get("base") or total)
        taxes = 0.0
        for t in price.get("taxes") or []:
            taxes += float(t.get("amount") or 0)
        seats = offer.get("numberOfBookableSeats")
        availability = "SOLD_OUT" if seats == 0 else ("LIMITED" if isinstance(seats, int) and seats <= 9 else "AVAILABLE")
        depart = str(first_seg.get("departure", {}).get("at") or q.departure_date.isoformat())
        payload = {
            "offer_id": offer.get("id"),
            "origin": str(first_seg.get("departure", {}).get("iataCode") or q.origin).upper(),
            "destination": str(first_seg.get("arrival", {}).get("iataCode") or q.destination).upper(),
            "departure_date": depart[:10],
            "airline": carrier,
            "airline_name": carriers.get(carrier, carrier),
            "flight_number": f"{carrier}{first_seg.get('flightNumber', '')}".strip(),
            "cabin": (offer.get("travelerPricers") or [{}])[0].get("cabin")
            or (itineraries[0].get("segments") or [{}])[0].get("cabinClassName")
            or "ECONOMY",
            "fare_class": ((first_seg.get("bookingClassDetails") or [{}])[0].get("carrierCode") or ""),
            "currency": str(price.get("currency") or q.currency).upper(),
            "base_fare": base,
            "taxes": taxes,
            "fees": max(0.0, total - base - taxes),
            "total_fare": total,
            "availability": availability,
            "seats_remaining": seats,
            "stops": len(segs) - 1,
            "duration": itineraries[0].get("duration"),
            "raw_offer_id": offer.get("id"),
        }
        return RawOffer(
            payload=payload, source=self.id, url=url, http_status=resp.status_code,
            fetched_at=self._stamp(), latency_ms=resp.elapsed_ms, query=q.as_dict(),
        )

    async def health_check(self) -> HealthStatus:
        try:
            await self._auth()
        except CollectionError as exc:
            return HealthStatus(ok=False, state="blocked", detail=str(exc), compliance=self.compliance)
        return HealthStatus(
            ok=True, state="healthy", detail=f"OAuth token issued by {self.base_url}", compliance=self.compliance
        )


# --------------------------------------------------------------------------- #
# Offline authorized capture (no network, no credentials)
# --------------------------------------------------------------------------- #


def simulate_market(origin: str, destination: str, dep: dt.date, lead: int, sweep_seq: int) -> list[dict[str, Any]]:
    """One deterministic price tick for a route+date, shared by both captures.

    The JSON capture and the HTML capture render the *same* market state, so a
    demo can switch between "API-shaped" and "web-page-shaped" sources without
    the numbers moving.
    """
    rng = random.Random(int(hashlib.sha256(f"{origin}{destination}{dep}{lead}|{sweep_seq}".encode()).hexdigest()[:12], 16))
    route_key = f"{origin}-{destination}"
    meta = ROUTES.get(route_key) or next(iter(ROUTES.values()))
    airlines = ROUTE_AIRLINES.get(route_key) or list(AIRLINES)[:4]
    lf = LEAD_FACTOR.get(max(1, min(45, lead)), 1.0)

    offers: list[dict[str, Any]] = []
    for i, code in enumerate(airlines):
        factor = AIRLINES[code]["factor"]
        drift = 1.0 + rng.uniform(-0.035, 0.045) + min(0.20, 0.004 * sweep_seq) * rng.choice([-1, 1])
        total = round(meta["base_fare"] * factor * lf * drift, 2)
        outlier = rng.random() < 0.06
        if outlier:
            total = round(total * rng.uniform(1.3, 1.7), 2)
        seats = rng.choice([1, 2, 3, 7, 9, 14, 21, 33, 40])
        sold_out = rng.random() < 0.05
        hour = 5 + (i * 4) % 18
        offers.append(
            {
                "offerId": f"CAP-{origin}{destination}{dep.strftime('%y%m%d')}-{i}",
                "marketingCarrier": code,
                "carrierName": AIRLINES[code]["name"],
                "flightNumber": f"{code}{101 + rng.randint(0, 880)}",
                "departureAirport": origin,
                "arrivalAirport": destination,
                "departureDateTime": f"{dep.isoformat()}T{hour:02d}:{rng.choice([0, 15, 30, 45]):02d}:00",
                "cabin": "ECONOMY",
                "bookingClass": rng.choice(["E", "L", "M", "V", "K", "B", "Q"]),
                "currency": "INR",
                "fareComponents": {
                    "base": round(total * 0.78, 2),
                    "tax": round(total * 0.16, 2),
                    "fee": round(total * 0.06, 2),
                    "total": total,
                },
                "seatsLeft": 0 if sold_out else seats,
                "availability": "SOLD_OUT" if sold_out else ("LIMITED" if seats <= 9 else "AVAILABLE"),
                "numberOfStops": 0 if rng.random() < 0.82 else 1,
                "baggageCheckedKg": rng.choice([None, 15, 25]),
                "fareRules": {"refundable": rng.random() < 0.18, "changeable": rng.random() < 0.42},
            }
        )
    return offers


class CaptureTransport(CallableTransport):
    """Serves an OTA-style JSON payload from an in-process market simulator.

    This is *not* a stand-in for a real provider's data. It is a fixture: it
    exercises the identical fetch/parse/normalize path while making no network
    request at all, so the collector can be demoed and regression-tested offline.
    Every sweep produces a fresh (deterministic) price tick so movement is real
    *within the simulation*.
    """

    def __init__(self, sweep_seq: int, as_of: dt.date):
        super().__init__(self._handle, politeness=Politeness(min_gap=0.0, max_retries=0))
        self.sweep_seq = sweep_seq
        self.as_of = as_of
        self.requested: list[str] = []
        self.started = time.monotonic()

    def _handle(self, url: str) -> dict[str, Any] | HttpResponse:
        self.requested.append(url)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        origin = qs.get("origin", "DEL")
        destination = qs.get("destination", "BOM")
        dep = dt.date.fromisoformat(qs.get("departureDate", self.as_of.isoformat()))
        lead = int(qs.get("leadTime", (dep - self.as_of).days or 1))

        rng = random.Random(int(hashlib.sha256(f"{origin}{destination}{dep}{lead}|{self.sweep_seq}".encode()).hexdigest()[:12], 16))
        route_key = f"{origin}-{destination}"
        meta = ROUTES.get(route_key) or next(iter(ROUTES.values()))
        airlines = ROUTE_AIRLINES.get(route_key) or list(AIRLINES)[:4]
        lf = LEAD_FACTOR.get(max(1, min(45, lead)), 1.0)

        offers: list[dict[str, Any]] = []
        for i, code in enumerate(airlines):
            factor = AIRLINES[code]["factor"]
            drift = 1.0 + rng.uniform(-0.035, 0.045) + min(0.20, 0.004 * self.sweep_seq) * rng.choice([-1, 1])
            total = round(meta["base_fare"] * factor * lf * drift, 2)
            outlier = rng.random() < 0.06
            if outlier:
                total = round(total * rng.uniform(1.3, 1.7), 2)
            seats = rng.choice([1, 2, 3, 7, 9, 14, 21, 33, 40])
            sold_out = rng.random() < 0.05
            hour = 5 + (i * 4) % 18
            flight_no = f"{code}{101 + rng.randint(0, 880)}"
            offers.append(
                {
                    "offerId": f"CAP-{origin}{destination}{dep.strftime('%y%m%d')}-{i}",
                    "marketingCarrier": code,
                    "carrierName": AIRLINES[code]["name"],
                    "flightNumber": flight_no,
                    "departureAirport": origin,
                    "arrivalAirport": destination,
                    "departureDateTime": f"{dep.isoformat()}T{hour:02d}:{rng.choice([0, 15, 30, 45]):02d}:00",
                    "cabin": "ECONOMY",
                    "bookingClass": rng.choice(["E", "L", "M", "V", "K", "B", "Q"]),
                    "currency": "INR",
                    "fareComponents": {
                        "base": round(total * 0.78, 2),
                        "tax": round(total * 0.16, 2),
                        "fee": round(total * 0.06, 2),
                        "total": total,
                    },
                    "seatsLeft": 0 if sold_out else seats,
                    "availability": "SOLD_OUT" if sold_out else ("LIMITED" if seats <= 9 else "AVAILABLE"),
                    "numberOfStops": 0 if rng.random() < 0.82 else 1,
                    "baggageCheckedKg": rng.choice([None, 15, 25]),
                    "fareRules": {"refundable": rng.random() < 0.18, "changeable": rng.random() < 0.42},
                }
            )

        body = {
            "meta": {
                "generator": "apix-offline-capture",
                "sweep": self.sweep_seq,
                "capturedAt": self._stamp(),
                "synthetic": True,
                "note": "Authorized in-process capture used to exercise the live pipeline without third-party access.",
            },
            "queries": {
                "origin": origin,
                "destination": destination,
                "departureDate": dep.isoformat(),
                "leadTime": lead,
                "adults": 1,
                "currency": "INR",
            },
            "offers": offers,
        }
        return HttpResponse(
            url=url,
            status_code=200,
            headers={"content-type": "application/json", "x-ratelimit-remaining": "999"},
            body=json.dumps(body).encode(),
            elapsed_ms=int((time.monotonic() - self.started) * 1000) + rng.randint(45, 260),
        )

    @staticmethod
    def _stamp() -> str:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")


class FixtureCaptureAdapter(HttpJsonAdapter):
    """Configures the generic JSON adapter against the in-process capture."""

    id = "capture"
    name = "Authorized Offline Capture"
    type = "synthetic"
    compliance = "authorized"
    requires_robots_gate = False

    def __init__(self, sweep_seq: int = 0, as_of: Optional[dt.date] = None, *, source_id: str = "capture"):
        super().__init__(
            source_id=source_id,
            name="Authorized Offline Capture",
            url_template="https://capture.apix.invalid/v1/fares"
            "?origin={origin}&destination={destination}&departureDate={departure_date}"
            "&leadTime={lead_time_days}&currency={currency}",
            offers_path="offers",
            compliance="authorized",
            fields=_CAPTURE_FIELDS,
        )
        self.bind_transport(CaptureTransport(sweep_seq, as_of or dt.date.today()))
        self.base_url = "in-process://capture.apix.invalid"

    async def _allowed(self, transport, url: str) -> None:
        return None  # our own fixture; no third-party policy in play

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=True,
            state="healthy",
            detail="in-process authorized capture; no third-party access involved",
            compliance=self.compliance,
            latency_ms=1,
        )


from .adapters_http import FieldMap  # noqa: E402  (placed after import cycle-safe point)

_CAPTURE_FIELDS = FieldMap(
    offer_id="offerId",
    airline="marketingCarrier",
    flight_number="flightNumber",
    cabin="cabin",
    fare_class="bookingClass",
    total="fareComponents.total",
    base="fareComponents.base",
    taxes="fareComponents.tax",
    fees="fareComponents.fee",
    currency="currency",
    availability="availability",
    seats="seatsLeft",
    origin="departureAirport",
    destination="arrivalAirport",
    departure_date="departureDateTime",
    stops="numberOfStops",
)
