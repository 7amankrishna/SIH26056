"""Preflight — decide *before* scraping whether a target is fair game.

This is the useful half of "make the bot feel human": the reason people reach for
evasion is that a request failed, and the reason it failed is almost always that
the site does not want automated traffic. This tool answers that question up
front, in one command, against the same `RobotsGate` the collector actually uses:

    python -m app.collect.preflight https://example.com/del-bom-fares

It reports the robots verdict, the crawl-delay we would adopt, the request budget
that implies for a full sweep, and a checklist of the things a machine cannot
determine for you (the terms-of-service clause, whether you may store and
redistribute the data, whether prices are personal data).

It deliberately stops short of being a reconnaissance tool: it will not enumerate
sitemaps, probe alternate paths, rotate identities or test whether a block can be
worked around. If the answer here is "denied", the answer is denied.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from typing import Any, Optional
from urllib.parse import urlparse

from ..config import settings
from ..dataset import ROUTES
from .robots import RobotsGate
from .transport import CollectionError, HttpTransport, UrllibTransport

#: The questions a robots file cannot answer, but a reviewer will ask anyway.
HUMAN_CHECKLIST = (
    "Read the site's Terms of Service / `robots`+`crawler` clauses. robots.txt "
    "permission is not a licence; ToS can prohibit what robots allows.",
    "Confirm you may **store and republish** the data, not merely view it. An "
    "index that caches fares is a redistribution question.",
    "Check for personal data in the payload (passenger names, session tokens, "
    "cookies). None should be collected or retained.",
    "Check for a licensing/press programme or a partner feed — usually faster "
    "than scraping and it survives review.",
    "If the answer is ambiguous, ask for written permission and record the reply. "
    "Ambiguity resolves to 'do not collect', not 'collect quietly'.",
)

WILL_NOT_DO = (
    "Rotate user-agents, IPs or TLS/HTTP2 fingerprints",
    "Solve, outsource or bypass CAPTCHAs and JS challenges",
    "Forge browser client-hints or Sec-Fetch-* navigation metadata",
    "Reuse a browser's cookies/consent state to look like a signed-in person",
    "Retry around a 401/403/451 or a `Disallow`",
)


async def preflight(url: str, *, transport: Optional[HttpTransport] = None, ua: Optional[str] = None) -> dict[str, Any]:
    """Adjudicate one target URL the way the collector would."""
    parsed = urlparse(url)
    out: dict[str, Any] = {
        "url": url,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "user_agent": ua or settings.user_agent,
        "host": parsed.netloc or None,
        "path": parsed.path or "/",
        "verdict": "denied",
        "reason": "",
        "would_send_headers": sorted(
            {
                "User-Agent",
                "From",
                "Accept",
                "Accept-Language",
                "Accept-Encoding",
                "Cache-Control",
            }
        ),
        "will_not_do": list(WILL_NOT_DO),
        "human_checklist": list(HUMAN_CHECKLIST),
    }

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        out["reason"] = "not an absolute http(s) URL — refusing to interpret it further"
        return out
    if parsed.scheme == "http":
        out["reason"] = "plain http is not accepted for third-party collection (set an https:// URL)"
        return out

    ua = ua or settings.user_agent
    tr = transport or UrllibTransport()
    gate = RobotsGate()
    try:
        verdict = await gate.check(tr, url)
    except CollectionError as exc:
        out["reason"] = f"robots.txt could not be read ({exc.kind}); policy fails closed"
        return out
    finally:
        await tr.aclose()

    out["robots"] = verdict.as_dict()
    if not verdict.allowed:
        out["reason"] = verdict.reason
        return out

    # Allowed — now quantify what "politely" means for this host.
    gap = max(settings.min_seconds_between_requests, verdict.crawl_delay or 0.0)
    per_day = len(settings.sweep_lead_times)
    routes = settings.sweep_routes or list(ROUTES.keys())
    requests_per_sweep = min(len(routes) * per_day, settings.max_requests_per_sweep)
    out.update(
        {
            "verdict": "allowed",
            "reason": verdict.reason,
            "effective_min_gap_seconds": round(gap, 2),
            "crawl_delay_published": verdict.crawl_delay,
            "sweep_budget": {
                "routes": len(routes),
                "lead_times": settings.sweep_lead_times,
                "requests_per_sweep": requests_per_sweep,
                "approx_seconds_per_sweep": round(requests_per_sweep * gap, 1),
                "sweeps_per_day_at_interval": round(86400 / max(1, settings.sweep_interval_seconds), 2),
                "requests_per_day": round(requests_per_sweep * (86400 / max(1, settings.sweep_interval_seconds))),
            },
            "next_steps": [
                "Set APIX_LIVE_HTTP_HTML_URL (or APIX_LIVE_HTTP_JSON_URL) to the endpoint template",
                "Set APIX_LIVE_HTTP_HTML_ITEM_SELECTOR + _FIELDS (or _OFFERS_PATH for JSON)",
                "Add APIX_COLLECTOR_SOURCES=http_html and restart, then POST /api/collect/sweep",
                "Keep APIX_LIVE_HTTP_HTML_ALLOW_HOSTS pinned to this host only",
            ],
        }
    )
    if out["sweep_budget"]["requests_per_day"] > 5_000:
        out["advisory"] = (
            f"{out['sweep_budget']['requests_per_day']} requests/day against one host is "
            "aggressive for a page scrape — widen APIX_SWEEP_INTERVAL_SECONDS or narrow "
            "APIX_SWEEP_ROUTES before enabling this source."
        )
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="apix-preflight", description="Check whether a URL may be collected from.")
    ap.add_argument("url", help="absolute https:// URL of a listing/results page or JSON endpoint")
    ap.add_argument("--user-agent", default=None, help="override the UA whose robots rules we evaluate")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    report = asyncio.run(preflight(args.url, ua=args.user_agent))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["verdict"] == "allowed" else 1

    allowed = report["verdict"] == "allowed"
    print(f"\n  target   {report['url']}")
    print(f"  host     {report['host']}")
    print(f"  UA       {report['user_agent']}")
    print(f"  verdict  {'ALLOWED' if allowed else 'DENIED'}")
    print(f"  why      {report['reason']}")
    if allowed:
        b = report["sweep_budget"]
        print(f"  politeness  gap {report['effective_min_gap_seconds']}s "
              f"(published crawl-delay: {report['crawl_delay_published']})")
        print(f"  volume      {b['requests_per_sweep']} req/sweep · {b['requests_per_day']} req/day · "
              f"~{b['approx_seconds_per_sweep']}s per sweep")
        if report.get("advisory"):
            print(f"  advisory    {report['advisory']}")
        print("  headers we send:  " + ", ".join(report["would_send_headers"]))
        print("  to wire it up:")
        for step in report["next_steps"]:
            print(f"      - {step}")
    else:
        print("  headers we will NOT send:  " + "; ".join(report["will_not_do"]))

    print("\n  Before you collect anything, settle these by hand:")
    for item in report["human_checklist"]:
        print(f"    • {item}")
    print()
    return 0 if allowed else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
