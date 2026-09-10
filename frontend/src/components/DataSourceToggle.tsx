// The dashboard's data-source switch: scraped data vs demo data.
//
// Flipping it calls POST /api/data-source, which changes which dataset the
// *backend* serves — so every screen switches together and the choice persists
// across reloads. The control also surfaces the truth about the live path:
// how much has been collected, whether the collector is actually running, and
// the last block/failure if there was one. A live indicator that could be green
// while the source is blocked would be worse than no indicator at all.

import { useCallback } from "react";
import { AlertTriangle, Database, Loader2, Moon, RefreshCw, Sun } from "lucide-react";
import { useDataSource } from "../hooks/useDataSource";
import type { DataMode } from "../lib/types";

const OPTIONS: { id: DataMode; label: string; icon: typeof Sun; hint: string }[] = [
  { id: "demo", label: "Demo data", icon: Moon, hint: "Deterministic synthetic dataset — offline, reproducible (replaced by your own files in data/ when present)" },
  { id: "live", label: "Scraper", icon: Sun, hint: "Fares collected by the background collection engine" },
];

export function DataSourceToggle({ withCollectButton = true }: { withCollectButton?: boolean }) {
  const { mode, isLive, isCustom, busy, collecting, setMode, collectNow, counts, note, locked, actionError, storeAvailable, storeNote, dataFiles } = useDataSource();

  // When the user's own files are loaded, the "demo" position really means
  // "your data" — the label has to say which one is being served.
  const offlineLabel = isCustom ? "Your data" : "Demo data";
  const offlineHint = isCustom
    ? `${(dataFiles?.totals?.observations ?? 0).toLocaleString("en-IN")} observations imported from ${dataFiles?.files?.length ?? 0} file(s) in ${dataFiles?.data_dir ?? "data/"}`
    : "Deterministic synthetic dataset — offline, reproducible";

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
    <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 min-w-0">
      {withCollectButton && (
        <button
          onClick={collectNow}
          disabled={collecting || busy}
          title="Run one collection sweep now (POST /api/collect/sweep)"
          className="btn btn-sm btn-secondary hidden sm:inline-flex shrink-0"
        >
          {collecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          <span className="hidden md:inline">{collecting ? "Collecting…" : "Collect now"}</span>
          <span className="md:hidden">{collecting ? "…" : "Collect"}</span>
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
            ? "Serving data collected by the scraper — click to switch back"
            : `${offlineHint} — click to serve scraped data`
        }
        className={`group relative inline-flex select-none items-center rounded-lg border p-0.5 transition-colors shrink-0 ${
          locked ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        } ${mode === "live" ? "border-emerald-300 bg-emerald-50" : "border-ink-200 bg-ink-100"}`}
      >
        {/* sliding knob */}
        <span
          className={`absolute top-0.5 h-[26px] w-[76px] sm:w-[86px] rounded-md bg-surface shadow-card ring-1 transition-transform duration-200 ${
            mode === "live" ? "translate-x-[76px] sm:translate-x-[86px]" : "translate-x-0"
          }`}
          style={{ "--tw-ring-color": "rgb(var(--ink-900) / 0.1)" } as React.CSSProperties}
          aria-hidden
        />
        {OPTIONS.map((opt) => {
          const active = mode === opt.id;
          return (
            <span
              key={opt.id}
              title={opt.id === "demo" ? offlineHint : opt.hint}
              className={`relative z-10 flex h-[26px] w-[76px] sm:w-[86px] items-center justify-center gap-1 sm:gap-1.5 text-[10.5px] sm:text-[11px] font-semibold transition-colors ${
                active ? "text-ink-900" : "text-ink-500 group-hover:text-ink-600"
              }`}
            >
              <opt.icon className={`h-3 w-3 shrink-0 ${opt.id === "live" && active ? "text-emerald-700" : ""}`} />
              <span className="truncate">{opt.id === "demo" ? offlineLabel : opt.label}</span>
            </span>
          );
        })}
        {busy && <Loader2 className="absolute -right-1 -top-1 h-3 w-3 animate-spin text-brand-600" />}
      </div>

      {/* A refused switch or a store that cannot persist is never silent. */}
      {(actionError || (!locked && storeAvailable === false)) && (
        <span
          className="chip max-w-[140px] sm:max-w-[240px] truncate bg-red-50 text-red-700"
          title={actionError ?? storeNote ?? "The collection store is unavailable on this deployment."}
        >
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span className="truncate">{actionError ?? "collection store unavailable"}</span>
        </span>
      )}

      {/* Imported-data readout: what your files actually contain. */}
      {mode !== "live" && isCustom && (
        <span
          className="chip hidden lg:inline-flex"
          title={
            (dataFiles?.files ?? []).map((f) => `${f.name}: ${f.observations.toLocaleString("en-IN")} obs`).join("\n") ||
            "imported files"
          }
        >
          <Database className="h-3 w-3 shrink-0" />
          {(dataFiles?.totals?.observations ?? 0).toLocaleString("en-IN")} obs · {dataFiles?.totals?.routes ?? 0} routes
        </span>
      )}

      {/* Live-mode status readout: what the scraper has actually stored. */}
      {mode === "live" && (
        <span
          className={`chip hidden lg:inline-flex ${
            isLive ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
          }`}
          title={isLive ? `${stored.toLocaleString("en-IN")} observations in the collection store` : (note ?? "Nothing collected yet")}
        >
          {!isLive && <AlertTriangle className="h-3 w-3 shrink-0" />}
          {isLive ? (
            <>
              <span className="relative flex h-1.5 w-1.5 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              <span>{stored.toLocaleString("en-IN")} obs · {counts?.days_collected ?? 0}d</span>
            </>
          ) : (
            <span>waiting for first sweep</span>
          )}
        </span>
      )}
    </div>
  );
}
