"""Generic policy-respecting fetch adapters.

These are the actual "scraper" implementations. Both are *declarative*: a
source is a URL template, a place to read the offers from, and a field map. That
keeps the politeness/robots/bot-wall logic in one place instead of copy-pasted
per source, and means adding a permitted source is configuration, not code.

    http_json  -> a public JSON endpoint that permits automated access
    http_html  -> a public HTML price page that permits automated access
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base import HealthStatus, Query, RawBatch, RawOffer, SourceAdapter
from .robots import RobotsGate
from .transport import CollectionError, HttpTransport


def _dig(obj: Any, path: str) -> Any:
    """Follow a dotted path (``data.offers``) through dicts/lists."""
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _int_or_none(value: Any) -> Optional[int]:
    """First integer in a cell's text, e.g. '3 left' -> 3, '' -> None."""
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def _money(value: Any) -> float:
    """Parse '4,899.00', '₹4899', 'INR 4,899', 4899 -> 4899.0."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return 0.0
    # collapse accidental multi-dots ("1.234.56" -> "1234.56" style grouping)
    if cleaned.count(".") > 1:
        head, *rest = cleaned.split(".")
        cleaned = head + "".join(rest)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


@dataclass
class FieldMap:
    """How a source's own field names map onto the canonical fare model."""

    offer_id: str = "offer_id"
    airline: str = "airline"
    flight_number: str = "flight_number"
    cabin: str = "cabin"
    fare_class: str = "fare_class"
    total: str = "total"
    base: str = "base"
    taxes: str = "taxes"
    fees: str = "fees"
    currency: str = "currency"
    availability: str = "availability"
    seats: str = "seats_remaining"
    origin: str = "origin"
    destination: str = "destination"
    departure_date: str = "departure_date"
    stops: str = "stops"
    #: optional post-processors keyed by canonical field
    transforms: dict[str, Callable[[Any], Any]] = field(default_factory=dict)


def _norm_airline(value: Any) -> str:
    """'IndiGo', '6E 512', 'AI123' -> '6E' / 'AI' where possible."""
    s = str(value or "").strip().upper()
    if not s:
        return "NA"
    m = re.match(r"^([A-Z0-9]{2})(?=\d|\s|$)", s)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z]{2})\d{2,4}\b", s)
    if m:
        return m.group(1)
    known = {
        "INDIGO": "6E", "AIR INDIA": "AI", "SPICEJET": "SG", "VISTARA": "UK",
        "AKASA": "QP", "AIRASIA": "I5", "STARLUX": "JX",
    }
    for label, code in known.items():
        if label in s:
            return code
    return s[:2] if len(s) >= 2 else "NA"


