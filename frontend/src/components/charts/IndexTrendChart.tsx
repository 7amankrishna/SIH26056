// Headline APIx time-series chart with range controls.

import { useMemo, useState } from "react";
import { AlertCircle, Calendar, Info } from "lucide-react";
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
import { useOverview, useTrend } from "../../hooks/useApi";
import { useChartTheme } from "../../hooks/useChartTheme";
import { DataBoundary } from "../DataState";
import { formatIndex, shortDate } from "../../lib/format";

const RANGES = [
  { key: "7d", label: "7D", days: 7 },
  { key: "30d", label: "30D", days: 30 },
  { key: "90d", label: "90D", days: 90 },
  { key: "6m", label: "6M", days: 180 },
  { key: "1y", label: "1Y", days: 365 },
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
  const { data: overview } = useOverview();

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

  // Available data window bounds from backend
  const seriesStart = chartData.length > 0 ? chartData[0].date : null;
  const seriesEnd = chartData.length > 0 ? chartData[chartData.length - 1].date : null;
  const periodStart = overview?.data_period?.start ?? seriesStart;
  const periodEnd = overview?.data_period?.end ?? seriesEnd;
  const totalDays = chartData.length;

  const activeRangeObj = RANGES.find((r) => r.key === range);
  const isCapped = Boolean(activeRangeObj && activeRangeObj.days > totalDays && totalDays > 0);

  return (
    <ChartCard
      title={title ?? "Airfare Price Index"}
      subtitle={
        subtitle ?? (
          <span className="flex items-center gap-1.5 flex-wrap">
            <span>Base period {data?.base_period?.start ?? "—"} → {data?.base_period?.end ?? "—"}</span>
            {periodStart && periodEnd && (
              <span className="inline-flex items-center gap-1 rounded-md bg-ink-100 dark:bg-white/10 px-2 py-0.5 text-[11px] font-medium text-ink-600 dark:text-ink-300">
                <Calendar className="h-3 w-3 text-cyan-600 dark:text-cyan-400" />
                Available data: {shortDate(periodStart)} – {shortDate(periodEnd)} ({totalDays} days)
              </span>
            )}
          </span>
        )
      }
      actions={
        showRanges ? (
          <div className="flex items-center gap-2 flex-wrap justify-end">
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
          </div>
        ) : null
      }
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-2">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <div>
            <span className="text-2xl font-bold tabular-nums text-ink-900">
              {current != null ? formatIndex(current) : "—"}
            </span>
            <span className="ml-2 text-xs text-ink-500">index value</span>
          </div>
          {change7d != null && (
            <span className="text-xs text-ink-500">
              7d change{" "}
              <span className={change7d > 0 ? "font-semibold text-red-600 dark:text-red-400" : "font-semibold text-emerald-700 dark:text-emerald-400"}>
                {change7d > 0 ? "+" : ""}
                {change7d.toFixed(1)}%
              </span>
            </span>
          )}
        </div>

        {/* Depict data restriction when range selection exceeds available historical time period */}
        {isCapped && (
          <div className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1 text-[11px] text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/40 dark:text-amber-300">
            <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
            <span>
              Restricted to available window ({totalDays} days). Historical data prior to {periodStart ? shortDate(periodStart) : "recorded start"} is not accrued.
            </span>
          </div>
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
