"""Collection service — the background scraping engine.

Owns four things:

1. **Source registry** — which adapters are enabled, their compliance state.
2. **The sweep loop** — a scheduled background task that walks the route basket,
   fetches, normalizes, quality-gates and persists. Manual sweeps use the same
   code path as scheduled ones so a demo and production behave identically.
3. **Circuit breaker** — consecutive failures open it; while open the source is
   reported ``blocked`` and *no requests are made at all*. This implements
   policy rule 2 ("if a source blocks automated collection: STOP_AND_BACKOFF")
   and the corollary that a blocked run is never recorded as healthy.
4. **Data-source mode** — ``demo`` or ``live``. Persisted in SQLite so the
   dashboard toggle survives a restart, and read by ``dataset.get_dataset()`` on
   every request, which is what makes the whole dashboard switch at once.
"""

from __future__ import annotations

import asyncio
import os
import datetime as dt
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import settings
from ..dataset import ROUTES
from ..dataset import invalidate_live_cache
from .adapters_sources import AmadeusAdapter, FixtureCaptureAdapter
from .base import Query, SourceAdapter
from .normalize import QualityContext, dedupe_within_batch, normalize_offer
from .store import get_store
from .transport import AllowListTransport, CollectionError, HttpTransport, UrllibTransport

MODE_KEY = "data_mode"
LIVE = "live"
DEMO = "demo"


@dataclass
class Breaker:
    """Per-source stop-and-backoff state."""

    failures: int = 0
    open_until: float = 0.0
    last_error: str = ""
    last_error_kind: str = ""

    @property
    def open(self) -> bool:
        return time.time() < self.open_until

    def cooldown_left(self) -> int:
        return max(0, int(self.open_until - time.time()))

    def record_failure(self, kind: str, message: str) -> None:
        self.failures += 1
        self.last_error = message[:400]
        self.last_error_kind = kind
        if kind == "blocked" or self.failures >= settings.circuit_breaker_threshold:
            self.open_until = time.time() + settings.circuit_breaker_cooldown_seconds

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.last_error = ""
        self.last_error_kind = ""


@dataclass
class SweepResult:
    run_id: str
    started_at: str
    finished_at: str = ""
    per_source: dict[str, dict[str, Any]] = field(default_factory=dict)
    observations: int = 0
    valid: int = 0
    requests: int = 0
    error: Optional[str] = None
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "observations": self.observations,
            "valid_observations": self.valid,
            "requests": self.requests,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "sources": self.per_source,
        }