class HttpJsonAdapter(SourceAdapter):
    """Reads an authorized, machine-readable JSON endpoint.

    ``url_template`` supports ``{origin}``, ``{destination}``,
    ``{departure_date}``, ``{lead_time_days}``, ``{cabin}``, ``{currency}``.
    """

    type = "json_api"
    compliance = "robots_permitted"
    requires_robots_gate = True

    def __init__(
        self,
        *,
        source_id: str,
        name: str,
        url_template: str,
        offers_path: str = "offers",
        fields: Optional[FieldMap] = None,
        compliance: Optional[str] = None,
        robots_gate: Optional[RobotsGate] = None,
        health_url: Optional[str] = None,
        base_date_placeholder: Optional[Callable[[], str]] = None,
    ):
        super().__init__()
        self.id = source_id
        self.name = name
        self.url_template = url_template
        self.offers_path = offers_path
        self.fields = fields or FieldMap()
        if compliance:
            self.compliance = compliance
        self.robots_gate = robots_gate or RobotsGate()
        self.health_url = health_url
        self.base_date_placeholder = base_date_placeholder
        self.base_url = url_template.split("{", 1)[0].rstrip("/")

    @property
    def base_url_host(self) -> str:
        """Scheme+host of the configured template — the only host we may contact."""
        tail = self.base_url.split("//", 1)[-1]
        return tail.split("/", 1)[0]

    # ------------------------------------------------------------------ #
    def _url_for(self, q: Query) -> str:
        return self.url_template.format(
            origin=q.origin,
            destination=q.destination,
            departure_date=q.departure_date.isoformat(),
            lead_time_days=q.lead_time_days,
            cabin=q.cabin.lower(),
            currency=q.currency,
        )

    async def _allowed(self, transport: HttpTransport, url: str) -> None:
        if not self.requires_robots_gate or self.compliance == "authorized":
            return
        verdict = await self.robots_gate.check(transport, url)
        if not verdict.allowed:
            raise CollectionError(f"{verdict.reason} — not requesting {url}", "robots_denied")
        if verdict.crawl_delay:
            transport.politeness.min_gap = max(transport.politeness.min_gap, verdict.crawl_delay)

    async def health_check(self) -> HealthStatus:
        url = self.health_url or self.url_template.format(
            origin="DEL", destination="BOM", departure_date="2026-09-19",
            lead_time_days=7, cabin="economy", currency="INR",
        )
        try:
            await self._allowed(self.transport, url)
            resp = await self.transport.get(url, accept="application/json,*/*")
        except CollectionError as exc:
            return HealthStatus(
                ok=False,
                state="blocked" if exc.kind in ("blocked", "robots_denied") else "degraded",
                detail=str(exc),
                compliance=self.compliance,
            )
        return HealthStatus(
            ok=True, state="healthy", detail=f"{resp.status_code} from {url}",
            compliance=self.compliance, latency_ms=resp.elapsed_ms,
        )

    async def collect(self, query: Query) -> RawBatch:
        url = self._url_for(query)
        await self._allowed(self.transport, url)
        resp = await self.transport.get(url, accept="application/json,*/*")
        self._guard_against_denial(resp)
        try:
            doc = resp.json()
        except Exception as exc:
            raise CollectionError(f"response from {self.name} is not valid JSON: {exc}", "parse") from exc

        rows = _dig(doc, self.offers_path)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise CollectionError(
                f"path '{self.offers_path}' not found in {self.name}'s payload", "parse"
            )

        batch = RawBatch(query=query, request_count=1)
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            offer = self._to_raw_offer(raw, query, url, resp)
            if offer is not None:
                batch.offers.append(offer)
        if not batch.offers:
            batch.note = f"HTTP {resp.status_code} but zero offers at '{self.offers_path}'"
        return batch

    def _to_raw_offer(self, raw: dict[str, Any], q: Query, url: str, resp) -> Optional[RawOffer]:
        f = self.fields
        total = _money(_dig(raw, f.total))
        base = _money(_dig(raw, f.base)) or total
        payload: dict[str, Any] = {
            "offer_id": _dig(raw, f.offer_id),
            "origin": str(_dig(raw, f.origin) or q.origin).upper(),
            "destination": str(_dig(raw, f.destination) or q.destination).upper(),
            "departure_date": str(_dig(raw, f.departure_date) or q.departure_date.isoformat())[:10],
            "airline": _norm_airline(_dig(raw, f.airline) or _dig(raw, f.flight_number)),
            "flight_number": _dig(raw, f.flight_number),
            "cabin": str(_dig(raw, f.cabin) or q.cabin).upper(),
            "fare_class": _dig(raw, f.fare_class),
            "currency": str(_dig(raw, f.currency) or q.currency).upper(),
            "base_fare": base,
            "taxes": _money(_dig(raw, f.taxes)),
            "fees": _money(_dig(raw, f.fees)),
            "total_fare": total,
            "availability": str(_dig(raw, f.availability) or "AVAILABLE").upper(),
            "seats_remaining": _dig(raw, f.seats),
            "stops": _dig(raw, f.stops),
        }
        if payload["seats_remaining"] is not None:
            try:
                payload["seats_remaining"] = int(float(payload["seats_remaining"]))
            except (TypeError, ValueError):
                payload["seats_remaining"] = None
        if total <= 0 and not raw:
            return None
        return RawOffer(
            payload=payload, source=self.id, url=url, http_status=resp.status_code,
            fetched_at=self._stamp(), latency_ms=resp.elapsed_ms, query=q.as_dict(),
        )


