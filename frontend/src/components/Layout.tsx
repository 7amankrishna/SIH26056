// Application shell: institutional navy sidebar + contextual top header.
// Information-dense and professional — built for a large-screen SIH jury
// demonstration. The sidebar keeps a fixed government/aviation treatment in
// both themes; the content area follows the user's theme.

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Building2,
  CalendarClock,
  Database,
  Gauge,
  Landmark,
  Menu,
  Plane,
  Route,
  TrendingUp,
  Upload,
  X,
} from "lucide-react";
import { DataModeBadge } from "./DemoBadge";
import { DataSourceToggle } from "./DataSourceToggle";
import { ThemeToggle } from "./ThemeToggle";
import { useOverview } from "../hooks/useApi";
import { useDataSource } from "../hooks/useDataSource";
import { DeltaBadge } from "./badges";
import { formatDateTime } from "../lib/format";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/index", label: "Airfare Index", icon: TrendingUp },
  { to: "/routes", label: "Routes", icon: Route },
  { to: "/airlines", label: "Airlines", icon: Building2 },
  { to: "/lead-time", label: "Lead Time", icon: CalendarClock },
  { to: "/import", label: "Import Data", icon: Upload },
  { to: "/methodology", label: "Methodology", icon: BookOpen },
  { to: "/api", label: "API / Data Access", icon: Activity },
];

const FLAT_NAV = NAV_ITEMS;

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col justify-between overflow-hidden">
      <div className="flex min-h-0 flex-col">
        {/* Brand */}
        <div className="flex items-center gap-3 px-4 pb-3 pt-5 shrink-0">
          <div className="brand-mark flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-md">
            <Plane className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="brand-wordmark text-xl font-extrabold tracking-tight leading-tight">
              APIx
            </div>
            <div className="text-[11px] leading-tight text-[#93a5c4] truncate">
              Real-Time Airfare Index · India
            </div>
          </div>
        </div>

        {/* Primary Navigation items */}
        <nav className="flex-1 space-y-0.5 px-3 py-2 overflow-y-auto" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
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
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Government / statistical identity */}
      <div className="border-t border-white/10 px-4 py-3 shrink-0 bg-black/15">
        <div className="flex items-center gap-3">
          <img 
            src="https://upload.wikimedia.org/wikipedia/commons/5/55/Emblem_of_India.svg" 
            alt="Government of India"
            className="h-8 w-auto opacity-75 shrink-0"
            style={{ filter: "brightness(0) invert(1)" }}
          />
          <div className="min-w-0 text-[10.5px] leading-snug text-[#93a5c4]">
            <p className="font-semibold text-white/90">Ministry of Statistics (MoSPI)</p>
            <p className="text-[9.5px] text-[#8598be]">CPI Augmentation Prototype</p>
            <p className="text-[9px] text-[#6d7e9f]">v0.1.0 · SIH26056</p>
          </div>
        </div>
      </div>
    </div>
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
    <div className="flex h-full min-h-screen bg-page w-full max-w-full">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[70] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-ink-900 focus:shadow-overlay"
      >
        Skip to content
      </a>

      {/* Desktop sidebar — sticky top-0 h-screen follows viewport naturally without blank gaps */}
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

      <div className="flex min-w-0 flex-1 flex-col max-w-full">
        {/* Top header */}
        <header
          className="sticky top-0 z-30 w-full max-w-full border-b bg-surface/85 backdrop-blur-md"
          style={{ borderColor: "rgb(var(--ink-900) / 0.08)" }}
        >
          <div className="flex items-center justify-between gap-2 px-3 py-2.5 sm:gap-4 sm:px-6 sm:py-3 min-w-0 max-w-full">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0 shrink">
              <button
                className="btn btn-ghost -ml-1 p-1.5 sm:-ml-2 sm:p-2 lg:hidden shrink-0"
                onClick={() => setMobileOpen(true)}
                aria-label="Open navigation menu"
              >
                <Menu className="h-5 w-5" />
              </button>
              <div className="min-w-0 truncate">
                <p className="truncate text-sm sm:text-base font-bold text-ink-900 leading-tight">
                  {current.label}
                </p>
                <p className="hidden text-[11px] text-ink-500 xl:block truncate">
                  High-frequency airfare intelligence for CPI augmentation
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 min-w-0">
              <DataSourceToggle />
              <div className="hidden md:block shrink-0">
                <DataModeBadge />
              </div>
              <div className="shrink-0">
                <ThemeToggle />
              </div>
              {overview?.current_apix != null && (
                <div className="hidden items-center gap-2 xl:flex shrink-0">
                  <DeltaBadge value={overview.daily_change} />
                  <span className="text-xs text-ink-500">
                    Last run {formatDateTime(overview.last_run_at)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>

        <main id="main" className="flex-1 min-w-0 max-w-full px-4 py-6 sm:px-6">
          {/* keyed remount gives each route a 160ms ease-out entrance */}
          <div key={location.pathname} className="page-enter min-w-0 max-w-full">
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
                <Activity className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                  <span className="font-semibold">Live mode requested — no observations stored yet.</span> The screens below are
                  still on demo data so nothing looks broken. Use the scraper control in the header, or check that an adapter is
                  enabled via <span className="font-mono">APIX_COLLECTOR_SOURCES</span>.
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
