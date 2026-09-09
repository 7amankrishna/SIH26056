// India airfare route heatmap — an origin × destination matrix encoded by
// price level or % change. Analytical, not decorative.
//
// Tooltip: rendered in a portal with position:fixed, so it can never be
// clipped by the matrix's overflow-x scroll container (the old absolute
// tooltip was cut off on the bottom rows). It uses the shared `.tt` token —
// solid dark glass, backdrop blur, z-60, pointer-events: none — and flips
// above/below the cell depending on viewport room.

import { Fragment, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useRouteHeatmap } from "../hooks/useApi";
import { DataBoundary } from "./DataState";
import { useChartTheme } from "../hooks/useChartTheme";
import { useTheme } from "../hooks/useTheme";
import { formatINR, formatPercent } from "../lib/format";
import type { RouteSummary } from "../lib/types";

type Row = RouteSummary;

type Mode = "change" | "price";

const TIP_W = 232; // px, used for horizontal clamping

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function withAlpha(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}

function heatColor(value: number, mode: Mode, t: ReturnType<typeof useChartTheme>, dark: boolean) {
  if (mode === "change") {
    // -10 (green) -> 0 (neutral) -> +12 (red)
    const clamped = Math.max(-10, Math.min(12, value));
    if (clamped >= 0) {
      const alpha = 0.1 + (clamped / 12) * (dark ? 0.62 : 0.75);
      return { css: withAlpha(t.red, alpha), strength: alpha };
    }
    const alpha = 0.1 + (Math.abs(clamped) / 10) * (dark ? 0.62 : 0.75);
    return { css: withAlpha(t.emerald, alpha), strength: alpha };
  }
  // Price level normalized against base (index ~ 100): 80 → 140
  const clamped = Math.max(80, Math.min(140, value));
  const alpha = 0.16 + ((clamped - 80) / 60) * (dark ? 0.6 : 0.72);
  return { css: withAlpha(t.brand, alpha), strength: alpha };
}

