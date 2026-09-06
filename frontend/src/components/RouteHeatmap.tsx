// India airfare route heatmap — an origin × destination matrix encoded by
// price level or % change. Analytical, not decorative.

import { Fragment, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRouteHeatmap } from "../hooks/useApi";
import { DataBoundary } from "./DataState";
import { ChartTooltip } from "./ChartCard";
import { formatINR, formatPercent } from "../lib/format";

type Mode = "change" | "price";

function heatColor(value: number, mode: Mode): string {
  if (mode === "change") {
    // -10 (green) -> 0 (neutral) -> +12 (red)
    const clamped = Math.max(-10, Math.min(12, value));
    if (clamped >= 0) {
      const alpha = 0.15 + (clamped / 12) * 0.75;
      return `rgba(220, 38, 38, ${alpha})`; // red for increase
    }
    const alpha = 0.15 + (Math.abs(clamped) / 10) * 0.75;
    return `rgba(16, 185, 129, ${alpha})`; // green for decrease
  }
  // Price level normalized against base (index ~ 100)
  // 80 (low) -> 100 (base) -> 140 (high)
  const clamped = Math.max(80, Math.min(140, value));
  const alpha = 0.18 + ((clamped - 80) / 60) * 0.72;
  return `rgba(14, 116, 144, ${alpha})`; // cyan/teal intensity
}

function tooltipText(r: any, mode: Mode) {
  const metric =
    mode === "change"
      ? `7D ${r.change_7d != null ? formatPercent(r.change_7d) : "—"} ${r.change_24h != null ? `· 24h ${formatPercent(r.change_24h)}` : ""}`
      : `Route index ${r.route_index ?? "—"}`;
  return {
    title: `${r.origin_city} → ${r.destination_city}`,
    lines: [
      ["Current fare", formatINR(r.current_fare)],
      ["Route index", r.route_index != null ? r.route_index.toFixed(1) : "—"],
      ["7-day", formatPercent(r.change_7d)],
      ["24-hour", formatPercent(r.change_24h)],
      ["Observations", r.observations?.toLocaleString("en-IN") ?? "—"],
      ["Quality", `${r.quality ?? "—"}%`],
    ],
    metric,
  };
}

export function RouteHeatmap({ compact = false }: { compact?: boolean }) {
  const { data, isLoading, isError, error } = useRouteHeatmap();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>("change");

  const { rows, cols, lookup } = useMemo(() => {
    const routes = data?.routes ?? [];
    const origins = Array.from(new Set(routes.map((r) => r.origin))).sort();
    const dests = Array.from(new Set(routes.map((r) => r.destination))).sort();
    const map = new Map<string, (typeof routes)[number]>();
    for (const r of routes) map.set(`${r.origin}|${r.destination}`, r);
    return { rows: origins, cols: dests, lookup: map };
  }, [data]);

  return (
    <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={rows.length === 0} emptyTitle="No route data available">
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex rounded-lg border border-ink-200 p-0.5">
            {(["change", "price"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-md px-3 py-1 text-xs font-medium ${
                  mode === m ? "bg-brand-600 text-white" : "text-ink-500 hover:bg-ink-50"
                }`}
              >
                {m === "change" ? "% Change" : "Price Level"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-[11px] text-ink-400">
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-sm bg-emerald-400" /> Cheaper
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-sm bg-ink-200" /> Base
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-sm bg-red-400" /> Pricier
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <div
            className="grid gap-[3px]"
            style={{
              gridTemplateColumns: `60px repeat(${cols.length}, minmax(56px, 1fr))`,
              minWidth: 60 + cols.length * 60,
            }}
          >
            {/* corner */}
            <div />
            {cols.map((c) => (
              <div key={c} className="pb-1 text-center text-[10px] font-semibold uppercase text-ink-400">
                {c}
              </div>
            ))}
            {rows.map((o) => (
              <FragmentRow key={o} o={o} cols={cols} lookup={lookup} mode={mode} compact={compact} onNavigate={navigate} />
            ))}
          </div>
        </div>
      </div>
    </DataBoundary>
  );
}

function FragmentRow({ o, cols, lookup, mode, compact, onNavigate }: any) {
  return (
    <Fragment>
      <div className="flex items-center justify-center text-[10px] font-semibold uppercase text-ink-500">{o}</div>
      {cols.map((d: string) => {
        const r = lookup.get(`${o}|${d}`);
        if (!r) {
          return <div key={d} className="h-[38px] rounded bg-ink-50" />;
        }
        const value = mode === "change" ? r.change_7d ?? 0 : r.route_index ?? 100;
        const color = heatColor(value, mode);
        const tip = tooltipText(r, mode);
        return (
          <button
            key={d}
            onClick={() => onNavigate(`/routes?route=${r.route}`)}
            style={{ background: color }}
            title={`${r.origin_city} → ${r.destination_city}`}
            className="group relative h-[38px] rounded transition-transform hover:scale-[1.04] hover:ring-2 hover:ring-brand-500"
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLElement;
              const tipEl = el.querySelector("[data-tip]") as HTMLElement | null;
              if (tipEl) tipEl.style.opacity = "1";
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLElement;
              const tipEl = el.querySelector("[data-tip]") as HTMLElement | null;
              if (tipEl) tipEl.style.opacity = "0";
            }}
          >
            {!compact && value != null && (
              <span className="text-[9px] font-semibold tabular-nums text-ink-900/70">
                {mode === "change" ? `${value > 0 ? "+" : ""}${value.toFixed(0)}` : Math.round(value)}
              </span>
            )}
            {compact && (
              <span className="block h-1 w-full rounded" style={{ background: color }} />
            )}
            {/* tooltip */}
            <div data-tip className="pointer-events-none absolute left-1/2 top-full z-20 -translate-x-1/2 whitespace-nowrap rounded-lg border border-ink-200 bg-white px-3 py-2 opacity-0 shadow-xl transition-opacity">
              <div className="text-xs font-semibold text-ink-800">{tip.title}</div>
              <div className="mt-1 space-y-0.5 text-[11px] text-ink-500">
                {tip.lines.map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-5">
                    <span>{k}</span>
                    <span className="font-semibold text-ink-700">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </button>
        );
      })}
    </Fragment>
  );
}
