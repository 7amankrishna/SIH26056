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


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
