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
  Database,
  Gauge,
  Menu,
  Radar,
  Route,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import { DataModeBadge } from "./DemoBadge";
import { DataSourceToggle } from "./DataSourceToggle";
import { useOverview } from "../hooks/useApi";
import { useDataSource } from "../hooks/useDataSource";
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
  { to: "/live-feed", label: "Live Feed (Scraper)", icon: Database },
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
  const { isLive, mode, daysCollected, counts, ready } = useDataSource();
  const [bannerHidden, setBannerHidden] = useState(false);

  // A young live store legitimately has one day of data. Say what that means for
  // the index instead of letting a flat 100.0 line look like a real result.
  const thinLiveIndex = isLive && (daysCollected || 0) < 8;
  const thinNotice = thinLiveIndex
    ? `Live mode is serving ${counts?.valid_observations ?? 0} index-eligible observations from ` +
      `${daysCollected || 1} collection day(s). APIx is rebased to 100 against its own base period, so the trend is ` +
      `flat by construction until ≥8 days (and ideally 30+) have accrued. Switch back to Demo data for the ` +
      `full 90-day history.`
    : null;

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
              <DataSourceToggle />
              <DataModeBadge />
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
          {thinNotice && !bannerHidden && (
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <Database className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <p className="text-xs leading-relaxed text-amber-800">
                <span className="font-semibold">Live data is thin — this is expected, not an error.</span> {thinNotice}
              </p>
              <button
                onClick={() => setBannerHidden(true)}
                className="ml-auto shrink-0 rounded-md px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
              >
                Dismiss
              </button>
            </div>
          )}
          {mode === "live" && !isLive && ready && (
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-800">
              <Radar className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                <span className="font-semibold">Live mode requested — no observations stored yet.</span> The screens below are
                still on demo data so nothing looks broken. Open <span className="font-mono">Live Feed (Scraper)</span> and run a
                sweep, or check that an adapter is enabled via <span className="font-mono">APIX_COLLECTOR_SOURCES</span>.
              </p>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
