"""APIx collection engine — background scraping, normalization and storage.

The package is intentionally the *only* place that touches the network. Its
output is the canonical observation model, so the index/quality/API layers stay
completely agnostic about where data came from.

    transport.py        politeness, retries/backoff, honest failure kinds
    robots.py           robots.txt gate (fail closed)
    headers.py          content-negotiation headers + a written blocklist
    base.py             the SourceAdapter contract
    adapters_http.py    generic JSON / HTML fetchers (config-driven)
    adapters_sources.py Amadeus (permissioned API) + offline authorized capture
    normalize.py        raw payload -> canonical observation + quality gate
    store.py            SQLite: runs, raw payloads, observations, toggle state
    service.py          sweep scheduler, circuit breaker, demo/live mode
    live.py (app/)      stored observations -> Dataset the engine already knows

Policy: docs/SCRAPING_POLICY.md. No CAPTCHA solving, no bot-detection evasion,
no access-control circumvention — see ``headers.NOT_IMPLEMENTED``.
"""

from __future__ import annotations

from .service import collection_service

__all__ = ["collection_service"]
