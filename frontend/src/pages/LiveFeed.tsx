// Live Feed — the scraper's own screen.
//
// Everything here is read straight from the collection store: the payloads
// exactly as they were received, the normalized observations they produced, the
// run log (blocked and failed runs included, not hidden), and the rules the
// engine enforces. This is deliberately *not* the analytical dashboard — no
// smoothing, no indexing, no aggregation. If the source returned a field we
// could not use, you still see it.

import { useMemo, useState } from "react";
import {
  Activity,
  Ban,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Database,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { DataBoundary } from "../components/DataState";
import { StatusPill } from "../components/badges";
import { KpiCard } from "../components/KpiCard";
import { useCollectFares, useCollectPolicy, useCollectRuns, useCollectStatus, useRawPayloads } from "../hooks/useApi";
import { useDataSource } from "../hooks/useDataSource";
import { formatDateTime, formatINR } from "../lib/format";
import type { CollectFareRow, RawPayloadRow } from "../lib/types";

const TABS = [
  { id: "fares", label: "Collected fares" },
  { id: "raw", label: "Payload as received" },
  { id: "runs", label: "Run log" },
  { id: "policy", label: "Collection rules" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function LiveFeed() {
  const [tab, setTab] = useState<TabId>("fares");
  const [selected, setSelected] = useState<string | null>(null);
  const { mode, effectiveMode, isLive, collecting, setMode, collectNow, daysCollected } = useDataSource();

  const statusQ = useCollectStatus();
  const runsQ = useCollectRuns(30);
  const payloadsQ = useRawPayloads(40);
  const faresQ = useCollectFares(200);
  const policyQ = useCollectPolicy();

  const status = statusQ.data;
  const store = status?.store;

  const payloadByFingerprint = useMemo(() => {
    const map = new Map<string, RawPayloadRow>();
    (payloadsQ.data?.rows ?? []).forEach((r) => {
      const key = `${String(r.payload?.flight_number ?? "")}|${String(r.payload?.departure_date ?? "")}|${String(r.payload?.total_fare ?? "")}`;
      if (!map.has(key)) map.set(key, r);
    });
    return map;
  }, [payloadsQ.data]);

  const selectedRow = useMemo(() => {
    if (!selected) return null;
    const fare = (faresQ.data?.rows ?? []).find((r) => r.observation_id === selected);
    return { fare, payload: fare ? payloadByFingerprint.get(`${fare.flight_number}|${fare.departure_date}|${fare.total_fare}`) : undefined };
  }, [selected, faresQ.data, payloadByFingerprint]);

  return (
    <div className="space-y-5">
      {/* ---- engine header ---- */}
      <div className="card card-pad">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-brand-600" />
              <h2 className="text-base font-bold text-ink-900">Collection engine</h2>
              <span className={`chip ${isLive ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                {isLive ? "serving scraped data" : "serving demo data"}
              </span>
              {status?.background_running && (
                <span className="chip bg-sky-50 text-sky-700" title={`Next scheduled sweep in ≤ ${status.sweep_interval_seconds}s`}>
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-sky-500" />
                  </span>
                  scheduler on · every {Math.round(status.sweep_interval_seconds / 60)}m
                </span>
              )}
            </div>
            <p className="mt-1 max-w-2xl text-xs text-ink-500">
              Background collector: {status?.queries_per_sweep ?? "—"} queries per sweep ·{" "}
              {(status?.lead_times ?? []).map((l) => `T+${l}`).join(", ") || "—"} ·{" "}
              {status?.sources.length ?? 0} adapter(s) registered · {store?.db_bytes ? `${(store.db_bytes / 1024).toFixed(0)} KB` : "0 KB"}{" "}
              stored
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setMode(mode === "live" ? "demo" : "live")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-semibold text-ink-700 hover:bg-ink-50"
            >
              <Activity className="h-3.5 w-3.5" />
              Switch to {mode === "live" ? "demo" : "scraped"}
            </button>
            <button
              onClick={collectNow}
              disabled={collecting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
            >
              {collecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {collecting ? "Sweep running…" : "Run sweep now"}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard label="Observations stored" value={(store?.observations ?? 0).toLocaleString("en-IN")} sub="all rows in SQLite, incl. rejected" />
          <KpiCard
            label="Index-eligible"
            value={(store?.valid_observations ?? 0).toLocaleString("en-IN")}
            sub="VALID after the quality gate"
          />
          <KpiCard label="Raw payloads archived" value={(store?.raw_payloads ?? 0).toLocaleString("en-IN")} sub="byte-for-byte as received" />
          <KpiCard label="Days collected" value={String(daysCollected || store?.days_collected || 0)} sub="each sweep adds one day" />
        </div>

        {status?.last_sweep_error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="font-mono">{status.last_sweep_error}</span>
          </div>
        )}
      </div>

      {/* ---- sources ---- */}
      <ChartCard
        title="Sources"
        subtitle="Compliance state and the outcome of the last sweep. A source that stopped is never shown as live."
      >
        <DataBoundary
          isLoading={statusQ.isLoading}
          isError={statusQ.isError}
          error={statusQ.error}
          isEmpty={!status?.sources?.length}
          emptyTitle="No collection adapter is enabled"
          emptyHint="Set APIX_COLLECTOR_SOURCES=fixture (offline capture) or =amadeus (permissioned API), then restart the backend."
        >
          <div className="grid gap-3 lg:grid-cols-2">
            {(status?.sources ?? []).map((s) => {
              const blocked = s.status === "blocked" || s.circuit_open;
              return (
                <div
                  key={s.id}
                  className={`rounded-lg border p-4 ${blocked ? "border-red-200 bg-red-50/40" : "border-ink-200 bg-ink-50/40"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Cpu className="h-3.5 w-3.5 text-ink-400" />
                        <span className="text-sm font-semibold text-ink-800">{s.name}</span>
                        <StatusPill status={s.status === "success" ? "healthy" : s.status === "partial" ? "degraded" : s.status} />
                      </div>
                      <p className="mt-1 font-mono text-[11px] text-ink-500">
                        {s.adapter} · {s.type}
                      </p>
                    </div>
                    <span
                      className={`chip shrink-0 ${
                        s.compliance === "authorized"
                          ? "bg-emerald-50 text-emerald-700"
                          : s.compliance === "robots_permitted"
                            ? "bg-sky-50 text-sky-700"
                            : "bg-amber-50 text-amber-700"
                      }`}
                      title={s.compliance_note}
                    >
                      <ShieldCheck className="h-3 w-3" />
                      {s.compliance.replace(/_/g, " ")}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                    <MiniStat label="observations" value={(s.observations ?? 0).toLocaleString("en-IN")} />
                    <MiniStat label="requests" value={String(s.last_run?.requests ?? 0)} />
                    <MiniStat label="latency" value={s.last_run?.avg_latency_ms ? `${s.last_run.avg_latency_ms} ms` : "—"} />
                  </div>

                  <div className="mt-3 space-y-1 text-[11px]">
                    <p className="text-ink-500">
                      {s.robots_gated ? (
                        <>
                          robots.txt: <span className="font-semibold text-ink-700">enforced</span> · UA{" "}
                          <span className="font-mono">{s.user_agent?.split(" ")[0]}</span>
                        </>
                      ) : (
                        "authorized channel — no robots restriction in play"
                      )}
                    </p>
                    {s.last_run ? (
                      <p className="text-ink-500">
                        last sweep {formatDateTime(s.last_run.started_at)} —{" "}
                        <span className={s.last_run.status === "success" ? "text-emerald-700" : "text-amber-700"}>
                          {s.last_run.status}
                        </span>
                        {s.last_run.detail ? ` · ${s.last_run.detail}` : ""}
                      </p>
                    ) : (
                      <p className="text-ink-400">no sweep has run against this source yet</p>
                    )}
                    {s.circuit_open && (
                      <p className="font-medium text-red-700">
                        circuit breaker OPEN — backing off {Math.ceil((s.cooldown_seconds_left ?? 0) / 60)} min after{" "}
                        {s.consecutive_failures} consecutive failure(s). No requests are being sent.
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </DataBoundary>
      </ChartCard>

      {/* ---- data tabs ---- */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-1 border-b border-ink-100 px-3 py-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                tab === t.id ? "bg-brand-50 text-brand-700" : "text-ink-500 hover:bg-ink-50 hover:text-ink-800"
              }`}
            >
              {t.label}
            </button>
          ))}
          <span className="ml-auto pr-2 text-[11px] text-ink-400">
            {effectiveMode === "live" ? "store is the source of truth" : "store still available while demo mode is displayed"}
          </span>
        </div>

        <div className="p-3">
          {tab === "fares" && <FaresTable rows={faresQ.data?.rows ?? []} loading={faresQ.isLoading} onSelect={setSelected} selected={selected} />}
          {tab === "raw" && <RawTable rows={payloadsQ.data?.rows ?? []} loading={payloadsQ.isLoading} />}
          {tab === "runs" && <RunsTable runs={runsQ.data?.runs ?? []} loading={runsQ.isLoading} />}
          {tab === "policy" && <PolicyPanel policy={policyQ.data} />}
        </div>
      </div>

      {/* ---- inspector ---- */}
      {selectedRow && (
        <ChartCard
          title="Observation ↔ raw payload"
          subtitle="Normalized canonical model beside the bytes it came from — this is the audit pair the methodology relies on."
          actions={
            <button onClick={() => setSelected(null)} className="rounded-lg border border-ink-200 px-2.5 py-1 text-xs text-ink-600 hover:bg-ink-50">
              Close
            </button>
          }
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="section-title mb-2">Normalized (canonical fare model)</p>
              <div className="overflow-hidden rounded-lg border border-ink-200">
                <table className="w-full text-[11px]">
                  <tbody className="divide-y divide-ink-100">
                    {selectedRow.fare &&
                      Object.entries(selectedRow.fare).map(([k, v]) => (
                        <tr key={k} className="bg-white">
                          <td className="w-40 px-3 py-1.5 font-medium text-ink-500">{k}</td>
                          <td className="px-3 py-1.5 font-mono text-ink-800">
                            {typeof v === "number" ? v.toLocaleString("en-IN") : String(v ?? "—")}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <p className="section-title mb-2">Source payload verbatim</p>
              <pre className="max-h-80 overflow-auto rounded-lg border border-ink-200 bg-ink-900 p-3 text-[11px] leading-relaxed text-ink-100">
                {selectedRow.payload ? JSON.stringify(selectedRow.payload.payload, null, 2) : "No archived payload matched this row."}
              </pre>
            </div>
          </div>
        </ChartCard>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-ink-200 bg-white py-1.5">
      <div className="text-sm font-bold tabular-nums text-ink-800">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-ink-400">{label}</div>
    </div>
  );
}

function FaresTable({
  rows,
  loading,
  onSelect,
  selected,
}: {
  rows: CollectFareRow[];
  loading: boolean;
  onSelect: (id: string) => void;
  selected: string | null;
}) {
  if (loading) return <DataBoundary isLoading children={null} />;
  if (!rows.length)
    return (
      <DataBoundary
        isEmpty
        emptyTitle="Nothing collected yet"
        emptyHint="Run a sweep. The store is written per query, so rows appear as soon as a source answers."
        children={null}
      />
    );
  return (
    <div className="max-h-[460px] overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-ink-50 text-[10px] uppercase tracking-wide text-ink-500">
          <tr>
            {["collected", "route", "airline", "flight", "dep date", "lead", "fare", "seats", "status", ""].map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {rows.map((r) => (
            <tr
              key={r.observation_id}
              onClick={() => onSelect(r.observation_id)}
              className={`cursor-pointer hover:bg-brand-50/40 ${selected === r.observation_id ? "bg-brand-50" : ""}`}
            >
              <td className="whitespace-nowrap px-3 py-1.5 tabular-nums text-ink-500">{formatDateTime(r.collection_timestamp)}</td>
              <td className="whitespace-nowrap px-3 py-1.5 font-semibold text-ink-800">{r.route}</td>
              <td className="px-3 py-1.5">{r.airline}</td>
              <td className="whitespace-nowrap px-3 py-1.5 font-mono text-ink-600">{r.flight_number ?? "—"}</td>
              <td className="whitespace-nowrap px-3 py-1.5 text-ink-600">{r.departure_date}</td>
              <td className="px-3 py-1.5 tabular-nums text-ink-600">T+{r.lead_time_days}</td>
              <td className="whitespace-nowrap px-3 py-1.5 text-right font-semibold tabular-nums text-ink-900">{formatINR(r.total_fare)}</td>
              <td className="px-3 py-1.5 tabular-nums text-ink-600">{r.seats_remaining ?? "—"}</td>
              <td className="px-3 py-1.5">
                <StatusPill status={r.quality_status} />
              </td>
              <td className="px-3 py-1.5 text-ink-400">
                <ChevronRight className="h-3.5 w-3.5" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RawTable({ rows, loading }: { rows: RawPayloadRow[]; loading: boolean }) {
  const [open, setOpen] = useState<number | null>(0);
  if (loading) return <DataBoundary isLoading children={null} />;
  if (!rows.length)
    return <DataBoundary isEmpty emptyTitle="No payloads archived yet" emptyHint="Every successful response is stored verbatim before parsing." children={null} />;
  return (
    <div className="max-h-[460px] space-y-1.5 overflow-auto">
      {rows.map((r, i) => (
        <div key={`${r.run_id}-${i}`} className="overflow-hidden rounded-lg border border-ink-200">
          <button
            onClick={() => setOpen(open === i ? null : i)}
            className="flex w-full items-center gap-3 bg-ink-50/60 px-3 py-2 text-left text-[11px] hover:bg-ink-50"
          >
            <span className={`chip ${r.http_status === 200 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
              {r.http_status}
            </span>
            <span className="font-mono text-ink-700">{r.source}</span>
            <span className="truncate font-mono text-ink-400">{r.url}</span>
            <span className="ml-auto shrink-0 tabular-nums text-ink-400">
              {r.latency_ms ? `${r.latency_ms} ms` : "—"} · {formatDateTime(r.fetched_at)}
            </span>
          </button>
          {open === i && (
            <pre className="max-h-72 overflow-auto bg-ink-900 p-3 text-[11px] leading-relaxed text-ink-100">
              {JSON.stringify({ query: r.query, payload: r.payload }, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

function RunsTable({ runs, loading }: { runs: import("../lib/types").CollectionRun[]; loading: boolean }) {
  if (loading) return <DataBoundary isLoading children={null} />;
  if (!runs.length)
    return <DataBoundary isEmpty emptyTitle="No sweeps recorded yet" emptyHint="Scheduled and manual sweeps both land here." children={null} />;
  const tone: Record<string, string> = {
    success: "bg-emerald-50 text-emerald-700",
    partial: "bg-amber-50 text-amber-700",
    blocked: "bg-red-50 text-red-700",
    failed: "bg-red-50 text-red-700",
    running: "bg-sky-50 text-sky-700",
  };
  return (
    <div className="max-h-[460px] overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-ink-50 text-[10px] uppercase tracking-wide text-ink-500">
          <tr>
            {["started", "source", "status", "queries", "reqs", "stored", "valid", "dupes", "susp", "fail", "ms", "trigger", "detail"].map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {runs.map((r) => (
            <tr key={`${r.run_id}-${r.source}`} className="hover:bg-ink-50/60">
              <td className="whitespace-nowrap px-3 py-1.5 tabular-nums text-ink-500">{formatDateTime(r.started_at)}</td>
              <td className="px-3 py-1.5 font-mono text-ink-700">{r.source}</td>
              <td className="px-3 py-1.5">
                <span className={`chip ${tone[r.status] ?? "bg-ink-100 text-ink-600"}`}>
                  {r.status === "success" ? <CheckCircle2 className="h-3 w-3" /> : r.status === "blocked" ? <Ban className="h-3 w-3" /> : null}
                  {r.status}
                </span>
              </td>
              <td className="px-3 py-1.5 tabular-nums">{r.queries}</td>
              <td className="px-3 py-1.5 tabular-nums">{r.requests}</td>
              <td className="px-3 py-1.5 font-semibold tabular-nums">{r.observations}</td>
              <td className="px-3 py-1.5 tabular-nums text-emerald-700">{r.valid_observations}</td>
              <td className="px-3 py-1.5 tabular-nums">{r.duplicates}</td>
              <td className="px-3 py-1.5 tabular-nums text-amber-700">{r.suspicious}</td>
              <td className="px-3 py-1.5 tabular-nums text-red-700">{r.failures}</td>
              <td className="px-3 py-1.5 tabular-nums text-ink-500">{r.avg_latency_ms ?? "—"}</td>
              <td className="px-3 py-1.5 text-ink-500">{r.trigger}</td>
              <td className="max-w-[280px] truncate px-3 py-1.5 text-ink-500" title={r.detail ?? ""}>
                {r.detail ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PolicyPanel({ policy }: { policy?: import("../lib/types").CollectionPolicy }) {
  if (!policy)
    return (
      <div className="flex items-center gap-2 p-4 text-xs text-ink-400">
        <Database className="h-3.5 w-3.5" /> Loading policy…
      </div>
    );
  const p = policy.politeness as Record<string, unknown>;
  return (
    <div className="grid gap-4 p-2 lg:grid-cols-2">
      <div>
        <p className="section-title mb-2">What every request does</p>
        <ul className="space-y-1.5 text-xs text-ink-600">
          {policy.sent_headers.map((h) => (
            <li key={h} className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
              <span className="font-mono text-[11px]">{h}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3">
          {Object.entries(p).map(([k, v]) => (
            <div key={k} className="rounded-md border border-ink-200 bg-ink-50 px-2 py-1.5">
              <div className="text-ink-400">{k.replace(/_/g, " ")}</div>
              <div className="font-mono font-semibold text-ink-700">{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <p className="section-title mb-2">Deliberately not implemented</p>
        <ul className="space-y-1.5 text-xs">
          {policy.not_implemented.map((h) => (
            <li key={h} className="flex items-start gap-2 rounded-md border border-red-100 bg-red-50/50 px-2.5 py-1.5 text-red-800">
              <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="text-[11px] leading-relaxed">{h}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 rounded-lg border border-ink-200 bg-ink-50 p-3 text-[11px] leading-relaxed text-ink-600">
          A fare series feeding a statistical index has to survive an auditor asking “where did this number come from?”. Data pulled off a consumer site in
          secret cannot: it is unlicensed, un-re-derivable and — per that site's terms — not permitted in the first place. The engine therefore collects from
          authorized channels, archives the raw payload behind every observation, and records a blocked collection as a failure rather than retrying around it.
          Full policy: <span className="font-mono">{policy.policy_document}</span>
        </p>
      </div>
    </div>
  );
}
