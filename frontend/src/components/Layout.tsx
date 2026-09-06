// Application shell: sticky sidebar navigation + top header. Information-dense
// and professional — built for a large-screen SIH jury demonstration.

import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  AirVent,
  BarChart3,
  BookOpen,
  Building2,
  CalendarClock,
  ClipboardCheck,
  Gauge,
  Menu,
  Radar,
  Route,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import { DemoBadge } from "./DemoBadge";
import { useOverview } from "../hooks/useApi";
import { DeltaBadge } from "./badges";
import { formatDateTime } from "../lib/format";

const NAV = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/index", label: "Airfare Index", icon: TrendingUp },
  { to: "/routes", label: "Routes", icon: Route },
  { to: "/airlines", label: "Airlines", icon: Building2 },
  { to: "/lead-time", label: "Lead Time", icon: CalendarClock },
  { to: "/quality", label: "Data Quality", icon: ClipboardCheck },
  { to: "/collection", label: "Collection Monitor", icon: Radar },
  { to: "/methodology", label: "Methodology", icon: BookOpen },
  { to: "/api", label: "API / Data Access", icon: Activity },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="flex items-center gap-2.5 px-4 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent text-white">
          <AirVent className="h-5 w-5" />
        </div>
        <div>
          <div className="text-base font-bold tracking-tight text-ink-900">APIx</div>
          <div className="text-[10px] leading-tight text-ink-400">Airfare Price Index · India</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
              }`
            }
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-4">
        <div className="rounded-lg border border-ink-100 bg-ink-50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">Methodology</p>
          <p className="mt-0.5 text-xs text-ink-600">v1.0.0 · Provisional weights</p>
        </div>
      </div>
    </>
  );
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: overview } = useOverview();

  return (
    <div className="flex h-full min-h-screen bg-ink-50">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-200 bg-white lg:flex">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink-900/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-white">
            <button
              className="absolute right-3 top-3 text-ink-400"
              onClick={() => setMobileOpen(false)}
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top header */}
        <header className="sticky top-0 z-30 border-b border-ink-200 bg-white/90 backdrop-blur">
          <div className="flex items-center gap-4 px-4 py-3 sm:px-6">
            <button
              className="rounded-lg p-2 text-ink-500 hover:bg-ink-100 lg:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-base font-bold text-ink-900">Real-Time Airfare Price Index</h1>
              <p className="hidden text-[11px] text-ink-400 sm:block">
                High-frequency airfare intelligence for CPI augmentation
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <DemoBadge />
              {overview?.current_apix != null && (
                <div className="hidden items-center gap-2 md:flex">
                  <DeltaBadge value={overview.daily_change} />
                  <span className="text-xs text-ink-400">
                    Last run {formatDateTime(overview.last_run_at)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
