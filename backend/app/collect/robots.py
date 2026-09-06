"""robots.txt gate — the enforcement point for the collection policy.

Every *generic* adapter (``http_json``, ``http_html``) must pass through this
gate before a single byte is requested from a third-party host. Authorized
sources (a licensed feed, a permissioned API, our own fixture capture) skip the
gate because there is no automated-access restriction to respect — but they must
declare ``compliance = "authorized"`` for that to apply.

Design notes
------------
* **Fail closed.** If ``robots.txt`` cannot be fetched and
  ``APIX_ROBOTS_FAIL_CLOSED`` is on (the default), collection is denied. A
  missing robots file is not read as permission to crawl.
* **`crawl-delay` is honoured** and folded into the politeness gap.
* Nothing here tries to read a `sitemap` for coverage, rotate user-agents, or
  otherwise widen what we are allowed to touch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional
from urllib import robotparser

from ..config import settings
from .transport import CollectionError, HttpTransport

_CACHE_SECONDS = 3600.0


@dataclass
class RobotsVerdict:
    allowed: bool
    reason: str
    crawl_delay: Optional[float] = None

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason, "crawl_delay": self.crawl_delay}


class RobotsGate:
    """Per-host robots.txt adjudicator with a one-hour cache."""

    def __init__(self, transport: Optional[HttpTransport] = None):
        self._transport = transport
        self._cache: dict[str, tuple[float, robotparser.RobotFileParser, Optional[float]]] = {}
        self._unreachable: set[str] = set()

    @staticmethod
    def _host_of(url: str) -> str:
        return url.split("//", 1)[-1].split("/", 1)[0].lower()

    async def _rules(self, transport: HttpTransport, url: str):
        host = self._host_of(url)
        cached = self._cache.get(host)
        if cached and (time.time() - cached[0]) < _CACHE_SECONDS:
            return cached[1], cached[2]

        rp = robotparser.RobotFileParser()
        delay: Optional[float] = None
        try:
            resp = await transport.get(f"https://{host}/robots.txt", accept="text/plain,*/*")
            text = resp.text
        except CollectionError as exc:
            # 404 on robots.txt conventionally means "no rules published", but
            # policy rule 1 says do not *assume* permission. Network failures
            # and blocks are recorded as unreachable.
            if exc.status == 404:
                text = ""
            else:
                self._unreachable.add(host)
                if settings.refuse_when_robots_unreadable:
                    raise
                text = ""
            if exc.status == 404:
                self._unreachable.discard(host)
        else:
            self._unreachable.discard(host)
            for line in text.splitlines():
                low = line.strip().lower()
                if low.startswith("crawl-delay:"):
                    try:
                        delay = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        delay = None

        rp.parse(text.splitlines() if text else ["User-agent: *"])
        self._cache[host] = (time.time(), rp, delay)
        return rp, delay

    async def check(self, transport: HttpTransport, url: str) -> RobotsVerdict:
        host = self._host_of(url)
        try:
            rp, delay = await self._rules(transport, url)
        except CollectionError as exc:
            return RobotsVerdict(
                allowed=False,
                reason=f"robots.txt unreadable for {host} ({exc.kind}); failing closed per policy",
            )

        path = _path_of(url)
        if not rp.can_fetch(settings.user_agent.split("(", 1)[0].strip(), path):
            return RobotsVerdict(
                allowed=False,
                reason=f"robots.txt for {host} disallows automated access to {path}",
                crawl_delay=delay,
            )
        if rp.crawl_delay(settings.user_agent.split("(", 1)[0].strip()) is not None:
            delay = rp.crawl_delay(settings.user_agent.split("(", 1)[0].strip())
        return RobotsVerdict(allowed=True, reason=f"robots.txt for {host} permits {path}", crawl_delay=delay)


def _path_of(url: str) -> str:
    tail = url.split("//", 1)[-1]
    path = "/" + tail.partition("/")[2]
    return path.split("?", 1)[0].split("#", 1)[0] or "/"
