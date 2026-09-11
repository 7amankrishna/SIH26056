"""SQLite and Postgres persistence for collected data.

Stdlib ``sqlite3`` for local and the Vercel fallback demo: no service to
provision, works offline. A configured ``DATABASE_URL`` is honoured on every
platform (including Vercel) and selects Postgres via psycopg2; set
``APIX_IGNORE_DATABASE_URL=1`` only to force the offline SQLite fallback. Three tables:

    collection_runs   one row per sweep per source, incl. blocked/failed runs
    raw_payloads      the payload *exactly as received* (never rewritten)
    observations      the normalized canonical fare model, quality-flagged

Plus ``apix_state`` — a tiny KV table that persists the dashboard's data-source
toggle so the selection survives a restart.
"""

from __future__ import annotations

import os
import datetime as dt
import json
import socket
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from ..config import settings

SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """Base class for store failures the API reports instead of crashing on."""


class StoreConfigurationError(StoreError):
    """Raised when the deployment database configuration is unsafe or unusable."""


class StoreConnectionError(StoreError):
    """Raised when a configured database exists but cannot be reached."""


def _vercel_environment() -> bool:
    return any(os.getenv(name, "").strip() for name in ("VERCEL", "VERCEL_ENV"))


def _production_environment() -> bool:
    """Detect hosted production contexts without importing application settings."""
    if _vercel_environment():
        return True
    return any(
        os.getenv(name, "").strip().lower() in {"production", "prod"}
        for name in ("APIX_ENV", "APP_ENV", "ENVIRONMENT", "PYTHON_ENV")
    )


def _ignore_database_url() -> bool:
    """Whether to explicitly opt out of a configured PostgreSQL database.

    A configured ``DATABASE_URL`` must mean "use the database" on every host,
    including Vercel. The old Vercel-specific default silently ignored a valid
    Supabase URL and made successful imports land only in ephemeral SQLite.
    Set ``APIX_IGNORE_DATABASE_URL=1`` only for an intentionally offline demo.
    """
    value = os.getenv("APIX_IGNORE_DATABASE_URL", "").strip() or "0"
    return value.lower() in {"1", "true", "yes", "on"}


#: Seconds between re-tries of a store that failed for a *transient* reason.
DB_RETRY_SECONDS = float(os.getenv("APIX_DB_RETRY_SECONDS", "15"))

#: Query parameters that are client-library hints rather than libpq options.
#: Supabase's pooler hands out ``…?pgbouncer=true&connect_timeout=15``; libpq
#: rejects any key it does not know ("invalid URI query parameter"), so a URL
#: that is perfectly correct for a JS or Go driver takes the whole store down
#: here. Dropping a pure hint is safe — it changes no connection behaviour.
_NON_LIBPQ_URL_PARAMS = ("pgbouncer",)


def _strip_wrapper_quotes(value: str) -> str:
    """Drop quotes a copy/paste left around the value (``"postgres://…"``)."""
    text = value.strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _drop_client_hints(database_url: str, parsed: Any) -> tuple[str, list[str]]:
    """Remove client-hint-only query parameters libpq would refuse outright."""
    if not parsed.query:
        return database_url, []
    kept: list[str] = []
    dropped: list[str] = []
    for part in parsed.query.split("&"):
        if not part:
            continue
        key = part.split("=", 1)[0].strip().lower()
        (dropped if key in _NON_LIBPQ_URL_PARAMS else kept).append(part)
    if not dropped:
        return database_url, []
    rebuilt = urlunsplit(parsed._replace(query="&".join(kept)))
    return rebuilt, sorted({p.split("=", 1)[0] for p in dropped})


def redact_credentials(text: str, database_url: Optional[str]) -> str:
    """Make a driver message safe to surface: no password, one line, bounded.

    The store has to say *why* the database is unreachable — "OperationalError"
    on its own is undiagnosable — without ever echoing the connection string.
    """
    message = " ".join(str(text or "").split())
    if database_url:
        try:
            password = urlsplit(database_url).password
        except ValueError:
            password = None
        if password:
            message = message.replace(password, "***")
    return message[:300] or type(text).__name__


# --------------------------------------------------------------------------- #
# Address-family diagnostics
# ----------------------------------------------------------------------------
# "Cannot assign requested address" / "Network is unreachable" from libpq is not
# a database problem: the host resolved to an IPv6 address and the runtime has
# no outbound IPv6 (Vercel functions, most containers). Supabase's *direct*
# host ``db.<ref>.supabase.co`` is IPv6-only on current projects, so a URL that
# looks perfectly correct can never connect there — while the pooler endpoint
# publishes IPv4. Detect that, retry over IPv4 when the host has an A record,
# and otherwise say exactly which endpoint to use instead.
# --------------------------------------------------------------------------- #

#: libpq's wordings for "this address family cannot be used from here".
_ADDRESS_FAMILY_HINTS = (
    "cannot assign requested address",
    "network is unreachable",
    "no route to host",
    "address family not supported by protocol",
)


