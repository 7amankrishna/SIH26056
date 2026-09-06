// Headline APIx time-series chart with range controls.

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard, ChartTooltip } from "../ChartCard";
import { useTrend } from "../../hooks/useApi";
import { DataBoundary } from "../DataState";
import { formatIndex, shortDate } from "../../lib/format";

const RANGES = [
  { key: "7d", label: "7D" },
  { key: "30d", label: "30D" },
  { key: "90d", label: "90D" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
];

export function IndexTrendChart({ title, subtitle, defaultRange = "90d", showRanges = true }: {
  title?: string;
  subtitle?: string;
  defaultRange?: string;
  showRanges?: boolean;
}) {
  const [range, setRange] = useState(defaultRange);
  const { data, isLoading, isError, error } = useTrend(range);

  const chartData = useMemo(
    () =>
      (data?.series ?? []).map((p) => ({
        date: p.date,
        apix: p.apix,
        observations: p.observations,
        routes: p.routes,
        change: p.change,
      })),
    [data],
  );

  const current = data?.current;
  const change7d = data?.change_7d;

  return (
    <ChartCard
      title={title ?? "Airfare Price Index"}
      subtitle={subtitle ?? `Base period ${data?.base_period?.start ?? "—"} → ${data?.base_period?.end ?? "—"}`}
      actions={
        showRanges ? (
          <div className="flex rounded-lg border border-ink-200 p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  range === r.key ? "bg-brand-600 text-white" : "text-ink-500 hover:bg-ink-50"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        ) : null
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1">
        <div>
          <span className="text-2xl font-bold tabular-nums text-ink-900">
            {current != null ? formatIndex(current) : "—"}
          </span>
          <span className="ml-2 text-xs text-ink-400">index value</span>
        </div>
        {change7d != null && (
          <span className="text-xs text-ink-500">
            7d change{" "}
            <span className={change7d > 0 ? "font-semibold text-red-600" : "font-semibold text-emerald-600"}>
              {change7d > 0 ? "+" : ""}
              {change7d.toFixed(1)}%
            </span>
          </span>
        )}
      </div>
      <div className="h-[320px]">
        <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!chartData.length} emptyTitle="No index data available for this range">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 10, right: 12, bottom: 0, left: -14 }}>
              <defs>
                <linearGradient id="apixFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0891b2" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#0891b2" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="apixBase" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#718096" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#718096" stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={28}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={44}
              />
              <Tooltip content={<IndexTooltip />} />
              {data?.base_period && (
                <ReferenceLine y={100} stroke="#64748b" strokeDasharray="4 4" label={{ value: "Base = 100", color: "#64748b", fontSize: 10, position: "insideTopRight" }} />
              )}
              <Area
                type="monotone"
                dataKey="apix"
                name="APIx"
                stroke="#0891b2"
                strokeWidth={2.2}
                fill="url(#apixFill)"
                animationDuration={500}
              />
            </AreaChart>
          </ResponsiveContainer>
        </DataBoundary>
      </div>
    </ChartCard>
  );
}

export function IndexTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-ink-200 bg-white/95 px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold text-ink-700">{label}</p>
      <div className="mt-1.5 space-y-1 text-xs">
        <div className="flex justify-between gap-6">
          <span className="text-ink-500">APIx</span>
          <span className="font-semibold tabular-nums text-ink-800">{formatIndex(p.apix)}</span>
        </div>
        {p.change != null && (
          <div className="flex justify-between gap-6">
            <span className="text-ink-500">Change</span>
            <span className={`font-semibold tabular-nums ${p.change >= 0 ? "text-red-600" : "text-emerald-600"}`}>
              {p.change >= 0 ? "+" : ""}
              {p.change.toFixed(2)}%
            </span>
          </div>
        )}
        <div className="flex justify-between gap-6">
          <span className="text-ink-500">Observations</span>
          <span className="font-semibold tabular-nums text-ink-800">{p.observations?.toLocaleString("en-IN")}</span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="text-ink-500">Routes</span>
          <span className="font-semibold tabular-nums text-ink-800">{p.routes}</span>
        </div>
      </div>
    </div>
  );
}
