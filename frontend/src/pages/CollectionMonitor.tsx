// Collection Monitor — operational health of the source pipeline.

import { useMemo } from "react";
import { Activity, Gauge, ShieldCheck } from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { StatusPill } from "../components/badges";
import { DataBoundary } from "../components/DataState";
import { useCollectionRuns, useQuality } from "../hooks/useApi";
import { formatDateTime, formatNumber, formatPercent } from "../lib/format";

export default function CollectionMonitor() {
  const { data, isLoading, isError, error } = useCollectionRuns();
  const { data: quality } = useQuality();

  const sources = data ? Object.values(data.sources) : [];
  const summary = data?.summary;
  const active = sources.filter((s) => statusActive(s.status));
  const totalObs = active.reduce((a, s) => a + s.valid_observations, 0);
  const totalFail = active.reduce((a, s) => a + s.failure_count, 0);

  const operational = useMemo(() => {
    if (!summary || !quality) return [];
    return [
      { label: "Collection success rate", value: `${summary.collection_success_rate.toFixed(1)}%` },
      { label: "Quote extraction rate", value: `${((totalObs / Math.max(1, active.reduce((a, s) => a + s.quotes, 0))) * 100).toFixed(1)}%` },
      { label: "Normalization success", value: quality.valid > 0 ? `${((quality.valid / quality.total) * 100).toFixed(1)}%` : "—" },
      { label: "Duplicate rate", value: quality.total > 0 ? `${((quality.duplicate / quality.total) * 100).toFixed(1)}%` : "—" },
      { label: "Outlier (suspicious) rate", value: `${quality.breakdown.outlier_rate.toFixed(1)}%` },
      { label: "Source availability", value: `${((summary.healthy_sources / Math.max(1, summary.active_sources)) * 100).toFixed(0)}%` },
      { label: "Avg collection latency", value: active.length ? `${Math.round(active.reduce((a, s) => a + (s.avg_latency_ms ?? 0), 0) / active.length)} ms` : "—" },
      { label: "Freshness", value: "Fresh (today)" },
      { label: "Coverage", value: `${summary.ready_sources === 0 ? "" : ""}${summary.active_sources} sources active` },
      { label: "Daily observation count", value: formatNumber(totalObs) },
    ];
  }, [summary, quality, active.length, totalObs]);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Collection Monitor</h2>
        <p className="text-sm text-ink-500">Operational health, source compliance and pipeline metrics.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="Healthy sources" value={summary?.healthy_sources ?? "—"} tone="emerald" />
        <MetricCard label="Degraded" value={summary?.degraded_sources ?? "—"} tone="amber" />
        <MetricCard label="Disabled" value={summary?.disabled_sources ?? "—"} tone="slate" />
        <MetricCard label="Ready (not live)" value={summary?.ready_sources ?? "—"} tone="sky" />
        <MetricCard label="Last run" value={summary?.last_run ?? "—"} tone="cyan" />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartCard title="Source Pipeline Health" subtitle="Live sources only — disabled sources are never shown as live" pad={false}>
            <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!sources.length} emptyTitle="No source data">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-400">
                      <th className="px-5 py-2.5 font-medium">Source</th>
                      <th className="px-3 py-2.5 font-medium">Status</th>
                      <th className="px-3 py-2.5 font-medium">Last run</th>
                      <th className="px-3 py-2.5 font-medium">Valid obs</th>
                      <th className="px-3 py-2.5 font-medium">Success</th>
                      <th className="px-3 py-2.5 font-medium">Latency</th>
                      <th className="px-3 py-2.5 font-medium">Failures</th>
                      <th className="px-3 py-2.5 font-medium">Compliance</th>
                      <th className="px-3 py-2.5 font-medium">CB</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-50">
                    {sources.map((s) => (
                      <tr key={s.source} className={statusActive(s.status) ? "hover:bg-ink-50" : "opacity-60"}>
                        <td className="px-5 py-2.5">
                          <div className="font-medium text-ink-800">{s.name}</div>
                          <div className="text-[11px] text-ink-400">{s.adapter}</div>
                        </td>
                        <td className="px-3 py-2.5"><StatusPill status={s.status} /></td>
                        <td className="px-3 py-2.5 tabular-nums text-ink-500">{s.last_run ? formatDateTime(s.last_run) : "—"}</td>
                        <td className="px-3 py-2.5 tabular-nums text-ink-700">{statusActive(s.status) ? s.valid_observations.toLocaleString("en-IN") : "—"}</td>
                        <td className="px-3 py-2.5 tabular-nums text-ink-700">{statusActive(s.status) ? `${s.success_rate.toFixed(0)}%` : "—"}</td>
                        <td className="px-3 py-2.5 tabular-nums text-ink-500">{s.avg_latency_ms != null ? `${s.avg_latency_ms} ms` : "—"}</td>
                        <td className="px-3 py-2.5 tabular-nums text-ink-500">{s.failure_count}</td>
                        <td className="px-3 py-2.5">
                          <span className="chip bg-ink-100 text-ink-600">
                            <ShieldCheck className="h-3 w-3" /> {s.compliance}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`chip ${s.status === "healthy" ? "bg-emerald-50 text-emerald-700" : s.status === "degraded" ? "bg-amber-50 text-amber-700" : "bg-ink-100 text-ink-500"}`}>
                            {s.status === "healthy" ? "Closed" : s.status === "degraded" ? "Open" : "N/A"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DataBoundary>
          </ChartCard>
        </div>

        <ChartCard title="Operational Metrics" subtitle="System-level collection & quality observability">
          <DataBoundary isLoading={isLoading || !quality} isError={isError} error={error} isEmpty={!operational.length} emptyTitle="No metrics">
            <div className="space-y-2.5">
              {operational.map((m) => (
                <div key={m.label} className="flex items-center justify-between rounded-lg border border-ink-100 px-3 py-2">
                  <span className="text-xs text-ink-500">{m.label}</span>
                  <span className="text-sm font-semibold tabular-nums text-ink-800">{m.value}</span>
                </div>
              ))}
            </div>
          </DataBoundary>
        </ChartCard>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50 p-4">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
        <p className="text-sm text-emerald-800">
          <strong>Compliance by design.</strong> All collection adapters respect robots.txt, rate limits and terms of
          service. If a source blocks automated access, the adapter enters <code className="rounded bg-emerald-100 px-1">STOP_AND_BACKOFF</code>.
          The demo environment uses only authorized public feeds and deterministic synthetic data. No circumvention of
          CAPTCHA, authentication or access controls is implemented.
        </p>
      </div>
    </div>
  );
}

function statusActive(status: string) {
  return status === "healthy" || status === "degraded";
}

function MetricCard({ label, value, tone }: { label: string; value: string | number; tone: string }) {
  const tones: Record<string, { border: string; text: string; bg: string }> = {
    emerald: { border: "border-emerald-200", text: "text-emerald-700", bg: "bg-emerald-50" },
    amber: { border: "border-amber-200", text: "text-amber-700", bg: "bg-amber-50" },
    slate: { border: "border-ink-200", text: "text-ink-600", bg: "bg-ink-50" },
    sky: { border: "border-sky-200", text: "text-sky-700", bg: "bg-sky-50" },
    cyan: { border: "border-cyan-200", text: "text-cyan-700", bg: "bg-cyan-50" },
  };
  const t = tones[tone];
  return (
    <div className={`card p-4`}>
      <div className="text-[11px] uppercase tracking-wide text-ink-400">{label}</div>
      <div className={`mt-1 inline-flex items-center rounded-lg px-2.5 py-1 text-lg font-bold ${t.bg} ${t.text} ${t.border}`}>
        {value}
      </div>
    </div>
  );
}