class HttpHtmlAdapter(HttpJsonAdapter):
    """Scrapes a public HTML price page whose robots.txt permits automation.

    ``item_selector`` matches one repeated block per offer; the per-offer
    sub-selections read *within* the whole page, which is enough for the flat
    list markup real price tables use (and keeps us off a headless browser).
    """

    type = "html_page"

    def __init__(
        self,
        *,
        source_id: str,
        name: str,
        url_template: str,
        offer_selector: str,
        field_selectors: dict[str, str],
        **kw: Any,
    ):
        super().__init__(source_id=source_id, name=name, url_template=url_template, **kw)
        self.offer_selector = offer_selector
        self.field_selectors = field_selectors

    async def collect(self, query: Query) -> RawBatch:
        from .htmltext import _TreeBuilder, _matches, walk  # local import: parser internals

        url = self._url_for(query)
        await self._allowed(self.transport, url)
        resp = await self.transport.get(url, accept="text/html,*/*")
        self._guard_against_denial(resp)
        html = resp.text

        parser = _TreeBuilder()
        try:
            parser.feed(html)
        except Exception as exc:  # pragma: no cover
            raise CollectionError(f"could not parse HTML from {self.name}: {exc}", "parse") from exc

        blocks = [n for n in walk([parser.root]) if n.tag != "#document" and _matches(n, self.offer_selector)]
        batch = RawBatch(query=query, request_count=1)
        for b in blocks:
            values: dict[str, str] = {}
            for key, sel in self.field_selectors.items():
                # A selector starting with "@" reads an attribute off the block
                # element itself — real pages put ids in data-* attributes, not text.
                if sel.startswith("@"):
                    values[key] = b.attrs.get(sel[1:], "")
                    continue
                found = [n for n in walk([b]) if _matches(n, sel)]
                values[key] = found[0].text if found else ""
            batch.offers.append(
                RawOffer(
                    payload=self._block_to_payload(values, query),
                    source=self.id,
                    url=url,
                    http_status=resp.status_code,
                    fetched_at=self._stamp(),
                    latency_ms=resp.elapsed_ms,
                    query=query.as_dict(),
                )
            )
        if not batch.offers:
            batch.note = f"HTTP {resp.status_code} but '{self.offer_selector}' matched 0 blocks"
            raise CollectionError(f"selector '{self.offer_selector}' matched nothing on {url}", "parse")
        return batch

    def _block_to_payload(self, v: dict[str, str], q: Query) -> dict[str, Any]:
        total = _money(v.get("total"))
        return {
            "offer_id": v.get("offer_id") or None,
            "origin": (v.get("origin") or q.origin).upper(),
            "destination": (v.get("destination") or q.destination).upper(),
            "departure_date": (v.get("departure_date") or q.departure_date.isoformat())[:10],
            "airline": _norm_airline(v.get("airline") or v.get("flight_number")),
            "flight_number": v.get("flight_number") or None,
            "cabin": (v.get("cabin") or q.cabin).upper(),
            "fare_class": v.get("fare_class") or None,
            "currency": (v.get("currency") or "INR").upper(),
            "base_fare": _money(v.get("base")) or total,
            "taxes": _money(v.get("taxes")),
            "fees": _money(v.get("fees")),
            "total_fare": total,
            "availability": (v.get("availability") or "AVAILABLE").upper(),
            # Pages usually render the seat count as plain digits ("3 left" -> 3).
            "seats_remaining": _int_or_none(v.get("seats")),
            "stops": _int_or_none(v.get("stops")),
        }
