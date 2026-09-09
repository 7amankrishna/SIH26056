// Card wrapper for charts with a consistent header (title, subtitle, controls),
// and the shared chart tooltip used by every Recharts view.
//
// The tooltip uses the `.tt` token: solid near-opaque dark glass in BOTH
// themes, backdrop blur, z-index 60, pointer-events none — readable over any
// series color, light or dark canvas.

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
      <div
        className="flex items-start justify-between gap-3 border-b px-5 py-3.5"
        style={{ borderColor: "rgb(var(--ink-900) / 0.07)" }}
      >
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink-800">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
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
    <div className="tt">
      <p className="tt-label">{label}</p>
      {payload.map((entry: any, i: number) => (
        <div key={i} className="mt-1 flex items-center justify-between gap-4 text-xs">
          <span className="tt-key flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: entry.color || entry.stroke }} />
            {entry.name}
          </span>
          <span className="tt-val">
            {typeof entry.value === "number" ? entry.value.toLocaleString("en-IN") : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}
