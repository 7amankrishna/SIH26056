// Card wrapper for charts with a consistent header (title, subtitle, controls).

import type { ReactNode } from "react";

export function ChartCard({
  title,
  subtitle,
  actions,
  children,
  className = "",
  pad = true,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  pad?: boolean;
}) {
  return (
    <div className={`card ${className}`}>
      <div className="flex items-start justify-between gap-3 border-b border-ink-100 px-5 py-3.5">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink-800">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div className={pad ? "p-5" : ""}>{children}</div>
    </div>
  );
}

// Shared custom tooltip for the index / route charts.
export function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-ink-200 bg-white/95 px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold text-ink-700">{label}</p>
      {payload.map((entry: any, i: number) => (
        <div key={i} className="mt-1 flex items-center justify-between gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-ink-500">
            <span className="h-2 w-2 rounded-full" style={{ background: entry.color || entry.stroke }} />
            {entry.name}
          </span>
          <span className="font-semibold tabular-nums text-ink-800">
            {typeof entry.value === "number" ? entry.value.toLocaleString("en-IN") : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}
