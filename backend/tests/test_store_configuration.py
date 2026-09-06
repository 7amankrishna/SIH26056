from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import app.collect.store as store_module
from app.collect.store import Store, StoreConfigurationError, validate_database_url


@pytest.fixture(autouse=True)
def clear_database_environment(monkeypatch):
    for name in (
        "DATABASE_URL",
        "VERCEL",
        "VERCEL_ENV",
        "APIX_ENV",
        "APP_ENV",
        "ENVIRONMENT",
        "PYTHON_ENV",
    ):
        monkeypatch.delenv(name, raising=False)


def test_valid_postgres_url_selects_postgresql_without_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db.example/app")
    monkeypatch.setattr(Store, "_init", lambda self: None)

    store = Store()

    assert store.backend == "postgresql"
    assert store.path is None


def test_keyword_dsn_is_accepted():
    assert validate_database_url("dbname=app host=db.example user=app") == (
        "dbname=app host=db.example user=app"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/7amankrishna/SIH26056/branches",
        "http://db.example/app",
        "sqlite:///tmp/apix.sqlite3",
        "mysql://user:pass@db/app",
        "mongodb://db/app",
        "redis://db:6379/0",
        "/tmp/apix.sqlite3",
    ],
)
def test_invalid_database_urls_are_rejected(value):
    with pytest.raises(StoreConfigurationError):
        validate_database_url(value)


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    with pytest.raises(StoreConfigurationError, match="DATABASE_URL is required"):
        Store()


def test_production_never_falls_back_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("APIX_ENV", "production")
    monkeypatch.setenv("APIX_DATA_DIR", str(tmp_path))

    with pytest.raises(StoreConfigurationError):
        Store()

    assert not list(tmp_path.iterdir())


def test_sqlite_remains_available_for_local_development(tmp_path):
    store = Store(tmp_path / "local.sqlite3")

    assert store.backend == "sqlite"
    assert store.path == tmp_path / "local.sqlite3"


class _PostgresBranchCursor:
    def __init__(self, connection):
        self._cursor = connection._sqlite.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self._cursor.close()

    def execute(self, query, args=()):
        query = query.replace("%s", "?").replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        self._cursor.execute(query, args)
        return self

    def executemany(self, query, args_list):
        query = query.replace("%s", "?").replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        self._cursor.executemany(query, args_list)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _PostgresBranchConnection:
    def __init__(self):
        self._sqlite = sqlite3.connect(":memory:")
        self._sqlite.row_factory = sqlite3.Row

    def cursor(self, cursor_factory=None):
        return _PostgresBranchCursor(self)

    def commit(self):
        self._sqlite.commit()

    def close(self):
        pass


def test_postgres_branch_performs_store_crud(monkeypatch):
    connection = _PostgresBranchConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db.example/app")
    monkeypatch.setattr(store_module.psycopg2, "connect", lambda _url: connection)

    store = Store()
    store.set_state("mode", "live")
    store.begin_run("run-1", "fixture", "manual")
    store.finish_run("run-1", status="success", observations=1)
    store.insert_observations(
        "run-1",
        [{"observation_id": "obs-1", "collection_date": "2026-09-06", "quality_status": "VALID"}],
    )

    assert store.get_state("mode") == "live"
    assert store.last_run()["status"] == "success"
    assert store.counts()["observations"] == 1


def test_importing_vercel_entrypoint_does_not_initialize_store(tmp_path):
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["VERCEL"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

    result = subprocess.run(
        [sys.executable, "-c", "import api.index"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DATABASE_URL is required" not in result.stderr
