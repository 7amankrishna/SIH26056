// Data Quality panel — explicit uncertainty and audit drill-down.

import { useMemo, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { StatusPill } from "../components/badges";
import { DataBoundary } from "../components/DataState";
import { useQuality, useQualityRejected } from "../hooks/useApi";
import { useChartTheme } from "../hooks/useChartTheme";
import { usePageTitle } from "../hooks/usePageTitle";
import type { Quality } from "../lib/types";

const DIMENSIONS: { key: keyof Quality["breakdown"]; label: string }[] = [
  { key: "completeness", label: "Completeness" },
  { key: "consistency", label: "Consistency" },
  { key: "uniqueness", label: "Uniqueness" },
  { key: "freshness", label: "Freshness" },
  { key: "coverage", label: "Source coverage" },
  { key: "outlier_rate", label: "Outlier rate" },
];

export default function DataQuality() {
  const { data, isLoading, isError, error } = useQuality();
  const t = useChartTheme();
  usePageTitle("Data Quality");
  const [filter, setFilter] = useState<string>("all");

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Data Quality</h2>
        <p className="text-sm text-ink-500">The dashboard does not hide uncertainty — every index value is traceable to quality-flagged observations.</p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Score */}
        <div className="card flex flex-col items-center justify-center p-6">
          <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!data}>
            {data && (
              <div className="text-center">
                <div className="relative mx-auto flex h-32 w-32 items-center justify-center">
                  <svg className="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
                    <circle cx="60" cy="60" r="52" fill="none" stroke={t.grid} strokeWidth="12" />
                    <circle
                      cx="60"
                      cy="60"
                      r="52"
                      fill="none"
                      stroke={t.brand}
                      strokeWidth="12"
                      strokeLinecap="round"
                      strokeDasharray={`${(data.weighted_score / 100) * 326.7} 326.7`}
                    />
                  </svg>
                  <div className="absolute">
                    <div className="text-3xl font-bold tabular-nums text-ink-900">{data.score.toFixed(1)}</div>
                    <div className="text-[11px] text-ink-500">/ 100</div>
                  </div>
                </div>
                <p className="mt-3 text-sm font-semibold text-ink-700">Overall Quality Score</p>
                <p className="text-xs text-ink-500">{data.included.toLocaleString("en-IN")} of {data.total.toLocaleString("en-IN")} observations eligible for the index</p>
              </div>
            )}
          </DataBoundary>
        </div>

        {/* Breakdown */}
        <div className="card lg:col-span-2">
          <div className="border-b border-ink-100 px-5 py-3.5">
            <h3 className="text-sm font-semibold text-ink-800">Quality Breakdown</h3>
          </div>
          <div className="p-5">
            <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!data}>
              {data && (
                <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
                  {DIMENSIONS.map((d) => (
                    <div key={d.key}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-medium text-ink-700">{d.label}</span>
                        <span className="tabular-nums text-ink-500">{data.breakdown[d.key].toFixed(1)}</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-ink-100">
                        <div className="h-1.5 rounded-full bg-brand-500" style={{ width: `${data.breakdown[d.key]}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </DataBoundary>
          </div>
        </div>
      </div>

      {/* Status counts */}
      <ChartCard title="Rejected / Suspicious Observations" subtitle="Excluded from the index but fully auditable">
        <QualityDrilldown filter={filter} setFilter={setFilter} />
      </ChartCard>
    </div>
  );
}

function QualityDrilldown({ filter, setFilter }: { filter: string; setFilter: (s: string) => void }) {
  const { data, isLoading, isError, error } = useQualityRejected();
  const rows = useMemo(
    () => (filter === "all" ? data?.rows ?? [] : (data?.rows ?? []).filter((r) => r.quality_status === filter)),
    [data, filter],
  );
  const statuses = data?.statuses ?? {};

  const filters = [
    { key: "all", label: `All (${data?.count ?? 0})` },
    ...Object.entries(statuses)
      .filter(([k]) => k !== "VALID")
      .map(([k, v]) => ({ key: k, label: `${k} (${v})` })),
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        <div className="seg flex-wrap" role="group" aria-label="Filter by status">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={`seg-item ${filter === f.key ? "seg-item-active" : ""}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!rows.length} emptyTitle="No rejected observations in this category." variant="table">
        <div className="max-h-[420px] overflow-auto rounded-lg border border-ink-100">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                <th className="px-4 py-2.5 font-medium">Obs ID</th>
                <th className="px-3 py-2.5 font-medium">Source</th>
                <th className="px-3 py-2.5 font-medium">Route</th>
                <th className="px-3 py-2.5 font-medium">Departure</th>
                <th className="px-3 py-2.5 font-medium">Airline</th>
                <th className="px-3 py-2.5 font-medium">Lead</th>
                <th className="px-3 py-2.5 font-medium">Fare</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 font-medium">Score</th>
                <th className="px-3 py-2.5 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100/70">
              {rows.map((r) => (
                <tr key={r.observation_id} className="hover:bg-ink-50">
                  <td className="px-4 py-2 font-mono text-xs text-ink-500">{r.observation_id}</td>
                  <td className="px-3 py-2 text-ink-700">{r.source}</td>
                  <td className="px-3 py-2 text-ink-700">{r.route}</td>
                  <td className="px-3 py-2 tabular-nums text-ink-500">{r.departure_date}</td>
                  <td className="px-3 py-2 text-ink-700">{r.airline}</td>
                  <td className="px-3 py-2 tabular-nums text-ink-500">T+{r.lead_time_days}</td>
                  <td className="px-3 py-2 tabular-nums text-ink-700">₹{r.total_fare.toLocaleString("en-IN")}</td>
                  <td className="px-3 py-2"><StatusPill status={r.quality_status} /></td>
                  <td className="px-3 py-2 tabular-nums text-ink-500">{r.quality_score.toFixed(2)}</td>
                  <td className="px-3 py-2 text-xs text-ink-500">{r.exclusion_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-500">
          <ShieldAlert className="h-3.5 w-3.5" />
          Suspicious and rejected observations are preserved for audit and never silently deleted.
        </div>
      </DataBoundary>
    </div>
  );
}