export function RouteHeatmap({ compact = false }: { compact?: boolean }) {
  const { data, isLoading, isError, error } = useRouteHeatmap();
  const navigate = useNavigate();
  const t = useChartTheme();
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  const [mode, setMode] = useState<Mode>("change");

  // Floating tooltip state (fixed positioning + portal → never clipped).
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    place: "above" | "below";
    row: Row;
    mode: Mode;
  } | null>(null);

  const hideTip = () => setTip(null);

  // The matrix scrolls horizontally; a scroll anywhere must not leave a
  // detached tooltip floating in space.
  useEffect(() => {
    if (!tip) return;
    window.addEventListener("scroll", hideTip, true);
    window.addEventListener("resize", hideTip);
    return () => {
      window.removeEventListener("scroll", hideTip, true);
      window.removeEventListener("resize", hideTip);
    };
  }, [tip]);

  const { rows, cols, lookup } = useMemo(() => {
    const routes = data?.routes ?? [];
    const origins = Array.from(new Set(routes.map((r) => r.origin))).sort();
    const dests = Array.from(new Set(routes.map((r) => r.destination))).sort();
    const map = new Map<string, (typeof routes)[number]>();
    for (const r of routes) map.set(`${r.origin}|${r.destination}`, r);
    return { rows: origins, cols: dests, lookup: map };
  }, [data]);

  const showTip = (
    e: { currentTarget: { getBoundingClientRect(): DOMRect } },
    row: Row,
  ) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const place: "above" | "below" = rect.top > 200 ? "above" : "below";
    const cx = rect.left + rect.width / 2;
    const x = Math.min(Math.max(cx, TIP_W / 2 + 8), window.innerWidth - TIP_W / 2 - 8);
    setTip({ x, y: place === "above" ? rect.top - 8 : rect.bottom + 8, place, row, mode });
  };

  const tipLines = (r: Row) => [
    ["Current fare", formatINR(r.current_fare)] as const,
    ["Route index", r.route_index != null ? r.route_index.toFixed(1) : "—"] as const,
    ["7-day", formatPercent(r.change_7d)] as const,
    ["24-hour", formatPercent(r.change_24h)] as const,
    ["Observations", r.observations?.toLocaleString("en-IN") ?? "—"] as const,
    ["Quality", `${r.quality ?? "—"}%`] as const,
  ];

  return (
    <DataBoundary
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={rows.length === 0}
      emptyTitle="No route data available"
    >
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="seg">
            {(["change", "price"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={`seg-item ${mode === m ? "seg-item-active" : ""}`}
              >
                {m === "change" ? "% Change" : "Price Level"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-ink-500">
            {mode === "change" ? (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: withAlpha(t.emerald, 0.85) }} /> Cheaper
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm bg-ink-200" /> Base
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: withAlpha(t.red, 0.85) }} /> Pricier
                </span>
              </>
            ) : (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: withAlpha(t.brand, 0.2) }} /> Lower fare
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: withAlpha(t.brand, 0.9) }} /> Higher fare
                </span>
              </>
            )}
          </div>
        </div>

        <div className="overflow-x-auto pb-1">
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
              <div key={c} className="pb-1 text-center text-[10px] font-semibold uppercase text-ink-500">
                {c}
              </div>
            ))}
            {rows.map((o) => (
              <Fragment key={o}>
                <div className="flex items-center justify-center text-[10px] font-semibold uppercase text-ink-500">
                  {o}
                </div>
                {cols.map((d) => {
                  const r = lookup.get(`${o}|${d}`);
                  if (!r) {
                    return (
                      <div
                        key={d}
                        className="h-[38px] rounded bg-ink-100"
                        style={{ background: "rgb(var(--ink-900) / 0.04)" }}
                      />
                    );
                    }
                  const value = mode === "change" ? r.change_7d ?? 0 : r.route_index ?? 100;
                  const { css, strength } = heatColor(value, mode, t, dark);
                  // Strong tints need white text in light mode; weak tints read
                  // better with ink text. In dark, text is always light.
                  const lightText = dark || strength > 0.55;
                  const label =
                    `${r.origin_city} → ${r.destination_city}. ` +
                    `Fare ${formatINR(r.current_fare)}, 7-day ${formatPercent(r.change_7d)}. Click to open the route.`;
                  return (
                    <button
                      key={d}
                      onClick={() => {
                        hideTip();
                        navigate(`/routes?route=${r.route}`);
                      }}
                      style={{ background: css }}
                      aria-label={label}
                      className="group relative h-[38px] rounded-md outline-offset-1 transition-transform duration-150 hover:z-10 hover:scale-[1.05] hover:ring-2 hover:ring-brand-500"
                      onMouseEnter={(e) => showTip(e, r)}
                      onMouseLeave={hideTip}
                      onFocus={(e) => showTip(e, r)}
                      onBlur={hideTip}
                    >
                      {!compact && (
                        <span
                          className={`text-[10px] font-semibold tabular-nums ${
                            lightText ? "text-white/95" : "text-ink-800"
                          }`}
                        >
                          {mode === "change"
                            ? `${value > 0 ? "+" : ""}${value.toFixed(0)}`
                            : Math.round(value)}
                        </span>
                      )}
                      {compact && (
                        <span className="block h-1 w-full rounded" style={{ background: css }} />
                      )}
                    </button>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Floating cell tooltip — portal so the matrix scroll container can't clip it */}
      {tip &&
        createPortal(
          <div
            role="tooltip"
            className="tt"
            style={{
              position: "fixed",
              left: tip.x,
              top: tip.y,
              width: TIP_W,
              transform:
                tip.place === "above" ? "translate(-50%, -100%)" : "translate(-50%, 0)",
              animation: "tt-in 120ms ease-out",
            }}
          >
            <div className="text-xs font-semibold text-white">
              {tip.row.origin_city} → {tip.row.destination_city}
            </div>
            {tip.mode === "change" && (
              <div className="mt-0.5 text-[11px]">
                <span className="tt-key">7D </span>
                <span
                  className="font-semibold"
                  style={{ color: (tip.row.change_7d ?? 0) >= 0 ? t.red : t.emerald }}
                >
                  {formatPercent(tip.row.change_7d)}
                </span>
                {tip.row.change_24h != null && (
                  <>
                    <span className="tt-key"> · 24h </span>
                    <span className="font-semibold text-white">{formatPercent(tip.row.change_24h)}</span>
                  </>
                )}
              </div>
            )}
            <div className="mt-1.5 space-y-0.5">
              {tipLines(tip.row).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-5">
                  <span className="tt-key">{k}</span>
                  <span className="tt-val">{v}</span>
                </div>
              ))}
            </div>
          </div>,
          document.body,
        )}
    </DataBoundary>
  );
}
