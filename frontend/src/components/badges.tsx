// Semantic badges and delta indicators.

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { formatPercent } from "../lib/format";

export function DeltaBadge({
  value,
  suffix = "%",
  className = "",
}: {
  value: number | null | undefined;
  suffix?: string;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return (
      <span className={`chip bg-ink-100 text-ink-500 ${className}`}>—</span>
    );
  }
  const up = value > 0;
  const down = value < 0;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const cls = up
    ? "bg-red-50 text-red-600"
    : down
      ? "bg-emerald-50 text-emerald-700"
      : "bg-ink-100 text-ink-500";
  return (
    <span className={`chip ${cls} ${className}`}>
      <Icon className="h-3 w-3" />
      {value > 0 ? "+" : ""}
      {value.toFixed(1)}
      {suffix}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    healthy: { label: "Healthy", cls: "bg-emerald-50 text-emerald-700" },
    degraded: { label: "Degraded", cls: "bg-amber-50 text-amber-700" },
    disabled: { label: "Disabled", cls: "bg-ink-100 text-ink-500" },
    ready: { label: "Ready", cls: "bg-sky-50 text-sky-700" },
    active: { label: "Active", cls: "bg-emerald-50 text-emerald-700" },
    VALID: { label: "Valid", cls: "bg-emerald-50 text-emerald-700" },
    SUSPICIOUS: { label: "Suspicious", cls: "bg-amber-50 text-amber-700" },
    DUPLICATE: { label: "Duplicate", cls: "bg-ink-100 text-ink-600" },
    INVALID: { label: "Invalid", cls: "bg-red-50 text-red-700" },
    SOLD_OUT: { label: "Sold out", cls: "bg-orange-50 text-orange-700" },
    STALE: { label: "Stale", cls: "bg-purple-50 text-purple-700" },
    MISSING: { label: "Missing", cls: "bg-ink-100 text-ink-500" },
  };
  const m = map[status] ?? { label: status, cls: "bg-ink-100 text-ink-600" };
  return <span className={`chip ${m.cls}`}>{m.label}</span>;
}
