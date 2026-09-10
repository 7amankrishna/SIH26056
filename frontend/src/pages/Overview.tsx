// Executive dashboard — the default landing page.

import { useNavigate } from "react-router-dom";
import { Activity, ArrowDownRight, ArrowUpRight, Layers, Route } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { HeroBanner } from "../components/HeroBanner";
import { KpiCard } from "../components/KpiCard";
import { DeltaBadge } from "../components/badges";
import { IndexTrendChart } from "../components/charts/IndexTrendChart";
import { RouteHeatmap } from "../components/RouteHeatmap";
import { Sparkline } from "../components/Sparkline";
import { FilterBar } from "../components/FilterBar";
import { useAirlines, useLeadTime, useOverview, useRoutes } from "../hooks/useApi";
import { useChartTheme } from "../hooks/useChartTheme";
import { useFilters } from "../hooks/useFilters";
import { usePageTitle } from "../hooks/usePageTitle";
import { formatIndex, formatINR, formatNumber, formatPercent } from "../lib/format";

export default function Overview() {
  const navigate = useNavigate();
  const t = useChartTheme();
  usePageTitle("Overview");
  const { route, airline, source } = useFilters();
  const { data: overview, isLoading, isError, error } = useOverview();
  const { data: routesData } = useRoutes();
  const { data: leadTimeData, isLoading: isLeadTimeLoading } = useLeadTime({
    route: route ?? undefined,
    airline: airline ?? undefined,
    source: source ?? undefined,
  });
  const { data: airlinesData, isLoading: isAirlinesLoading } = useAirlines(route ?? undefined);

  const routes = routesData?.routes ?? [];
  const topUp = routes.filter((r) => (r.change_7d ?? 0) > 0).slice(0, 4);
  const topDown = routes
    .filter((r) => (r.change_7d ?? 0) < 0)
    .sort((a, b) => (a.change_7d ?? 0) - (b.change_7d ?? 0))
    .slice(0, 3);

  // Dynamic Lead Time data from API / data store
  const leadTimeChartData = (leadTimeData?.series ?? []).map((s) => ({
    label: s.label,
    fare: Math.round(s.avg_fare),
    observations: s.observations,
  }));

  // Dynamic Airline Comparison data from API / data store
  const airlineChartData = (airlinesData?.airlines ?? [])
    .filter((a) => a.observations > 0 && a.avg_fare != null)
    .map((a, i) => {
      const colors = ["#3b82f6", "#ef4444", "#f97316", "#ea580c", "#a855f7", "#06b6d4", "#10b981", "#64748b"];
      return {
        name: a.airline,
        fullName: a.name,
        fare: Math.round(a.avg_fare ?? 0),
        color: colors[i % colors.length],
      };
    });

  const deltaColor = (v: number | null | undefined) =>
    v == null ? "text-ink-500" : v > 0 ? "text-red-600" : v < 0 ? "text-emerald-700" : "text-ink-500";

  return (
    <div className="space-y-5">
      <HeroBanner />

      <div>
        <h2 className="text-xl font-bold text-ink-900">Overview</h2>
        <p className="text-sm text-ink-500">
          India's online airfare movement, transformed into a transparent, auditable index.
        </p>
      </div>

      <FilterBar />

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6 sm:gap-4 min-w-0 max-w-full">
        <KpiCard
          label="APIx"
          value={formatIndex(overview?.current_apix)}
          loading={isLoading}
          accent={t.brand}
          icon={<Activity className="h-5 w-5" />}
          delta={overview && <DeltaBadge value={overview.daily_change} />}
        />
        <KpiCard
          label="24h movement"
          value={
            <span className={deltaColor(overview?.daily_change)}>
              {formatPercent(overview?.daily_change)}
            </span>
          }
          loading={isLoading}
          icon={overview && overview.daily_change != null && overview.daily_change > 0 ? <ArrowUpRight className="h-5 w-5" /> : <ArrowDownRight className="h-5 w-5" />}
        />
        <KpiCard
          label="7-day movement"
          value={<span className={deltaColor(overview?.weekly_change)}>{formatPercent(overview?.weekly_change)}</span>}
          loading={isLoading}
          icon={<Activity className="h-5 w-5" />}
        />
        <KpiCard
          label="30-day movement"
          value={<span className={deltaColor(overview?.monthly_change)}>{formatPercent(overview?.monthly_change)}</span>}
          loading={isLoading}
          icon={<Activity className="h-5 w-5" />}
        />
        <KpiCard
          label="Observations"
          value={formatNumber(overview?.observation_count)}
          loading={isLoading}
          icon={<Layers className="h-5 w-5" />}
          sub={<span className="text-ink-500">in current window</span>}
        />
        <KpiCard
          label="Coverage"
          value={`${overview?.route_count ?? "—"} routes`}
          loading={isLoading}
          icon={<Route className="h-5 w-5" />}
          sub={<span className="text-ink-500">{overview?.source_count ?? "—"} sources · {overview?.airline_count ?? "—"} airlines</span>}
        />
      </div>

      {/* Hero chart */}
      <IndexTrendChart />

      {/* Heatmap */}
      <div className="card min-w-0 max-w-full">
        <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3 sm:px-5 sm:py-3.5 min-w-0">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-ink-800">India Airfare Route Heatmap</h3>
            <p className="mt-0.5 text-xs text-ink-500 truncate">Origin × destination, encoded by route movement. Hover a cell for detail.</p>
          </div>
        </div>
        <div className="p-3.5 sm:p-5 min-w-0 max-w-full overflow-hidden">
          <RouteHeatmap />
        </div>
      </div>

      {/* Rankings + airline mini */}
      <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-2 min-w-0 max-w-full">
        <RouteRanking title="Routes with Largest Price Movement · Increases" routes={topUp} up />
        <RouteRanking title="Routes with Largest Price Movement · Decreases" routes={topDown} down />
      </div>

      {/* Bottom Row: Lead Time & Airline Comparison powered by live data */}
      <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-2 min-w-0 max-w-full">
        {/* Average Fare by Lead Time */}
        <div className="card min-w-0 max-w-full p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-ink-800">Average Fare by Lead Time</h3>
              <p className="mt-0.5 text-xs text-ink-500">How prices change with advance booking</p>
            </div>
            <button
              onClick={() => navigate("/lead-time")}
              className="text-xs font-semibold text-sky-600 hover:text-sky-700 inline-flex items-center gap-1 shrink-0"
            >
              Drill down &rarr;
            </button>
          </div>
          <div className="h-56 w-full min-w-0 max-w-full overflow-hidden">
            {leadTimeChartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-ink-400">
                {isLeadTimeLoading ? "Loading lead time data..." : "No lead time observations available."}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={leadTimeChartData}
                  margin={{ top: 18, right: 10, left: -15, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={t.grid} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: t.tick }} axisLine={false} tickLine={false} />
                  <YAxis
                    tick={{ fontSize: 10, fill: t.tick }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `₹${v.toLocaleString("en-IN")}`}
                  />
                  <Tooltip
                    formatter={(val: number) => [`₹${val.toLocaleString("en-IN")}`, "Avg Fare"]}
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="fare" fill={t.brand} radius={[4, 4, 0, 0]}>
                    <LabelList
                      dataKey="fare"
                      position="top"
                      formatter={(val: number) => `₹${val.toLocaleString("en-IN")}`}
                      style={{ fontSize: "10px", fill: t.tick, fontWeight: 600 }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Airline Price Comparison */}
        <div className="card min-w-0 max-w-full p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-ink-800">Airline Price Comparison</h3>
              <p className="mt-0.5 text-xs text-ink-500">Average observed airfare by carrier</p>
            </div>
            <button
              onClick={() => navigate("/airlines")}
              className="text-xs font-semibold text-sky-600 hover:text-sky-700 inline-flex items-center gap-1 shrink-0"
            >
              All airlines &rarr;
            </button>
          </div>
          <div className="h-56 w-full min-w-0 max-w-full overflow-hidden">
            {airlineChartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-ink-400">
                {isAirlinesLoading ? "Loading airline data..." : "No airline observations available."}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={airlineChartData}
                  margin={{ top: 18, right: 10, left: -15, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={t.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: t.tick }} axisLine={false} tickLine={false} />
                  <YAxis
                    tick={{ fontSize: 10, fill: t.tick }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `₹${v.toLocaleString("en-IN")}`}
                  />
                  <Tooltip
                    formatter={(val: number, _name: string, props: any) => [
                      `₹${val.toLocaleString("en-IN")}`,
                      props?.payload?.fullName || "Avg Fare",
                    ]}
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="fare" radius={[4, 4, 0, 0]}>
                    <LabelList
                      dataKey="fare"
                      position="top"
                      formatter={(val: number) => `₹${val.toLocaleString("en-IN")}`}
                      style={{ fontSize: "10px", fill: t.tick, fontWeight: 600 }}
                    />
                    {airlineChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function RouteRanking({
  title,
  routes,
  up,
}: {
  title: string;
  routes: { route: string; origin_city: string; destination_city: string; change_7d: number | null; current_fare: number | null; sparkline: (number | null)[] }[];
  up?: boolean;
  down?: boolean;
}) {
  const navigate = useNavigate();
  const t = useChartTheme();
  return (
    <div className="card min-w-0 max-w-full">
      <div className="border-b border-ink-100 px-4 py-3 sm:px-5 sm:py-3.5">
        <h3 className="text-sm font-semibold text-ink-800">{title}</h3>
      </div>
      <div className="divide-y divide-ink-100">
        {routes.length === 0 && <div className="p-6 text-sm text-ink-500">No routes in this category.</div>}
        {routes.map((r, i) => (
          <button
            key={r.route}
            onClick={() => navigate(`/routes?route=${r.route}`)}
            className="flex w-full items-center gap-2 sm:gap-4 px-3 sm:px-5 py-3 text-left transition-colors duration-150 hover:bg-ink-50 min-w-0"
          >
            <span className="w-5 sm:w-6 text-center text-xs sm:text-sm font-bold text-ink-500 shrink-0">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs sm:text-sm font-medium text-ink-800">
                {r.origin_city} → {r.destination_city}
              </div>
              <div className="text-xs text-ink-500">₹{r.current_fare?.toLocaleString("en-IN") ?? "—"}</div>
            </div>
            <div className="hidden sm:block shrink-0">
              <Sparkline data={r.sparkline} color={up ? t.red : t.emerald} />
            </div>
            <span className={`w-16 sm:w-20 shrink-0 text-right text-xs sm:text-sm font-semibold tabular-nums ${up ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`}>
              {r.change_7d != null ? `${r.change_7d > 0 ? "+" : ""}${r.change_7d.toFixed(1)}%` : "—"}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
