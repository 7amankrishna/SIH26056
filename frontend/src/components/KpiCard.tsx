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
    <div className="card group relative min-w-0 max-w-full overflow-hidden p-3.5 sm:p-4 transition-shadow duration-200 hover:shadow-pop">
      {accent && (
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-1"
          style={{
            background: `linear-gradient(90deg, ${accent} 0%, ${accent}00 100%)`,
          }}
        />
      )}
      <div className="flex items-start justify-between gap-1.5 sm:gap-2 min-w-0">
        <div className="min-w-0 flex-1">
          <p className="kpi-label truncate">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-24 max-w-full" />
          ) : (
            <div className="kpi-value mt-1 break-words leading-tight">{value}</div>
          )}
          {sub && <div className="mt-1 text-xs text-ink-500 truncate">{sub}</div>}
        </div>
        {icon && (
          <div className="kpi-icon-tile shrink-0 rounded-lg p-1.5 sm:p-2 transition-transform duration-200 group-hover:scale-105">
            {icon}
          </div>
        )}
      </div>
      {delta && <div className="mt-2 min-w-0 truncate">{delta}</div>}
    </div>
  );
}
