"""SQLite and Postgres persistence for collected data.

Stdlib ``sqlite3`` on purpose for local: no service to provision, works on a laptop
offline. Postgres via psycopg2 (``DATABASE_URL``) for Vercel/production. Three tables:

    collection_runs   one row per sweep per source, incl. blocked/failed runs
    raw_payloads      the payload *exactly as received* (never rewritten)
    observations      the normalized canonical fare model, quality-flagged

Plus ``apix_state`` — a tiny KV table that persists the dashboard's data-source
toggle so the selection survives a restart.

Initialisation is **lazy**. A :class:`Store` is created while the app is being
imported (the ``collection_service`` singleton), and on Vercel a failure at import
time takes the whole function down — health checks, docs and the SPA included.
So ``Store.__init__`` does no I/O at all: the connection, the schema and the
``DATABASE_URL`` validation all happen in :meth:`Store._ensure_init` on first use.
"""

from __future__ import annotations

import os
import datetime as dt
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_IMPORT_ERROR: Optional[str] = None
except ImportError as _exc:  # pragma: no cover - depends on the environment
    psycopg2 = None
    _PSYCOPG2_IMPORT_ERROR = str(_exc)

from ..config import settings

SCHEMA_VERSION = 1


def _env_int(name: str, default: int) -> int:
    """Lenient int env parsing — a typo here must never break module import."""
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


#: Seconds psycopg2 waits for a TCP connection before giving up (libpq's
#: default is "forever", which on a serverless runtime means a hung request).
PG_CONNECT_TIMEOUT_SECONDS = _env_int("APIX_PG_CONNECT_TIMEOUT_SECONDS", 10)


# --------------------------------------------------------------------------- #
# DATABASE_URL handling
# --------------------------------------------------------------------------- #

class DatabaseConfigError(RuntimeError):
    """``DATABASE_URL`` is set to something that is not a usable Postgres DSN.

    Raised lazily (on first store access), never at import time, and always
    *before* the value reaches ``psycopg2`` so the message stays actionable.
    """


_PG_SCHEMES = {"postgres", "postgresql"}
# github.com / *.github.com / raw.githubusercontent.com / *.github.io ...
_GITHUB_HOST_RE = re.compile(r"^(?:[\w-]+\.)*(?:github\.com|githubusercontent\.com|github\.io)$", re.IGNORECASE)
# ... in any of the shapes people paste: https://, git@github.com:, ssh://, bare "github.com/…".
_GITHUB_RE = re.compile(
    r"(?:^|[/@.\s=])(?:github\.com|githubusercontent\.com|github\.io)(?=$|[/:?#])",
    re.IGNORECASE,
)
# libpq keyword/value form: "host=db.example.com dbname=apix user=…"
_KV_DSN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S")
_KV_HOST_RE = re.compile(r"\bhost(?:addr)?\s*=", re.IGNORECASE)
_KV_HOST_VALUE_RE = re.compile(r"\bhost\s*=\s*'?([^\s']+)", re.IGNORECASE)
_CONNECT_TIMEOUT_RE = re.compile(r"\bconnect_timeout\s*=", re.IGNORECASE)
_URL_PASSWORD_RE = re.compile(r"^([a-z][a-z0-9+.\-]*://[^/@]*?:)[^@]*@", re.IGNORECASE)
_KV_PASSWORD_RE = re.compile(r"(password\s*=\s*)\S+", re.IGNORECASE)
_ENV_LINE_PREFIX_RE = re.compile(r"^(?:export\s+)?DATABASE_URL\s*=\s*", re.IGNORECASE)

# Vercel's function bundle is read-only; /tmp is the only writable location.
_VERCEL_TMP_DIR = Path("/tmp/apix-data")

_DSN_EXAMPLE = "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
_VERCEL_HINT = (
    " On Vercel: Project -> Settings -> Environment Variables -> DATABASE_URL, then redeploy. "
    "Remove the variable to fall back to ephemeral SQLite under /tmp."
)
_LOCAL_HINT = " Unset DATABASE_URL to use the local SQLite store."


def _is_vercel() -> bool:
    """True inside a Vercel build or function (Vercel sets ``VERCEL=1``)."""
    return os.environ.get("VERCEL", "").strip().lower() in {"1", "true", "yes", "on"}


def _ensure_writable_dir(directory: Path) -> None:
    """Create ``directory`` if needed and prove it is writable (raises OSError)."""
    directory.mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK):
        raise PermissionError(f"{directory} is not writable")


def _redact(value: str, limit: int = 96) -> str:
    """Mask the password and cap the length so a bad DSN can be logged safely."""
    shown = _URL_PASSWORD_RE.sub(r"\1***@", value, count=1)
    shown = _KV_PASSWORD_RE.sub(r"\1***", shown)
    return shown if len(shown) <= limit else shown[: limit - 3] + "..."


