// Global filter bar. Shared filters update all relevant visualizations and
// are synchronized to the URL.

import { RotateCcw } from "lucide-react";
import { useFilters } from "../hooks/useFilters";
import { useAirlines, useRoutes } from "../hooks/useApi";

function Select({
  value,
  onChange,
  options,
  placeholder,
  label,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  options: { value: string; label: string }[];
  placeholder: string;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-ink-500">
      <span className="uppercase tracking-wide">{label}</span>
      <select
        value={value ?? "ALL"}
        onChange={(e) => onChange(e.target.value === "ALL" ? null : e.target.value)}
        className="h-8 rounded-lg border bg-surface px-2.5 text-sm text-ink-700 shadow-card outline-none transition-colors duration-150 hover:border-ink-300 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
        style={{ borderColor: "rgb(var(--ink-900) / 0.14)" }}
      >
        <option value="ALL">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function FilterBar() {
  const { route, airline, source, setRoute, setAirline, setSource, clear, hasFilters } = useFilters();
  const { data: routesData } = useRoutes();
  const { data: airlinesData } = useAirlines();

  const routeOptions = (routesData?.routes ?? []).map((r) => ({
    value: r.route,
    label: `${r.origin_city} → ${r.destination_city}`,
  }));
  const airlineOptions = (airlinesData?.airlines ?? []).map((a) => ({
    value: a.airline,
    label: `${a.name} (${a.airline})`,
  }));

  return (
    <div className="card flex flex-wrap items-center gap-3 px-4 py-2.5">
      <span className="kpi-label">Filters</span>
      <Select label="Route" value={route} onChange={setRoute} options={routeOptions} placeholder="All routes" />
      <Select label="Airline" value={airline} onChange={setAirline} options={airlineOptions} placeholder="All airlines" />
      <Select
        label="Source"
        value={source}
        onChange={setSource}
        options={[
          { value: "mock", label: "Mock Source" },
          { value: "ota_a", label: "Mock OTA A" },
          { value: "ota_b", label: "Mock OTA B" },
          { value: "airline_direct", label: "Mock Airline Direct" },
          { value: "ota_c", label: "Mock OTA C" },
        ]}
        placeholder="All sources"
      />
      <div className="ml-auto flex items-center gap-2">
        {hasFilters && (
          <button onClick={clear} className="btn btn-sm btn-secondary">
            <RotateCcw className="h-3 w-3" /> Clear
          </button>
        )}
      </div>
    </div>
  );
}
