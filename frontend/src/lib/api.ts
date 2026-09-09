// Typed API client. All requests go to the Vite proxy (`/api/...`); no
// hard-coded origins. Errors are surfaced to React Query as exceptions.

import type {
  AirlineSummary,
  CollectStatus,
  CustomDataReport,
  DatabaseStatus,
  DataSourceState,
  PersistenceReport,
  UploadResponse,
  DataMode,
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
  RouteDetail,
  RouteSummary,
  StatsOverview,
  Trend,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Do not let an old browser response mask a fresh deployment/API error. The
  // app has no offline mode, so a no-store request is safer than serving a
  // stale JSON shape after a deploy.
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Cache-Control": "no-cache",
      ...(init?.headers ?? {}),
    },
  });
  // Test doubles and a few older proxies omit the header; successful responses
  // without a content type retain the historic JSON assumption.
  const contentType = res.headers?.get?.("content-type");
  const isJson = !contentType || contentType.includes("application/json");
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = isJson ? await res.json() : null;
      if (body?.detail) detail = body.detail;
      else if (!isJson) detail = `Request failed (${res.status}): the server returned an unexpected non-JSON response.`;
    } catch {
      /* preserve the useful HTTP status */
    }
    throw new Error(detail);
  }
  if (!isJson) {
    throw new Error("The API returned an unexpected non-JSON response. Reload the application to fetch the current deployment.");
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

  // ---- imported data (the user's own files) ----------------------------- //
  dataFiles: () => request<CustomDataReport>("/data/files"),
  reloadDataFiles: () =>
    request<CustomDataReport>("/data/reload", { method: "POST" }),
  /** Multipart upload — no JSON body, so the browser sets the boundary itself. */
  uploadDataFiles: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return request<UploadResponse>("/data/upload", { method: "POST", body: form });
  },
  deleteDataFile: (name: string) =>
    request<CustomDataReport>(`/data/files/${encodeURIComponent(name)}`, { method: "DELETE" }),
  /** Health of the durable store (Supabase/PostgreSQL) — never the DSN itself. */
  databaseStatus: () => request<DatabaseStatus>("/data/database"),
  persistDataFiles: (file?: string) =>
    request<PersistenceReport>(`/data/persist${file ? `?file=${encodeURIComponent(file)}` : ""}`, {
      method: "POST",
    }),
  /** Seed the deterministic built-in demo observations directly into the store. */
  persistDemoData: () => request<PersistenceReport>("/data/persist-demo", { method: "POST" }),

  methodology: () => request<Methodology>("/methodology"),
  collectionRuns: () => request<CollectionRuns>("/collection-runs"),
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
  fares: (params?: { route?: string; airline?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.route) q.set("route", params.route);
    if (params?.airline) q.set("airline", params.airline);
    if (params?.limit) q.set("limit", String(params.limit));
    const suffix = q.size ? `?${q.toString()}` : "";
    return request<FaresResponse>(`/fares${suffix}`);
  },
};
