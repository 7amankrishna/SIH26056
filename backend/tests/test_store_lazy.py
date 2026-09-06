"""Store initialisation must be lazy, thread-safe and safe to import on Vercel.

Background: ``collection_service`` (and therefore a ``Store``) is created while
``app.main`` is imported. Vercel imports the module to serve *every* request, so
any database work in ``Store.__init__`` — a bad ``DATABASE_URL``, an unreachable
host, a read-only filesystem — took the whole function down. These tests pin the
contract that fixes it:

* constructing a ``Store`` does no I/O and never raises for configuration;
* the backend is initialised exactly once, on first use, under a re-entrant lock;
* a failed initialisation is retried on the next call, not cached;
* ``DATABASE_URL`` is validated *before* it reaches psycopg2, with a clear
  ``RuntimeError`` for the classic mistake of pasting a GitHub URL.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from app.collect import store as store_mod
from app.collect.store import DatabaseConfigError, Store, parse_database_url


GITHUB_URL = "https://github.com/7amankrishna/SIH26056"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class _NeverCalled:
    """Stand-in for the psycopg2 module that fails the test if it is touched."""

    class extras:  # noqa: D106 - mirrors psycopg2.extras
        RealDictCursor = object()

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def connect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError(f"psycopg2.connect must not be reached, got {args} {kwargs}")


@pytest.fixture
def no_env(monkeypatch):
    """Neutral environment: no DATABASE_URL, not on Vercel."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)


@pytest.fixture
def fake_psycopg2(monkeypatch):
    fake = _NeverCalled()
    monkeypatch.setattr(store_mod, "psycopg2", fake)
    return fake


# --------------------------------------------------------------------------- #
# lazy initialisation
# --------------------------------------------------------------------------- #

def test_constructor_does_no_io(tmp_path, no_env):
    target = tmp_path / "nested" / "dir" / "lazy.sqlite3"
    st = Store(target)
    assert not st.initialized
    assert not target.exists()
    assert not target.parent.exists(), "__init__ must not create directories"


def test_first_query_initialises_once(tmp_path, no_env):
    st = Store(tmp_path / "once.sqlite3")
    calls: list[str] = []
    original = st._create_schema

    def counting():
        calls.append("schema")
        original()

    st._create_schema = counting  # type: ignore[method-assign]
    assert st.get_state("data_mode") is None
    assert st.initialized
    st.set_state("data_mode", "live")
    assert st.get_state("data_mode") == "live"
    assert st.counts()["observations"] == 0
    assert calls == ["schema"], "schema must be created exactly once"


def test_module_import_does_not_touch_database(tmp_path, monkeypatch):
    """Importing the app with a broken DATABASE_URL must succeed.

    This is the Vercel scenario: import failure == every route 500s.
    """
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", GITHUB_URL)
    monkeypatch.setattr(store_mod, "_store", None)

    st = store_mod.get_store()  # what CollectionService.__init__ does at import time
    assert not st.initialized

    # ... and the misconfiguration surfaces on first use, as a clear RuntimeError.
    with pytest.raises(RuntimeError, match="GitHub URL"):
        st.counts()


def test_failed_init_is_not_cached(tmp_path, monkeypatch):
    """A transient failure must not poison the store: the next call retries."""
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("DATABASE_URL", GITHUB_URL)
    st = Store()  # no explicit path -> honours DATABASE_URL
    with pytest.raises(DatabaseConfigError):
        st.get_state("x")
    assert not st.initialized

    # Operator fixes the environment; same Store instance must recover.
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setattr(store_mod.settings, "data_dir", tmp_path)
    assert st.get_state("x") is None
    assert st.initialized
    assert st.path == tmp_path / "apix.sqlite3"
    assert st.db_url is None


