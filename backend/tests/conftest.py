"""Pytest fixtures for APIx backend tests.

Environment is pinned *before* any ``app`` import so the settings singleton sees
it: tests get a throwaway data directory, no background collector, and no
third-party collection adapters. Without this a suite run after a live sweep
would read whatever the developer's store happens to hold.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["APIX_DATA_DIR"] = tempfile.mkdtemp(prefix="apix-tests-")
os.environ["APIX_COLLECTOR_ENABLED"] = "0"
os.environ["APIX_COLLECTOR_SOURCES"] = ""
os.environ["APIX_DEMO_MODE"] = "1"
# Never let the ordinary suite read or write a developer's deployment database.
# PostgreSQL integration tests explicitly opt in via APIX_TEST_DATABASE_URL.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("APIX_IGNORE_DATABASE_URL", None)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
