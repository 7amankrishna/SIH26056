// Compact, consistent KPI / stat card used across the dashboard.

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
    <div className="card relative overflow-hidden p-4 transition-shadow duration-200 hover:shadow-pop">
      {accent && (
        <span
          className="absolute inset-x-0 top-0 h-1"
          style={{ background: accent }}
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
          <div
            className="shrink-0 rounded-lg p-1.5 text-ink-500"
            style={{ background: "rgb(var(--ink-900) / 0.05)" }}
          >
            {icon}
          </div>
        )}
      </div>
      {delta && <div className="mt-2">{delta}</div>}
    </div>
  );
}