def _host_and_port(database_url: str) -> tuple[Optional[str], int]:
    try:
        parsed = urlsplit(database_url)
    except ValueError:
        return None, 5432
    try:
        port = parsed.port or 5432
    except ValueError:
        port = 5432
    return (parsed.hostname or None), port


def _ipv4_address(host: str, port: int) -> Optional[str]:
    """First A record for ``host``, or None when it has no IPv4 address."""
    try:
        for info in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            return info[4][0]
    except OSError:
        return None
    return None


def has_ipv6_egress() -> bool:
    """Can this process open an IPv6 socket at all? (UDP connect sends nothing.)"""
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    except OSError:
        return False
    try:
        probe.connect(("2001:4860:4860::8888", 53))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _supabase_project_ref(host: str) -> Optional[str]:
    """``db.<ref>.supabase.co`` -> ``<ref>`` (the direct, IPv6-only endpoint)."""
    if host.endswith(".supabase.co") and host.startswith("db."):
        ref = host[3 : -len(".supabase.co")]
        return ref or None
    return None


def pin_database_url_to_ipv4(database_url: str) -> Optional[str]:
    """Rewrite a URL to dial the host's IPv4 address via ``hostaddr``.

    ``host`` stays the hostname so TLS certificate verification still matches;
    ``hostaddr`` only tells libpq which address to connect to. Returns None when
    the host has no A record — there is then nothing to pin and the operator has
    to use a different endpoint.
    """
    host, port = _host_and_port(database_url)
    if not host:
        return None
    ipv4 = _ipv4_address(host, port)
    if not ipv4:
        return None
    if "hostaddr=" in database_url:
        return None  # already pinned; do not stack pins
    parsed = urlsplit(database_url)
    query = f"{parsed.query}&hostaddr={ipv4}" if parsed.query else f"hostaddr={ipv4}"
    return urlunsplit(parsed._replace(query=query))


def describe_address_failure(database_url: str, exc: Exception) -> Optional[str]:
    """Explain an address-family failure in terms the operator can act on.

    Returns None when the error is not about address families — the caller then
    reports the driver's own message unchanged.
    """
    text = str(exc).lower()
    if not any(hint in text for hint in _ADDRESS_FAMILY_HINTS):
        return None
    host, port = _host_and_port(database_url)
    if not host:
        return None
    if _ipv4_address(host, port):
        return None  # dual-stack host: the IPv4 retry handles it
    detail = (
        f"host '{host}' has no IPv4 address (IPv6-only DNS) and this runtime cannot "
        "reach it over IPv6"
    )
    if not has_ipv6_egress():
        detail += " — this process cannot open an outbound IPv6 socket at all"
    detail += ". "
    project = _supabase_project_ref(host)
    if project:
        detail += (
            f"Use Supabase's IPv4 pooler endpoint instead: user 'postgres.{project}', "
            "host 'aws-0-<region>.pooler.supabase.com' (the region is shown in Supabase "
            "→ Project Settings → Database → Connection string), port 5432 for session "
            "mode or 6543 for transaction mode, same password and database. Note the "
            "user changes to 'postgres.<ref>', so re-run db/supabase_schema.sql — its "
            "row-level-security policies are created per login role."
        )
    else:
        detail += "Point DATABASE_URL at an endpoint that publishes an IPv4 address."
    return detail



POSTGRES_STORE_HINT = (
    "For durable collection history, set DATABASE_URL to a PostgreSQL database "
    "(and ensure APIX_IGNORE_DATABASE_URL is not set to 1)."
)
EPHEMERAL_STORE_NOTE = (
    "Ephemeral serverless store: SQLite under the only writable path (/tmp), so collected "
    "data is per-instance and is lost on a cold start or redeploy. "
    + POSTGRES_STORE_HINT
)