class CollectionService:
    """Background collector + the demo/live switch the dashboard toggles."""

    def __init__(self) -> None:
        self.store = get_store()
        self.adapters: dict[str, SourceAdapter] = {}
        self.breakers: dict[str, Breaker] = {}
        self.transport: HttpTransport = UrllibTransport()
        self._task: Optional[asyncio.Task] = None
        self._sweep_lock = asyncio.Lock()
        self._current: Optional[SweepResult] = None
        #: fire-and-forget sweeps launched from the API (kept referenced so they
        #: are not garbage-collected mid-flight, and awaitable on shutdown)
        self._tasks: list["asyncio.Task"] = []
        self._last_sweep_error: Optional[str] = None
        self._sweep_seq = 0
        self._registered = False

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def ensure_registered(self) -> None:
        if self._registered:
            self._refresh_fixture_bindings()
            return

        requested = [s.strip() for s in settings.collector_sources if s.strip()]
        for sid in requested:
            adapter = self._build(sid)
            if adapter is None:
                continue
            # Key on adapter.id, not the config alias: the run log, the stored
            # observations and the Collection Monitor all reference sources by
            # their canonical id, so they must agree on one string.
            self.adapters[adapter.id] = adapter
            self.breakers.setdefault(adapter.id, Breaker())
        self._registered = True

    def _build(self, source_id: str) -> Optional[SourceAdapter]:
        if source_id in {"fixture", "capture", "fixture_json"}:
            adapter = FixtureCaptureAdapter(sweep_seq=self._sweep_seq)
            adapter.bind_transport(self._wrap(adapter, in_process=True))
            return adapter
        if source_id in {"fixture_html", "capture_html"}:
            # Page scraping: markup in, selector extraction, no API in the path.
            from .capture_html import FixtureHtmlCaptureAdapter

            adapter = FixtureHtmlCaptureAdapter(sweep_seq=self._sweep_seq)
            adapter.bind_transport(self._wrap(adapter, in_process=True))
            return adapter
        if source_id == "amadeus":
            adapter = AmadeusAdapter()
            # Even a permissioned API is host-pinned: a mis-set base_url must not
            # turn a credentialed client into a request to somewhere else.
            adapter.bind_transport(self._wrap(None, allowed_hosts=[adapter.base_url_host]))
            return adapter
        if source_id in {"http_json", "http_html"}:
            # Generic adapters are pure configuration (see docs/API.md): a source
            # is a URL template + a field map, never new code. Refuse to build one
            # without an explicit, operator-supplied host on the allow-list.
            from .adapters_http import HttpHtmlAdapter, HttpJsonAdapter

            cfg = settings_live_kwargs(source_id)
            if not cfg.get("url_template"):
                return None
            cls = HttpHtmlAdapter if source_id == "http_html" else HttpJsonAdapter
            adapter = cls(**cfg)
            allowed = os.getenv(f"APIX_LIVE_{source_id.upper()}_ALLOW_HOSTS", adapter.base_url_host)
            adapter.bind_transport(self._wrap(None, allowed_hosts=[h.strip() for h in allowed.split(",") if h.strip()]))
            return adapter
        return None

    def _wrap(self, adapter: Optional[SourceAdapter], *, in_process: bool = False, allowed_hosts: Optional[list[str]] = None) -> HttpTransport:
        """Give every source its own politeness state + request ceiling."""
        from .transport import Politeness

        if in_process:
            transport = adapter.transport  # type: ignore[union-attr]
        else:
            base = UrllibTransport(politeness=Politeness())
            transport = AllowListTransport(allowed_hosts or [], base) if allowed_hosts else base
        transport.max_requests = settings.max_requests_per_sweep
        return transport

    def _refresh_fixture_bindings(self) -> None:
        """Advance the offline captures to the next price tick and re-apply ceilings."""
        from .adapters_sources import CaptureTransport
        from .capture_html import HtmlCaptureTransport

        for adapter in self.adapters.values():
            if isinstance(adapter, FixtureCaptureAdapter):
                transport: Any = CaptureTransport(self._sweep_seq, dt.date.today())
            elif _is_html_capture(adapter):
                transport = HtmlCaptureTransport(self._sweep_seq, dt.date.today())
            else:
                continue
            transport.max_requests = settings.max_requests_per_sweep
            adapter.bind_transport(transport)

    def register(self, adapter: SourceAdapter) -> None:
        """Let a deployment inject its own adapter (tests, licensed feeds)."""
        self.adapters[adapter.id] = adapter
        self.breakers.setdefault(adapter.id, Breaker())
        self._registered = True

    def unregister(self, source_id: str) -> None:
        self.adapters.pop(source_id, None)
        self.breakers.pop(source_id, None)

    # ------------------------------------------------------------------ #
    # Mode (the dashboard toggle)
    # ------------------------------------------------------------------ #
    @property
    def mode(self) -> str:
        """Precedence: explicit env override > persisted toggle > demo default.

        ``APIX_DATA_MODE=demo`` is what a reproducible demo run uses, so a stray
        toggle on a shared machine cannot silently change the headline numbers.
        """
        if settings.forced_data_mode in (LIVE, DEMO):
            return settings.forced_data_mode
        stored = self.store.get_state(MODE_KEY)
        return stored if stored in (LIVE, DEMO) else ("demo" if settings.demo_mode else LIVE)

    @property
    def mode_locked(self) -> bool:
        return settings.forced_data_mode in (LIVE, DEMO)

    @property
    def has_live_data(self) -> bool:
        try:
            return self.store.counts()["observations"] > 0
        except Exception:
            return False

    def set_mode(self, mode: str) -> dict[str, Any]:
        mode = (mode or "").strip().lower()
        if mode not in (LIVE, DEMO):
            raise ValueError(f"mode must be '{LIVE}' or '{DEMO}'")
        if settings.forced_data_mode in (LIVE, DEMO) and mode != settings.forced_data_mode:
            raise ValueError(
                f"data source is locked to '{settings.forced_data_mode}' by APIX_DATA_MODE; "
                "unset that variable to make the dashboard switchable"
            )
        self.store.set_state(MODE_KEY, mode)
        invalidate_live_cache()
        note = None
        if mode == LIVE and not self.has_live_data:
            note = (
                "Live mode selected but the store is empty — the dashboard keeps serving demo "
                "data until a sweep lands. Trigger one with POST /api/collect/sweep."
            )
        return {
            "mode": mode,
            "locked": self.mode_locked,
            "effective_mode": DEMO if mode == DEMO else (LIVE if self.has_live_data else DEMO),
            "has_live_data": self.has_live_data,
            "note": note,
            "updated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"),
        }

    # ------------------------------------------------------------------ #
    # Background loop
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        self.ensure_registered()
        if not settings.collector_enabled:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="apix-collector")

    async def stop(self) -> None:
        for t in list(self._tasks):
            if not t.done():
                t.cancel()
        self._tasks = []
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    async def _loop(self) -> None:
        """Sweeps only while live mode is on — demo mode makes no requests."""
        # Catch up on startup: if live mode was left on, the first sweep runs
        # now instead of up to an interval after boot.
        if self.mode == LIVE:
            try:
                await self.run_sweep(trigger="startup")
            except Exception:
                self._last_sweep_error = traceback.format_exc(limit=3)

        while True:
            try:
                await asyncio.sleep(settings.sweep_interval_seconds)
                if self.mode == LIVE and settings.collector_enabled:
                    await self.run_sweep(trigger="scheduled")
            except asyncio.CancelledError:
                raise
            except Exception:  # a bad sweep must never kill the loop
                self._last_sweep_error = traceback.format_exc(limit=3)
                await asyncio.sleep(min(60.0, settings.sweep_interval_seconds / 4))

    @property
    def background_running(self) -> bool:
        return bool(self._task and not self._task.done())

    # ------------------------------------------------------------------ #
    # Sweeps
    # ------------------------------------------------------------------ #
    def build_queries(self, routes: Optional[list[str]] = None) -> list[Query]:
        today = dt.date.today()
        keys = routes or settings.sweep_routes or list(ROUTES.keys())
        out: list[Query] = []
        for key in keys:
            meta = ROUTES.get(key.upper())
            if not meta:
                continue
            for lead in settings.sweep_lead_times:
                out.append(
                    Query(
                        origin=meta["origin"],
                        destination=meta["destination"],
                        departure_date=today + dt.timedelta(days=lead),
                        lead_time_days=lead,
                    )
                )
        return out

    def start_sweep(
        self,
        *,
        source_ids: Optional[list[str]] = None,
        trigger: str = "manual",
        routes: Optional[list[str]] = None,
    ) -> str:
        """Launch a sweep without blocking the caller; returns a run label.

        The dashboard's "Collect now" button uses this so a slow source cannot
        stall an HTTP request. Progress is polled via :meth:`status`.
        """
        task = asyncio.create_task(self.run_sweep(source_ids=source_ids, trigger=trigger, routes=routes))
        self._tasks = [t for t in self._tasks if not t.done()]
        self._tasks.append(task)
        return f"queued:{len(self._tasks)}"

    async def drain(self) -> None:
        for t in list(self._tasks):
            if not t.done():
                t.cancel()
        self._tasks = []

    async def run_sweep(
        self,
        *,
        source_ids: Optional[list[str]] = None,
        trigger: str = "manual",
        routes: Optional[list[str]] = None,
    ) -> SweepResult:
        """One collection pass across the basket. The background loop and the
        dashboard's "Collect now" button both call exactly this."""
        self.ensure_registered()
        async with self._sweep_lock:
            self._sweep_seq += 1
            self._refresh_fixture_bindings()

            run_id = f"sweep-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{self._sweep_seq}"
            started = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
            result = SweepResult(run_id=run_id, started_at=started)
            self._current = result
            t0 = time.monotonic()

            targets = source_ids or list(self.adapters.keys())
            queries = self.build_queries(routes)
            try:
                for sid in targets:
                    adapter = self.adapters.get(sid)
                    if adapter is None:
                        continue
                    stats = await self._sweep_source(adapter, queries, run_id, trigger)
                    result.per_source[sid] = stats
                    result.observations += stats["observations"]
                    result.valid += stats["valid_observations"]
                    result.requests += stats["requests"]
            except Exception as exc:  # unexpected: record, never hide
                result.error = f"{type(exc).__name__}: {exc}"
                self._last_sweep_error = result.error
            finally:
                result.finished_at = dt.datetime.now(
                    dt.timezone(dt.timedelta(hours=5, minutes=30))
                ).isoformat(timespec="seconds")
                result.duration_ms = int((time.monotonic() - t0) * 1000)
                invalidate_live_cache()
            return result

    async def _sweep_source(self, adapter: SourceAdapter, queries: list[Query], run_id: str, trigger: str) -> dict[str, Any]:
        self.store.begin_run(run_id, adapter.id, trigger)
        breaker = self.breakers.setdefault(adapter.id, Breaker())

        stats: dict[str, Any] = {
            "source": adapter.id, "name": adapter.name, "status": "success",
            "queries": 0, "attempted": 0, "requests": 0, "observations": 0, "valid_observations": 0,
            "duplicates": 0, "invalid": 0, "suspicious": 0, "failures": 0, "skipped": 0,
            "ceiling_hit": False,
            "latencies": [], "detail": "", "blocked_reason": None, "errors": [],
        }

        if breaker.open:
            stats.update(
                status="blocked",
                detail=(
                    f"circuit breaker open for {breaker.cooldown_left()}s after "
                    f"{breaker.failures} consecutive failure(s): {breaker.last_error}"
                ),
                blocked_reason=breaker.last_error,
            )
            self.store.finish_run(
                run_id, status="blocked", error_kind=breaker.last_error_kind or "blocked",
                detail=stats["detail"], queries=0, requests=0, observations=0,
                valid_observations=0, duplicates=0, invalid=0, suspicious=0, failures=1,
            )
            return _finalize_stats(stats)

        today = dt.date.today().isoformat()
        ctx = QualityContext.build(
            collection_date=today,
            route_medians=self.store.route_median_levels(today),
            seen=self.store.fingerprints_for_day(today),
            batch_tag=run_id.rsplit("-", 1)[-1],
        )

        collected: list[dict[str, Any]] = []
        raw_offers: list[Any] = []
        stop_and_backoff = False

        for q in queries:
            stats["queries"] += 1
            stats["attempted"] += 1
            try:
                batch = await adapter.collect(q)
            except CollectionError as exc:
                if exc.kind == "ceiling":
                    # We stopped ourselves; the source did nothing wrong. Record the
                    # untried remainder honestly and close the run as partial — but do
                    # not let it count toward the breaker, or a wide manual sweep would
                    # leave a healthy source blocked for 30 minutes.
                    stats["skipped"] = max(0, len(queries) - stats["attempted"])
                    stats["ceiling_hit"] = True
                    break
                stats["failures"] += 1
                stats["errors"].append({"route": q.route, "lead": q.lead_time_days, "kind": exc.kind, "detail": str(exc)[:300]})
                if exc.kind in ("blocked", "robots_denied"):
                    stop_and_backoff = True
                    breaker.record_failure(exc.kind, str(exc))
                    stats["blocked_reason"] = str(exc)
                    break  # STOP_AND_BACKOFF: do not keep hammering the source
                breaker.record_failure(exc.kind, str(exc))
                continue
            except Exception as exc:  # adapter bug: record as a failure, keep sweep alive
                stats["failures"] += 1
                stats["errors"].append({"route": q.route, "lead": q.lead_time_days, "kind": "parse", "detail": f"{type(exc).__name__}: {exc}"[:300]})
                continue

            stats["requests"] += batch.request_count
            raw_offers.extend(batch.offers)
            for offer in batch.offers:
                obs = normalize_offer(offer, q, ctx, seq=len(collected))
                obs["run_id"] = run_id
                obs["source"] = adapter.id
                collected.append(obs)
                ctx.seen_fingerprints.add(obs["fingerprint"])
            stats["latencies"].extend(o.latency_ms for o in batch.offers if o.latency_ms)

        collected = dedupe_within_batch(collected)
        if raw_offers:
            self.store.add_raw_payloads(run_id, raw_offers)
        if collected:
            self.store.insert_observations(run_id, collected)

        counts = {
            "observations": len(collected),
            "valid_observations": sum(1 for o in collected if o["quality_status"] == "VALID"),
            "duplicates": sum(1 for o in collected if o["quality_status"] == "DUPLICATE"),
            "invalid": sum(1 for o in collected if o["quality_status"] == "INVALID"),
            "suspicious": sum(1 for o in collected if o["quality_status"] == "SUSPICIOUS"),
        }
        stats.update(counts)
        ctx.route_medians = self.store.route_median_levels(today)

        if stop_and_backoff:
            status = "blocked"
            detail = stats["blocked_reason"] or "source refused automated access"
        elif stats["failures"] and not collected:
            status = "failed"
            detail = f"all {stats['queries']} queries failed; first: {stats['errors'][0]['detail'] if stats['errors'] else 'unknown'}"
        elif stats["ceiling_hit"]:
            status = "partial"
            detail = (
                f"per-sweep request ceiling reached after {stats['attempted']} requests; "
                f"{stats['skipped']} queued queries were not attempted (no penalty applied)"
            )
        elif stats["failures"]:
            status = "partial"
            detail = f"{stats['failures']}/{stats['queries']} queries failed"
        elif not collected:
            status = "partial"
            detail = "source answered but returned no offers"
        else:
            status = "success"
            detail = f"{stats['observations']} observations from {stats['queries']} queries"
            breaker.record_success()

        stats["status"] = status
        stats["detail"] = detail
        self.store.finish_run(
            run_id, status=status,
            error_kind=(stats["errors"][0]["kind"] if stats["errors"] and status != "success" else None),
            detail=detail[:500], queries=stats["queries"], requests=stats["requests"],
            observations=counts["observations"], valid_observations=counts["valid_observations"],
            duplicates=counts["duplicates"], invalid=counts["invalid"],
            suspicious=counts["suspicious"], failures=stats["failures"],
            avg_latency_ms=int(sum(stats["latencies"]) / len(stats["latencies"])) if stats["latencies"] else None,
        )
        return _finalize_stats(stats)

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    def status(self) -> dict[str, Any]:
        self.ensure_registered()
        counts = self.store.counts()
        all_obs = self.store.all_observations()
        per_source_count = {}
        for o in all_obs:
            per_source_count[o.get("source")] = per_source_count.get(o.get("source"), 0) + 1
        sources = []
        for sid, adapter in self.adapters.items():
            breaker = self.breakers.setdefault(sid, Breaker())
            desc = adapter.describe()
            last = self.store.last_run(source=sid)
            desc.update(
                {
                    "status": "blocked" if breaker.open else (last["status"] if last else "ready"),
                    "last_run": last,
                    "circuit_open": breaker.open,
                    "cooldown_seconds_left": breaker.cooldown_left(),
                    "consecutive_failures": breaker.failures,
                    "last_error": breaker.last_error or None,
                    "last_error_kind": breaker.last_error_kind or None,
                    "observations": per_source_count.get(sid, 0),
                }
            )
            sources.append(desc)

        return {
            "mode": self.mode,
            "mode_locked": self.mode_locked,
            "effective_mode": "live" if self.mode == LIVE and counts["observations"] else "demo",
            "collector_enabled": settings.collector_enabled,
            "background_running": self.background_running,
            "sweep_interval_seconds": settings.sweep_interval_seconds,
            "current_run": self._current.as_dict() if self._current else None,
            "store": counts,
            "sources": sources,
            "queries_per_sweep": len(self.build_queries()),
            "lead_times": settings.sweep_lead_times,
            "politeness": {
                "min_gap_seconds": settings.min_seconds_between_requests,
                "max_retries": settings.max_retries,
                "backoff_base_seconds": settings.backoff_base_seconds,
                "max_requests_per_sweep": settings.max_requests_per_sweep,
                "user_agent": settings.user_agent,
                "robots_fail_closed": settings.refuse_when_robots_unreadable,
            },
            "last_sweep_error": self._last_sweep_error,
        }

    def collection_runs_view(self) -> dict[str, Any]:
        """Live replacement for the Collection Monitor payload in live mode.

        Shows the *real* run log, including blocked/failed rows — a source that
        stopped collecting is shown stopped, never as live.
        """
        self.ensure_registered()
        runs = self.store.recent_runs(limit=40)
        all_obs = self.store.all_observations()
        by_source: dict[str, list[dict[str, Any]]] = {}
        for r in runs:
            by_source.setdefault(r["source"], []).append(r)

        per_source: dict[str, Any] = {}
        for sid, adapter in self.adapters.items():
            breaker = self.breakers.setdefault(sid, Breaker())
            src_runs = by_source.get(sid, [])
            done = [r for r in src_runs if r["status"] != "running"]
            mine = [o for o in all_obs if o.get("source") == sid]
            valid = sum(1 for o in mine if o["quality_status"] in ("VALID", "SUSPICIOUS"))
            successful = sum(1 for r in done if r["status"] in ("success", "partial"))
            per_source[sid] = {
                "source": sid,
                "name": adapter.name,
                "type": adapter.type,
                "status": (
                    "blocked" if breaker.open
                    else "healthy" if (done and done[0]["status"] == "success")
                    else "degraded" if done
                    else "ready"
                ),
                "adapter": type(adapter).__name__,
                "compliance": adapter.compliance,
                "compliance_note": adapter.describe()["compliance_note"],
                "last_run": done[0]["started_at"] if done else None,
                "observations": len(mine),
                "valid_observations": valid,
                "success_rate": round(successful / len(done) * 100.0, 1) if done else 0.0,
                # Queries that failed across the recorded runs — not a count of
                # runs, and never padded for the breaker being open (that would
                # double-count the same event on the monitor).
                "failure_count": sum(int(r["failures"] or 0) for r in done),
                "blocked_runs": sum(1 for r in done if r["status"] in ("blocked", "failed")),
                "avg_latency_ms": done[0]["avg_latency_ms"] if done else None,
                "quotes": sum(r["requests"] or 0 for r in done),
                "circuit_open": breaker.open,
                "cooldown_seconds_left": breaker.cooldown_left(),
                "consecutive_failures": breaker.failures,
                "last_error": breaker.last_error or (done[0]["detail"] if done and done[0]["status"] != "success" else None),
                "recent_runs": done[:5],
            }
        for sid, src_runs in by_source.items():
            per_source.setdefault(sid, {
                "source": sid, "name": sid, "type": "unknown", "status": "disabled",
                "adapter": "(unregistered)", "compliance": "policy_gated",
                "compliance_note": "data present but no adapter currently registered",
                "last_run": src_runs[0]["started_at"], "observations": 0, "valid_observations": 0,
                "success_rate": 0.0, "failure_count": 0, "avg_latency_ms": src_runs[0]["avg_latency_ms"],
                "quotes": sum(r["requests"] or 0 for r in src_runs), "circuit_open": False,
                "cooldown_seconds_left": 0, "consecutive_failures": 0, "last_error": None,
                "recent_runs": src_runs[:5],
            })

        vals = list(per_source.values())
        return {
            "as_of": (runs[0]["started_at"][:10] if runs else dt.date.today().isoformat()),
            "sources": per_source,
            "summary": {
                "active_sources": len([v for v in vals if v["status"] in ("healthy", "degraded")]),
                "healthy_sources": len([v for v in vals if v["status"] == "healthy"]),
                "degraded_sources": len([v for v in vals if v["status"] in ("degraded", "blocked")]),
                "disabled_sources": len([v for v in vals if v["status"] == "disabled"]),
                "ready_sources": len([v for v in vals if v["status"] == "ready"]),
                "last_run": runs[0]["started_at"] if runs else "",
                "collection_success_rate": round(sum(v["success_rate"] for v in vals) / len(vals), 1) if vals else 0.0,
            },
            "runs": runs,
        }

    async def test_connection(self, source_id: str) -> dict[str, Any]:
        self.ensure_registered()
        adapter = self.adapters.get(source_id)
        if adapter is None:
            raise KeyError(source_id)
        t0 = time.monotonic()
        try:
            health = await adapter.health_check()
        except CollectionError as exc:
            health = None
            return {"source": source_id, "ok": False, "state": "blocked" if exc.kind in ("blocked", "robots_denied") else "degraded",
                    "detail": str(exc), "kind": exc.kind, "latency_ms": int((time.monotonic() - t0) * 1000)}
        except Exception as exc:
            return {"source": source_id, "ok": False, "state": "degraded", "detail": f"{type(exc).__name__}: {exc}",
                    "kind": "network", "latency_ms": int((time.monotonic() - t0) * 1000)}
        return {
            "source": source_id, "ok": health.ok, "state": health.state, "detail": health.detail,
            "compliance": health.compliance, "latency_ms": health.latency_ms or int((time.monotonic() - t0) * 1000),
        }


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    lat = stats.pop("latencies", [])
    stats["avg_latency_ms"] = int(sum(lat) / len(lat)) if lat else None
    stats["errors"] = stats["errors"][:12]
    return stats


def settings_live_kwargs(source_id: str) -> dict[str, Any]:
    """Build a generic adapter from env config (``APIX_LIVE_<SRC>_*``)."""
    prefix = f"APIX_LIVE_{source_id.upper()}_"
    out: dict[str, Any] = {
        "source_id": source_id,
        "name": os.getenv(prefix + "NAME", source_id),
        "url_template": os.getenv(prefix + "URL", ""),
        "offers_path": os.getenv(prefix + "OFFERS_PATH", "offers"),
        "compliance": os.getenv(prefix + "COMPLIANCE", "robots_permitted"),
    }
    if source_id == "http_html":
        out["offer_selector"] = os.getenv(prefix + "ITEM_SELECTOR", "div.offer")
        fields = os.getenv(prefix + "FIELDS", "total:.price,flight_number:.flight,airline:.carrier")
        out["field_selectors"] = dict(
            kv.split(":", 1) for kv in fields.split(",") if ":" in kv
        )
    return out


def _is_html_capture(adapter: Any) -> bool:
    """Type-check without importing capture_html at module load (it imports us)."""
    return type(adapter).__name__ == "FixtureHtmlCaptureAdapter"


#: process-wide singleton used by FastAPI dependency + lifespan hooks
collection_service = CollectionService()
