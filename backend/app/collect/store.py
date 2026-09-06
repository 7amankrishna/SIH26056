"""SQLite and Postgres persistence for collected data.

Stdlib ``sqlite3`` on purpose for local: no service to provision, works on a laptop
offline. Postgres via psycopg2 for Vercel/production. Three tables:

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
except ImportError:
    psycopg2 = None

from ..config import settings

SCHEMA_VERSION = 1


class StoreConfigurationError(RuntimeError):
    """Raised when the deployment database configuration is unsafe or unusable."""


def _production_environment() -> bool:
    """Detect hosted production contexts without importing application settings."""
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        return True
    return any(
        os.getenv(name, "").strip().lower() in {"production", "prod"}
        for name in ("APIX_ENV", "APP_ENV", "ENVIRONMENT", "PYTHON_ENV")
    )


def validate_database_url(value: str) -> str:
    """Validate a psycopg2 connection URI or keyword DSN without exposing it."""
    database_url = value.strip()
    if not database_url:
        raise StoreConfigurationError("DATABASE_URL must not be empty.")

    if "://" in database_url:
        parsed = urlsplit(database_url)
        if parsed.scheme.lower() not in {"postgres", "postgresql"}:
            raise StoreConfigurationError(
                "DATABASE_URL must be a PostgreSQL connection URL."
            )
        if not parsed.netloc and not parsed.path:
            raise StoreConfigurationError("DATABASE_URL is not a valid PostgreSQL URL.")
        return database_url

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
        raise StoreConfigurationError("DATABASE_URL is not a valid PostgreSQL DSN.") from exc
    if not parsed_dsn.get("dbname") and not parsed_dsn.get("service"):
        raise StoreConfigurationError("DATABASE_URL DSN must specify a database.")
    return database_url

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

class Store:
    def __init__(self, path: Optional[Path] = None):
        configured_url = os.environ.get("DATABASE_URL", "").strip()
        if configured_url:
            self.db_url = validate_database_url(configured_url)
            self.backend = "postgresql"
        elif _production_environment():
            raise StoreConfigurationError(
                "DATABASE_URL is required in production; SQLite is local-development only."
            )
        else:
            self.db_url = None
            self.backend = "sqlite"
        if self.db_url:
            if not psycopg2:
                raise StoreConfigurationError(
                    "DATABASE_URL is configured but psycopg2-binary is not installed."
                )
            self.path = None
        else:
            self.path = Path(path or settings.data_dir / "apix.sqlite3")
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init()

    @contextmanager
    def _connect(self):
        if self.db_url:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                class PseudoConn:
                    def execute(self, q, args=()):
                        q = q.replace("?", "%s")
                        q = q.replace("INSERT OR IGNORE", "INSERT")
                        if "INSERT INTO observations" in q:
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
                        if "INSERT INTO observations" in q:
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
            conn = sqlite3.connect(str(self.path), timeout=20.0, check_same_thread=False)
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
            "db_path": str(self.path) if self.path else "postgres",
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
        return _store
