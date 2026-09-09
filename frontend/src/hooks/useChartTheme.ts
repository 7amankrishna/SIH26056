// Theme-aware chart palette. Recharts needs concrete color strings, so this
// hook reads the current resolved theme and returns the palette for it. Every
// chart/heatmap/sparkline consumes this — no hardcoded hex in components.

import { useMemo } from "react";
import { useTheme } from "./useTheme";

export interface ChartPalette {
  /** axis tick + label text */
  tick: string;
  /** grid lines */
  grid: string;
  /** reference lines (base = 100) */
  refLine: string;
  /** hover cursor fill */
  cursor: string;
  /** series palette */
  brand: string;
  indigo: string;
  emerald: string;
  red: string;
  amber: string;
  slate: string;
}

export function useChartTheme(): ChartPalette {
  const { resolvedTheme } = useTheme();
  return useMemo<ChartPalette>(() => {
    if (resolvedTheme === "dark") {
      return {
        tick: "#9b9ba8",
        grid: "rgba(255,255,255,0.07)",
        refLine: "rgba(255,255,255,0.35)",
        cursor: "rgba(255,255,255,0.05)",
        brand: "#22d3ee",
        indigo: "#818cf8",
        emerald: "#34d399",
        red: "#f87171",
        amber: "#fbbf24",
        slate: "#9b9ba8",
      };
    }
    return {
      tick: "#64748b",
      grid: "#eef2f7",
      refLine: "#64748b",
      cursor: "rgba(15,23,42,0.04)",
      brand: "#0891b2",
      indigo: "#6366f1",
      emerald: "#10b981",
      red: "#dc2626",
      amber: "#f59e0b",
      slate: "#64748b",
    };
  }, [resolvedTheme]);
}
