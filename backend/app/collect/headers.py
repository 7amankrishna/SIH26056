"""Request headers for the collection engine.

This module exists so that our requests are *correct and well-behaved*:
content negotiation, compression, language, cache revalidation, and an honest
self-identifying User-Agent with a contact address. Well-formed headers are how
a considerate client behaves; several of them (``If-None-Match``, ``Accept``,
``Accept-Encoding``) also *reduce* load on the source, which is the point.

The boundary, stated plainly
---------------------------
Header **content negotiation** — yes, included here.
Header **impersonation** — deliberately absent.

What a "human-like" bot actually means in practice is a set of headers assembled
to look like Chrome (``sec-ch-ua``, ``Sec-Fetch-Site``, a browser-grade
``User-Agent``, mimicked TLS/JA3 fingerprints, cookie/consent reuse, UA
rotation). Those fields serve no purpose for a JSON/HTML price endpoint; their
only function is to make an access-control system misclassify us as a person.
Building them would breach the terms of the services in question and would put
a statistical-agency project at risk of IP bans and takedowns at the worst
possible moment. So they are not here, and adding them is the one change this
codebase is designed to resist.

Note also the substantive (not just compliance) reason: fare data collected in
secret from a consumer website cannot be attested, re-derived, or audited.
An MoSPI/NSO reviewer rejects a series whose provenance is "we scraped Google
on Tuesdays". A series whose provenance is "licensed feed, payload archived at
``raw_payload_reference``" survives the audit. The scraper is built for the
second case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import settings


@dataclass
class RequestHeaders:
    """A small, honest set of default request headers."""

    user_agent: str = settings.user_agent
    accept: str = "*/*"
    accept_language: str = "en-IN,en;q=0.9"
    accept_encoding: str = "gzip, deflate"
    #: Ask the source not to hand us a fresh render every time — polite and faster.
    cache_control: str = "max-age=0"
    #: Explicitly tell the host we are not a browser and want no cookies back.
    dnt: str = "1"
    x_requested_with: str = "APIx-Collector"

    def as_dict(
        self,
        *,
        accept: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        extra: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        out: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": accept or self.accept,
            "Accept-Language": self.accept_language,
            "Accept-Encoding": self.accept_encoding,
            "Cache-Control": self.cache_control,
            "DNT": self.dnt,
            "X-Requested-With": self.x_requested_with,
            # Reachable contact in the UA itself: what robots.txt conventions
            # expect from an automated collector, and what lets a site owner
            # ask us to stop instead of blocking the whole IP range.
            "From": _contact_from_ua(self.user_agent),
        }
        if etag:
            out["If-None-Match"] = etag
        if last_modified:
            out["If-Modified-Since"] = last_modified
        if extra:
            out.update(extra)
        return out


def _contact_from_ua(user_agent: str) -> str:
    """Pull the `contact:` address out of the configured UA string, if present."""
    marker = "contact:"
    low = user_agent.lower()
    if marker in low:
        tail = user_agent[low.index(marker) + len(marker):]
        return tail.rstrip(");").strip()
    return "unknown"


#: A ready-made instance; the transport merges these over its own defaults.
DEFAULT_HEADERS = RequestHeaders()

#: Headers we will send. Kept next to the blocklist so the intent is unmistakable.
SENT_FIELDS = (
    "User-Agent (self-identifying, with contact URL)",
    "From",
    "Accept",
    "Accept-Language",
    "Accept-Encoding",
    "Cache-Control",
    "If-None-Match / If-Modified-Since (conditional GET)",
    "DNT",
    "Authorization (only for sources that issued us a credential)",
)

#: Fields deliberately not implemented. See docs/SCRAPING_POLICY.md.
NOT_IMPLEMENTED = (
    "Browser User-Agent spoofing / sec-ch-ua client-hint emulation",
    "Sec-Fetch-* navigation-metadata forgery",
    "User-Agent / IP / TLS-fingerprint rotation",
    "CAPTCHA detection, solving or bypass",
    "Cookie or consent-state reuse to appear logged-in-as-a-human",
    "Headless-browser stealth patches (navigator.webdriver masking, etc.)",
    "Robots.txt or ToS restriction avoidance",
)
