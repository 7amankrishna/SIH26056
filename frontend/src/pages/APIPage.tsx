// API / Data Access — documented, typed endpoints for external statistical consumers.

import { ExternalLink, FileJson } from "lucide-react";
import { useHealth } from "../hooks/useApi";
import { usePageTitle } from "../hooks/usePageTitle";
import { formatDateTime } from "../lib/format";

const ENDPOINTS: { method: string; path: string; desc: string }[] = [
  { method: "GET", path: "/api/health", desc: "Liveness probe, version, demo mode and data window." },
  { method: "GET", path: "/api/overview", desc: "Headline KPI envelope: current APIx, 24h/7d/30d movement, coverage and freshness." },
  { method: "GET", path: "/api/index", desc: "Current index value (same envelope as overview)." },
  { method: "GET", path: "/api/index/trend?range=90d", desc: "Time-series of APIx with observations and route coverage per day." },
  { method: "GET", path: "/api/index/route/{route}", desc: "Route-level index, series and airline breakdown." },
  { method: "GET", path: "/api/index/airline/{airline}", desc: "Airline index contribution." },
  { method: "GET", path: "/api/index/lead-time", desc: "Lead-time elasticity bucket analysis (filters: route, airline, source)." },
  { method: "GET", path: "/api/routes", desc: "All routes ordered by 7-day movement with sparkline data." },
  { method: "GET", path: "/api/routes/heatmap", desc: "Same route data for the matrix heatmap." },
  { method: "GET", path: "/api/airlines", desc: "Airline comparison on observed & index metrics." },
  { method: "GET", path: "/api/fares", desc: "Recent canonical fare observations (auditor drill-down)." },
  { method: "GET", path: "/api/fares/distribution", desc: "Fare percentiles and histogram for the current day." },
  { method: "GET", path: "/api/quality", desc: "Quality score, breakdown and status counts." },
  { method: "GET", path: "/api/quality/rejected", desc: "Rejected/suspicious observations for audit." },
  { method: "GET", path: "/api/data/files", desc: "Imported-file parse report plus safe upload-storage diagnostics." },
  { method: "POST", path: "/api/data/upload", desc: "Upload CSV, JSON or Excel fare exports (multipart field: files)." },
  { method: "GET", path: "/api/data/database", desc: "Safe database capability and observation-count report; never exposes the DSN." },
  { method: "POST", path: "/api/data/persist", desc: "Idempotently upsert the active imported data into the configured store." },
  { method: "POST", path: "/api/data/persist-demo", desc: "Idempotently seed the deterministic built-in demo observations." },
  { method: "GET", path: "/api/collection-runs", desc: "Per-source collection health and compliance state." },
  { method: "GET", path: "/api/collect/status", desc: "Collection engine state: mode, store health, scheduler and circuit breakers." },
  { method: "GET", path: "/api/collect/runs", desc: "Per-sweep run log, blocked and failed runs included (audit)." },
  { method: "GET", path: "/api/collect/payloads", desc: "Raw source payloads exactly as received (audit)." },
  { method: "GET", path: "/api/collect/fares", desc: "Normalized collected fare observations with quality status." },
  { method: "POST", path: "/api/collect/sweep", desc: "Trigger a collection sweep programmatically." },
  { method: "GET", path: "/api/methodology", desc: "Methodological framework, formula and definitions." },
  { method: "GET", path: "/api/provenance/{index_id}", desc: "Trace a given index value to contributing routes and observations." },
  { method: "GET", path: "/api/stats/overview", desc: "Validation / backtest summary relative to prior period." },
];

export default function APIPage() {
  usePageTitle("API / Data Access");
  const { data: health } = useHealth();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">API / Data Access</h2>
        <p className="text-sm text-ink-500">A typed, documented REST contract usable by external statistical consumers.</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="card p-4">
          <div className="text-[11px] uppercase tracking-wide text-ink-500">Base URL</div>
          <div className="mt-1 font-mono text-sm text-ink-800">/api</div>
        </div>
        <div className="card p-4">
          <div className="text-[11px] uppercase tracking-wide text-ink-500">Interactive docs</div>
          <a href="/docs" target="_blank" className="mt-1 inline-flex items-center gap-1.5 font-mono text-sm text-brand-700 hover:underline">
            <ExternalLink className="h-3.5 w-3.5" /> /docs
          </a>
        </div>
        <div className="card p-4">
          <div className="text-[11px] uppercase tracking-wide text-ink-500">Version</div>
          <div className="mt-1 font-mono text-sm text-ink-800">{health?.version ?? "0.1.0"} {health?.demo_mode ? "· demo" : ""}</div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3.5">
          <h3 className="text-sm font-semibold text-ink-800">Endpoints</h3>
          <span className="text-xs text-ink-500">{ENDPOINTS.length} endpoints · JSON responses · no auth required (demo)</span>
        </div>
        <div className="divide-y divide-ink-100/70">
          {ENDPOINTS.map((e) => (
            <div key={e.path} className="flex flex-col gap-1 px-5 py-3 sm:flex-row sm:items-center sm:gap-4">
              <span className="shrink-0 rounded bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-700">{e.method}</span>
              <code className="shrink-0 font-mono text-sm text-ink-800">{e.path}</code>
              <span className="text-sm text-ink-500">{e.desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-sky-100 bg-sky-50 p-4">
        <div className="flex items-start gap-3">
          <FileJson className="mt-0.5 h-5 w-5 shrink-0 text-sky-600" />
          <p className="text-sm text-sky-800">
            All responses are validated against strongly typed Pydantic models — database/session models are never
            exposed directly. Every index response carries <code className="rounded bg-sky-100 px-1">methodology_version</code> and
            <code className="rounded bg-sky-100 px-1"> weight_version</code> so an auditor can reproduce the exact calculation.
            Parameters and error states are documented in the OpenAPI schema.
          </p>
        </div>
      </div>

      {health && (
        <div className="card p-4 text-xs text-ink-500">
          Service: {health.title} · uptime {Math.round(health.uptime_seconds)}s · data window {health.period_start} → {health.period_end} · last health check {formatDateTime(new Date().toISOString())}
        </div>
      )}
    </div>
  );
}