def normalize_database_url(value: str) -> tuple[str, list[str]]:
    """Validate a psycopg2 connection URI or keyword DSN without exposing it.

    Returns the URL to hand to the driver plus human-readable notes about
    anything that was repaired on the way (a wrapper quote, a client-only query
    parameter). Raises :class:`StoreConfigurationError` with an *actionable*
    message otherwise: the whole store is disabled when this fails, so "not a
    valid PostgreSQL URL" is not good enough — the message has to say which
    paste mistake happened and what to type instead.
    """
    database_url = _strip_wrapper_quotes(value)
    notes: list[str] = []
    if database_url != value.strip():
        notes.append("Removed surrounding quotes from DATABASE_URL.")
    if not database_url:
        raise StoreConfigurationError("DATABASE_URL must not be empty.")

    if "://" in database_url:
        parsed = urlsplit(database_url)
        if parsed.scheme.lower() not in {"postgres", "postgresql"}:
            raise StoreConfigurationError(
                f"DATABASE_URL must be a PostgreSQL connection URL, got scheme "
                f"'{parsed.scheme or '?'}://' (expected 'postgresql://')."
            )
        if not parsed.netloc and not parsed.path:
            raise StoreConfigurationError("DATABASE_URL is not a valid PostgreSQL URL.")
        if parsed.netloc and not parsed.hostname:
            raise StoreConfigurationError(
                "DATABASE_URL has no host. Expected "
                "'postgresql://USER:PASSWORD@HOST:PORT/DATABASE'."
            )
        # An unescaped '@', '/' or ':' in the password truncates the authority,
        # which surfaces as a nonsense port or host instead of an auth error.
        try:
            parsed.port
        except ValueError as exc:
            raise StoreConfigurationError(
                f"DATABASE_URL has an unreadable port ({exc}). This is almost always a "
                "password containing '@', ':' or '/' that must be percent-encoded "
                "('@' -> %40, ':' -> %3A, '/' -> %2F)."
            ) from exc
        if "@" in (parsed.path or ""):
            raise StoreConfigurationError(
                "DATABASE_URL is truncated: an unescaped '@' or '/' in the password ends the "
                "authority early. Percent-encode those characters in the password "
                "('@' -> %40, ':' -> %3A, '/' -> %2F)."
            )
        database_url, dropped = _drop_client_hints(database_url, parsed)
        if dropped:
            notes.append(
                "Ignored unsupported DATABASE_URL parameter(s): "
                + ", ".join(dropped)
                + " (client hints that libpq rejects; the connection is unchanged without them)."
            )
        return database_url, notes

    # psycopg2 also accepts keyword DSNs such as "dbname=app host=db user=...".
    # Reject filesystem paths and opaque values before handing them to the driver.
    if "=" not in database_url or database_url.startswith(("/", "./", "../", "~")):
        raise StoreConfigurationError(
            "DATABASE_URL must be a PostgreSQL URL or keyword DSN."
        )
    if psycopg2 is None:
        raise StoreConfigurationError(
            "DATABASE_URL is configured but psycopg2-binary is not installed."
        )
    try:
        parsed_dsn = psycopg2.extensions.parse_dsn(database_url)
    except Exception as exc:
        raise StoreConfigurationError(
            f"DATABASE_URL is not a valid PostgreSQL DSN ({redact_credentials(exc, database_url)})."
        ) from exc
    if not parsed_dsn.get("dbname") and not parsed_dsn.get("service"):
        raise StoreConfigurationError("DATABASE_URL DSN must specify a database.")
    return database_url, notes


def validate_database_url(value: str) -> str:
    """Validate a connection string, returning the URL the driver should get."""
    return normalize_database_url(value)[0]

OBS_COLUMNS = (
    "observation_id", "source", "origin", "destination", "route", "departure_date",
    "collection_date", "collection_timestamp", "airline", "flight_number", "cabin",
    "fare_class", "lead_time_days", "base_fare", "taxes", "fees", "total_fare",
    "currency", "availability", "seats_remaining", "raw_payload_reference",
    "fingerprint", "quality_status", "quality_score", "exclusion_reason",
)

_NUMERIC_COLS = {"base_fare", "taxes", "fees", "total_fare", "quality_score"}
_INT_COLS = {"lead_time_days", "seats_remaining"}

_SCHEMA_TMPL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,               -- running | success | partial | blocked | failed
    error_kind TEXT,
    detail TEXT,
    queries INTEGER DEFAULT 0,
    requests INTEGER DEFAULT 0,
    observations INTEGER DEFAULT 0,
    valid_observations INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    invalid INTEGER DEFAULT 0,
    suspicious INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    avg_latency_ms INTEGER,
    trigger TEXT DEFAULT 'scheduled'    -- scheduled | manual | startup
);
CREATE INDEX IF NOT EXISTS ix_runs_source_started ON collection_runs (source, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_started ON collection_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS raw_payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    http_status INTEGER,
    fetched_at TEXT NOT NULL,
    latency_ms INTEGER,
    query_json TEXT,
    payload_json TEXT NOT NULL,
    payload_sha TEXT
);
CREATE INDEX IF NOT EXISTS ix_raw_run ON raw_payloads (run_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS ix_raw_source ON raw_payloads (source, fetched_at DESC);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL UNIQUE,
    run_id TEXT,
    __OBS_COLUMNS__,
    in_basket INTEGER DEFAULT 1,
    inserted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_obs_day ON observations (collection_date, route, quality_status);
CREATE INDEX IF NOT EXISTS ix_obs_route_date ON observations (route, collection_date);
CREATE INDEX IF NOT EXISTS ix_obs_fp_day ON observations (fingerprint, collection_date);
CREATE INDEX IF NOT EXISTS ix_obs_source ON observations (source, collection_date);

CREATE TABLE IF NOT EXISTS apix_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_OBS_DDL = ",\n    ".join(
    f"{c} " + ("REAL" if c in _NUMERIC_COLS else "INTEGER" if c in _INT_COLS else "TEXT")
    for c in OBS_COLUMNS[1:]
)
_SCHEMA = _SCHEMA_TMPL.replace("__OBS_COLUMNS__", _OBS_DDL)

def _now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")

@dataclass
class StoredRun:
    run_id: str
    source: str
    started_at: str
    finished_at: Optional[str]
    status: str
    error_kind: Optional[str]
    detail: Optional[str]
    queries: int
    requests: int
    observations: int
    valid_observations: int
    duplicates: int
    invalid: int
    suspicious: int
    failures: int
    avg_latency_ms: Optional[int]
    trigger: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "error_kind": self.error_kind,
            "detail": self.detail,
            "queries": self.queries,
            "requests": self.requests,
            "observations": self.observations,
            "valid_observations": self.valid_observations,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
            "suspicious": self.suspicious,
            "failures": self.failures,
            "avg_latency_ms": self.avg_latency_ms,
            "trigger": self.trigger,
        }


