// Typed shapes mirroring the FastAPI Pydantic response models.

export interface Health {
  status: string;
  version: string;
  title: string;
  demo_mode: boolean;
  data_origin?: "live" | "demo";
  collector_running?: boolean;
  uptime_seconds: number;
  timestamp: string;
  period_start: string;
  period_end: string;
}

export interface Overview {
  current_apix: number | null;
  daily_change: number | null;
  weekly_change: number | null;
  monthly_change: number | null;
  observation_count: number;
  valid_observation_count: number;
  route_count: number;
  airline_count: number;
  source_count: number;
  quality_score: number;
  last_collection: string;
  last_run_at: string;
  index_freshness: string;
  demo_mode: boolean;
  /** Which dataset the API served: 'live' = scraped, 'demo' = synthetic. */
  data_origin?: "live" | "demo";
  live_sources?: string[];
  days_collected?: number;
  routes_with_data?: number;
  data_period: { start: string; end: string };
  base_period: { start: string; end: string };
  methodology_version: string;
  weight_version: string;
}

export interface TrendPoint {
  date: string;
  apix: number | null;
  observations: number;
  routes: number;
  change?: number | null;
}

export interface Trend {
  range: string;
  current: number | null;
  change_7d: number | null;
  change_30d: number | null;
  base_period: { start: string; end: string };
  methodology_version: string;
  series: TrendPoint[];
}

export interface RouteSummary {
  route: string;
  origin: string;
  destination: string;
  origin_city: string;
  destination_city: string;
  current_fare: number | null;
  route_index: number | null;
  change_24h: number | null;
  change_7d: number | null;
  base_price: number;
  weight: number;
  observations: number;
  quality: number | null;
  airlines: number;
  sparkline: (number | null)[];
}

export interface RouteDetail {
  route: string;
  origin: string;
  destination: string;
  origin_city: string;
  destination_city: string;
  distance_km: number;
  base_price: number;
  weight: number;
  meta: RouteSummary;
  series: {
    date: string;
    route_index: number;
    price: number;
    observations: number;
    change?: number | null;
  }[];
  airlines: { airline: string; name: string; avg_fare: number; median_fare: number; observations: number }[];
}

export interface AirlineSummary {
  airline: string;
  name: string;
  alliance: string;
  hub: string;
  avg_fare: number | null;
  median_fare: number | null;
  observations: number;
  volatility: number | null;
  index_contribution: number | null;
  quality: number | null;
  availability: number | null;
}

export interface LeadTime {
  as_of: string;
  series: { lead_time_days: number; label: string; avg_fare: number; median_fare: number; observations: number }[];
  elasticity: number | null;
  insight: string | null;
  routes?: string | null;
  airline?: string | null;
  source?: string | null;
}

export interface FareDistribution {
  as_of: string;
  route: string | null;
  observations: number;
  currency: string;
  p10: number;
  p25: number;
  median: number;
  mean: number;
  p75: number;
  p90: number;
  min: number;
  max: number;
  std_dev: number;
  histogram: { bin: string; from: number; to: number; count: number }[];
}

export interface Quality {
  score: number;
  valid: number;
  suspicious: number;
  invalid: number;
  duplicate: number;
  sold_out: number;
  stale: number;
  missing: number;
  total: number;
  included: number;
  breakdown: {
    completeness: number;
    consistency: number;
    uniqueness: number;
    freshness: number;
    coverage: number;
    outlier_rate: number;
  };
  weighted_score: number;
}

export interface SourceRun {
  source: string;
  name: string;
  type: string;
  status: string;
  adapter: string;
  compliance: string;
  last_run: string | null;
  observations: number;
  valid_observations: number;
  success_rate: number;
  failure_count: number;
  avg_latency_ms: number | null;
  quotes: number;
  /** live mode only — real breaker + failure state from the SQLite run log */
  circuit_open?: boolean;
  cooldown_seconds_left?: number;
  consecutive_failures?: number;
  last_error?: string | null;
  compliance_note?: string;
  recent_runs?: CollectionRun[];
}

export interface CollectionRuns {
  as_of: string;
  sources: Record<string, SourceRun>;
  summary: {
    active_sources: number;
    healthy_sources: number;
    degraded_sources: number;
    disabled_sources: number;
    ready_sources: number;
    last_run: string;
    collection_success_rate: number;
  };
  /** live mode only — the full run log, blocked/failed rows included */
  runs?: CollectionRun[];
}

export interface Provenance {
  index_date: string;
  api_value: number;
  methodology_version: string;
  weight_version: string;
  route_contributions: {
    route: string;
    price: number;
    base: number;
    weight: number;
    index: number;
    contribution: number;
    observations: number;
    quality: number;
  }[];
}

