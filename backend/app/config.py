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


class Settings:
    """Runtime settings for the APIx backend."""

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
    # Kept out of git (see .gitignore) so deployed instances start clean.
    data_dir: Path = Path(_env("APIX_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))

    # Master switch for the background loop. When false, the API still serves
    # everything already stored, but no new collection runs are scheduled.
    collector_enabled: bool = _env_bool("APIX_COLLECTOR_ENABLED", "1")

    # Seconds between scheduled sweeps.
    sweep_interval_seconds: int = int(_env("APIX_SWEEP_INTERVAL_SECONDS", "900"))

    # Adapters to register, comma separated.
    #   fixture  - authorized local replay capture (no network, demo-safe)
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


settings = Settings()
