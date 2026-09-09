// Application shell: institutional navy sidebar + contextual top header.
// Information-dense and professional — built for a large-screen SIH jury
// demonstration. The sidebar keeps a fixed government/aviation treatment in
// both themes; the content area follows the user's theme.

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  Building2,
  CalendarClock,
  Database,
  Gauge,
  Landmark,
  Menu,
  Plane,
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

const NAV_SECTIONS = [
  {
    title: "Intelligence",
    items: [
      { to: "/", label: "Overview", icon: Gauge, end: true },
      { to: "/index", label: "Airfare Index", icon: TrendingUp },
      { to: "/routes", label: "Routes", icon: Route },
      { to: "/airlines", label: "Airlines", icon: Building2 },
      { to: "/lead-time", label: "Lead Time", icon: CalendarClock },
    ],
  },
  {
    title: "Operations",
    items: [
      { to: "/collection", label: "Collection Monitor", icon: Radar },
      { to: "/api", label: "API / Data Access", icon: Activity },
    ],
  },
];

const FLAT_NAV = NAV_SECTIONS.flatMap((s) => s.items);

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      {/* Brand — mark and wordmark rendered ~20% larger than the previous
          36px / 16px treatment (44px mark, 20px wordmark). */}
      <div className="flex items-center gap-3 px-4 pb-5 pt-6">
        <div className="brand-mark flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white">
          <Plane className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <div className="brand-wordmark text-xl font-extrabold tracking-tight">
            APIx
          </div>
          <div className="text-[11px] leading-tight text-[#93a5c4]">
            Real-Time Airfare Price Index · India
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4" aria-label="Primary">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            <p className="sidebar-kicker mb-1.5">{section.title}</p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `sidebar-nav-item ${isActive ? "sidebar-nav-item-active" : ""}`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Government / statistical identity — neutral placeholder seal,
          deliberately not an official emblem. */}
      <div className="px-4 pb-3">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3.5">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#7dd3fc]/30 bg-[#38bdf8]/10 text-[#7dd3fc]">
              <Landmark className="h-[18px] w-[18px]" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7dd3fc]/90">
                A prototype for
              </p>
              <p className="mt-0.5 text-xs font-medium leading-snug text-[#e2e8f0]">
                Ministry of Statistics &amp; Programme Implementation
              </p>
              <p className="mt-1 text-[11px] leading-snug text-[#93a5c4]">
                High-frequency airfare intelligence for CPI augmentation
              </p>
            </div>
          </div>
        </div>
      </div>
      <p className="px-4 pb-4 text-[10px] text-[#7d8db1]">v0.1.0 · SIH26056</p>
    </>
  );
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: overview } = useOverview();
  const { isLive, isCustom, mode, daysCollected, counts, ready, dataFiles } = useDataSource();
  const [bannerHidden, setBannerHidden] = useState(false);
  const [dataBannerHidden, setDataBannerHidden] = useState(false);
  const location = useLocation();

  // Contextual title for the top header (rendered as a paragraph so the
  // page-level h2 headings keep the document outline).
  const current =
    FLAT_NAV.find((item) =>
      item.end
        ? location.pathname === item.to
        : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`),
    ) ?? FLAT_NAV[0];

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
      <aside className="sidebar-surface sticky top-0 z-20 hidden h-screen w-64 shrink-0 flex-col lg:flex">
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
          <aside className="sidebar-surface absolute left-0 top-0 flex h-full w-64 flex-col overflow-y-auto shadow-overlay">
            <button
              className="absolute right-3 top-3 rounded-md p-1 text-[#93a5c4] transition-colors hover:bg-white/10 hover:text-white"
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
              <p className="truncate text-base font-bold text-ink-900">
                {current.label}
              </p>
              <p className="hidden text-[11px] text-ink-500 sm:block">
                High-frequency airfare intelligence for CPI augmentation
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <DataSourceToggle />
              <div className="hidden sm:block">
                <DataModeBadge />
              </div>
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
            {isCustom && !dataBannerHidden && (dataFiles?.notes?.length ?? 0) > 0 && (
              <div className="mb-4 flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
                <Database className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" />
                <p className="text-xs leading-relaxed text-sky-800">
                  <span className="font-semibold">Serving your imported data.</span>{" "}
                  {dataFiles?.notes?.[0]}
                  {dataFiles?.files?.length ? (
                    <>
                      {" "}Files:{" "}
                      <span className="font-mono">{dataFiles.files.map((f) => f.name).join(", ")}</span>
                    </>
                  ) : null}
                  {overview?.index_coverage && !overview.index_coverage.complete ? (
                    <>
                      {" "}The latest day covers{" "}
                      <span className="font-semibold">
                        {overview.index_coverage.routes}/{overview.index_coverage.basket_routes} routes
                      </span>{" "}
                      ({Math.round(overview.index_coverage.weight * 100)}% of basket weight), so the
                      headline index is renormalised over those routes only.
                    </>
                  ) : null}
                </p>
                <button
                  onClick={() => setDataBannerHidden(true)}
                  className="ml-auto shrink-0 rounded-md px-2 py-1 text-[11px] font-medium text-sky-700 transition-colors hover:bg-sky-100"
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
                  still on demo data so nothing looks broken. Run a sweep from the{" "}
                  <span className="font-mono">Collection Monitor</span>, or check that an adapter is enabled via{" "}
                  <span className="font-mono">APIX_COLLECTOR_SOURCES</span>.
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
