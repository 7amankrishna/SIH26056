"""Vercel entrypoint for the APIx FastAPI app.

Vercel's Python/FastAPI runtime looks for an ``app`` instance at recognised
entrypoints (``app.py``, ``index.py``, ``server.py``, ``main.py``, etc. under
the project root or ``src/``/``app/``/``api/``). This module re-exports the
existing FastAPI application so we keep the app in ``backend/app`` while still
satisfying Vercel's discovery.

The backend package lives in ``backend/`` (which contains ``app/``), so we add
it to ``sys.path`` before importing. No uvicorn/Mangum wrapper is required —
Vercel runs the ASGI app natively.

Robust path handling supports both local dev and Vercel's bundled filesystem
where ``includeFiles: backend/**`` preserves the backend at the project root
but the function may be invoked from a different working directory.
"""

import os
import sys

# Resolve project root (api/index.py -> project root)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")

# Fallback candidates for Vercel's file layout
_CANDIDATES = [
    _BACKEND_DIR,
    os.path.join(_HERE, "backend"),
    os.path.join(_HERE, "..", "backend"),
]

for _p in _CANDIDATES:
    _ap = os.path.abspath(_p)
    if os.path.isdir(_ap) and _ap not in sys.path:
        sys.path.insert(0, _ap)
        break
else:
    # Ensure project root backend is at least tried
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)

# Expose the ASGI app under the name Vercel expects.
from app.main import app  # noqa: E402,F401
