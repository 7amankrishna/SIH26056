-- ============================================================================
--  APIx — collection store schema for Supabase (PostgreSQL)
--  SIH26056 · MoSPI · Real-Time Airfare Price Index for India
-- ----------------------------------------------------------------------------
--  HOW TO USE (no terminal needed)
--    1. Supabase dashboard → your project → "SQL Editor" (left sidebar).
--    2. Click "New query", paste this whole file, press "Run".
--    3. You should see "Success. No rows returned".
--  That's it. The backend creates any missing table on boot too, but running
--  this once gives you the explicit, reviewed version — with row-level security
--  turned on and comments a statistical reviewer can read.
--
--  Safe to run more than once: everything below is IF NOT EXISTS / idempotent.
--
--  WHAT THESE TABLES ARE
--    collection_runs   one row per sweep per source — including blocked and
--                      failed runs (a source that stopped is never hidden)
--    raw_payloads      the response body exactly as received, byte for byte
--    observations      the normalized canonical fare model, quality-flagged
--    apix_state        tiny key/value table (persists the Demo ↔ Scraper toggle)
--    schema_meta       schema version stamp
--
--  WHY DATES ARE TEXT
--    The collector writes ISO-8601 strings ("2026-09-07", "...T01:19:27+05:30")
--    and every query casts them with CAST(x AS DATE) when it needs date maths.
--    Fixed-offset ISO strings sort chronologically as plain text, which keeps one
--    code path for SQLite (local/offline demo) and PostgreSQL (deployed).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Schema version stamp
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO public.schema_meta (key, value)
VALUES ('version', '1')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Collection runs — the run log (audit trail of every sweep)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.collection_runs (
    id                 SERIAL PRIMARY KEY,
    run_id             TEXT NOT NULL,
    source             TEXT NOT NULL,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    status             TEXT NOT NULL,   -- running | success | partial | blocked | failed
    error_kind         TEXT,            -- blocked | robots_denied | network | parse | ceiling | timeout
    detail             TEXT,
    queries            INTEGER DEFAULT 0,
    requests           INTEGER DEFAULT 0,
    observations       INTEGER DEFAULT 0,
    valid_observations INTEGER DEFAULT 0,
    duplicates         INTEGER DEFAULT 0,
    invalid            INTEGER DEFAULT 0,
    suspicious         INTEGER DEFAULT 0,
    failures           INTEGER DEFAULT 0,
    avg_latency_ms     INTEGER,
    trigger            TEXT DEFAULT 'scheduled'  -- scheduled | manual | startup | mode-switch
);

