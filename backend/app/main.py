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
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .collect import collection_service
from .collect.store import StoreError
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
        store = collection_service.store
        if not store.available:
            # Scraping is disabled until storage is fixed — say so loudly at boot.
            print(f"[apix] collection store unavailable: {store.unavailable_reason}")
        elif store.note:
            print(f"[apix] collection store ({store.path}): {store.note}")
        await collection_service.start()
        if not collection_service.background_running:
            print("[apix] no background collector loop — sweeps run inside the request that asks for them")
    except Exception as exc:  # a broken source must never stop the API
        print(f"[apix] collector did not start: {type(exc).__name__}: {exc}")
    yield
    try:
        await collection_service.stop()
    except Exception as exc:
        print(f"[apix] collector did not stop cleanly: {type(exc).__name__}: {exc}")


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


@app.exception_handler(StoreError)
async def store_unavailable_handler(request, exc: StoreError):
    """Storage problems are a 503 with a reason, never an opaque 500.

    The scraper's own endpoints can fail — the dashboard must still be able to
    tell the operator *why* instead of rendering "Internal Server Error".
    """
    return JSONResponse(
        status_code=503,
        content={"detail": f"Collection store unavailable: {exc}", "store_error": True},
    )


@app.exception_handler(sqlite3.Error)
async def sqlite_error_handler(request, exc: sqlite3.Error):
    return JSONResponse(
        status_code=503,
        content={"detail": f"Collection store error: {type(exc).__name__}: {exc}", "store_error": True},
    )


@app.get(settings.api_prefix + "/health", tags=["Health"])
def health() -> dict:
    """Liveness/readiness probe for orchestration and the frontend.

    A probe must never 500 because a *subsystem* is misconfigured: the API is up
    and serving the index, so it reports the collection store's state instead of
    hiding behind an exception.
    """
    ds = get_dataset()
    try:
        counts = collection_service.store.counts()
        collector_running = bool(collection_service.background_running)
    except Exception as exc:  # store misconfigured/unreachable — degrade, don't die
        counts = {"available": False, "unavailable_reason": f"{type(exc).__name__}: {exc}"}
        collector_running = False
    return {
        "status": "ok",
        "version": settings.version,
        "title": settings.title,
        "demo_mode": ds.origin == "demo",
        "data_origin": ds.origin,
        "collector_running": collector_running,
        "collector_enabled": settings.collector_enabled,
        "request_scoped_runtime": settings.request_scoped_runtime,
        "store_backend": counts.get("backend", "unavailable"),
        "store_available": bool(counts.get("available", False)),
        "store_note": counts.get("note"),
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
