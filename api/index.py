"""Vercel entrypoint for the APIx FastAPI app.

Vercel's Python/FastAPI runtime looks for an ``app`` instance at recognised
entrypoints (``app.py``, ``index.py``, ``server.py``, ``main.py``, etc. under
the project root or ``src/``/``app/``/``api/``). This module re-exports the
existing FastAPI application so we keep the app in ``backend/app`` while still
satisfying Vercel's discovery.

The backend package lives in ``backend/`` (which contains ``app/``), so we add
it to ``sys.path`` before importing. No uvicorn/Mangum wrapper is required —
Vercel runs the ASGI app natively.
"""

import os
import sys

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Expose the ASGI app under the name Vercel expects.
from app.main import app  # noqa: E402,F401
