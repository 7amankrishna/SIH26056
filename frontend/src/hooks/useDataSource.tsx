// Data-source mode: the single place that decides whether the dashboard shows
// scraped (live) data or the deterministic demo dataset.
//
// The switch is server-side state (persisted in SQLite), not just React state:
// every screen reads the same `/api/*` endpoints, and the backend decides which
// dataset to serve. That keeps the whole dashboard consistent — one toggle flips
// Overview, Index, Routes, Airlines, Quality and the Collection Monitor at once,
// and the selection survives a refresh or a shared link (?source=live).

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { DataMode, StoreCounts } from "../lib/types";

const URL_PARAM = "source";

interface DataSourceValue {
  /** what the user asked for */
  mode: DataMode;
  /** what the API is actually serving (live falls back to demo until data lands) */
  effectiveMode: DataMode;
  isLive: boolean;
  isDemo: boolean;
  ready: boolean;
  busy: boolean;
  collecting: boolean;
  note?: string | null;
  /** APIX_DATA_MODE pins the source server-side; the UI must not pretend to switch. */
  locked: boolean;
  counts?: StoreCounts;
  daysCollected: number;
  lastSweepError?: string | null;
  setMode: (mode: DataMode) => void;
  toggle: () => void;
  collectNow: () => void;
  refresh: () => void;
}

const Ctx = createContext<DataSourceValue | null>(null);

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [collecting, setCollecting] = useState(false);

  const statusQ = useQuery({
    queryKey: ["collect-status"],
    queryFn: api.collectStatus,
    // While live mode is on, the run log is the story — keep it moving.
    refetchInterval: (q) => (q.state.data?.mode === "live" ? 5_000 : 60_000),
  });

  const stateQ = useQuery({ queryKey: ["data-source"], queryFn: api.dataSource, refetchInterval: 60_000 });

  // URL wins on first load, so a link can hand someone the live view directly.
  const initial = useMemo<DataMode | null>(() => {
    const fromUrl = new URLSearchParams(window.location.search).get(URL_PARAM);
    return fromUrl === "live" || fromUrl === "demo" ? fromUrl : null;
  }, []);

  const serverMode = stateQ.data?.mode ?? statusQ.data?.mode ?? "demo";
  const mode: DataMode = initial ?? serverMode;

  const setModeMutation = useMutation({
    mutationFn: (next: DataMode) => api.setDataSource(next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["data-source"] });
      qc.invalidateQueries({ queryKey: ["collect-status"] });
      // Every analytical screen changes when the source changes.
      ["overview", "trend", "routes", "airlines", "leadtime", "distribution", "quality", "collection-runs", "stats-overview", "health"]
        .forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });

  const setMode = useCallback(
    (next: DataMode) => {
      setModeMutation.mutate(next);
      const params = new URLSearchParams(window.location.search);
      if (next === "live") params.set(URL_PARAM, "live");
      else params.delete(URL_PARAM);
      const qs = params.size ? `?${params}` : "";
      window.history.replaceState({}, "", `${window.location.pathname}${qs}`);
    },
    [setModeMutation],
  );

  const collectNow = useCallback(() => {
    setCollecting(true);
    // Promise.resolve() + try/catch: a sweep request must never be able to throw
    // synchronously out of a render effect (it would unmount the whole tree).
    try {
      Promise.resolve(api.runSweepBackground())
        .catch(() => undefined)
        .finally(() => {
          // Poll once quickly so the UI reflects the sweep that just landed.
          window.setTimeout(() => {
            qc.invalidateQueries({ queryKey: ["collect-status"] });
            qc.invalidateQueries({ queryKey: ["data-source"] });
            setCollecting(false);
          }, 1500);
        });
    } catch {
      setCollecting(false);
    }
  }, [qc]);

  // A live toggle with an empty store would be an empty screen; kick a sweep.
  // Skipped when the source is server-locked, since the request would 409.
  useEffect(() => {
    if (mode === "live" && stateQ.data && !stateQ.data.has_live_data && !stateQ.data.locked && !collecting) {
      collectNow();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, stateQ.data?.has_live_data, stateQ.data?.locked]);

  const store = statusQ.data?.store;
  const value: DataSourceValue = {
    mode,
    effectiveMode: (statusQ.data?.effective_mode ?? stateQ.data?.effective_mode ?? mode) as DataMode,
    isLive: (statusQ.data?.effective_mode ?? stateQ.data?.effective_mode) === "live",
    isDemo: (statusQ.data?.effective_mode ?? stateQ.data?.effective_mode ?? "demo") !== "live",
    ready: !statusQ.isLoading && !stateQ.isLoading,
    busy: setModeMutation.isPending,
    collecting,
    note: stateQ.data?.note ?? null,
    locked: Boolean(stateQ.data?.locked ?? statusQ.data?.mode_locked),
    counts: store,
    daysCollected: store?.days_collected ?? 0,
    lastSweepError: statusQ.data?.last_sweep_error ?? null,
    setMode,
    toggle: () => setMode(mode === "live" ? "demo" : "live"),
    collectNow,
    refresh: () => {
      qc.invalidateQueries({ queryKey: ["collect-status"] });
      qc.invalidateQueries({ queryKey: ["data-source"] });
    },
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDataSource(): DataSourceValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDataSource must be used inside DataSourceProvider");
  return ctx;
}

export function useCollectStatus(enabled = true) {
  return useQuery({
    queryKey: ["collect-status"],
    queryFn: api.collectStatus,
    enabled,
    refetchInterval: enabled ? 5_000 : false,
  });
}
