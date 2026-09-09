"""Application configuration.

All values default to safe, demo-friendly settings and can be overridden
through environment variables (prefixed with ``APIX_``).
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_bool(name: str, default: str) -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    raw = _env(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _request_scoped_runtime() -> bool:
    """True on serverless platforms where a background loop cannot survive.

    Vercel/Lambda-style runtimes freeze or destroy the process the moment a
    response is returned, so an ``asyncio`` sweep loop never gets to run: the
    collector has to do its work *inside* the request that asks for it. Detecting
    that here keeps the rest of the code free of platform special cases.
    """
    return any(
        _env(name, "").strip()
        for name in (
            "VERCEL",
            "VERCEL_ENV",
            "AWS_LAMBDA_FUNCTION_NAME",
            "LAMBDA_TASK_ROOT",
            "FUNCTION_TARGET",
        )
    )


def _default_data_dir() -> str:
    """Where collected data lives unless ``APIX_DATA_DIR`` says otherwise.

    Serverless filesystems are read-only except ``/tmp``, so the default there is
    ``/tmp/apix-data`` — otherwise the store cannot be created at all and the
    scraper looks "broken" while every other screen works normally.
    """
    explicit = _env("APIX_DATA_DIR", "").strip()
    if explicit:
        return explicit
    if _request_scoped_runtime():
        return "/tmp/apix-data"
    return str(Path(__file__).resolve().parents[1] / "data")


class Settings:
    """Runtime settings for the APIx backend."""

    #: True when the process only lives for the duration of a request.
    request_scoped_runtime: bool = _request_scoped_runtime()

    title: str = "APIx — Real-Time Airfare Price Index for India"
    version: str = "0.2.0"
    description: str = (
        "High-frequency airfare intelligence for CPI augmentation. "
        "Collection -> Normalization -> Quality -> Index -> API."
    )

    # Demo / offline mode is the default. Real collection engines (scrapers)
    # plug into the same pipeline behind this flag.
    demo_mode: bool = _env_bool("APIX_DEMO_MODE", "1")

    # Number of days for which the deterministic demo store is generated.
    demo_history_days: int = int(_env("APIX_DEMO_DAYS", "90"))

    # ------------------------------------------------------------------ #
    # Custom data (the user's own fare exports replace the demo dataset)
    # ------------------------------------------------------------------ #

    # Directory scanned for the user's own data files (CSV/JSON/JSONL). Every
    # supported file in it is loaded and merged, so more data = drop a file in.
    # Default: <repo>/data (committed, unlike backend/data which is runtime state).
    custom_data_dir: Path = Path(_env("APIX_CUSTOM_DATA_DIR", "").strip()
                                 or str(Path(__file__).resolve().parents[2] / "data"))

    # Master switch for custom data. When off (or when APIX_DATA_MODE=demo pins
    # the source to the synthetic store) the demo generator serves the dashboard.
    custom_data_enabled: bool = _env_bool("APIX_CUSTOM_DATA", "1")

    # Prefix for the REST API (the SPA is served by Vite in dev and proxied).
    api_prefix: str = "/api"

    # CORS origins allowed to call the API in development.
    cors_origins: list[str] = ["*"]

    # ------------------------------------------------------------------ #
    # Collection engine (background scraper / live ingestion)
    # ------------------------------------------------------------------ #

    # Forces the data source regardless of what the persisted toggle says.
    # "demo" locks the dashboard to the deterministic dataset (a jury demo wants
    # reproducible numbers even if someone toggled live earlier on this machine);
    # "live" forces scraped data; "" (default) honours the persisted selection.
    forced_data_mode: str = _env("APIX_DATA_MODE", "").strip().lower()

    # Where collected observations, raw payloads and run logs are persisted.
    # Kept out of git (see .gitignore) so deployed instances start clean. On a
    # serverless runtime this defaults to /tmp/apix-data (the only writable path).
    data_dir: Path = Path(_default_data_dir())

    # Master switch for the background loop. When false, the API still serves
    # everything already stored, but no new collection runs are scheduled —
    # sweeps then happen inside the request that asks for them, which is the only
    # thing that works on a request-scoped runtime (default off there).
    collector_enabled: bool = _env_bool(
        "APIX_COLLECTOR_ENABLED", "0" if _request_scoped_runtime() else "1"
    )

    # Seconds between scheduled sweeps.
    sweep_interval_seconds: int = int(_env("APIX_SWEEP_INTERVAL_SECONDS", "900"))

    # Adapters to register, comma separated.
    #   fixture       - authorized local JSON capture (no network, demo-safe)
    #   fixture_html  - authorized local HTML *page* capture: selector scraping,
    #                   no API anywhere in the path
    #   amadeus  - permissioned Amadeus for Developers self-service API
    #   http_json / http_html - generic policy-respecting fetchers for
    #                            sources that explicitly permit automation
    collector_sources: list[str] = _env_list("APIX_COLLECTOR_SOURCES", "fixture")

    # Per-source politeness (see docs/SCRAPING_POLICY.md).
    request_timeout_seconds: float = float(_env("APIX_REQUEST_TIMEOUT_SECONDS", "20"))
    min_seconds_between_requests: float = float(_env("APIX_MIN_REQUEST_GAP_SECONDS", "2.0"))
    max_retries: int = int(_env("APIX_MAX_RETRIES", "3"))
    backoff_base_seconds: float = float(_env("APIX_BACKOFF_BASE_SECONDS", "2.0"))

    # Identify ourselves honestly. Many policies require a reachable contact.
    user_agent: str = _env(
        "APIX_USER_AGENT", "APIxResearchBot/0.2 (+https://github.com/7amankrishna/SIH26056; contact: research@example.org)"
    )

    # Fail closed: if robots.txt cannot be read, refuse to collect from that host.
    refuse_when_robots_unreadable: bool = _env_bool("APIX_ROBOTS_FAIL_CLOSED", "1")

    # Sweep scope — deliberately small so a live sweep stays polite.
    sweep_routes: list[str] = _env_list("APIX_SWEEP_ROUTES", "")  # empty = all basket routes
    sweep_lead_times: list[int] = [
        int(x) for x in _env_list("APIX_SWEEP_LEAD_TIMES", "1,7,30")
    ]

    # Consecutive failed sweeps before a source trips its circuit breaker.
    circuit_breaker_threshold: int = int(_env("APIX_CB_THRESHOLD", "3"))
    circuit_breaker_cooldown_seconds: int = int(_env("APIX_CB_COOLDOWN_SECONDS", "1800"))

    # Amadeus credentials (only used by the `amadeus` adapter).
    amadeus_client_id: str = _env("AMADEUS_CLIENT_ID", "")
    amadeus_client_secret: str = _env("AMADEUS_CLIENT_SECRET", "")
    amadeus_base_url: str = _env("AMADEUS_BASE_URL", "https://test.api.amadeus.com")

    # Max requests issued per sweep per source (hard politeness ceiling).
    max_requests_per_sweep: int = int(_env("APIX_MAX_REQUESTS_PER_SWEEP", "120"))

    # Wall-clock budget for a sweep that has to finish *inside* one HTTP request
    # (serverless, or any deployment with the background loop off). Only used to
    # size the sweep when politeness delays would otherwise blow the platform's
    # function timeout; offline/in-process sources cost no wall-clock time and
    # are never truncated. Keep it below the function's maxDuration.
    request_sweep_budget_seconds: float = float(_env("APIX_REQUEST_SWEEP_BUDGET_SECONDS", "45"))


settings = Settings()
