// Compact, consistent KPI / stat card used across the dashboard.

import type { ReactNode } from "react";

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
    <div className="card relative overflow-hidden p-4">
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
            <div className="mt-2 h-8 w-24 animate-pulse rounded bg-ink-100" />
          ) : (
            <p className="kpi-value mt-1 truncate">{value}</p>
          )}
          {sub && <div className="mt-1 text-xs text-ink-400">{sub}</div>}
        </div>
        {icon && <div className="shrink-0 text-ink-300">{icon}</div>}
      </div>
      {delta && <div className="mt-2">{delta}</div>}
    </div>
  );
}
