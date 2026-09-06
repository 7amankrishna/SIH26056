"""Application configuration.

All values default to safe, demo-friendly settings and can be overridden
through environment variables (prefixed with ``APIX_``).
"""

from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


class Settings:
    """Runtime settings for the APIx backend."""

    title: str = "APIx — Real-Time Airfare Price Index for India"
    version: str = "0.1.0"
    description: str = (
        "High-frequency airfare intelligence for CPI augmentation. "
        "Collection -> Normalization -> Quality -> Index -> API."
    )

    # Demo / offline mode is the default. Real collection engines (scrapers)
    # plug into the same pipeline behind this flag.
    demo_mode: bool = _env("APIX_DEMO_MODE", "1").lower() in {"1", "true", "yes", "on"}

    # Number of days for which the deterministic demo store is generated.
    demo_history_days: int = int(_env("APIX_DEMO_DAYS", "90"))

    # Prefix for the REST API (the SPA is served by Vite in dev and proxied).
    api_prefix: str = "/api"

    # CORS origins allowed to call the API in development.
    cors_origins: list[str] = ["*"]


settings = Settings()
