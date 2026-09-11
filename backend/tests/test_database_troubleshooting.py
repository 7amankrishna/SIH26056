"""Regression tests for the "I set DATABASE_URL and it still does not work" class.

Each test here reproduces a failure that was observed against a real
PostgreSQL and then fixed:

* an upload whose data already existed under another file name persisted the
  loader's ``DUPLICATE``-flagged twin, so the database filled up with rows the
  index excludes (``valid_observations: 0``) and the live dashboard went empty;
* a ``DATABASE_URL`` pasted straight from a provider console (Supabase's
  ``?pgbouncer=true`` hint, wrapper quotes, an un-encoded password character)
  disabled the store with an undiagnosable message;
* one unreachable database at cold start disabled the store for the whole
  process lifetime, so a deployment stayed broken after the database recovered.

They run on SQLite where possible (see tests/test_persist.py) and assert on the
store contents, not on the HTTP status alone: the upload endpoint answers 200
even when persistence fails, which is exactly how the bug hid.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.collect.store as store_module  # noqa: E402
from app import custom_data  # noqa: E402
from app.collect.store import Store, StoreConfigurationError, normalize_database_url  # noqa: E402

REPO_DATA = Path(__file__).resolve().parents[2] / "data"
SAMPLE_FILE = REPO_DATA / "newfare1_1.csv"


# --------------------------------------------------------------------------- #
# 1. Upload persistence must write canonical rows, not duplicate-flagged twins
# --------------------------------------------------------------------------- #


@pytest.fixture()
def upload_env(tmp_path, monkeypatch):
    """Shipped data dir already holding the file the user is about to upload.

    This is the state that triggered the bug: the same export exists in the
    scanned data directory (or from an earlier upload) *and* arrives again
    through the browser, so the loader sees two identical copies.
    """
    shipped = tmp_path / "shipped"
    uploads = tmp_path / "uploads"
    shipped.mkdir()
    uploads.mkdir()
    (shipped / SAMPLE_FILE.name).write_bytes(SAMPLE_FILE.read_bytes())

    monkeypatch.setattr(custom_data, "data_root", lambda: shipped)
    monkeypatch.setenv("APIX_UPLOAD_DATA_DIR", str(uploads))
    monkeypatch.setenv("APIX_DATA_DIR", str(tmp_path / "store"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APIX_IGNORE_DATABASE_URL", raising=False)

    previous = store_module._store
    store_module._store = None
    custom_data.invalidate_cache()
    store = store_module.get_store()
    assert store.available, f"test store unavailable: {store.unavailable_reason}"
    store.reset()
    try:
        yield store
    finally:
        store.reset()
        store_module._store = previous
        custom_data.invalidate_cache()


def _upload(client, payload: bytes, name: str) -> dict:
    response = client.post("/api/data/upload", files={"files": (name, payload, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_of_data_that_already_exists_persists_valid_rows(client, upload_env):
    """The database must end up holding rows the index can actually use."""
    payload = SAMPLE_FILE.read_bytes()
    body = _upload(client, payload, SAMPLE_FILE.name)

    persistence = body["persistence"]
    assert persistence is not None, body
    assert persistence["persisted"] is True, persistence
    assert persistence["inserted"] > 0, persistence

    # The regression: every persisted row was the loader's DUPLICATE twin, so
    # the store held data and the dashboard showed none of it.
    counts = upload_env.counts()
    assert counts["observations"] == persistence["total"]
    assert counts["valid_observations"] > 0, counts
    assert "DUPLICATE" not in counts["by_status"], counts

    stored = upload_env.all_observations()
    assert stored, "nothing was written to the store"
    assert all(row["quality_status"] != "DUPLICATE" for row in stored)


def test_reuploading_the_same_file_keeps_the_database_valid(client, upload_env):
    """A corrected re-upload replaces rows; it must not flip them to DUPLICATE."""
    payload = SAMPLE_FILE.read_bytes()
    first = _upload(client, payload, SAMPLE_FILE.name)
    second = _upload(client, payload, SAMPLE_FILE.name)

    for body in (first, second):
        assert body["persistence"]["persisted"] is True, body["persistence"]

    counts = upload_env.counts()
    # Same ids both times: the second upload updates in place instead of adding
    # a duplicate set (see tests/test_persist.py for the idempot contract).
    assert counts["observations"] == first["persistence"]["total"]
    assert counts["valid_observations"] > 0, counts
    assert "DUPLICATE" not in counts["by_status"], counts


def test_persist_endpoint_canonicalises_rows(client, upload_env):
    """POST /api/data/persist must not upsert the duplicate twin over the good row."""
    _upload(client, SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name)
    upload_env.reset()

    response = client.post("/api/data/persist")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["persisted"] is True, report
    assert report["inserted"] > 0, report

    counts = upload_env.counts()
    assert counts["valid_observations"] > 0, counts
    assert "DUPLICATE" not in counts["by_status"], counts


# --------------------------------------------------------------------------- #
# 2. Connection strings pasted from a provider console
# --------------------------------------------------------------------------- #

POOLER_URL = (
    "postgresql://postgres.abcdefgh:s3cret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
)


def test_supabase_pooler_hint_is_dropped_instead_of_killing_the_store():
    """libpq rejects unknown URI parameters, so the pooler URL used to fail."""
    url, notes = normalize_database_url(POOLER_URL + "?pgbouncer=true&connect_timeout=15")

    assert "pgbouncer" not in url
    assert "connect_timeout=15" in url
    assert url.startswith("postgresql://postgres.abcdefgh:")
    assert any("pgbouncer" in note for note in notes)


def test_wrapper_quotes_are_stripped():
    url, _ = normalize_database_url(f'  "{POOLER_URL}"  ')
    assert url == POOLER_URL
    url, _ = normalize_database_url(f"'{POOLER_URL}'")
    assert url == POOLER_URL


def test_unescaped_password_characters_are_reported_actionably():
    """An '@' in the password truncates the URL; say so instead of 'port w'."""
    with pytest.raises(StoreConfigurationError) as excinfo:
        normalize_database_url("postgresql://postgres:p@ss:w/rd@db.example.com:5432/postgres")
    message = str(excinfo.value)
    assert "percent-encode" in message
    assert "p@ss" not in message  # never echo the credential back


def test_wrong_scheme_names_the_expected_one():
    with pytest.raises(StoreConfigurationError) as excinfo:
        normalize_database_url("mysql://user:pass@db.example.com:5432/app")
    assert "postgresql://" in str(excinfo.value)


def test_driver_messages_are_redacted_before_they_reach_the_ui():
    from app.collect.store import redact_credentials

    url = "postgresql://postgres:s3cret@db.example.com:5432/postgres"
    assert "s3cret" not in redact_credentials(
        'password authentication failed for user "postgres" (password=s3cret)', url
    )
    assert "db.example.com" in redact_credentials("connection refused to db.example.com", url)


# --------------------------------------------------------------------------- #
# 3. A transient outage must not disable the store for the process lifetime
# --------------------------------------------------------------------------- #


def test_connection_failure_is_retryable_and_heals(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(store_module, "DB_RETRY_SECONDS", 0)

    attempts = {"configure": 0}
    sqlite_path = tmp_path / "apix.sqlite3"

    def flaky_configure(self, path):
        attempts["configure"] += 1
        if attempts["configure"] == 1:
            self.backend = "postgresql"
            raise store_module.StoreConnectionError(
                "PostgreSQL is configured but could not be reached: OperationalError: boom"
            )
        self.db_url = None
        self.backend = "sqlite"
        self.path = sqlite_path

    monkeypatch.setattr(Store, "_configure", flaky_configure)

    store = Store()
    assert store.available is False
    assert store.retryable is True
    assert "could not be reached" in store.unavailable_reason

    assert store.maybe_reconnect() is True, "a recovered database must be picked up"
    assert store.available is True
    assert store.unavailable_reason is None
    assert store.counts()["observations"] == 0
    # "Available" is not enough: the schema has to exist, i.e. a write must land.
    store.set_state("data_mode", "live")
    assert store.get_state("data_mode") == "live"
    assert attempts["configure"] == 2


def test_configuration_failure_is_never_retried(monkeypatch):
    """A bad URL cannot fix itself; re-parsing it per request is pure overhead."""
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@db.example.com/app")
    monkeypatch.setattr(store_module, "DB_RETRY_SECONDS", 0)

    store = Store()
    assert store.available is False
    assert store.retryable is False
    assert store.maybe_reconnect() is False


def test_retry_is_rate_limited(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/db")
    monkeypatch.setattr(store_module, "DB_RETRY_SECONDS", 3600)

    store = Store()
    assert store.available is False
    assert store.retryable is True
    # Second call inside the window must not open another connection attempt.
    assert store.maybe_reconnect() is False
