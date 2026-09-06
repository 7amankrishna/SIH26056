// Typed API client. All requests go to the Vite proxy (`/api/...`); no
// hard-coded origins. Errors are surfaced to React Query as exceptions.

import type {
  AirlineSummary,
  CollectFareRow,
  CollectStatus,
  CollectionPolicy,
  CollectionRun,
  DataSourceState,
  DataMode,
  RawPayloadRow,
  SweepAccepted,
  SweepResult,
  CollectionRuns,
  FareDistribution,
  FaresResponse,
  Health,
  LeadTime,
  Methodology,
  Overview,
  Provenance,
  Quality,
  RejectedObservation,
  RouteDetail,
  RouteSummary,
  StatsOverview,
  Trend,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Merge, never replace: POSTs need Content-Type while Accept stays on every
  // call so a JSON error body is returned by the API rather than an HTML 406.
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  overview: () => request<Overview>("/overview"),

  trend: (range: string) => request<Trend>(`/index/trend?range=${range}`),

  routes: (top?: number) => request<{ routes: RouteSummary[] }>(`/routes${top ? `?top=${top}` : ""}`),
  routeHeatmap: () => request<{ routes: RouteSummary[] }>("/routes/heatmap"),
  routeDetail: (route: string) =>
    request<RouteDetail>(`/index/route/${encodeURIComponent(route)}`),

  airlines: (route?: string) =>
    request<{ airlines: AirlineSummary[] }>(`/airlines${route ? `?route=${route}` : ""}`),

  leadTime: (params?: { route?: string; airline?: string; source?: string }) => {
    const q = new URLSearchParams();
    if (params?.route) q.set("route", params.route);
    if (params?.airline) q.set("airline", params.airline);
    if (params?.source) q.set("source", params.source);
    const suffix = q.size ? `?${q.toString()}` : "";
    return request<LeadTime>(`/index/lead-time${suffix}`);
  },

  fareDistribution: (route?: string) =>
    request<FareDistribution>(`/fares/distribution${route ? `?route=${route}` : ""}`),

  quality: () => request<Quality>("/quality"),
  qualityRejected: () => request<{ count: number; rows: RejectedObservation[]; statuses: Record<string, number> }>("/quality/rejected"),

  collectionRuns: () => request<CollectionRuns>("/collection-runs"),
  methodology: () => request<Methodology>("/methodology"),
  provenance: (indexId: string) =>
    request<Provenance>(`/provenance/${encodeURIComponent(indexId)}`),
  statsOverview: () => request<StatsOverview>("/stats/overview"),
  // ---- collection engine (scraper) -------------------------------------- //
  dataSource: () => request<DataSourceState>("/data-source"),
  setDataSource: (mode: DataMode) =>
    request<DataSourceState>("/data-source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),

  collectStatus: () => request<CollectStatus>("/collect/status"),
  collectPolicy: () => request<CollectionPolicy>("/collect/policy"),
  collectRuns: (limit = 20, source?: string) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (source) q.set("source", source);
    return request<{ count: number; runs: CollectionRun[] }>(`/collect/runs?${q}`);
  },
  collectPayloads: (params?: { limit?: number; source?: string; runId?: string }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.source) q.set("source", params.source);
    if (params?.runId) q.set("run_id", params.runId);
    const suffix = q.size ? `?${q}` : "";
    return request<{ count: number; rows: RawPayloadRow[] }>(`/collect/payloads${suffix}`);
  },
  collectFares: (params?: { limit?: number; route?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.route) q.set("route", params.route);
    if (params?.status) q.set("status", params.status);
    const suffix = q.size ? `?${q}` : "";
    return request<{ count: number; total: number; rows: CollectFareRow[] }>(`/collect/fares${suffix}`);
  },
  /** Runs the sweep inside this request and resolves with its result. */
  runSweep: (body?: { routes?: string[]; lead_times?: number[]; wait?: boolean }) =>
    request<SweepResult & SweepAccepted>("/collect/sweep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wait: true, ...body }),
    }),
  /**
   * Fire-and-forget variant for runtimes with a surviving background loop. On a
   * request-scoped runtime (Vercel) the backend ignores the distinction and runs
   * the sweep synchronously anyway, so callers must handle both shapes.
   */
  runSweepBackground: () =>
    request<SweepResult & SweepAccepted>("/collect/sweep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }),
  testSource: (id: string) =>
    request<{ source: string; ok: boolean; state: string; detail: string; latency_ms?: number }>(
      `/collect/sources/${encodeURIComponent(id)}/test`,
      { method: "POST" },
    ),

  fares: (params?: { route?: string; airline?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.route) q.set("route", params.route);
    if (params?.airline) q.set("airline", params.airline);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.size ? `?${q.toString()}` : "";
    return request<FaresResponse>(`/fares${suffix}`);
  },
};