export interface StatsOverview {
  as_of: string;
  recent_mean: number | null;
  prior_mean: number | null;
  mean_deviation: number | null;
  backtest: {
    status: string;
    metrics: { mae: number; correlation: number };
    note: string;
  };
}

export interface FaresResponse {
  count: number;
  rows: {
    observation_id: string;
    departure_date: string;
    route: string;
    airline: string;
    lead_time_days: number;
    total_fare: number;
    quality_status: string;
  }[];
}

// --------------------------------------------------------------------------- //
// Collection engine (scraper) — data-source mode, runs, raw feed
// --------------------------------------------------------------------------- //

export type DataMode = "live" | "demo";

export interface StoreCounts {
  observations: number;
  valid_observations: number;
  raw_payloads: number;
  runs: number;
  days_collected: number;
  by_status: Record<string, number>;
  db_bytes: number;
  db_path?: string;
  /** false when no database could be configured: the scraper cannot persist anything. */
  available?: boolean;
  backend?: "sqlite" | "postgresql" | "unavailable" | string;
  /** true only for PostgreSQL — SQLite on a serverless runtime dies with the instance. */
  durable?: boolean;
  ephemeral?: boolean;
  /** DATABASE_URL is intentionally ignored; defaults to true for the Vercel demo. */
  ignores_database_url?: boolean;
  unavailable_reason?: string | null;
  /** Human-readable storage caveat, safe to show verbatim. */
  note?: string | null;
}

export interface DataSourceState {
  mode: DataMode;
  /** What the API is *actually* serving; 'demo' when live was asked for but nothing is collected yet. */
  effective_mode: DataMode;
  has_live_data: boolean;
  /** true when APIX_DATA_MODE pins the source and the toggle is inert */
  locked?: boolean;
  collector_enabled: boolean;
  background_running: boolean;
  /** No loop survives between requests (serverless): a sweep runs inside the POST. */
  request_scoped_sweeps?: boolean;
  store: StoreCounts;
  store_note?: string | null;
  sources: string[];
  note?: string | null;
  updated_at?: string | null;
}

export interface CollectionRun {
  run_id: string;
  source: string;
  started_at: string;
  finished_at?: string | null;
  status: "running" | "success" | "partial" | "blocked" | "failed";
  error_kind?: string | null;
  detail?: string | null;
  queries: number;
  requests: number;
  observations: number;
  valid_observations: number;
  duplicates: number;
  invalid: number;
  suspicious: number;
  failures: number;
  avg_latency_ms?: number | null;
  trigger: string;
}

export interface CollectorSource {
  id: string;
  name: string;
  type: string;
  status: string;
  adapter: string;
  compliance: string;
  compliance_note?: string;
  base_url?: string;
  requires_credentials?: boolean;
  robots_gated?: boolean;
  user_agent?: string;
  last_run?: CollectionRun | null;
  circuit_open?: boolean;
  cooldown_seconds_left?: number;
  consecutive_failures?: number;
  last_error?: string | null;
  last_error_kind?: string | null;
  observations?: number;
}

export interface CollectStatus {
  mode: DataMode;
  mode_locked?: boolean;
  effective_mode: DataMode;
  collector_enabled: boolean;
  background_running: boolean;
  request_scoped_sweeps?: boolean;
  request_sweep_query_cap?: number | null;
  store_note?: string | null;
  store_available?: boolean;
  sweep_interval_seconds: number;
  current_run?: Record<string, unknown> | null;
  store: StoreCounts;
  sources: CollectorSource[];
  queries_per_sweep: number;
  lead_times: number[];
  politeness: {
    min_gap_seconds: number;
    max_retries: number;
    backoff_base_seconds: number;
    max_requests_per_sweep: number;
    user_agent: string;
    robots_fail_closed: boolean;
  };
  last_sweep_error?: string | null;
}

export interface SweepResult {
  run_id: string;
  started_at: string;
  finished_at?: string;
  observations: number;
  valid_observations: number;
  requests: number;
  duration_ms: number;
  error?: string | null;
  /** Set when the sweep had to be shortened to fit inside one request. */
  note?: string | null;
  /** true when the backend ran the sweep inside this request instead of queueing it. */
  synchronous?: boolean;
  sources: Record<string, { status: string; detail?: string; observations?: number; queries?: number }>;
}

/** Shape returned when a sweep is queued for the background loop instead. */
export interface SweepAccepted {
  accepted?: boolean;
  synchronous?: boolean;
  detail?: string;
}
