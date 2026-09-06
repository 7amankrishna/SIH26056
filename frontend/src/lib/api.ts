// Typed API client. All requests go to the Vite proxy (`/api/...`); no
// hard-coded origins. Errors are surfaced to React Query as exceptions.

import type {
  AirlineSummary,
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
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
    ...init,
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
  fares: (params?: { route?: string; airline?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.route) q.set("route", params.route);
    if (params?.airline) q.set("airline", params.airline);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.size ? `?${q.toString()}` : "";
    return request<FaresResponse>(`/fares${suffix}`);
  },
};
