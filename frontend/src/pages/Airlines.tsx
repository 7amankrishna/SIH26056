// Airline Price Intelligence — compares airlines on observed & index metrics.

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info } from "lucide-react";
import { ChartCard, ChartTooltip } from "../components/ChartCard";
import { DeltaBadge } from "../components/badges";
import { DataBoundary } from "../components/DataState";
import { FilterBar } from "../components/FilterBar";
import { useAirlines } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { formatINR } from "../lib/format";

export default function Airlines() {
  const { route } = useFilters();
  const { data, isLoading, isError, error } = useAirlines(route ?? undefined);
  const airlines = data?.airlines ?? [];

  const chartData = airlines
    .filter((a) => a.observations > 0)
    .map((a) => ({
      name: a.airline,
      airline: a.name,
      avg_fare: a.avg_fare,
      median_fare: a.median_fare,
      observations: a.observations,
    }));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Airline Price Intelligence</h2>
        <p className="text-sm text-ink-500">Observed, normalized and index-level comparison across carriers.</p>
      </div>

      <FilterBar />

      <div className="rounded-lg border border-sky-100 bg-sky-50 p-3 text-xs text-sky-700">
        <div className="flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Comparisons reflect <strong>observed fares</strong>, not statistically controlled pricing. Differences are
            driven by route mix, lead time and availability, so a lower average does not imply an airline is "cheaper"
            on a like-for-like basis. Use the <strong>index contribution</strong> column for the normalized view.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ChartCard title="Average vs Median Fare by Airline" subtitle="Fares differ by route mix; treat as observed, not controlled">
          <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!chartData.length} emptyTitle="No airline data">
            <div className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: -8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={56} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "#f8fafc" }} />
                  <Bar dataKey="avg_fare" name="Avg fare" fill="#0891b2" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="median_fare" name="Median fare" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </DataBoundary>
        </ChartCard>

        <ChartCard title="Volatility vs Index Contribution" subtitle="Coefficient of variation of daily mean fares, and index contribution">
          <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!chartData.length} emptyTitle="No airline data">
            <AirlineMatrix airlines={airlines} />
          </DataBoundary>
        </ChartCard>
      </div>

      <ChartCard title="Airline Comparison Table" subtitle="Observed fare · normalized index contribution · quality" pad={false}>
        <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!airlines.length} emptyTitle="No airline data">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-400">
                  <th className="px-5 py-2.5 font-medium">Airline</th>
                  <th className="px-3 py-2.5 font-medium">Avg fare</th>
                  <th className="px-3 py-2.5 font-medium">Median fare</th>
                  <th className="px-3 py-2.5 font-medium">Index contrib.</th>
                  <th className="px-3 py-2.5 font-medium">Volatility</th>
                  <th className="px-3 py-2.5 font-medium">Availability</th>
                  <th className="px-3 py-2.5 font-medium">Quality</th>
                  <th className="px-3 py-2.5 font-medium">Obs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {airlines.map((a) => (
                  <tr key={a.airline} className="hover:bg-ink-50">
                    <td className="px-5 py-2.5">
                      <div className="font-medium text-ink-800">{a.name}</div>
                      <div className="text-[11px] text-ink-400">{a.airline} · {a.alliance} · {a.hub}</div>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(a.avg_fare)}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(a.median_fare)}</td>
                    <td className="px-3 py-2.5"><DeltaBadge value={a.index_contribution} /></td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{a.volatility != null ? `${a.volatility.toFixed(1)}%` : "—"}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{a.availability != null ? `${a.availability.toFixed(0)}%` : "—"}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">{a.quality != null ? `${a.quality.toFixed(0)}` : "—"}</td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-500">{a.observations.toLocaleString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DataBoundary>
      </ChartCard>
    </div>
  );
}

function AirlineMatrix({ airlines }: { airlines: any[] }) {
  // Scatter: volatility (x) vs index contribution (y) with bubble = observations
  const rows = airlines.filter((a) => a.observations > 0 && a.volatility != null);
  const maxObs = Math.max(...rows.map((r) => r.observations), 1);
  return (
    <div className="space-y-2">
      {rows.map((a) => {
        const size = 10 + (a.observations / maxObs) * 26;
        const positive = (a.index_contribution ?? 0) >= 0;
        return (
          <div key={a.airline} className="flex items-center gap-3 rounded-lg border border-ink-100 p-2.5">
            <span className="w-8 text-sm font-bold text-ink-700">{a.airline}</span>
            <div className="flex-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-ink-500">Volatility</span>
                <span className="font-semibold text-ink-700">{a.volatility?.toFixed(1)}%</span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-ink-100">
                <div className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.min(100, a.volatility ?? 0)}%` }} />
              </div>
            </div>
            <div className={`flex h-9 w-9 items-center justify-center rounded-full text-[10px] font-bold ${positive ? "bg-red-50 text-red-600" : "bg-emerald-50 text-emerald-600"}`} style={{ width: size, height: size }}>
              {a.index_contribution != null ? (a.index_contribution > 0 ? "+" : "") + a.index_contribution.toFixed(0) : "—"}
            </div>
          </div>
        );
      })}
      <p className="pt-1 text-[11px] text-ink-400">Bubble size = observation volume. Index contribution is normalized (relative to all-airline average).</p>
    </div>
  );
}
