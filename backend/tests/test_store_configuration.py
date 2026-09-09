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
        "APIX_IGNORE_DATABASE_URL",
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


def test_production_without_database_url_uses_a_labelled_ephemeral_store(monkeypatch, tmp_path):
    """Serverless has no durable disk, but the scraper must still work.

    The old behaviour raised here, which surfaced as a bare 500 on every
    collection endpoint (and on /api/health) of the deployed demo. SQLite is now
    allowed, but only as a store that says out loud that it is ephemeral.
    """
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("APIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store_module.settings, "data_dir", tmp_path)

    store = Store()

    assert store.path == tmp_path / "apix.sqlite3"
    assert store.available is True
    assert store.backend == "sqlite"
    assert store.ephemeral is True
    assert store.durable is False
    counts = store.counts()
    assert counts["available"] is True
    assert counts["ephemeral"] is True
    assert "DATABASE_URL" in (counts["note"] or "")


@pytest.mark.parametrize("platform_variable", ["VERCEL", "VERCEL_ENV"])
@pytest.mark.parametrize(
    "database_url",
    [
        "https://github.com/7amankrishna/SIH26056",
        "mysql://user:secret@db.example/app",
        "postgresql://user:secret@127.0.0.1:1/app",
        "postgresql://user:secret@[broken/app",
        "dbname=app host=db.example user=app password=secret",
    ],
)
def test_vercel_can_explicitly_ignore_database_url_without_using_postgres(
    monkeypatch, tmp_path, platform_variable, database_url
):
    """Offline mode is still available, but must now be an explicit choice."""
    monkeypatch.setenv(platform_variable, "1" if platform_variable == "VERCEL" else "preview")
    monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", "1")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(store_module.settings, "data_dir", tmp_path)

    def unexpected_postgres(*_args, **_kwargs):
        pytest.fail("An explicitly ignored DATABASE_URL must not be parsed or connected to")

    monkeypatch.setattr(store_module, "validate_database_url", unexpected_postgres)
    monkeypatch.setattr(store_module.psycopg2, "connect", unexpected_postgres)

    store = Store()
    store.set_state("data_mode", "live")
    store.begin_run("run-ignored-url", "fixture", "manual")
    store.finish_run("run-ignored-url", status="success")
    counts = store.counts()

    assert store.path == tmp_path / "apix.sqlite3"
    assert store.db_url is None
    assert counts["available"] is True
    assert counts["backend"] == "sqlite"
    assert counts["ephemeral"] is True
    assert counts["durable"] is False
    assert counts["ignores_database_url"] is True
    assert "DATABASE_URL is ignored" in counts["note"]
    assert "cold start or redeploy" in counts["note"]
    assert database_url not in counts["note"]
    assert "secret" not in counts["note"]
    assert counts["runs"] == 1
    assert store.last_run()["status"] == "success"
    assert Store().get_state("data_mode") == "live"


def test_vercel_honours_database_url_without_an_opt_in_flag(monkeypatch):
    """A valid Supabase URL must not be silently routed to ephemeral SQLite."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db.example/app")
    monkeypatch.setattr(Store, "_init", lambda self: None)

    store = Store()

    assert store.available is True
    assert store.backend == "postgresql"
    assert store.path is None
    assert store.durable is True
    assert store.ignore_database_url is False


@pytest.mark.parametrize("ignore_value", ["1", "true", "yes", "on", " TRUE "])
def test_ignore_database_url_can_be_enabled_locally_without_psycopg2(
    monkeypatch, tmp_path, ignore_value
):
    monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", ignore_value)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.example/app")
    monkeypatch.setattr(store_module, "psycopg2", None)

    store = Store(tmp_path / "local.sqlite3")
    store.set_state("data_mode", "live")

    assert store.available is True
    assert store.backend == "sqlite"
    assert store.ephemeral is False
    assert store.db_url is None
    assert store.get_state("data_mode") == "live"
    assert "DATABASE_URL is ignored" in store.note


@pytest.mark.parametrize("ignore_value", ["0", "false", "no", "off"])
def test_vercel_can_explicitly_opt_in_to_postgres(monkeypatch, ignore_value):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", ignore_value)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.example/app")
    monkeypatch.setattr(Store, "_init", lambda self: None)

    store = Store()

    assert store.available is True
    assert store.backend == "postgresql"
    assert store.path is None
    assert store.durable is True
    assert store.ephemeral is False
    assert store.note is None


def test_invalid_database_url_still_fails_closed_when_explicitly_enabled(monkeypatch, tmp_path):
    """Opting in to a database must not silently downgrade it to SQLite."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", "0")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/apix.sqlite3")
    monkeypatch.setenv("APIX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store_module.settings, "data_dir", tmp_path)

    store = Store()

    assert store.available is False
    assert store.backend == "unavailable"
    assert "PostgreSQL" in (store.unavailable_reason or "")
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_data_dir_degrades_to_an_unavailable_store(monkeypatch, tmp_path):
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)
    monkeypatch.setenv("APIX_DATA_DIR", str(readonly / "data"))
    monkeypatch.setattr(store_module.settings, "data_dir", readonly / "data")

    store = Store()

    assert store.available is False
    assert "not writable" in (store.unavailable_reason or "")
    # Reads answer empty, writes are no-ops: nothing raises into the API layer.
    assert store.counts()["observations"] == 0
    assert store.all_observations() == []
    assert store.recent_runs() == []
    assert store.add_raw_payloads("run-1", []) == 0
    store.set_state("data_mode", "live")
    assert store.get_state("data_mode") is None


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


@pytest.mark.parametrize("vercel", [False, True])
def test_postgres_branch_performs_store_crud(monkeypatch, vercel):
    if vercel:
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("APIX_IGNORE_DATABASE_URL", "0")
    connection = _PostgresBranchConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@db.example/app")
    monkeypatch.setattr(store_module.psycopg2, "connect", lambda _url, **_kwargs: connection)

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
