"""HTTP transport layer for the collection engine.

Adapters never talk to a socket directly. They go through a
:class:`HttpTransport`, which gives us three things:

* **Politeness in one place** — the minimum inter-request gap and the retry /
  backoff schedule live here, so no adapter can accidentally hammer a source.
* **Testability** — offline tests and the bundled demo use an in-process
  transport instead of a real network.
* **Honest failure reporting** — a blocked or rate-limited request surfaces as
  a :class:`CollectionError` with a ``kind``, never as a silent empty result.
"""

from __future__ import annotations

import asyncio
import json as _json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..config import settings


class CollectionError(Exception):
    """A collection attempt failed in a way the pipeline must report honestly.

    ``kind`` drives the Collection Monitor state:

    ``blocked``      source refused automated access (401/403/407/451 or a bot
                     wall). -> STOP_AND_BACKOFF; never recorded as a healthy run.
    ``robots_denied`` our user-agent is disallowed by robots.txt -> not requested.
    ``rate_limited`` 429 / Retry-After -> exponential backoff, then ``blocked``.
    ``ceiling``      our own per-sweep request cap; a self-imposed stop, not a
                     source failure, so it must not trip the circuit breaker.
    ``network``      DNS/connect/TLS failure (including "no egress").
    ``timeout``      request exceeded the configured timeout.
    ``parse``        response arrived but could not be normalized.
    """

    def __init__(self, message: str, kind: str = "network", *, retryable: bool = False, status: Optional[int] = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status = status


@dataclass
class HttpResponse:
    url: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: int = 0

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return _json.loads(self.body.decode("utf-8", errors="replace"))


class Politeness:
    """Enforces the per-host request gap and the retry/backoff schedule."""

    def __init__(
        self,
        min_gap: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
    ):
        self.min_gap = settings.min_seconds_between_requests if min_gap is None else min_gap
        self.max_retries = settings.max_retries if max_retries is None else max_retries
        self.backoff_base = settings.backoff_base_seconds if backoff_base is None else backoff_base
        self._last_request_at: dict[str, float] = {}
        self.requests_made = 0
        self.retries = 0
        self._lock = asyncio.Lock()

    @staticmethod
    def _host_of(url: str) -> str:
        return url.split("//", 1)[-1].split("/", 1)[0] if "//" in url else url

    async def wait_turn(self, url: str) -> None:
        host = self._host_of(url)
        async with self._lock:
            last = self._last_request_at.get(host)
            now = time.monotonic()
            if last is not None:
                wait = self.min_gap - (now - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_request_at[host] = time.monotonic()
            self.requests_made += 1

    def should_retry(self, attempt: int, err: CollectionError, retry_after: Optional[float] = None) -> Optional[float]:
        """Return how long to sleep before the next attempt, or ``None`` to stop."""
        if attempt >= self.max_retries or not err.retryable:
            return None
        self.retries += 1
        if retry_after is not None:
            # Honour the server's own schedule, capped so a sweep cannot stall.
            return min(max(retry_after, 1.0), 60.0)
        return min(self.backoff_base ** (attempt + 1), 30.0)


class HttpTransport:
    """Base transport. Subclasses implement :meth:`_send`."""

    def __init__(self, politeness: Optional[Politeness] = None, extra_headers: Optional[dict[str, str]] = None):
        self.politeness = politeness or Politeness()
        self.extra_headers = extra_headers or {}
        #: hard ceiling on requests per sweep, set by the service
        self.max_requests: Optional[int] = None

    # ------------------------------------------------------------------ #
    def _headers(self, accept: str, overrides: Optional[dict[str, str]] = None) -> dict[str, str]:
        h = {"User-Agent": settings.user_agent, "Accept": accept}
        h.update(self.extra_headers)
        if overrides:
            h.update(overrides)
        return h

    async def get(self, url: str, *, accept: str = "*/*", headers: Optional[dict[str, str]] = None) -> HttpResponse:
        return await self.request(url, method="GET", accept=accept, headers=headers)

    async def post_form(self, url: str, form: dict[str, str], *, headers: Optional[dict[str, str]] = None) -> HttpResponse:
        body = urllib.parse.urlencode(form).encode()
        merged = {"Content-Type": "application/x-www-form-urlencoded"}
        merged.update(headers or {})
        return await self.request(url, method="POST", accept="application/json,*/*", headers=merged, body=body)

    async def request(
        self,
        url: str,
        *,
        method: str = "GET",
        accept: str = "*/*",
        headers: Optional[dict[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> HttpResponse:
        if self.max_requests is not None and self.politeness.requests_made >= self.max_requests:
            raise CollectionError(
                f"per-sweep request ceiling ({self.max_requests}) reached — stopping politely",
                "ceiling",
            )
        merged = self._headers(accept, headers)

        attempt = 0
        while True:
            await self.politeness.wait_turn(url)
            try:
                resp = await self._send(url, merged, method=method, body=body)
            except CollectionError as exc:
                delay = self.politeness.should_retry(attempt, exc)
                if delay is None:
                    raise
                await asyncio.sleep(delay)
                attempt += 1
                continue

            if resp.status_code in (429, 503):
                err = CollectionError(
                    f"{resp.status_code} from {resp.url}", "rate_limited", retryable=True, status=resp.status_code
                )
                delay = self.politeness.should_retry(attempt, err, _parse_retry_after(resp.headers.get("retry-after")))
                if delay is None:
                    raise err
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if resp.status_code in (401, 403, 407, 451):
                raise CollectionError(
                    f"{resp.status_code} from {resp.url}: source refuses automated access",
                    "blocked",
                    status=resp.status_code,
                )
            if resp.status_code >= 500:
                err = CollectionError(f"{resp.status_code} from {resp.url}", "network", retryable=True, status=resp.status_code)
                delay = self.politeness.should_retry(attempt, err)
                if delay is None:
                    raise err
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if resp.status_code >= 400:
                raise CollectionError(f"HTTP {resp.status_code} from {resp.url}", "parse", status=resp.status_code)
            return resp

    async def get_json(self, url: str, **kw: Any) -> Any:
        return (await self.get(url, accept="application/json", **kw)).json()

    async def get_text(self, url: str, **kw: Any) -> str:
        return (await self.get(url, accept="text/html,*/*", **kw)).text

    async def _send(
        self, url: str, headers: dict[str, str], *, method: str = "GET", body: Optional[bytes] = None
    ) -> HttpResponse:  # pragma: no cover - abstract
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


def _parse_retry_after(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class UrllibTransport(HttpTransport):
    """Default transport: stdlib ``urllib`` over a worker thread.

    The project deliberately avoids a browser/automation stack — a plain HTTP
    client can only ever see what a source chooses to serve to an honest,
    self-identified client, which is exactly the boundary the policy respects.
    """

    def __init__(self, politeness: Optional[Politeness] = None, timeout: Optional[float] = None, **kw: Any):
        super().__init__(politeness=politeness, **kw)
        self.timeout = settings.request_timeout_seconds if timeout is None else timeout

    async def _send(self, url: str, headers: dict[str, str], *, method: str = "GET", body: Optional[bytes] = None) -> HttpResponse:
        return await asyncio.to_thread(self._send_sync, url, headers, method, body)

    def _send_sync(self, url: str, headers: dict[str, str], method: str = "GET", body: Optional[bytes] = None) -> HttpResponse:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        ctx = ssl.create_default_context()
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as fh:  # noqa: S310
                body_bytes = fh.read()
                return HttpResponse(
                    url=fh.geturl(),
                    status_code=fh.status,
                    headers={k.lower(): v for k, v in dict(fh.headers).items()},
                    body=body_bytes,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                url=url,
                status_code=exc.code,
                headers={k.lower(): v for k, v in dict(exc.headers or {}).items()},
                body=exc.read() if hasattr(exc, "read") else b"",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        except (TimeoutError, ssl.SSLError, OSError) as exc:
            kind = "timeout" if isinstance(exc, TimeoutError) else "network"
            raise CollectionError(f"{kind} contacting {url}: {exc}", kind, retryable=True) from exc


class CallableTransport(HttpTransport):
    """In-process transport backed by a caller-supplied callable.

    Used by the bundled offline capture and by the test-suite: the *entire*
    pipeline (robots gate, politeness, parse, normalize, quality, storage) runs
    unchanged — only the bytes on the wire are synthetic.
    """

    def __init__(
        self,
        handler: Callable[..., Any],
        politeness: Optional[Politeness] = None,
        *,
        wants_method: bool = False,
        **kw: Any,
    ):
        # An in-process source is not a real host: no gap, no retry pressure.
        super().__init__(politeness=politeness or Politeness(min_gap=0.0, max_retries=0), **kw)
        self.handler = handler
        self.wants_method = wants_method

    async def _send(self, url: str, headers: dict[str, str], *, method: str = "GET", body: Optional[bytes] = None) -> HttpResponse:
        result = self.handler(url, method, body) if self.wants_method else self.handler(url)
        if asyncio.iscoroutine(result):
            result = await result
        if isinstance(result, CollectionError):
            raise result
        if isinstance(result, HttpResponse):
            return result
        if isinstance(result, tuple) and len(result) == 2:
            status, payload = result
            return HttpResponse(
                url=url,
                status_code=int(status),
                body=payload if isinstance(payload, bytes) else str(payload).encode(),
            )
        if isinstance(result, dict):
            return HttpResponse(url=url, status_code=200, headers={"content-type": "application/json"}, body=_json.dumps(result).encode())
        raise CollectionError(f"transport handler returned {type(result).__name__}", "parse")


class AllowListTransport(HttpTransport):
    """Only ever speaks to explicitly permitted hosts.

    Belt-and-braces guard so a mis-configured source URL can never turn the
    generic adapters into an open-ended crawler.
    """

    def __init__(self, allowed_hosts: list[str], inner: HttpTransport):
        super().__init__(politeness=inner.politeness, extra_headers=inner.extra_headers)
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.inner = inner

    async def _send(self, url: str, headers: dict[str, str], *, method: str = "GET", body: Optional[bytes] = None) -> HttpResponse:
        host = url.split("//", 1)[-1].split("/", 1)[0].lower().split(":")[0]
        if host not in self.allowed_hosts:
            raise CollectionError(f"host '{host}' is not on APIx's source allow-list — refusing to request it", "robots_denied")
        return await self.inner._send(url, headers, method=method, body=body)

    async def aclose(self) -> None:
        await self.inner.aclose()
