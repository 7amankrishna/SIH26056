// Executive dashboard — the default landing page.

import { useNavigate } from "react-router-dom";
import { Activity, ArrowDownRight, ArrowUpRight, Building2, Layers, Route, Shuffle } from "lucide-react";
import { KpiCard } from "../components/KpiCard";
import { DeltaBadge } from "../components/badges";
import { IndexTrendChart } from "../components/charts/IndexTrendChart";
import { RouteHeatmap } from "../components/RouteHeatmap";
import { Sparkline } from "../components/Sparkline";
import { FilterBar } from "../components/FilterBar";
import { useOverview, useRoutes } from "../hooks/useApi";
import { useChartTheme } from "../hooks/useChartTheme";
import { usePageTitle } from "../hooks/usePageTitle";
import { formatIndex, formatINR, formatNumber, formatPercent } from "../lib/format";

export default function Overview() {
  const navigate = useNavigate();
  const t = useChartTheme();
  usePageTitle("Overview");
  const { data: overview, isLoading, isError, error } = useOverview();
  const { data: routesData } = useRoutes();

  const routes = routesData?.routes ?? [];
  const topUp = routes.filter((r) => (r.change_7d ?? 0) > 0).slice(0, 4);
  const topDown = routes
    .filter((r) => (r.change_7d ?? 0) < 0)
    .sort((a, b) => (a.change_7d ?? 0) - (b.change_7d ?? 0))
    .slice(0, 3);

  const deltaColor = (v: number | null | undefined) =>
    v == null ? "text-ink-500" : v > 0 ? "text-red-600" : v < 0 ? "text-emerald-600" : "text-ink-500";

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Overview</h2>
        <p className="text-sm text-ink-500">
          India's online airfare movement, transformed into a transparent, auditable index.
        </p>
      </div>

      <FilterBar />

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
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
      <div className="card">
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3.5">
          <div>
            <h3 className="text-sm font-semibold text-ink-800">India Airfare Route Heatmap</h3>
            <p className="mt-0.5 text-xs text-ink-500">Origin × destination, encoded by route movement. Hover a cell for detail.</p>
          </div>
        </div>
        <div className="p-5">
          <RouteHeatmap />
        </div>
      </div>

      {/* Rankings + airline mini */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <RouteRanking title="Routes with Largest Price Movement · Increases" routes={topUp} up />
        <RouteRanking title="Routes with Largest Price Movement · Decreases" routes={topDown} down />
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
    <div className="card">
      <div className="border-b border-ink-100 px-5 py-3.5">
        <h3 className="text-sm font-semibold text-ink-800">{title}</h3>
      </div>
      <div className="divide-y divide-ink-100">
        {routes.length === 0 && <div className="p-6 text-sm text-ink-500">No routes in this category.</div>}
        {routes.map((r, i) => (
          <button
            key={r.route}
            onClick={() => navigate(`/routes?route=${r.route}`)}
            className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors duration-150 hover:bg-ink-50"
          >
            <span className="w-6 text-center text-sm font-bold text-ink-400">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-ink-800">
                {r.origin_city} → {r.destination_city}
              </div>
              <div className="text-xs text-ink-500">₹{r.current_fare?.toLocaleString("en-IN") ?? "—"}</div>
            </div>
            <Sparkline data={r.sparkline} color={up ? t.red : t.emerald} />
            <span className={`w-20 text-right text-sm font-semibold tabular-nums ${up ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
              {r.change_7d != null ? `${r.change_7d > 0 ? "+" : ""}${r.change_7d.toFixed(1)}%` : "—"}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