def test_explicit_path_wins_over_database_url(tmp_path, monkeypatch, fake_psycopg2):
    """Tests and tools pin a SQLite file; DATABASE_URL must not hijack them."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com:5432/apix")
    st = Store(tmp_path / "pinned.sqlite3")
    st.set_state("k", "v")
    assert st.db_url is None
    assert st.path == tmp_path / "pinned.sqlite3"
    assert fake_psycopg2.calls == []


# --------------------------------------------------------------------------- #
# locking
# --------------------------------------------------------------------------- #

def test_init_lock_is_reentrant(tmp_path, no_env):
    st = Store(tmp_path / "rlock.sqlite3")
    assert isinstance(st._init_lock, type(threading.RLock()))

    # Re-entering _ensure_init from inside initialisation (same thread) must be a
    # no-op rather than a deadlock or infinite recursion.
    original = st._create_schema
    reentered = []

    def reentrant():
        st._ensure_init()  # would deadlock with a plain Lock
        reentered.append(True)
        original()

    st._create_schema = reentrant  # type: ignore[method-assign]
    assert st.counts()["observations"] == 0
    assert reentered == [True]
    assert st.initialized


def test_concurrent_first_use_initialises_once(tmp_path, no_env):
    st = Store(tmp_path / "threads.sqlite3")
    schema_calls: list[int] = []
    original = st._create_schema
    gate = threading.Barrier(8)
    errors: list[BaseException] = []

    def slow_schema():
        schema_calls.append(1)
        original()

    st._create_schema = slow_schema  # type: ignore[method-assign]

    def worker():
        try:
            gate.wait(timeout=5)
            st.set_state(f"k-{threading.get_ident()}", "v")
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not errors
    assert len(schema_calls) == 1
    assert st.counts()["observations"] == 0


# --------------------------------------------------------------------------- #
# DATABASE_URL parsing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw", [None, "", "   ", '""', "''"])
def test_blank_database_url_means_sqlite(raw):
    assert parse_database_url(raw, vercel=True) is None
    assert parse_database_url(raw, vercel=False) is None


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://user:pw@ep-cool-name.us-east-1.aws.neon.tech/apix?sslmode=require",
        "postgres://user:pw@db.example.com:5432/apix",
        "POSTGRESQL://user:pw@db.example.com/apix",
        "postgresql://u:p@h1:5432,h2:5433/apix",  # libpq multi-host
        "host=db.example.com dbname=apix user=u password=p sslmode=require",
        "  postgresql://user:pw@db.example.com/apix  ",  # stray whitespace
        '"postgresql://user:pw@db.example.com/apix"',  # quotes pasted from .env
        "DATABASE_URL=postgresql://user:pw@db.example.com/apix",  # whole .env line pasted
    ],
)
def test_valid_postgres_dsns_pass_through(raw):
    out = parse_database_url(raw, vercel=True)
    assert out == raw.strip().removeprefix("DATABASE_URL=").strip("'\"")
    assert parse_database_url(raw, vercel=False) == out


@pytest.mark.parametrize(
    "raw",
    [
        GITHUB_URL,
        GITHUB_URL + ".git",
        "http://github.com/7amankrishna/SIH26056",
        "git@github.com:7amankrishna/SIH26056.git",
        "ssh://git@github.com/7amankrishna/SIH26056.git",
        "github.com/7amankrishna/SIH26056",
        "https://raw.githubusercontent.com/7amankrishna/SIH26056/main/README.md",
        "https://7amankrishna.github.io/SIH26056",
        "postgresql://user:pw@github.com/7amankrishna/SIH26056",  # right scheme, wrong host
        "host=github.com dbname=SIH26056 user=7amankrishna",
    ],
)
def test_github_url_is_rejected_with_clear_error(raw):
    with pytest.raises(DatabaseConfigError) as info:
        parse_database_url(raw, vercel=True)
    msg = str(info.value)
    assert "GitHub URL" in msg
    assert "DATABASE_URL" in msg
    assert "postgresql://" in msg
    assert "Vercel" in msg  # points the operator at the project settings
    assert isinstance(info.value, RuntimeError)


def test_github_error_message_is_environment_aware():
    with pytest.raises(DatabaseConfigError, match="Unset DATABASE_URL"):
        parse_database_url(GITHUB_URL, vercel=False)
    with pytest.raises(DatabaseConfigError, match="Environment Variables"):
        parse_database_url(GITHUB_URL, vercel=True)


def test_vercel_env_is_detected_from_environment(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(DatabaseConfigError, match="Environment Variables"):
        parse_database_url(GITHUB_URL)
    monkeypatch.delenv("VERCEL")
    with pytest.raises(DatabaseConfigError, match="Unset DATABASE_URL"):
        parse_database_url(GITHUB_URL)


@pytest.mark.parametrize(
    "raw, expect",
    [
        ("mysql://u:p@db.example.com/apix", "scheme 'mysql'"),
        ("https://db.example.com/apix", "scheme 'https'"),
        ("sqlite:///apix.sqlite3", "scheme 'sqlite'"),
        ("just-some-text", "no URL scheme"),
        ("/var/lib/postgresql/data", "no URL scheme"),
    ],
)
def test_non_postgres_values_are_rejected(raw, expect):
    with pytest.raises(DatabaseConfigError, match=expect):
        parse_database_url(raw, vercel=True)
    with pytest.raises(DatabaseConfigError, match=expect):
        parse_database_url(raw, vercel=False)


def test_hostless_dsn_rejected_on_vercel_only():
    # Fine locally (peer auth over a unix socket), impossible on Vercel.
    assert parse_database_url("postgresql:///apix", vercel=False) == "postgresql:///apix"
    assert parse_database_url("dbname=apix user=u", vercel=False) == "dbname=apix user=u"
    with pytest.raises(DatabaseConfigError, match="no host"):
        parse_database_url("postgresql:///apix", vercel=True)
    with pytest.raises(DatabaseConfigError, match="no host"):
        parse_database_url("dbname=apix user=u", vercel=True)
    # ... unless the host comes via the query string / keywords.
    assert parse_database_url("postgresql:///apix?host=db.example.com", vercel=True)
    assert parse_database_url("host=db.example.com dbname=apix", vercel=True)


def test_error_messages_never_leak_passwords():
    with pytest.raises(DatabaseConfigError) as info:
        parse_database_url("mysql://alice:hunter2@db.example.com/apix", vercel=True)
    assert "hunter2" not in str(info.value)
    assert "alice" in str(info.value)
    with pytest.raises(DatabaseConfigError) as info:
        parse_database_url("password=hunter2 dbname=apix", vercel=True)
    assert "hunter2" not in str(info.value)


# --------------------------------------------------------------------------- #
# the bad value must never reach psycopg2
# --------------------------------------------------------------------------- #

def test_bad_dsn_never_reaches_psycopg2(monkeypatch, fake_psycopg2):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", GITHUB_URL)
    st = Store()
    with pytest.raises(RuntimeError, match="GitHub URL"):
        st.counts()
    assert fake_psycopg2.calls == []
    assert not st.initialized


def test_valid_dsn_reaches_psycopg2_with_connect_timeout(monkeypatch):
    """Sanity check the happy path hands a *valid* DSN to psycopg2 (and bounds the wait)."""
    monkeypatch.setenv("VERCEL", "1")
    dsn = "postgresql://u:p@db.example.com:5432/apix?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", dsn)
    seen: list[tuple] = []

    class _Boom(Exception):
        pass

    class _FakePg:
        class extras:
            RealDictCursor = object()

        @staticmethod
        def connect(*args, **kwargs):
            seen.append((args, kwargs))
            raise _Boom("simulated network failure")

    monkeypatch.setattr(store_mod, "psycopg2", _FakePg)
    st = Store()
    with pytest.raises(_Boom):
        st.counts()
    assert seen == [((dsn,), {"connect_timeout": store_mod.PG_CONNECT_TIMEOUT_SECONDS})]
    assert not st.initialized  # retried next time, not cached as broken

    # An explicit connect_timeout in the DSN is respected, not overridden.
    monkeypatch.setenv("DATABASE_URL", dsn + "&connect_timeout=3")
    st2 = Store()
    with pytest.raises(_Boom):
        st2.counts()
    assert seen[-1][1] == {}


def test_missing_psycopg2_is_a_clear_config_error(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.com/apix")
    monkeypatch.setattr(store_mod, "psycopg2", None)
    monkeypatch.setattr(store_mod, "_PSYCOPG2_IMPORT_ERROR", "No module named 'psycopg2'")
    st = Store()
    with pytest.raises(DatabaseConfigError, match="psycopg2-binary==2.9.10"):
        st.counts()


# --------------------------------------------------------------------------- #
# Vercel filesystem fallback
# --------------------------------------------------------------------------- #

def test_read_only_data_dir_falls_back_to_tmp_on_vercel(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    fallback_dir = tmp_path / "vercel-tmp"
    monkeypatch.setattr(store_mod, "_VERCEL_TMP_DIR", fallback_dir)

    ro_root = tmp_path / "ro"
    monkeypatch.setattr(store_mod.settings, "data_dir", ro_root / "data")

    real_ensure = store_mod._ensure_writable_dir

    def ensure(directory):
        if str(directory).startswith(str(ro_root)):
            raise PermissionError(f"[Errno 30] Read-only file system: '{directory}'")
        return real_ensure(directory)

    monkeypatch.setattr(store_mod, "_ensure_writable_dir", ensure)

    st = Store()
    st.set_state("k", "v")
    assert st.path == fallback_dir / "apix.sqlite3"
    assert st.path.exists()
    assert st.get_state("k") == "v"
    assert "ephemeral" in capsys.readouterr().out


def test_read_only_data_dir_is_an_error_off_vercel(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(store_mod.settings, "data_dir", tmp_path / "ro" / "data")
    monkeypatch.setattr(
        store_mod,
        "_ensure_writable_dir",
        lambda d: (_ for _ in ()).throw(PermissionError("read-only")),
    )
    st = Store()
    with pytest.raises(PermissionError):
        st.counts()
    assert not st.initialized


# --------------------------------------------------------------------------- #
# the whole app, in the Vercel failure mode
# --------------------------------------------------------------------------- #

def test_app_survives_bad_database_url(monkeypatch):
    """Simulates the crashing deployment: VERCEL=1 with a GitHub URL as DATABASE_URL.

    Routes that do not need the store must keep working; routes that do must
    answer with a 503 that names the problem, not a 500 (and never a crashed
    import).
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", GITHUB_URL)
    monkeypatch.setattr(store_mod, "_store", None)
    fresh = store_mod.get_store()
    # The app's singleton service was built at import time — point it at a store
    # that will resolve the (bad) environment lazily, exactly as on Vercel.
    from app.collect import collection_service

    monkeypatch.setattr(collection_service, "store", fresh)

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/index").status_code == 200
        assert client.get("/docs").status_code == 200

        r = client.get("/api/collect/runs")
        assert r.status_code == 503
        body = r.json()
        assert body["error"] == "database_misconfigured"
        assert "GitHub URL" in body["detail"]
        assert "DATABASE_URL" in body["detail"]
        assert r.headers["retry-after"] == "60"

    assert not fresh.initialized
    monkeypatch.setattr(store_mod, "_store", None)


# --------------------------------------------------------------------------- #
# existing behaviour still holds
# --------------------------------------------------------------------------- #

def test_schema_is_created_on_first_use_and_reused(tmp_path, no_env):
    p = tmp_path / "schema.sqlite3"
    Store(p).begin_run("r1", "stub", "manual")
    with sqlite3.connect(str(p)) as raw:
        tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = raw.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    assert {"collection_runs", "raw_payloads", "observations", "apix_state", "schema_meta"} <= tables
    assert version == str(store_mod.SCHEMA_VERSION)

    again = Store(p)  # second process: schema already there, data visible
    assert again.last_run()["run_id"] == "r1"
    assert again.counts()["db_path"] == str(p)
