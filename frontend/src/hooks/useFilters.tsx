// Global filter state shared across dashboard visualizations.
// Syncs to the URL query string so filters survive navigation / refresh.

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

export interface Filters {
  route: string | null;
  airline: string | null;
  source: string | null;
}

interface FilterContextValue extends Filters {
  setRoute: (v: string | null) => void;
  setAirline: (v: string | null) => void;
  setSource: (v: string | null) => void;
  clear: () => void;
  hasFilters: boolean;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const route = params.get("route") || null;
  const airline = params.get("airline") || null;
  const source = params.get("source") || null;

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value && value !== "ALL") next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const value = useMemo<FilterContextValue>(
    () => ({
      route,
      airline,
      source,
      setRoute: (v) => update("route", v),
      setAirline: (v) => update("airline", v),
      setSource: (v) => update("source", v),
      hasFilters: !!(route || airline || source),
      clear: () => setParams({}, { replace: true }),
    }),
    [route, airline, source, params],
  );

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used inside FiltersProvider");
  return ctx;
}
