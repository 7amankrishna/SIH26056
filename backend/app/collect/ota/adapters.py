"""Playwright-based OTA source adapters (Cleartrip / EaseMyTrip).

These are real browser scrapers plugged into the same ``SourceAdapter`` contract
as every other source: ``collect(query)`` returns a ``RawBatch`` of ``RawOffer``
payloads, and the rest of the pipeline (normalize -> quality gate -> store ->
index -> API) is untouched. Playwright is imported lazily so the serverless
(Vercel) path — which never registers these sources — never needs a browser.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Optional

from ..base import COMPLIANCE_LABELS, HealthStatus, Query, RawBatch, RawOffer, SourceAdapter
from ..transport import CollectionError
from .extractors import (
    EASEMYTRIP_EXTRACT_JS,
    build_cleartrip_url,
    build_easemytrip_url,
    parse_cleartrip_cards,
    parse_easemytrip_cards,
)

#: A compliance label that is honest about what these adapters are: consumer
#: OTA pages enabled by the operator, with no policy gate applied.
COMPLIANCE_LABELS["ota_unchecked"] = (
    "Consumer OTA page; operator opted in via APIX_OTA_ENABLED — no policy gate applied."
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

#: Bot-wall markers, mirroring the engine's ``_guard_against_denial``: a 200
#: page that is actually an interstitial is recorded ``blocked``, never solved.
_DENIAL_MARKERS = (
    "unusual traffic", "are you a robot", "captcha", "access denied",
    "enable javascript and cookies to continue", "too many requests",
)

CLEARTRIP_RESULTS_SELECTOR = "body"
EASEMYTRIP_RESULTS_SELECTOR = "div.nw_listing_bx_tp"


class PlaywrightOtaAdapter(SourceAdapter):
    """One adapter per OTA site. Selects the extraction path on ``site``."""

    id = "ota"
    name = "OTA"
    type = "browser"
    compliance = "ota_unchecked"
    requires_robots_gate = False
    # Browser scraping cannot finish inside a short-lived serverless request:
    # it needs Chromium and a real process (Docker/VM or the standalone CLI).
    # Request-scoped runtimes refuse these sources fast instead of 504-ing.
    request_safe = False
    cost_per_query_seconds = 20.0

    def __init__(
        self,
        *,
        source_id: str,
        site: str,
        headless: Optional[bool] = None,
        timeout_ms: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.id = source_id
        self.site = site
        self.name = {"cleartrip": "Cleartrip", "easemytrip": "EaseMyTrip"}.get(site, site)
        if site not in ("cleartrip", "easemytrip"):
            raise ValueError(f"unknown OTA site: {site!r}")
        from ...config import settings

        self.headless = settings.ota_headless if headless is None else headless
        self.timeout_ms = settings.ota_timeout_ms if timeout_ms is None else timeout_ms
        self.base_url = "https://www.cleartrip.com" if site == "cleartrip" else "https://www.easemytrip.com"

    # ------------------------------------------------------------------ #
    def _url_for(self, query: Query) -> str:
        dep = query.departure_date.isoformat()
        if self.site == "cleartrip":
            return build_cleartrip_url(query.origin, query.destination, dep)
        return build_easemytrip_url(query.origin, query.destination, dep)

    def _check_page(self, title: str, text: str) -> None:
        haystack = f"{title} {text[:20000]}".lower()
        hit = next((m for m in _DENIAL_MARKERS if m in haystack), None)
        if hit:
            raise CollectionError(
                f"{self.name} served an interstitial ('{hit}') instead of fare data; "
                "recording this run as blocked (no evasion attempted)",
                "blocked",
            )

    # ------------------------------------------------------------------ #
    async def collect(self, query: Query) -> RawBatch:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - depends on deployment
            raise CollectionError(
                f"{self.name} adapter needs playwright, which is not installed: {exc}",
                "network",
            ) from exc

        url = self._url_for(query)
        started = time.monotonic()
        rows: list[dict[str, Any]] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1366, "height": 768},
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                )
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)

                    if self.site == "cleartrip":
                        try:
                            await page.wait_for_selector(CLEARTRIP_RESULTS_SELECTOR, timeout=self.timeout_ms)
                            await page.wait_for_timeout(8000)
                        except Exception:
                            pass
                        text = await page.inner_text("body")
                        self._check_page(await page.title(), text)
                        # Card-grained scan (ported from ankit): each div's text
                        # is a candidate card.
                        card_texts = await page.locator("div").all_inner_texts()
                        rows = parse_cleartrip_cards(card_texts, query.origin, query.destination, query.departure_date.isoformat())
                    else:
                        try:
                            await page.wait_for_selector(EASEMYTRIP_RESULTS_SELECTOR, timeout=self.timeout_ms)
                            await page.wait_for_timeout(8000)
                        except Exception:
                            pass
                        self._check_page(await page.title(), await page.inner_text("body"))
                        raw_cards = await page.evaluate(EASEMYTRIP_EXTRACT_JS)
                        rows = parse_easemytrip_cards(raw_cards, query.origin, query.destination, query.departure_date.isoformat())
                finally:
                    await page.close()
                    await context.close()
            finally:
                await browser.close()

        latency = int((time.monotonic() - started) * 1000)
        batch = RawBatch(query=query, request_count=1)
        for row in rows:
            batch.offers.append(
                RawOffer(
                    payload=row,
                    source=self.id,
                    url=url,
                    http_status=200,
                    fetched_at=self._stamp(),
                    latency_ms=latency,
                    query=query.as_dict(),
                )
            )
        if not batch.offers:
            batch.note = f"{self.name} returned no parseable fare cards for {query.route} on {query.departure_date.isoformat()}"
        return batch

    async def health_check(self) -> HealthStatus:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return HealthStatus(
                ok=False,
                state="degraded",
                detail="playwright is not installed; the OTA adapter cannot launch a browser",
                compliance=self.compliance,
            )
        return HealthStatus(
            ok=True,
            state="ready",
            detail=f"{self.name} adapter ready (headless={self.headless}, timeout_ms={self.timeout_ms})",
            compliance=self.compliance,
        )

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update({"site": self.site, "headless": self.headless, "timeout_ms": self.timeout_ms})
        return out
