"""APIx backend — FastAPI application entrypoint.

Routes respond at ``/api/*`` (see ``settings.api_prefix``). The React SPA is
served separately by Vite in development and proxied to this backend.

On Vercel the whole app is deployed as a single serverless Function: the API
lives under ``/api`` and the built SPA (``frontend/dist``) is served from the
function so one origin serves both. When ``frontend/dist`` is absent (e.g. pure
API-only usage) the SPA routes are simply not mounted.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .collect import collection_service
from .collect.store import DatabaseConfigError
from .config import settings
from .dataset import get_dataset
from .routers import api, collect

START_TIME = time.time()

# Repo root = backend/app/main.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the dataset and start the background collector if it is enabled."""
    get_dataset()
    try:
        await collection_service.start()
    except Exception as exc:  # a broken source must never stop the API
        print(f"[apix] collector did not start: {type(exc).__name__}: {exc}")
    yield
    await collection_service.stop()


app = FastAPI(
    title=settings.title,
    version=settings.version,
    description=settings.description,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix=settings.api_prefix)
app.include_router(collect.router, prefix=settings.api_prefix)


@app.exception_handler(DatabaseConfigError)
async def _database_config_error(_: Request, exc: DatabaseConfigError) -> JSONResponse:
    """A bad ``DATABASE_URL`` is an operator error: say so instead of a bare 500.

    The store is initialised lazily, so this fires on the first request that
    needs the database — the rest of the app (health, docs, demo data, the SPA)
    keeps working while the environment variable gets fixed.
    """
    print(f"[apix] database configuration error: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "error": "database_misconfigured"},
        headers={"Retry-After": "60"},
    )


@app.get(settings.api_prefix + "/health", tags=["Health"])
def health() -> dict:
    """Liveness/readiness probe for orchestration and the frontend."""
    ds = get_dataset()
    ds = get_dataset()
    return {
        "status": "ok",
        "version": settings.version,
        "title": settings.title,
        "demo_mode": ds.origin != "live",
        "data_origin": ds.origin,
        "collector_running": collection_service.background_running,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": ds.end_date.isoformat() + "T09:00:00+05:30",
        "period_start": ds.base_period_start.isoformat(),
        "period_end": ds.end_date.isoformat(),
    }


# --------------------------------------------------------------------------- #
# Built SPA serving (Vercel promotes StaticFiles mounts to the CDN at build).
# Added only when the frontend has been built, so pure-API usage is unaffected.
# --------------------------------------------------------------------------- #

if _FRONTEND_DIST.is_dir():
    _ASSETS = _FRONTEND_DIST / "assets"
    if _ASSETS.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS)), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve the SPA for client-side routes, but never shadow the API/docs."""
        # Never serve the SPA in place of API routes or docs.
        if (
            full_path.startswith("api")
            or full_path == "docs"
            or full_path.startswith("docs/")
            or full_path == "redoc"
            or full_path == "openapi.json"
        ):
            raise HTTPException(status_code=404, detail=f"Route '{full_path}' not found.")
        candidate = (_FRONTEND_DIST / full_path).resolve()
        # Guard against path traversal.
        if _FRONTEND_DIST.resolve() not in candidate.parents and candidate != _FRONTEND_DIST.resolve():
            raise HTTPException(status_code=404, detail="Not found.")
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
