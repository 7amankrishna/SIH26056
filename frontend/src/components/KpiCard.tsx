// Compact, consistent KPI / stat card used across the dashboard.
// Subtle gradient accents only: a fading top bar and a tinted icon tile —
// the value stays the visual anchor.

import type { ReactNode } from "react";
import { Skeleton } from "./Skeleton";

export function KpiCard({
  label,
  value,
  sub,
  delta,
  icon,
  accent,
  loading,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  delta?: ReactNode;
  icon?: ReactNode;
  accent?: string;
  loading?: boolean;
}) {
  return (
    <div className="card group relative overflow-hidden p-4 transition-shadow duration-200 hover:shadow-pop">
      {accent && (
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-1"
          style={{
            background: `linear-gradient(90deg, ${accent} 0%, ${accent}00 100%)`,
          }}
        />
      )}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="kpi-label">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-24" />
          ) : (
            <p className="kpi-value mt-1 truncate">{value}</p>
          )}
          {sub && <div className="mt-1 text-xs text-ink-500">{sub}</div>}
        </div>
        {icon && (
          <div className="kpi-icon-tile shrink-0 rounded-lg p-2 transition-transform duration-200 group-hover:scale-105">
            {icon}
          </div>
        )}
      </div>
      {delta && <div className="mt-2">{delta}</div>}
    </div>
  );
}
