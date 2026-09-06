// Typed shapes mirroring the FastAPI Pydantic response models.

export interface Health {
  status: string;
  version: string;
  title: string;
  demo_mode: boolean;
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

export interface RejectedObservation {
  observation_id: string;
  source: string;
  route: string;
  departure_date: string;
  collection_date: string;
  airline: string;
  lead_time_days: number;
  total_fare: number;
  quality_status: string;
  quality_score: number;
  exclusion_reason: string | null;
}

export interface CollectionRuns {
  as_of: string;
  sources: Record<
    string,
    {
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
    }
  >;
  summary: {
    active_sources: number;
    healthy_sources: number;
    degraded_sources: number;
    disabled_sources: number;
    ready_sources: number;
    last_run: string;
    collection_success_rate: number;
  };
}

export interface Methodology {
  title: string;
  version: string;
  status: string;
  steps: { step: number; title: string; detail: string }[];
  formula: string;
  definitions: Record<string, string>;
  base_period: { start: string; end: string };
  weight_version: string;
  disclaimer: string;
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
