// Lead-time elasticity — how airfare changes with advance booking.

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Lightbulb } from "lucide-react";
import { ChartCard, ChartTooltip } from "../components/ChartCard";
import { DataBoundary } from "../components/DataState";
import { FilterBar } from "../components/FilterBar";
import { useFilters } from "../hooks/useFilters";
import { useLeadTime, useFareDistribution } from "../hooks/useApi";
import { formatINR } from "../lib/format";

export default function LeadTime() {
  const { route, airline, source } = useFilters();
  const { data, isLoading, isError, error } = useLeadTime({
    route: route ?? undefined,
    airline: airline ?? undefined,
    source: source ?? undefined,
  });

  const { data: dist, isLoading: distLoading, isError: distError, error: distErrorObj } = useFareDistribution(route ?? undefined);
  const series = data?.series ?? [];

  const chartData = series.map((s) => ({
    label: s.label,
    avg_fare: s.avg_fare,
    median_fare: s.median_fare,
    observations: s.observations,
    lead_time_days: s.lead_time_days,
  }));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Lead-Time Elasticity</h2>
        <p className="text-sm text-ink-500">How the average observed fare changes with advance booking.</p>
      </div>

      <FilterBar />

      {data?.insight && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
          <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
          <div>
            <p className="text-sm font-semibold text-amber-800">Insight</p>
            <p className="text-sm text-amber-700">{data.insight}</p>
          </div>
        </div>
      )}

      <ChartCard title="Elasticity Curve" subtitle="Average and median observed fare vs advance booking (days before departure)">
        <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!chartData.length} emptyTitle="No observations available for this filter combination.">
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 12, bottom: 0, left: -6 }}>
                <defs>
                  <linearGradient id="leadFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={60} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
                <Tooltip content={<LeadTooltip />} />
                <Area type="monotone" dataKey="avg_fare" name="Average fare" stroke="#6366f1" strokeWidth={2.2} fill="url(#leadFill)" />
                <Area type="monotone" dataKey="median_fare" name="Median fare" stroke="#0891b2" strokeWidth={2} fill="transparent" strokeDasharray="4 3" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </DataBoundary>
      </ChartCard>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ChartCard title="By Lead Time" subtitle="Observations and average fare per bucket" pad={false}>
          <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!series.length} emptyTitle="No data">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-400">
                  <th className="px-5 py-2.5 font-medium">Lead time</th>
                  <th className="px-3 py-2.5 font-medium">Avg fare</th>
                  <th className="px-3 py-2.5 font-medium">Median</th>
                  <th className="px-3 py-2.5 font-medium">Obs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {series.map((s) => (
                  <tr key={s.lead_time_days} className="hover:bg-ink-50">
                    <td className="px-5 py-2.5 font-medium text-ink-800">{s.label}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(s.avg_fare)}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(s.median_fare)}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-500">{s.observations.toLocaleString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataBoundary>
        </ChartCard>

        <ChartCard title="Fare Distribution (current day)" subtitle="Robust percentiles — median is the representative statistic">
          <DataBoundary isLoading={distLoading} isError={distError} error={distErrorObj} isEmpty={!dist || dist.observations === 0} emptyTitle="No distribution data">
            {dist && (
              <div>
                <div className="grid grid-cols-3 gap-2">
                  <DistTile label="P10" value={dist.p10} />
                  <DistTile label="Median" value={dist.median} highlight />
                  <DistTile label="P90" value={dist.p90} />
                </div>
                <div className="mt-4">
                  <div className="relative h-2 rounded-full bg-gradient-to-r from-emerald-400 via-slate-200 to-red-400">
                    <span className="absolute -top-1 h-4 w-0.5 rounded bg-ink-700" style={{ left: "50%" }} />
                  </div>
                  <div className="mt-1 flex justify-between text-[11px] text-ink-400">
                    <span>{formatINR(dist.min)}</span>
                    <span className="font-medium text-ink-600">Median {formatINR(dist.median)}</span>
                    <span>{formatINR(dist.max)}</span>
                  </div>
                </div>
                <p className="mt-3 text-xs text-ink-500">
                  Mean {formatINR(dist.mean)} · Std dev {formatINR(dist.std_dev)} · {dist.observations.toLocaleString("en-IN")} observations
                </p>
              </div>
            )}
          </DataBoundary>
        </ChartCard>
      </div>
    </div>
  );
}

function DistTile({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded-lg border p-3 ${highlight ? "border-brand-300 bg-brand-50" : "border-ink-100"}`}>
      <div className="text-[11px] uppercase tracking-wide text-ink-400">{label}</div>
      <div className={`text-sm font-bold tabular-nums ${highlight ? "text-brand-700" : "text-ink-800"}`}>{formatINR(value)}</div>
    </div>
  );
}

function LeadTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload;
  return (
    <div className="rounded-lg border border-ink-200 bg-white/95 px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold text-ink-700">{label} before departure</p>
      {payload.map((entry: any, i: number) => (
        <div key={i} className="mt-1 flex justify-between gap-6 text-xs">
          <span className="text-ink-500">{entry.name}</span>
          <span className="font-semibold tabular-nums text-ink-800">{formatINR(entry.value)}</span>
        </div>
      ))}
      {p?.observations != null && (
        <div className="mt-1 flex justify-between gap-6 text-xs">
          <span className="text-ink-500">Observations</span>
          <span className="font-semibold tabular-nums text-ink-800">{p.observations.toLocaleString("en-IN")}</span>
        </div>
      )}
    </div>
  );
}
