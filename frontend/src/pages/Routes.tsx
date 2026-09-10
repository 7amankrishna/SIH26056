// Routes page: route heatmap, movement table, and route-level drill-down.

import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "../components/ChartCard";
import { RouteHeatmap } from "../components/RouteHeatmap";
import { Sparkline } from "../components/Sparkline";
import { DeltaBadge } from "../components/badges";
import { DataBoundary } from "../components/DataState";
import { FilterBar } from "../components/FilterBar";
import { ChartTooltip } from "../components/ChartCard";
import { useFilters } from "../hooks/useFilters";
import { useRouteDetail, useRoutes } from "../hooks/useApi";
import { usePageTitle } from "../hooks/usePageTitle";
import { useChartTheme } from "../hooks/useChartTheme";
import { formatINR, shortDate } from "../lib/format";

export default function Routes() {
  usePageTitle("Routes");
  const { route } = useFilters();
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Routes</h2>
        <p className="text-sm text-ink-500">Route-level price movement across the Indian domestic network.</p>
      </div>

      <FilterBar />

      {route ? <RouteDetailPanel route={route} /> : null}

      <div className="card">
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3.5">
          <div>
            <h3 className="text-sm font-semibold text-ink-800">India Airfare Route Heatmap</h3>
            <p className="mt-0.5 text-xs text-ink-500">Click a cell to drill into that route.</p>
          </div>
        </div>
        <div className="p-5">
          <RouteHeatmap />
        </div>
      </div>

      <RouteMovementTable />
    </div>
  );
}

function RouteDetailPanel({ route }: { route: string }) {
  const { data, isLoading, isError, error } = useRouteDetail(route);
  const t = useChartTheme();
  const series = useMemo(() => (data?.series ?? []), [data]);

  return (
    <ChartCard title={`${data?.origin_city ?? ""} → ${data?.destination_city ?? ""}`} subtitle={`Route index · distance ${data?.distance_km ?? "—"} km`}>
      <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!series.length} emptyTitle={`No observations available for ${route}.`} variant="chart">
        <div className="grid grid-cols-2 gap-2.5 sm:gap-4 sm:grid-cols-4 min-w-0 max-w-full">
          <Meta label="Current fare" value={formatINR(data?.meta?.current_fare)} />
          <Meta label="Route index" value={data?.meta?.route_index?.toFixed(1)} />
          <Meta label="Base price" value={formatINR(data?.base_price)} />
          <Meta label="Weight" value={`${(Number(data?.weight ?? 0) * 100).toFixed(1)}%`} />
        </div>
        <div className="mt-4 h-[240px] w-full min-w-0 max-w-full overflow-hidden">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 6, right: 10, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="routeFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={t.indigo} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={t.indigo} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: t.tick }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis tick={{ fontSize: 11, fill: t.tick }} axisLine={false} tickLine={false} width={46} domain={["auto", "auto"]} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="route_index" name="Route index" stroke={t.indigo} strokeWidth={2} fill="url(#routeFill)" animationDuration={400} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3 min-w-0 max-w-full">
          {(data?.airlines ?? []).map((a) => (
            <div key={a.airline} className="rounded-lg border border-ink-100 p-3">
              <div className="text-xs font-semibold text-ink-700">{a.name}</div>
              <div className="mt-1 text-sm font-bold tabular-nums text-ink-900">{formatINR(a.avg_fare)}</div>
              <div className="text-[11px] text-ink-500">{a.observations} observations · median {formatINR(a.median_fare)}</div>
            </div>
          ))}
        </div>
      </DataBoundary>
    </ChartCard>
  );
}

function Meta({ label, value }: { label: string; value: string | undefined | number }) {
  return (
    <div className="rounded-lg border border-ink-100 p-3">
      <div className="text-[11px] uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-1 text-base font-bold tabular-nums text-ink-900">{value ?? "—"}</div>
    </div>
  );
}

function RouteMovementTable() {
  const { data, isLoading, isError, error } = useRoutes();
  const navigate = useNavigate();
  return (
    <ChartCard title="Route Movement" subtitle="All routes ordered by 7-day change" pad={false}>
      <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!data?.routes.length} emptyTitle="No route data" variant="table">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                <th className="px-5 py-2.5 font-medium">Route</th>
                <th className="px-3 py-2.5 font-medium">Fare</th>
                <th className="px-3 py-2.5 font-medium">Index</th>
                <th className="px-3 py-2.5 font-medium">24h</th>
                <th className="px-3 py-2.5 font-medium">7d</th>
                <th className="px-3 py-2.5 font-medium">Obs</th>
                <th className="px-3 py-2.5 font-medium">Quality</th>
                <th className="px-3 py-2.5 font-medium">Trend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100/70">
              {(data?.routes ?? []).map((r) => (
                <tr key={r.route} onClick={() => navigate(`?route=${r.route}`)} className="cursor-pointer hover:bg-ink-50">
                  <td className="px-5 py-2.5 font-medium text-ink-800">{r.origin_city} → {r.destination_city}</td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(r.current_fare)}</td>
                  <td className="px-3 py-2.5 tabular-nums font-semibold text-ink-900">{r.route_index?.toFixed(1)}</td>
                  <td className="px-3 py-2.5"><DeltaBadge value={r.change_24h} /></td>
                  <td className="px-3 py-2.5"><DeltaBadge value={r.change_7d} /></td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-500">{r.observations}</td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-500">{r.quality ?? "—"}%</td>
                  <td className="px-3 py-2.5"><Sparkline data={r.sparkline} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataBoundary>
    </ChartCard>
  );
}