CREATE INDEX IF NOT EXISTS ix_runs_source_started ON public.collection_runs (source, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_started        ON public.collection_runs (started_at DESC);

COMMENT ON TABLE  public.collection_runs            IS 'One row per collection sweep per source, including blocked and failed runs.';
COMMENT ON COLUMN public.collection_runs.status     IS 'success | partial | blocked | failed | running. A blocked source is recorded as blocked, never as healthy.';
COMMENT ON COLUMN public.collection_runs.trigger    IS 'What started the sweep: scheduled loop, manual API call, app startup, or the dashboard switching to live mode.';

-- ---------------------------------------------------------------------------
-- 3. Raw payloads — the bytes exactly as received (never rewritten)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.raw_payloads (
    id           SERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL,
    source       TEXT NOT NULL,
    url          TEXT NOT NULL,
    http_status  INTEGER,
    fetched_at   TEXT NOT NULL,
    latency_ms   INTEGER,
    query_json   TEXT,                  -- the query that produced this response
    payload_json TEXT NOT NULL,         -- the offer/response as parsed JSON, verbatim fields
    payload_sha  TEXT                   -- sha256 prefix, so tampering is detectable
);

CREATE INDEX IF NOT EXISTS ix_raw_run    ON public.raw_payloads (run_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS ix_raw_source ON public.raw_payloads (source, fetched_at DESC);

COMMENT ON TABLE  public.raw_payloads              IS 'Every collected response, archived verbatim before parsing — the "as collected" audit view.';
COMMENT ON COLUMN public.raw_payloads.payload_json IS 'Stored as received. Never normalized here; normalization lives in observations.';

-- ---------------------------------------------------------------------------
-- 4. Observations — the canonical fare model, quality-gated
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.observations (
    id                    SERIAL PRIMARY KEY,
    observation_id        TEXT NOT NULL UNIQUE,
    run_id                TEXT,
    source                TEXT,
    origin                TEXT,                  -- IATA, e.g. DEL
    destination           TEXT,                  -- IATA, e.g. BOM
    route                 TEXT,                  -- ORIGIN-DEST
    departure_date        TEXT,                  -- YYYY-MM-DD
    collection_date       TEXT,                  -- YYYY-MM-DD (the day the price was seen)
    collection_timestamp  TEXT,                  -- ISO-8601 with +05:30 offset
    airline               TEXT,                  -- IATA carrier code, e.g. 6E
    flight_number         TEXT,
    cabin                 TEXT,                  -- ECONOMY | PREMIUM_ECONOMY | BUSINESS | FIRST
    fare_class            TEXT,                  -- booking class letter, e.g. M
    lead_time_days        INTEGER,               -- departure_date - collection_date
    base_fare             DOUBLE PRECISION,
    taxes                 DOUBLE PRECISION,
    fees                  DOUBLE PRECISION,
    total_fare            DOUBLE PRECISION,      -- INR unless currency says otherwise
    currency              TEXT DEFAULT 'INR',
    availability          TEXT,                  -- AVAILABLE | LIMITED | SOLD_OUT
    seats_remaining       INTEGER,
    raw_payload_reference TEXT,                  -- link back into raw_payloads
    fingerprint           TEXT,                  -- duplicate detection key
    quality_status        TEXT,                  -- VALID | SUSPICIOUS | DUPLICATE | INVALID | SOLD_OUT | STALE
    quality_score         DOUBLE PRECISION,
    exclusion_reason      TEXT,                  -- why it was not allowed into the index
    in_basket             INTEGER DEFAULT 1,     -- 1 = route is part of the index basket
    inserted_at           TEXT NOT NULL
);

-- The indexes the analytical queries actually use.
CREATE INDEX IF NOT EXISTS ix_obs_day        ON public.observations (collection_date, route, quality_status);
CREATE INDEX IF NOT EXISTS ix_obs_route_date ON public.observations (route, collection_date);
CREATE INDEX IF NOT EXISTS ix_obs_fp_day     ON public.observations (fingerprint, collection_date);
CREATE INDEX IF NOT EXISTS ix_obs_source     ON public.observations (source, collection_date);
-- Recommended by docs/DEPLOYMENT.md for larger histories.
CREATE INDEX IF NOT EXISTS ix_obs_airline    ON public.observations (airline, collection_date);
CREATE INDEX IF NOT EXISTS ix_obs_lead       ON public.observations (lead_time_days);
CREATE INDEX IF NOT EXISTS ix_obs_departure  ON public.observations (departure_date);

COMMENT ON TABLE  public.observations                  IS 'Normalized airfare observations: one row per fare quote that passed (or was explicitly rejected by) the quality gate.';
COMMENT ON COLUMN public.observations.quality_status   IS 'VALID and SUSPICIOUS feed the index; DUPLICATE / INVALID / SOLD_OUT / STALE are kept for audit but excluded.';
COMMENT ON COLUMN public.observations.lead_time_days   IS 'Advance-booking window in days (T+n) — the elasticity curve is built from this.';
COMMENT ON COLUMN public.observations.total_fare       IS 'base_fare + taxes + fees as observed, in the currency column (INR for the basket).';

-- ---------------------------------------------------------------------------
-- 5. apix_state — persisted dashboard state (the Demo ↔ Scraper toggle)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.apix_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

COMMENT ON TABLE public.apix_state IS 'Key/value app state. "data_mode" = demo | live: which dataset the dashboard is served from.';

-- ---------------------------------------------------------------------------
-- 6. Row-level security
-- ----------------------------------------------------------------------------
-- Supabase exposes every table in the public schema through its auto-generated
-- REST API. With RLS enabled and no policy for the anonymous keys, nobody can
-- read or write these tables with the anon/service key from a browser.
--
-- The policy must name the role the BACKEND logs in as, and that is not always
-- literally `postgres`: today's Supabase connection strings use the per-project
-- role `postgres.<project-ref>`. A policy scoped to `postgres` alone leaves
-- that role with RLS and no policy, which fails in the worst possible way —
-- INSERTs raise "new row violates row-level security policy" and SELECTs
-- silently return zero rows, i.e. "the database is connected but empty".
-- So: one policy per candidate backend role, discovered at run time. Anonymous
-- roles still get nothing, which is the point of keeping RLS on.
-- ---------------------------------------------------------------------------
ALTER TABLE public.collection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.raw_payloads    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observations    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.apix_state      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_meta     ENABLE ROW LEVEL SECURITY;

-- One policy per candidate backend login role: `postgres` (the classic
-- Supabase role) and `postgres.<project-ref>` (what current connection strings
-- use). Re-running this file is safe — each policy is dropped before it is
-- re-created. Roles that are not a backend login (`anon`, `authenticated`)
-- get no policy at all, so the browser-facing REST keys still see nothing.
DO $$
DECLARE
  t text;
  r text;
  policy_name text;
BEGIN
  FOREACH t IN ARRAY ARRAY['collection_runs','raw_payloads','observations','apix_state','schema_meta']
  LOOP
    -- Policy name used by earlier versions of this file.
    EXECUTE format('DROP POLICY IF EXISTS "apix backend full access" ON public.%I', t);

    FOR r IN SELECT rolname FROM pg_roles
             WHERE rolname = 'postgres' OR rolname LIKE 'postgres.%'
    LOOP
      policy_name := 'apix backend access: ' || r;
      EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy_name, t);
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR ALL TO %I USING (true) WITH CHECK (true)',
        policy_name, t, r
      );
    END LOOP;
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 7. Verify — run this after a sweep and you should see numbers, not zeros
-- ---------------------------------------------------------------------------
-- SELECT
--   (SELECT count(*) FROM public.observations)     AS observations,
--   (SELECT count(*) FROM public.raw_payloads)     AS raw_payloads,
--   (SELECT count(*) FROM public.collection_runs)  AS runs,
--   (SELECT count(DISTINCT collection_date) FROM public.observations) AS days_collected;