# --------------------------------------------------------------------------- #
# Degraded mode: a store that could not be configured answers every read with an
# empty result and swallows every write, so one missing DATABASE_URL cannot take
# the whole API down with it. `counts()` still says *why*, and the UI shows it.
# --------------------------------------------------------------------------- #


class _NullRow(dict):
    """Row-shaped object that reports 0/None for any column asked of it."""

    def __missing__(self, key: str) -> Any:  # noqa: D105
        return 0


class _NullCursor:
    rowcount = 0

    def fetchone(self) -> _NullRow:
        # Empty-but-row-shaped: `COUNT(*)` reads answer 0 and truthiness stays
        # False, so `get_state()` still returns its default.
        return _NullRow()

    def fetchall(self) -> list[Any]:
        return []

    def keys(self) -> list[str]:
        return []


class _NullConnection:
    def execute(self, q: str, args: Any = ()) -> _NullCursor:
        return _NullCursor()

    def executemany(self, q: str, args_list: Any) -> _NullCursor:
        return _NullCursor()

    def executescript(self, q: str) -> _NullCursor:
        return _NullCursor()

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class Store:
    """Persistence for the collection engine.

    Construction never takes the API down: a deployment whose database is not
    configured (or whose filesystem is read-only) yields an *unavailable* store
    that answers every read with an empty result and every write with a no-op,
    and says why in :meth:`counts`. Endpoints then report a clear 503/``note``
    instead of an opaque 500 on every screen — a broken scraper must degrade the
    scraper, not the dashboard.
    """

    def __init__(self, path: Optional[Path] = None):
        self._write_lock = threading.Lock()
        # Separate lock for reconnection: ``_init`` (called from a retry) takes
        # ``_write_lock`` itself, and threading.Lock is not reentrant.
        self._reconnect_lock = threading.Lock()
        self._unavailable_reason: Optional[str] = None
        #: True when the failure was a *reachability* problem worth retrying
        #: (a cold start that raced a database blip), as opposed to a
        #: configuration error that retrying cannot fix.
        self._unavailable_is_transient = False
        self._last_attempt = 0.0
        #: Human-readable repairs made to DATABASE_URL (dropped client hints…).
        self.url_notes: list[str] = []
        #: True when SQLite is standing in for durable storage on a hosted runtime.
        self.ephemeral = False
        self.ignore_database_url = _ignore_database_url()
        self.db_url: Optional[str] = None
        #: The URL actually dialled, when it differs from ``db_url`` (IPv4 pin).
        self._effective_url: Optional[str] = None
        self.path: Optional[Path] = None
        self.backend = "sqlite"
        try:
            self._configure(path)
            self._init()
        except StoreError as exc:
            # Fail closed (nothing is written anywhere) but stay up: invalid or
            # unreachable PostgreSQL must become a visible capability failure,
            # never a process-wide 500 that makes the dashboard look blank.
            self._unavailable_reason = str(exc)
            self._unavailable_is_transient = isinstance(exc, StoreConnectionError)
            if self.backend != "postgresql":
                self.backend = "unavailable"
        finally:
            self._last_attempt = time.monotonic()

    #: ``path`` handed to :meth:`_configure`, kept so a retry rebuilds the same store.
    _configured_path: Optional[Path] = None

    def _configure(self, path: Optional[Path]) -> None:
        # Decide before reading, validating or connecting: even a valid-looking
        # but unreachable DATABASE_URL must not disable the Vercel demo.
        self._configured_path = path
        configured_url = "" if self.ignore_database_url else os.environ.get("DATABASE_URL", "").strip()
        if configured_url:
            # When PostgreSQL is enabled, retain fail-closed behaviour: a broken
            # durable store must not silently become an ephemeral one.
            self.db_url, self.url_notes = normalize_database_url(configured_url)
            self.backend = "postgresql"
            if not psycopg2:
                raise StoreConfigurationError(
                    "DATABASE_URL is configured but psycopg2-binary is not installed. "
                    "Install it with: pip install -r api/requirements.txt"
                )
            return

        self.backend = "sqlite"
        # On a hosted/serverless runtime SQLite is allowed, but only as an
        # explicitly labelled ephemeral store: it lives under the one writable
        # path and is thrown away with the instance.
        self.ephemeral = _production_environment()
        candidate = Path(path or settings.data_dir / "apix.sqlite3")
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            probe = candidate.parent / ".apix-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise StoreConfigurationError(
                f"SQLite collection store is not writable at {candidate} ({type(exc).__name__}: {exc}). "
                "Set APIX_DATA_DIR to a writable path (on Vercel: /tmp/apix-data), or set "
                "DATABASE_URL to a PostgreSQL database and ensure APIX_IGNORE_DATABASE_URL is not 1."
            ) from exc
        self.path = candidate

    # -- availability ----------------------------------------------------- #
    @property
    def available(self) -> bool:
        """False when no database could be configured at all."""
        return self._unavailable_reason is None

    @property
    def unavailable_reason(self) -> Optional[str]:
        return self._unavailable_reason

    @property
    def retryable(self) -> bool:
        """True when the store failed for a reason a later attempt can fix."""
        return self._unavailable_reason is not None and self._unavailable_is_transient

    def maybe_reconnect(self) -> bool:
        """Re-attempt configuration after a *transient* failure.

        Without this, a cold start that raced a database blip (DNS not warm yet,
        Supabase project resuming from pause, a failover) disables the store for
        the whole lifetime of the process — the deployment then reports
        "PostgreSQL could not be reached" forever even though the database came
        back seconds later. Configuration errors are never retried: they cannot
        fix themselves, and re-parsing a bad URL on every request would be pure
        overhead. Attempts are rate-limited so a dead database is not hammered.
        """
        if not self.retryable:
            return False
        if time.monotonic() - self._last_attempt < DB_RETRY_SECONDS:
            return False
        with self._reconnect_lock:
            if not self.retryable or time.monotonic() - self._last_attempt < DB_RETRY_SECONDS:
                return False
            self._last_attempt = time.monotonic()
            self.backend = "postgresql" if self.db_url else "sqlite"
            # ``_connect`` no-ops while the store is marked unavailable, and
            # ``_init`` goes through it — so the flag has to be cleared *before*
            # bootstrapping the schema, or the store would come back "healthy"
            # with no tables behind it. Restored below if the attempt fails.
            self._unavailable_reason = None
            try:
                self._configure(self._configured_path)
                self._init()
            except StoreError as exc:
                self._unavailable_reason = str(exc)
                self._unavailable_is_transient = isinstance(exc, StoreConnectionError)
                if self.backend != "postgresql":
                    self.backend = "unavailable"
                return False
            self._unavailable_is_transient = False
            return True

    @property
    def durable(self) -> bool:
        """Only Postgres survives a redeploy; SQLite on serverless does not."""
        return self.backend == "postgresql"

    @property
    def note(self) -> Optional[str]:
        notes = list(self.url_notes)
        if self.address_fallback == "ipv4":
            notes.append(
                "Connected to PostgreSQL over IPv4 (hostaddr pinned) because the "
                "host's IPv6 address is not reachable from this runtime."
            )
        if self.ignore_database_url:
            notes.append("DATABASE_URL is ignored because APIX_IGNORE_DATABASE_URL=1.")
        if not self.available:
            notes.append(f"Collection store unavailable — {self._unavailable_reason}")
            if self.retryable:
                notes.append(
                    f"Retrying every {DB_RETRY_SECONDS:g}s; a redeploy or a later request "
                    "will pick the database up as soon as it answers."
                )
        elif self.ephemeral:
            notes.append(EPHEMERAL_STORE_NOTE)
        elif self.ignore_database_url:
            notes.append(f"Using SQLite. {POSTGRES_STORE_HINT}")
        return " ".join(notes) or None

    #: Set when a connection succeeded by pinning ``hostaddr`` to an IPv4
    #: address after the default attempt hit an unusable IPv6 route.
    address_fallback: Optional[str] = None

    def _pg_connect(self):
        """Open a PostgreSQL connection, recovering from an IPv6-only DNS answer.

        Serverless runtimes generally have no outbound IPv6. When the host also
        publishes an A record, dialling that address directly turns an otherwise
        fatal "Cannot assign requested address" into a working connection; when
        it does not, no client-side trick can help, so the failure is reported in
        terms the operator can act on (which endpoint to use instead).
        """
        timeout = int(os.getenv("APIX_DB_CONNECT_TIMEOUT_SECONDS", "5"))
        url = self._effective_url or self.db_url
        try:
            return psycopg2.connect(url, connect_timeout=timeout)
        except Exception as exc:  # never echo the DSN (it carries credentials)
            pinned = pin_database_url_to_ipv4(self.db_url)
            if pinned and pinned != self._effective_url:
                try:
                    conn = psycopg2.connect(pinned, connect_timeout=timeout)
                except Exception as retry_exc:
                    hint = describe_address_failure(self.db_url, retry_exc)
                    raise StoreConnectionError(
                        "PostgreSQL is configured but could not be reached: "
                        f"{type(retry_exc).__name__}: "
                        f"{redact_credentials(retry_exc, self.db_url)}"
                        + (f" — {hint}" if hint else "")
                    ) from retry_exc
                # Remember it: every store operation opens a fresh connection.
                self._effective_url = pinned
                self.address_fallback = "ipv4"
                return conn
            hint = describe_address_failure(self.db_url, exc)
            raise StoreConnectionError(
                "PostgreSQL is configured but could not be reached: "
                f"{type(exc).__name__}: {redact_credentials(exc, self.db_url)}"
                + (f" — {hint}" if hint else "")
            ) from exc

    @contextmanager
    def _connect(self):
        if not self.available:
            yield _NullConnection()
            return
        if self.db_url:
            conn = self._pg_connect()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                class PseudoConn:
                    def execute(self, q, args=()):
                        q = q.replace("?", "%s")
                        q = q.replace("INSERT OR IGNORE", "INSERT")
                        # An upsert brings its own conflict clause — appending a
                        # second one would be a syntax error.
                        if "INSERT INTO observations" in q and "ON CONFLICT" not in q.upper():
                            q += " ON CONFLICT DO NOTHING"
                        # special SQLite date logic
                        q = q.replace("date(collection_date) <= date(%s)", "CAST(collection_date AS DATE) <= CAST(%s AS DATE)")
                        q = q.replace("date(collection_date) >= date(%s, '-' || %s || ' day')", "CAST(collection_date AS DATE) >= CAST(%s AS DATE) - CAST(%s || ' days' AS INTERVAL)")
                        q = q.replace("date(collection_date) >= date(%s)", "CAST(collection_date AS DATE) >= CAST(%s AS DATE)")
                        cur.execute(q, args)
                        return cur
                    def executemany(self, q, args_list):
                        q = q.replace("?", "%s")
                        q = q.replace("INSERT OR IGNORE", "INSERT")
                        if "INSERT INTO observations" in q and "ON CONFLICT" not in q.upper():
                            q += " ON CONFLICT DO NOTHING"
                        cur.executemany(q, args_list)
                        return cur
                    def commit(self): conn.commit()
                    def close(self): conn.close()
                    def executescript(self, q):
                        for stmt in q.split(";"):
                            if stmt.strip():
                                cur.execute(stmt)
                        return cur
                yield PseudoConn()
            conn.close()
        else:
            try:
                conn = sqlite3.connect(str(self.path), timeout=20.0, check_same_thread=False)
            except sqlite3.Error as exc:
                raise StoreConnectionError(f"SQLite store at {self.path} could not be opened: {exc}") from exc
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=20000")
                yield conn
            finally:
                conn.close()

    def _init(self) -> None:
        with self._write_lock, self._connect() as conn:
            schema = _SCHEMA
            if self.db_url:
                schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                conn.executescript(schema)
            else:
                conn.executescript(schema)
            
            cur = conn.execute("SELECT value FROM schema_meta WHERE key='version'")
            row = cur.fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta(key,value) VALUES('version',?)", (str(SCHEMA_VERSION),))
            conn.commit()

    def reset(self) -> None:
        with self._write_lock, self._connect() as conn:
            for t in ("collection_runs", "raw_payloads", "observations", "apix_state"):
                conn.execute(f"DELETE FROM {t}")  # noqa: S608
            conn.commit()

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM apix_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO apix_state(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value, _now()),
            )
            conn.commit()

    def begin_run(self, run_id: str, source: str, trigger: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO collection_runs(run_id,source,started_at,status,trigger) VALUES(?,?,?,?,?)",
                (run_id, source, _now(), "running", trigger),
            )
            conn.commit()

    def finish_run(self, run_id: str, **fields: Any) -> None:
        allowed = {
            "status", "error_kind", "detail", "queries", "requests", "observations",
            "valid_observations", "duplicates", "invalid", "suspicious", "failures",
            "avg_latency_ms",
        }
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        sets.append("finished_at=?")
        vals.append(_now())
        vals.append(run_id)
        with self._write_lock, self._connect() as conn:
            conn.execute(f"UPDATE collection_runs SET {', '.join(sets)} WHERE run_id=?", tuple(vals))
            conn.commit()

    def recent_runs(self, limit: int = 20, source: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM collection_runs"
        args: list[Any] = []
        if source:
            q += " WHERE source=?"
            args.append(source)
        q += " ORDER BY started_at DESC, id DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, tuple(args)).fetchall()
        out = []
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            d.pop("id", None)
            out.append(d)
        return out

    def last_run(self, source: Optional[str] = None) -> Optional[dict[str, Any]]:
        runs = self.recent_runs(limit=1, source=source)
        return runs[0] if runs else None

    def add_raw_payloads(self, run_id: str, offers: Iterable[Any]) -> int:
        rows = [
            (
                run_id, o.source, o.url, o.http_status, o.fetched_at or _now(), o.latency_ms,
                json.dumps(o.query or {}, ensure_ascii=False),
                json.dumps(o.payload, ensure_ascii=False, sort_keys=True),
                _sha(o.payload),
            )
            for o in offers
        ]
        if not rows:
            return 0
        if not self.available:
            return 0
        with self._write_lock, self._connect() as conn:
            conn.executemany(
                "INSERT INTO raw_payloads(run_id,source,url,http_status,fetched_at,latency_ms,"
                "query_json,payload_json,payload_sha) VALUES(?,?,?,?,?,?,?,?,?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def recent_payloads(self, limit: int = 50, source: Optional[str] = None, run_id: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM raw_payloads"
        cond, args = [], []
        if source:
            cond.append("source=?")
            args.append(source)
        if run_id:
            cond.append("run_id=?")
            args.append(run_id)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, tuple(args)).fetchall()
        out = []
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                d["payload"] = {}
            try:
                d["query"] = json.loads(d.pop("query_json") or "{}")
            except json.JSONDecodeError:
                d["query"] = {}
            out.append(d)
        return out

    def insert_observations(self, run_id: str, obs: list[dict[str, Any]]) -> int:
        if not obs:
            return 0
        now = _now()
        rows = []
        for o in obs:
            vals = [o.get(c) for c in OBS_COLUMNS]
            vals[0] = o["observation_id"]
            rows.append((run_id, *vals, 1 if o.get("in_basket", True) else 0, now))
        placeholders = ",".join(["?"] * (len(OBS_COLUMNS) + 3))
        cols = "run_id," + ",".join(OBS_COLUMNS) + ",in_basket,inserted_at"
        with self._write_lock, self._connect() as conn:
            if not self.db_url:
                conn.execute("BEGIN")
            cur = conn.executemany(
                f"INSERT OR IGNORE INTO observations({cols}) VALUES({placeholders})",
                rows,
            )
            conn.commit()
            return max(0, cur.rowcount)

    def delete_run_observations(self, run_id: str) -> int:
        """Remove the observations one import run wrote (before re-importing)."""
        if not run_id:
            return 0
        with self._write_lock, self._connect() as conn:
            if not self.db_url:
                conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM observations WHERE run_id=?", (run_id,))
            conn.commit()
            return max(0, cur.rowcount)

    def delete_superseded(self, previous_run_id: str, current_run_id: str) -> int:
        """Drop rows an earlier import wrote that this import did not refresh.

        Used when a file is re-uploaded: the new version's rows are upserted
        first (updating the ones that still exist), and whatever is left from the
        previous version — a corrected fare has a new id — is removed instead of
        lingering as a stale duplicate.
        """
        if not previous_run_id or previous_run_id == current_run_id:
            return 0
        with self._write_lock, self._connect() as conn:
            if not self.db_url:
                conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM observations WHERE run_id=? AND observation_id NOT IN "
                "(SELECT observation_id FROM observations WHERE run_id=?)",
                (previous_run_id, current_run_id),
            )
            conn.commit()
            return max(0, cur.rowcount)

    def upsert_observations(
        self,
        obs: list[dict[str, Any]],
        *,
        run_id: Optional[str] = None,
        conflict_key: str = "observation_id",
    ) -> dict[str, int]:
        """Insert-or-update canonical observations, keyed on ``observation_id``.

        This is the "import the same file twice and nothing duplicates" path:
        a row whose id already exists is *updated in place* (a re-uploaded or
        corrected fare), everything else is inserted. Works unchanged on
        PostgreSQL (Supabase) and SQLite, which share this schema.

        Returns ``{"inserted": n, "updated": m, "total": k}``.
        """
        if not obs:
            return {"inserted": 0, "updated": 0, "total": 0}
        if conflict_key not in OBS_COLUMNS:
            raise ValueError(f"conflict key must be one of {OBS_COLUMNS}, got {conflict_key!r}")

        now = _now()
        # One row per id: a batch that repeats an id (the same file imported
        # twice in one request) must write — and be counted — exactly once.
        deduped: dict[str, tuple] = {}
        for o in obs:
            key = o.get("observation_id")
            if not key:
                continue  # without an id there is nothing to de-duplicate on
            vals = [o.get(c) for c in OBS_COLUMNS]
            vals[0] = key
            deduped[key] = (run_id, *vals, 1 if o.get("in_basket", True) else 0, now)
        rows = list(deduped.values())
        if not rows:
            return {"inserted": 0, "updated": 0, "total": 0}

        cols = "run_id," + ",".join(OBS_COLUMNS) + ",in_basket,inserted_at"
        placeholders = ",".join(["?"] * (len(OBS_COLUMNS) + 3))
        # run_id is refreshed too: it marks the row as "touched by the latest
        # import", which is what lets delete_superseded() tell a refreshed row
        # from one the new version of a file no longer contains.
        updates = ",".join(
            f"{c}=excluded.{c}" for c in ("run_id", *OBS_COLUMNS[1:], "in_basket", "inserted_at")
        )

        with self._write_lock, self._connect() as conn:
            if not self.db_url:
                conn.execute("BEGIN")
            # Which ids are already there? That is what separates an insert from
            # an update, and it is what makes a re-import idempotent.
            existing: set[str] = set()
            ids = [r[1] for r in rows]  # rows[0] is run_id, rows[1] is observation_id
            for i in range(0, len(ids), 500):
                chunk = ids[i : i + 500]
                ph = ",".join(["?"] * len(chunk))
                found = conn.execute(
                    f"SELECT {conflict_key} FROM observations WHERE {conflict_key} IN ({ph})",
                    tuple(chunk),
                ).fetchall()
                existing.update(str(r[conflict_key]) for r in found)
            conn.executemany(
                f"INSERT INTO observations({cols}) VALUES({placeholders}) "
                f"ON CONFLICT({conflict_key}) DO UPDATE SET {updates}",
                rows,
            )
            conn.commit()

        updated = len(existing)
        return {"inserted": len(rows) - updated, "updated": updated, "total": len(rows)}

    def fingerprints_for_day(self, collection_date: str) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fingerprint FROM observations WHERE collection_date=?", (collection_date,)
            ).fetchall()
        return {r["fingerprint"] for r in rows if r["fingerprint"]}

    def route_median_levels(self, before_date: str, window_days: int = 7) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT route, total_fare FROM observations
                WHERE quality_status IN ('VALID','SUSPICIOUS')
                  AND date(collection_date) <= date(?)
                  AND date(collection_date) >= date(?, '-' || ? || ' day')
                """,
                (before_date, before_date, window_days),
            ).fetchall()
        buckets: dict[str, list[float]] = {}
        for r in rows:
            buckets.setdefault(r["route"], []).append(float(r["total_fare"]))
        out: dict[str, float] = {}
        for route, fares in buckets.items():
            fares.sort()
            n = len(fares)
            out[route] = fares[n // 2] if n % 2 else (fares[n // 2 - 1] + fares[n // 2]) / 2.0
        return out

    def all_observations(self, since: Optional[str] = None, include_excluded: bool = True) -> list[dict[str, Any]]:
        q = "SELECT * FROM observations"
        args: list[Any] = []
        cond = []
        if since:
            cond.append("date(collection_date) >= date(?)")
            args.append(since)
        if not include_excluded:
            cond.append("quality_status IN ('VALID','SUSPICIOUS')")
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY collection_date, id"
        with self._connect() as conn:
            rows = conn.execute(q, tuple(args)).fetchall()
        out = []
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            d.pop("id", None)
            d.pop("inserted_at", None)
            for f in ("base_fare", "taxes", "fees", "total_fare", "quality_score"):
                if d.get(f) is not None:
                    d[f] = round(float(d[f]), 2)
            out.append(d)
        return out

    def counts(self) -> dict[str, Any]:
        with self._connect() as conn:
            obs = conn.execute("SELECT COUNT(*) c FROM observations").fetchone()["c"]
            valid = conn.execute("SELECT COUNT(*) c FROM observations WHERE quality_status='VALID'").fetchone()["c"]
            raws = conn.execute("SELECT COUNT(*) c FROM raw_payloads").fetchone()["c"]
            runs = conn.execute("SELECT COUNT(*) c FROM collection_runs").fetchone()["c"]
            days = conn.execute("SELECT COUNT(DISTINCT collection_date) c FROM observations").fetchone()["c"]
            statuses = {
                r["quality_status"]: r["c"]
                for r in conn.execute(
                    "SELECT quality_status, COUNT(*) c FROM observations GROUP BY quality_status"
                ).fetchall()
            }
        size = self.path.stat().st_size if (self.path and self.path.exists()) else 0
        return {
            "observations": obs,
            "valid_observations": valid,
            "raw_payloads": raws,
            "runs": runs,
            "days_collected": days,
            "by_status": statuses,
            "db_bytes": size,
            "db_path": str(self.path) if self.path else self.backend,
            # Storage health, so the API/UI can say what the scraper can persist.
            "available": self.available,
            "backend": self.backend,
            "durable": self.durable,
            "ephemeral": self.ephemeral,
            "ignores_database_url": self.ignore_database_url,
            "unavailable_reason": self._unavailable_reason,
            "note": self.note,
        }

    def sources_seen(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT source FROM observations ORDER BY source").fetchall()
        return [r["source"] for r in rows]

def _sha(payload: Any) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

_store: Optional[Store] = None
_store_lock = threading.Lock()

def get_store() -> Store:
    global _store
    with _store_lock:
        if _store is None:
            _store = Store()
        else:
            # A store that failed for a transient reason gets another chance
            # (rate-limited inside) instead of staying dead for the process.
            _store.maybe_reconnect()
        return _store