def parse_database_url(raw: Optional[str], *, vercel: Optional[bool] = None) -> Optional[str]:
    """Validate ``DATABASE_URL`` and return the DSN to hand to psycopg2.

    Returns ``None`` when the variable is unset or blank (the store then uses
    SQLite). Raises :class:`DatabaseConfigError` — nothing else — for anything
    that is not recognisably a PostgreSQL connection string, so a bad value is
    never passed on to psycopg2. The classic mistake is pasting the repository's
    GitHub URL into the Vercel env var, which psycopg2 would otherwise report as
    an opaque ``invalid dsn: missing "="``.

    On Vercel (``vercel=True``, default: detected from ``VERCEL=1``) the error
    messages point at the project settings and a host is mandatory, since a
    serverless function has no local Postgres to fall back to.
    """
    if vercel is None:
        vercel = _is_vercel()
    if raw is None:
        return None
    value = raw.strip()
    # A value pasted from a .env file sometimes keeps its "KEY=" prefix or quotes.
    value = _ENV_LINE_PREFIX_RE.sub("", value, count=1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    if not value:
        return None

    hint = _VERCEL_HINT if vercel else _LOCAL_HINT
    shown = _redact(value)
    no_host = (
        f"DATABASE_URL has no host ({shown}). On Vercel there is no local Postgres: "
        f"the DSN must point at a managed database such as Neon or Supabase.{hint}"
    )

    github = DatabaseConfigError(
        f"DATABASE_URL looks like a GitHub URL ({shown}), not a PostgreSQL connection "
        f"string. GitHub is not a database host; set it to your Postgres DSN, "
        f"e.g. {_DSN_EXAMPLE}.{hint}"
    )

    if _KV_DSN_RE.match(value):
        # libpq keyword/value DSN ("host=… dbname=…") — psycopg2 accepts it as-is.
        m = _KV_HOST_VALUE_RE.search(value)
        if m and _GITHUB_HOST_RE.match(m.group(1)):
            raise github
        if vercel and not _KV_HOST_RE.search(value):
            raise DatabaseConfigError(no_host)
        return value

    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError as exc:
        raise DatabaseConfigError(
            f"DATABASE_URL could not be parsed ({shown}): {exc}. Expected {_DSN_EXAMPLE}.{hint}"
        ) from exc
    scheme = parts.scheme.lower()

    # The classic paste error. Check the host when we have a proper URL; for the
    # scp-like / scheme-less shapes fall back to scanning the whole string.
    if _GITHUB_HOST_RE.match(host) or (scheme not in _PG_SCHEMES and _GITHUB_RE.search(value)):
        raise github

    if scheme not in _PG_SCHEMES:
        what = f"scheme '{scheme}'" if scheme else "no URL scheme"
        raise DatabaseConfigError(
            f"DATABASE_URL must be a PostgreSQL connection string ({_DSN_EXAMPLE}); "
            f"got {what} ({shown}).{hint}"
        )
    if vercel and not host and not _KV_HOST_RE.search(parts.query):
        raise DatabaseConfigError(no_host)
    return value


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

class _PgConn:
    """Minimal ``sqlite3.Connection`` lookalike over a psycopg2 cursor.

    The store is written against SQLite's dialect; this rewrites the handful of
    constructs that differ so both backends share a single code path.
    """

    def __init__(self, conn: Any, cur: Any) -> None:
        self._conn = conn
        self._cur = cur

    @staticmethod
    def _translate(q: str) -> str:
        q = q.replace("?", "%s")
        q = q.replace("INSERT OR IGNORE", "INSERT")
        if "INSERT INTO observations" in q:
            q += " ON CONFLICT DO NOTHING"
        return q

    def execute(self, q: str, args: Any = ()) -> Any:
        q = self._translate(q)
        # SQLite date() arithmetic -> Postgres casts.
        q = q.replace(
            "date(collection_date) <= date(%s)",
            "CAST(collection_date AS DATE) <= CAST(%s AS DATE)",
        )
        q = q.replace(
            "date(collection_date) >= date(%s, '-' || %s || ' day')",
            "CAST(collection_date AS DATE) >= CAST(%s AS DATE) - CAST(%s || ' days' AS INTERVAL)",
        )
        q = q.replace(
            "date(collection_date) >= date(%s)",
            "CAST(collection_date AS DATE) >= CAST(%s AS DATE)",
        )
        self._cur.execute(q, args)
        return self._cur

    def executemany(self, q: str, args_list: Iterable[Any]) -> Any:
        self._cur.executemany(self._translate(q), args_list)
        return self._cur

    def executescript(self, q: str) -> Any:
        for stmt in q.split(";"):
            if stmt.strip():
                self._cur.execute(stmt)
        return self._cur

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class Store:
    """Persistence facade over SQLite (local) or Postgres (``DATABASE_URL``).

    Construction has **no side effects**: no directory is created, no connection
    is opened and ``DATABASE_URL`` is not even read until the first query. That
    keeps ``import app.main`` safe on Vercel, where a misconfigured database must
    surface as a clear error on the affected requests — not as a crashed function.

    An explicit ``path`` pins the store to that SQLite file even when
    ``DATABASE_URL`` is set, so a test run can never write to a real database.
    """

    def __init__(self, path: Optional[Path] = None):
        self._explicit_path: Optional[Path] = Path(path) if path is not None else None
        #: Resolved lazily by :meth:`_ensure_init`; exactly one of the two is set.
        self.db_url: Optional[str] = None
        self.path: Optional[Path] = None
        # RLock on purpose: see _ensure_init for why initialisation is re-entrant.
        self._init_lock = threading.RLock()
        self._initialized = False
        self._initializing = False
        self._write_lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        """True once the backend is resolved and the schema exists."""
        return self._initialized

    # ------------------------------------------------------------------ #
    # Lazy initialisation
    # ------------------------------------------------------------------ #
    def _ensure_init(self) -> None:
        """Resolve the backend and create the schema — once, on first use.

        Thread-safe (double-checked under ``_init_lock``) and retryable: if the
        database is misconfigured or unreachable the exception propagates to the
        caller, nothing is cached, and the next call simply tries again. The lock
        is an ``RLock`` so a re-entrant call from the initialising thread (anything
        that reaches ``_connect`` while the schema is being created) becomes a
        no-op instead of a deadlock or an infinite recursion.
        """
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized or self._initializing:
                return
            self._initializing = True
            try:
                self._resolve_backend()
                self._create_schema()
                self._initialized = True
            finally:
                self._initializing = False

    def _resolve_backend(self) -> None:
        """Pick Postgres or SQLite. Validates configuration, opens no connection."""
        if self._explicit_path is not None:
            self.db_url, self.path = None, self._explicit_path
        else:
            self.db_url = parse_database_url(os.environ.get("DATABASE_URL"))
            self.path = None if self.db_url else Path(settings.data_dir) / "apix.sqlite3"

        if self.db_url:
            if psycopg2 is None:
                raise DatabaseConfigError(
                    "DATABASE_URL is set but psycopg2 could not be imported "
                    f"({_PSYCOPG2_IMPORT_ERROR}). Add psycopg2-binary==2.9.10 to "
                    "api/requirements.txt (Vercel) and backend/requirements.txt, "
                    "or unset DATABASE_URL to use SQLite."
                )
        else:
            self.path = self._prepare_sqlite_path(self.path)

    def _prepare_sqlite_path(self, path: Path) -> Path:
        """Make sure the SQLite directory exists and is writable.

        Vercel's function bundle is read-only, so when the configured directory
        cannot be used there we fall back to ``/tmp`` (ephemeral, per instance)
        rather than failing every request. An explicit path is never redirected.
        """
        try:
            _ensure_writable_dir(path.parent)
            return path
        except OSError as exc:
            if self._explicit_path is not None or not _is_vercel():
                raise
            fallback = _VERCEL_TMP_DIR / path.name
            _ensure_writable_dir(fallback.parent)
            print(
                f"[apix] {path.parent} is not writable on Vercel ({exc}); using {fallback} "
                "(ephemeral). Set DATABASE_URL for durable storage."
            )
            return fallback

    def _create_schema(self) -> None:
        schema = _SCHEMA
        if self.db_url:
            schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        with self._open() as conn:
            conn.executescript(schema)
            row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta(key,value) VALUES('version',?)", (str(SCHEMA_VERSION),))
            conn.commit()

    # ------------------------------------------------------------------ #
    # Connections
    # ------------------------------------------------------------------ #
    def _pg_connect_kwargs(self) -> dict[str, Any]:
        # libpq waits forever by default; on a serverless runtime that turns an
        # unreachable database into a hung request. An explicit value in the DSN wins.
        if _CONNECT_TIMEOUT_RE.search(self.db_url or ""):
            return {}
        return {"connect_timeout": PG_CONNECT_TIMEOUT_SECONDS}

    @contextmanager
    def _open(self):
        """Open a raw connection to the resolved backend (no initialisation)."""
        if self.db_url:
            conn = psycopg2.connect(self.db_url, **self._pg_connect_kwargs())
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    yield _PgConn(conn, cur)
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(str(self.path), timeout=20.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=20000")
                yield conn
            finally:
                conn.close()

    @contextmanager
    def _connect(self):
        """Initialise on first use, then hand out a connection."""
        self._ensure_init()
        with self._open() as conn:
            yield conn

    # ------------------------------------------------------------------ #
    # Data access
    # ------------------------------------------------------------------ #
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
            "db_path": "postgres" if self.db_url else str(self.path),
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
    """Process-wide store singleton.

    Cheap and side-effect free: constructing a :class:`Store` touches neither the
    filesystem nor the network, so this is safe to call at import time. The
    backend is initialised lazily on the first query.
    """
    global _store
    with _store_lock:
        if _store is None:
            _store = Store()
        return _store
