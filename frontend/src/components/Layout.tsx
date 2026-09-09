// Application shell: sticky sidebar navigation + top header. Information-dense
// and professional — built for a large-screen SIH jury demonstration.

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  AirVent,
  BookOpen,
  Building2,
  CalendarClock,
  ClipboardCheck,
  Database,
  Gauge,
  Menu,
  Radar,
  Route,
  TrendingUp,
  X,
} from "lucide-react";
import { DataModeBadge } from "./DemoBadge";
import { DataSourceToggle } from "./DataSourceToggle";
import { ThemeToggle } from "./ThemeToggle";
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
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-accent text-white shadow-card">
          <AirVent className="h-5 w-5" />
        </div>
        <div>
          <div className="text-base font-bold tracking-tight text-ink-900">APIx</div>
          <div className="text-[10px] leading-tight text-ink-500">Airfare Price Index · India</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3" aria-label="Primary">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? "bg-brand-50 text-brand-700 dark:text-brand-300"
                  : "text-ink-600 hover:bg-ink-100 hover:text-ink-900"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {/* active indicator */}
                <span
                  aria-hidden
                  className={`absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-brand-600 transition-opacity duration-150 ${
                    isActive ? "opacity-100" : "opacity-0"
                  }`}
                />
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-4">
        <div className="rounded-lg border border-ink-200 bg-ink-50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">Methodology</p>
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
  const location = useLocation();

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

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
    <div className="flex h-full min-h-screen bg-page">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[70] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-ink-900 focus:shadow-overlay"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-200 bg-surface lg:flex"
        style={{ borderColor: "rgb(var(--ink-900) / 0.08)" }}>
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-surface shadow-overlay">
            <button
              className="absolute right-3 top-3 rounded-md p-1 text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-800"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation menu"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top header */}
        <header
          className="sticky top-0 z-30 border-b bg-surface/85 backdrop-blur-md"
          style={{ borderColor: "rgb(var(--ink-900) / 0.08)" }}
        >
          <div className="flex items-center gap-4 px-4 py-3 sm:px-6">
            <button
              className="btn btn-ghost -ml-2 p-2 lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-base font-bold text-ink-900">Real-Time Airfare Price Index</h1>
              <p className="hidden text-[11px] text-ink-500 sm:block">
                High-frequency airfare intelligence for CPI augmentation
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <DataSourceToggle />
              <DataModeBadge />
              <ThemeToggle />
              {overview?.current_apix != null && (
                <div className="hidden items-center gap-2 md:flex">
                  <DeltaBadge value={overview.daily_change} />
                  <span className="text-xs text-ink-500">
                    Last run {formatDateTime(overview.last_run_at)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>

        <main id="main" className="flex-1 px-4 py-6 sm:px-6">
          {/* keyed remount gives each route a 160ms ease-out entrance */}
          <div key={location.pathname} className="page-enter">
            {thinNotice && !bannerHidden && (
              <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                <Database className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <p className="text-xs leading-relaxed text-amber-800">
                  <span className="font-semibold">Live data is thin — this is expected, not an error.</span> {thinNotice}
                </p>
                <button
                  onClick={() => setBannerHidden(true)}
                  className="ml-auto shrink-0 rounded-md px-2 py-1 text-[11px] font-medium text-amber-700 transition-colors hover:bg-amber-100"
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
          </div>
        </main>
      </div>
    </div>
  );
}
