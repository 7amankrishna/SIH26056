"""Source adapter contract.

Everything the collection engine can talk to implements :class:`SourceAdapter`.
The rest of the pipeline (normalize -> quality -> store -> index -> API) is
completely source-agnostic: it does not care whether an observation came from a
licensed OTA feed, a permissioned airline API, a robots-permitted public price
page, or the bundled offline capture. They all become the same canonical
observation model.

Hard rules this contract exists to enforce (docs/SCRAPING_POLICY.md):

* an adapter **cannot** report success while hiding a block — :meth:`collect`
  raises :class:`CollectionError` with ``kind="blocked"`` and the service records
  that as a failed run;
* an adapter declares its ``compliance`` so collection-status responses can label it;
* an adapter never retries a denial — backoff is the transport's job and the
  circuit breaker is the service's.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import settings
from .transport import CollectionError, HttpTransport, Politeness

# Re-export so adapters only import from one place.
__all__ = ["Query", "RawOffer", "RawBatch", "HealthStatus", "SourceAdapter", "COMPLIANCE_LABELS"]

COMPLIANCE_LABELS = {
    "authorized": "Authorized feed / permissioned API — automated access is permitted.",
    "licensed": "Licensed commercial feed under contract.",
    "robots_permitted": "Public page; robots.txt and ToS verified to permit automated access.",
    "policy_gated": "Requires written permission before collection is enabled. Emits no data.",
    "prohibited": "Automated access is prohibited by the provider's terms. Never enabled.",
}


@dataclass
class Query:
    """One canonical collection request: route + date + lead time."""

    origin: str
    destination: str
    departure_date: dt.date
    lead_time_days: int
    cabin: str = "ECONOMY"
    adults: int = 1
    currency: str = "INR"

    @property
    def route(self) -> str:
        return f"{self.origin}-{self.destination}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date.isoformat(),
            "lead_time_days": self.lead_time_days,
            "cabin": self.cabin,
            "adults": self.adults,
            "currency": self.currency,
        }


@dataclass
class RawOffer:
    """A single quoted itinerary exactly as the source returned it.

    ``payload`` is preserved verbatim for provenance — that is what the
    dashboard's "as collected" view renders and what an auditor re-checks.
    """

    payload: dict[str, Any]
    source: str
    url: str = ""
    http_status: int = 200
    fetched_at: str = ""
    latency_ms: int = 0
    query: Optional[dict[str, Any]] = None

    def identifier(self) -> str:
        return str(self.payload.get("offer_id") or self.payload.get("id") or "")


@dataclass
class RawBatch:
    """Result of one query: offers plus the metadata needed for the run log."""

    query: Query
    offers: list[RawOffer] = field(default_factory=list)
    request_count: int = 1
    errors: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    @property
    def latency_ms(self) -> int:
        hits = [o.latency_ms for o in self.offers if o.latency_ms]
        return int(sum(hits) / len(hits)) if hits else 0


@dataclass
class HealthStatus:
    ok: bool
    state: str  # healthy | degraded | blocked | disabled | ready
    detail: str
    compliance: str = "authorized"
    latency_ms: Optional[int] = None


class SourceAdapter(ABC):
    """Base class for all collection adapters."""

    #: stable identifier used in SOURCES / the run log
    id: str = "adapter"
    name: str = "Adapter"
    type: str = "synthetic"
    #: one of COMPLIANCE_LABELS keys
    compliance: str = "authorized"
    #: generic scrapers must pass the robots gate; authorized feeds need not
    requires_robots_gate: bool = False
    #: adapters that emit no data until the operator configures credentials
    requires_credentials: bool = False
    #: True when a sweep of this source can finish inside one short-lived HTTP
    #: request. Browser scrapers (Playwright) set this False: they need Chromium
    #: and a long-lived process, so request-scoped runtimes must refuse them
    #: with a clear message instead of timing out mid-sweep (504).
    request_safe: bool = True
    #: Rough wall-clock cost per query, used to size in-request sweeps so a
    #: slow source can never blow the platform's function timeout.
    cost_per_query_seconds: float = 0.0

    def __init__(self, transport: Optional[HttpTransport] = None):
        self.transport = transport
        self.base_url: str = ""

    # ------------------------------------------------------------------ #
    @abstractmethod
    async def collect(self, query: Query) -> RawBatch:
        """Fetch offers for ``query``. Raise CollectionError on any failure."""

    async def health_check(self) -> HealthStatus:
        """Cheap probe. Default assumes an authorized adapter is usable."""
        return HealthStatus(
            ok=True,
            state="healthy",
            detail="adapter configured and authorized",
            compliance=self.compliance,
        )

    # ------------------------------------------------------------------ #
    def bind_transport(self, transport: HttpTransport) -> None:
        self.transport = transport

    @property
    def politeness(self) -> Politeness:
        assert self.transport is not None, "adapter used before bind_transport()"
        return self.transport.politeness

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": "ready",
            "adapter": type(self).__name__,
            "compliance": self.compliance,
            "compliance_note": COMPLIANCE_LABELS.get(self.compliance, ""),
            "base_url": self.base_url,
            "requires_credentials": self.requires_credentials,
            "robots_gated": self.requires_robots_gate,
            "request_safe": self.request_safe,
            "cost_per_query_seconds": self.cost_per_query_seconds,
            "user_agent": settings.user_agent if self.requires_robots_gate else "n/a (authorized channel)",
        }

    # Helpers shared by adapters ------------------------------------------ #
    @staticmethod
    def _stamp() -> str:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")

    def _guard_against_denial(self, resp) -> None:
        """Defensive: a 200 body that is a bot wall is still a denial.

        We do *not* attempt to solve it. We classify it and stop.
        """
        body = resp.text[:20000].lower()
        markers = (
            "enable javascript and cookies to continue",
            "unusual traffic",
            "detected unusual",
            "are you a robot",
            "captcha",
            "access denied",
            "referer blocked",
            "too many requests",
        )
        hit = next((m for m in markers if m in body), None)
        if hit:
            raise CollectionError(
                f"source served an interstitial ('{hit}') instead of fare data — automated access is refused; "
                "backing off and recording this run as blocked (no evasion attempted)",
                "blocked",
                status=resp.status_code,
            )
