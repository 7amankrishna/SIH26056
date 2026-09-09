# UI Audit — APIx Dashboard

Scope: `frontend/` (React 18 + TypeScript + Vite + Tailwind 3 + Recharts).
Business logic, API calls and data flow were **not modified** — this audit drove
visual/UX-only changes.

---

## Phase 1 findings

### A. Color system (highest severity)

| # | Finding | Where |
| --- | --- | --- |
| A1 | **No dark mode.** `color-scheme: light` hardcoded; body/page/card colors hardcoded (`#f1f5f9`, `bg-white`); every chart/tooltip assumes a light canvas. | `index.css`, all pages |
| A2 | **Hardcoded hex outside tokens**: chart grid `#eef2f7`, series `#0891b2` / `#6366f1` / `#dc2626` / `#10b981`, axis ticks `#94a3b8` (CSS), sparkline default `#0891b2`, Recharts cursor `#f8fafc`, heatmap `rgba(220,38,38…)`/`rgba(16,185,129…)`/`rgba(14,116,144…)` computed in JS. | `IndexTrendChart`, `Routes`, `Airlines`, `LeadTime`, `Sparkline`, `RouteHeatmap`, `index.css` |
| A3 | Semantic chip colors (`bg-emerald-50 text-emerald-700`, `amber-*`, `red-*`, `sky-*`, `purple-*`, `orange-*`) are raw Tailwind palette values used ~120× — impossible to theme, and several combinations fail contrast in either theme. | `badges.tsx`, `DemoBadge`, `CollectionMonitor`, `LiveFeed`, … |
| A4 | Methodology formula block + LiveFeed JSON panes hardcode `bg-ink-900 text-ink-100` — a "dark code surface" that is not tokenized. | `Methodology.tsx`, `LiveFeed.tsx` |

### B. Contrast (WCAG)

| # | Finding | Where |
| --- | --- | --- |
| B1 | `text-ink-400` (`#94a3b8`, **2.77:1**) used 54× for meaningful secondary text (card subtitles, timestamps, hints, legend labels) — fails AA 4.5:1. | all pages |
| B2 | `text-ink-300` (`#cbd5e1`, **1.58:1**) for rank numerals and the route-table arrow. | `Overview`, `AirfareIndex` |
| B3 | White text on `bg-brand-600` (`#0891b2`, **3.93:1**) for primary buttons/active segments — fails AA for 12px labels. | `IndexTrendChart`, `RouteHeatmap`, `DataQuality`, `LiveFeed` |
| B4 | Heatmap cell value text is `text-ink-900/70` over alpha-blended red/green — unreadable at high alpha in light mode and unusable in dark. | `RouteHeatmap` |

### C. Heatmap tooltip (flagship bug)

| # | Finding |
| --- | --- |
| C1 | Tooltip is `position: absolute` inside an `overflow-x-auto` grid → clipped for the bottom rows (CSS computes `overflow-y: auto` too); the tooltip is literally unreadable/cut off where the matrix is tallest. |
| C2 | Double tooltip: the cell `<button>` also carries a native `title` attr, so the browser tooltip fights the custom one. |
| C3 | `z-20` (below header `z-30`), no `pointer-events` hardening beyond class, no backdrop blur, translucent `bg-white` lets heatmap colors bleed through at the edges. |
| C4 | Cell text/tooltip colors hardcoded light-only. |

### D. States & feedback

| # | Finding | Where |
| --- | --- | --- |
| D1 | **Spinners everywhere** instead of skeleton loaders; async charts/tables blank → spinner → content (layout jolt). `KpiCard` has a lone pulse box. | `DataState.tsx` + every page |
| D2 | Sticky table headers (`bg-white` / `bg-ink-50`) hardcode light surfaces. | `DataQuality`, `LiveFeed` |
| D3 | Empty/error states exist (good) but their retry buttons have no focus ring and inconsistent heights. | `DataState.tsx` |

### E. Interactive polish

