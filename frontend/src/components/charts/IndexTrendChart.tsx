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
import { useChartTheme } from "../../hooks/useChartTheme";
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
  const t = useChartTheme();
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
          <div className="seg" role="group" aria-label="Index range">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                aria-pressed={range === r.key}
                className={`seg-item ${range === r.key ? "seg-item-active" : ""}`}
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
          <span className="ml-2 text-xs text-ink-500">index value</span>
        </div>
        {change7d != null && (
          <span className="text-xs text-ink-500">
            7d change{" "}
            <span className={change7d > 0 ? "font-semibold text-red-600 dark:text-red-400" : "font-semibold text-emerald-600 dark:text-emerald-400"}>
              {change7d > 0 ? "+" : ""}
              {change7d.toFixed(1)}%
            </span>
          </span>
        )}
      </div>
      <div className="h-[320px]">
        <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!chartData.length} emptyTitle="No index data available for this range" variant="chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 10, right: 12, bottom: 0, left: -14 }}>
              <defs>
                <linearGradient id="apixFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={t.brand} stopOpacity={0.32} />
                  <stop offset="95%" stopColor={t.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tick={{ fontSize: 11, fill: t.tick }}
                axisLine={false}
                tickLine={false}
                minTickGap={28}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11, fill: t.tick }}
                axisLine={false}
                tickLine={false}
                width={44}
              />
              <Tooltip content={<IndexTooltip />} cursor={{ stroke: t.refLine, strokeDasharray: "3 3" }} />
              {data?.base_period && (
                <ReferenceLine
                  y={100}
                  stroke={t.refLine}
                  strokeDasharray="4 4"
                  label={{ value: "Base = 100", fill: t.tick, fontSize: 10, position: "insideTopRight" }}
                />
              )}
              <Area
                type="monotone"
                dataKey="apix"
                name="APIx"
                stroke={t.brand}
                strokeWidth={2.2}
                fill="url(#apixFill)"
                animationDuration={400}
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
    <div className="tt">
      <p className="tt-label">{label}</p>
      <div className="mt-1.5 space-y-1 text-xs">
        <div className="flex justify-between gap-6">
          <span className="tt-key">APIx</span>
          <span className="tt-val">{formatIndex(p.apix)}</span>
        </div>
        {p.change != null && (
          <div className="flex justify-between gap-6">
            <span className="tt-key">Change</span>
            <span className={`tt-val ${p.change >= 0 ? "text-red-400" : "text-emerald-400"}`}>
              {p.change >= 0 ? "+" : ""}
              {p.change.toFixed(2)}%
            </span>
          </div>
        )}
        <div className="flex justify-between gap-6">
          <span className="tt-key">Observations</span>
          <span className="tt-val">{p.observations?.toLocaleString("en-IN")}</span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="tt-key">Routes</span>
          <span className="tt-val">{p.routes}</span>
        </div>
      </div>
    </div>
  );
}
