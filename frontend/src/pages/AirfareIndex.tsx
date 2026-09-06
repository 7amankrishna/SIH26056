// Airfare Index page: headline trend, route index ranking and the provenance
// "why is today's APIx this value" drill-down.

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { IndexTrendChart } from "../components/charts/IndexTrendChart";
import { ChartCard } from "../components/ChartCard";
import { Sparkline } from "../components/Sparkline";
import { DeltaBadge } from "../components/badges";
import { DataBoundary } from "../components/DataState";
import { useOverview, useProvenance, useRoutes } from "../hooks/useApi";
import { formatINR } from "../lib/format";

export default function AirfareIndex() {
  const navigate = useNavigate();
  const { data: overview } = useOverview();
  const latest = overview?.data_period?.end ?? "";
  const { data: prov, isLoading, isError, error } = useProvenance(latest);

  const contributions = useMemo(
    () => (prov?.route_contributions ?? []).slice().sort((a, b) => b.contribution - a.contribution),
    [prov],
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Airfare Index · APIx</h2>
        <p className="text-sm text-ink-500">
          How the headline index is built, and which routes are driving today's movement.
        </p>
      </div>

      <IndexTrendChart defaultRange="90d" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RouteIndexTable />
        </div>
        <div>
          <ChartCard title="Contribution to today's APIx" subtitle={`As of ${latest}`}>
            <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!contributions.length} emptyTitle="No contribution data">
              <div className="space-y-1.5">
                {contributions.slice(0, 10).map((c) => (
                  <button
                    key={c.route}
                    onClick={() => navigate(`/routes?route=${c.route}`)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-ink-50"
                  >
                    <span className="flex-1 text-left text-xs font-medium text-ink-700">{c.route}</span>
                    <span className="w-16 text-right text-xs tabular-nums text-ink-500">{c.index.toFixed(1)}</span>
                    <span className="w-14 text-right text-xs font-semibold tabular-nums text-ink-800">
                      {c.contribution.toFixed(1)}
                    </span>
                  </button>
                ))}
              </div>
              <div className="mt-3 rounded-lg bg-ink-50 p-3 text-xs text-ink-500">
                Values are weighted route-index contributions (wᵣ × route index). Click a route to audit it.
              </div>
            </DataBoundary>
          </ChartCard>
        </div>
      </div>
    </div>
  );
}

function RouteIndexTable() {
  const { data, isLoading, isError, error } = useRoutes();
  const navigate = useNavigate();
  return (
    <ChartCard title="Route Indices" subtitle="Route-level APIx and 7-day movement" pad={false}>
      <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!data?.routes.length} emptyTitle="No route indices">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-400">
                <th className="px-5 py-2.5 font-medium">Route</th>
                <th className="px-3 py-2.5 font-medium">Current fare</th>
                <th className="px-3 py-2.5 font-medium">Index</th>
                <th className="px-3 py-2.5 font-medium">24h</th>
                <th className="px-3 py-2.5 font-medium">7d</th>
                <th className="px-3 py-2.5 font-medium">Obs</th>
                <th className="px-3 py-2.5 font-medium">Quality</th>
                <th className="px-3 py-2.5 font-medium">Trend</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-50">
              {(data?.routes ?? []).map((r) => (
                <tr key={r.route} onClick={() => navigate(`/routes?route=${r.route}`)} className="cursor-pointer hover:bg-ink-50">
                  <td className="px-5 py-2.5 font-medium text-ink-800">
                    {r.origin_city} → {r.destination_city}
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-700">{formatINR(r.current_fare)}</td>
                  <td className="px-3 py-2.5 tabular-nums font-semibold text-ink-900">{r.route_index?.toFixed(1)}</td>
                  <td className="px-3 py-2.5"><DeltaBadge value={r.change_24h} /></td>
                  <td className="px-3 py-2.5"><DeltaBadge value={r.change_7d} /></td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-500">{r.observations}</td>
                  <td className="px-3 py-2.5 tabular-nums text-ink-500">{r.quality ?? "—"}%</td>
                  <td className="px-3 py-2.5"><Sparkline data={r.sparkline} /></td>
                  <td className="px-3 py-2.5 text-ink-300"><ArrowRight className="h-4 w-4" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataBoundary>
    </ChartCard>
  );
}
