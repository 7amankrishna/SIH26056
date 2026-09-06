// The dashboard's data-source switch: scraped data vs demo data.
//
// Flipping it calls POST /api/data-source, which changes which dataset the
// *backend* serves — so every screen switches together and the choice persists
// across reloads. The control also surfaces the truth about the live path:
// how much has been collected, whether the collector is actually running, and
// the last block/failure if there was one. A live indicator that could be green
// while the source is blocked would be worse than no indicator at all.

import { useCallback } from "react";
import { AlertTriangle, Loader2, Moon, RefreshCw, Sun } from "lucide-react";
import { useDataSource } from "../hooks/useDataSource";
import type { DataMode } from "../lib/types";

const OPTIONS: { id: DataMode; label: string; icon: typeof Sun; hint: string }[] = [
  { id: "demo", label: "Demo data", icon: Moon, hint: "Deterministic synthetic dataset — offline, reproducible" },
  { id: "live", label: "Scraper", icon: Sun, hint: "Fares collected by the background collection engine" },
];

export function DataSourceToggle({ withCollectButton = true }: { withCollectButton?: boolean }) {
  const { mode, isLive, busy, collecting, setMode, collectNow, counts, note, locked } = useDataSource();

  const onKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (locked) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setMode(mode === "live" ? "demo" : "live");
      }
    },
    [mode, setMode, locked],
  );

  const stored = counts?.observations ?? 0;
  if (locked) {
    return (
      <span
        className="chip border border-ink-200 bg-ink-50 text-ink-500"
        title="APIX_DATA_MODE is set on the server, so the data source is pinned and the switch is disabled."
      >
        {mode === "live" ? "scraper (locked)" : "demo (locked)"}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {withCollectButton && (
        <button
          onClick={collectNow}
          disabled={collecting || busy}
          title="Run one collection sweep now (POST /api/collect/sweep)"
          className="hidden items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-xs font-medium text-ink-600 transition-colors hover:bg-ink-50 disabled:opacity-50 sm:inline-flex"
        >
          {collecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          {collecting ? "Collecting…" : "Collect now"}
        </button>
      )}

      <div
        role="switch"
        aria-checked={mode === "live"}
        aria-disabled={locked || undefined}
        tabIndex={locked ? -1 : 0}
        onKeyDown={onKey}
        onClick={() => !busy && !locked && setMode(mode === "live" ? "demo" : "live")}
        title={
          mode === "live"
            ? "Serving data collected by the scraper — click to switch to demo data"
            : "Serving the deterministic demo dataset — click to serve scraped data"
        }
        className={`group relative inline-flex select-none items-center rounded-lg border p-0.5 transition-colors ${
          locked ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        } ${mode === "live" ? "border-emerald-300 bg-emerald-50" : "border-ink-200 bg-ink-100"}`}
      >
        {/* sliding knob */}
        <span
          className={`absolute top-0.5 h-[26px] w-[86px] rounded-md bg-white shadow-sm ring-1 ring-ink-200 transition-transform duration-200 ${
            mode === "live" ? "translate-x-[86px]" : "translate-x-0"
          }`}
          aria-hidden
        />
        {OPTIONS.map((opt) => {
          const active = mode === opt.id;
          return (
            <span
              key={opt.id}
              title={opt.hint}
              className={`relative z-10 flex h-[26px] w-[86px] items-center justify-center gap-1.5 text-[11px] font-semibold transition-colors ${
                active ? "text-ink-900" : "text-ink-400 group-hover:text-ink-600"
              }`}
            >
              <opt.icon className={`h-3 w-3 ${opt.id === "live" && active ? "text-emerald-600" : ""}`} />
              {opt.label}
            </span>
          );
        })}
        {busy && <Loader2 className="absolute -right-1 -top-1 h-3 w-3 animate-spin text-brand-600" />}
      </div>

      {/* Live-mode status readout: what the scraper has actually stored. */}
      {mode === "live" && (
        <span
          className={`chip hidden md:inline-flex ${
            isLive ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
          }`}
          title={isLive ? `${stored.toLocaleString("en-IN")} observations in the collection store` : (note ?? "Nothing collected yet")}
        >
          {!isLive && <AlertTriangle className="h-3 w-3" />}
          {isLive ? (
            <>
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              {stored.toLocaleString("en-IN")} obs · {counts?.days_collected ?? 0}d
            </>
          ) : (
            "waiting for first sweep"
          )}
        </span>
      )}
    </div>
  );
}