| # | Finding | Where |
| --- | --- | --- |
| E1 | **No focus-visible treatment anywhere** — keyboard users cannot see where they are (links, buttons, nav, heatmap cells, toggle). | global |
| E2 | Button heights ad-hoc: `py-1 text-[11px]`, `py-1.5 text-xs`, `px-2.5 py-1.5`, `py-2`… no hierarchy (primary/secondary/ghost). | all pages |
| E3 | `DataSourceToggle` uses Sun/Moon icons for *data source* — collides with any theme toggle vocabulary. | `DataSourceToggle.tsx` |
| E4 | No hover transitions on cards/rankings; nav transitions exist but active-state indicator is a flat fill only. | `Layout`, `Overview` |
| E5 | Mobile drawer close button has no `aria-label`, no Escape-to-close, no focus ring. | `Layout.tsx` |

### F. Metadata / branding

| # | Finding | Where |
| --- | --- | --- |
| F1 | **No favicon** — browser 404s `/favicon.ico`; tab shows default glyph. | `index.html` |
| F2 | Single static `<title>` for all 10 routes; no `theme-color`; no OG tags. | `index.html` |
| F3 | Inter loaded from Google Fonts CDN — render-blocking, FOUT, and breaks the "fully offline demo" story. | `index.html` |

### G. Misc

| # | Finding | Where |
| --- | --- | --- |
| G1 | `DeltaBadge` icon has invalid class `-w-3` (typo). | `badges.tsx` |
| G2 | Scrollbars styled for light only. | `index.css` |
| G3 | `{health ? "/api" : "/api"}` dead ternary. | `APIPage.tsx` |
| G4 | No page-transition affordance; content pops on route change. | `Layout.tsx` |
| G5 | Charts>500 kB chunk warning (informational; code-splitting out of scope for visual pass). | build output |

---

## Phase 2 — design system (implemented)

Single source of truth: **CSS variables** (`frontend/src/index.css`) surfaced as
Tailwind tokens (`frontend/tailwind.config.js`). All colors are theme-aware
`rgb(var(--token) / <alpha-value>)` triplets; `.dark` on `<html>` flips every
token at once.

- **Type**: Inter Variable (self-hosted via `@fontsource-variable/inter`), scale 11/12/sm/14/base/lg/xl + `tabular-nums` for all figures.
- **Spacing**: 4px grid (Tailwind default) — no arbitrary px paddings.
- **Radii**: `rounded-md` (6) chips · `rounded-lg` (8) controls · `rounded-xl` (12) cards — nothing else.
- **Elevation**: 3 levels (`shadow-card`, `shadow-pop`, `shadow-overlay`), reduced in dark mode (borders carry elevation).
- **Color tokens**: `page / surface / elevated / code` surfaces, `ink-*` text+fill scale (inverts in dark), `brand-*` (cyan), `accent`, semantic scales (emerald/amber/red/sky/purple/orange) re-tuned for AA on both themes, dark glass `.tt` tooltip token.

## Phase 3 — what changed (visual only)

- Dark mode with `system` default, persisted, OS-synced, **no flash on load** (pre-paint inline script), Sun/Moon toggle in the header.
- Heatmap tooltip: portal-rendered, `position: fixed` (never clipped), solid dark-glass surface (`rgba(17,24,39,.95)` light / `rgba(28,28,34,.96)` dark), `backdrop-filter: blur(8px)`, `z-index: 60`, `pointer-events: none`, viewport-aware flip, native `title` removed, `aria-label` added.
- All charts/heatmaps/sparklines read a theme-aware palette hook (`useChartTheme`) — zero hardcoded hex left in components.
- Skeleton loaders (`Skeleton`, `SkeletonTable`, `SkeletonChart`, `SkeletonStats`) replace spinners in `DataBoundary` with per-context variants.
- Consistent button system (`.btn`, `.btn-sm`, `.btn-primary/-secondary/-ghost`), global `:focus-visible` rings, `prefers-reduced-motion` respected.
- Themed scrollbars, per-route document titles, SVG favicon, `theme-color`, self-hosted font, page fade transition, mobile-drawer a11y (aria + Escape), contrast upgrades (`ink-400→500` for body text, `brand-700` solid buttons, AA chip palette).
