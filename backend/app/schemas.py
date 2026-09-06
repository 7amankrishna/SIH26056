"""Strongly typed Pydantic response models for the APIx API contract.

Database/session models are never exposed directly — the frontend always
receives these validated, versioned shapes.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApxModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- health ----------------------------------------------------------------- #

class Health(ApxModel):
    status: str
    version: str
    title: str
    demo_mode: bool
    uptime_seconds: float
    timestamp: str
    period_start: str
    period_end: str


# --- overview --------------------------------------------------------------- #

class DataPeriod(ApxModel):
    start: str
    end: str


class Overview(ApxModel):
    current_apix: Optional[float]
    daily_change: Optional[float]
    weekly_change: Optional[float]
    monthly_change: Optional[float]
    observation_count: int
    valid_observation_count: int
    route_count: int
    airline_count: int
    source_count: int
    quality_score: float
    last_collection: str
    last_run_at: str
    index_freshness: str
    demo_mode: bool
    data_period: DataPeriod
    base_period: DataPeriod
    methodology_version: str
    weight_version: str


# --- trend ------------------------------------------------------------------ #

class TrendPoint(ApxModel):
    date: str
    apix: Optional[float]
    observations: int
    routes: int
    change: Optional[float] = None


class Trend(ApxModel):
    range: str
    base_period: DataPeriod
    current: Optional[float]
    change_7d: Optional[float]
    change_30d: Optional[float]
    methodology_version: str
    series: list[TrendPoint]


# --- routes ----------------------------------------------------------------- #

class RouteSummary(ApxModel):
    route: str
    origin: str
    destination: str
    origin_city: str
    destination_city: str
    current_fare: Optional[float]
    route_index: Optional[float]
    change_24h: Optional[float]
    change_7d: Optional[float]
    base_price: float
    weight: float
    observations: int
    quality: Optional[float]
    airlines: int
    sparkline: list[Optional[float]]


class RouteDetail(ApxModel):
    route: str
    origin: str
    destination: str
    origin_city: str
    destination_city: str
    distance_km: int
    base_price: float
    weight: float
    meta: RouteSummary
    series: list[dict[str, Any]]
    airlines: list[dict[str, Any]]


class RouteList(ApxModel):
    routes: list[RouteSummary]


class RouteHeatmap(ApxModel):
    routes: list[RouteSummary]


# --- airlines --------------------------------------------------------------- #

class AirlineSummary(ApxModel):
    airline: str
    name: str
    alliance: str
    hub: str
    avg_fare: Optional[float]
    median_fare: Optional[float]
    observations: int
    volatility: Optional[float]
    index_contribution: Optional[float]
    quality: Optional[float]
    availability: Optional[float]


class AirlineList(ApxModel):
    airlines: list[AirlineSummary]


# --- lead time -------------------------------------------------------------- #

class LeadTimePoint(ApxModel):
    lead_time_days: int
    label: str
    avg_fare: float
    median_fare: float
    observations: int


class LeadTime(ApxModel):
    as_of: str
    series: list[LeadTimePoint]
    elasticity: Optional[float]
    insight: Optional[str]
    routes: Optional[str]
    airline: Optional[str]
    source: Optional[str]


# --- distribution ----------------------------------------------------------- #

class HistogramBin(ApxModel):
    bin: str
    from_value: int = Field(alias="from")
    to: int
    count: int

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class FareDistribution(ApxModel):
    as_of: str
    route: Optional[str]
    observations: int
    currency: str
    p10: float
    p25: float
    median: float
    mean: float
    p75: float
    p90: float
    min: float
    max: float
    std_dev: float
    histogram: list[dict[str, Any]]


# --- quality ---------------------------------------------------------------- #

class QualityBreakdown(ApxModel):
    completeness: float
    consistency: float
    uniqueness: float
    freshness: float
    coverage: float
    outlier_rate: float


class Quality(ApxModel):
    score: float
    valid: int
    suspicious: int
    invalid: int
    duplicate: int
    sold_out: int
    stale: int
    missing: int
    total: int
    included: int
    breakdown: QualityBreakdown
    weighted_score: float


class RejectedObservation(ApxModel):
    observation_id: str
    source: str
    route: str
    departure_date: str
    collection_date: str
    airline: str
    lead_time_days: int
    total_fare: float
    quality_status: str
    quality_score: float
    exclusion_reason: Optional[str]


class Rejected(ApxModel):
    count: int
    rows: list[RejectedObservation]
    statuses: dict[str, int]


# --- collection ------------------------------------------------------------- #

class SourceRun(ApxModel):
    source: str
    name: str
    type: str
    status: str
    adapter: str
    compliance: str
    last_run: Optional[str]
    observations: int
    valid_observations: int
    success_rate: float
    failure_count: int
    avg_latency_ms: Optional[int]
    quotes: int


class CollectionSummary(ApxModel):
    active_sources: int
    healthy_sources: int
    degraded_sources: int
    disabled_sources: int
    ready_sources: int
    last_run: str
    collection_success_rate: float


class CollectionRuns(ApxModel):
    as_of: str
    sources: dict[str, SourceRun]
    summary: CollectionSummary


# --- methodology ------------------------------------------------------------ #

class MethodologyStep(ApxModel):
    step: int
    title: str
    detail: str


class Methodology(ApxModel):
    title: str
    version: str
    status: str
    steps: list[MethodologyStep]
    formula: str
    definitions: dict[str, str]
    base_period: DataPeriod
    weight_version: str
    disclaimer: str


# --- provenance ------------------------------------------------------------- #

class RouteContribution(ApxModel):
    route: str
    price: float
    base: float
    weight: float
    index: float
    contribution: float
    observations: int
    quality: float


class Provenance(ApxModel):
    index_date: str
    api_value: float
    methodology_version: str
    weight_version: str
    route_contributions: list[RouteContribution]


class StatsOverview(ApxModel):
    as_of: str
    recent_mean: Optional[float]
    prior_mean: Optional[float]
    mean_deviation: Optional[float]
    backtest: dict[str, Any]
