// Import Data — put your own fare exports on the dashboard.
//
// The dashboard serves, in order: scraped (live) data, then whatever is in the
// data directory, then the synthetic demo dataset. This screen is the front door
// for the middle one: pick a CSV/Excel/JSON export, see exactly how it was read
// (rows, column mapping, rejects) before it is trusted, and remove files again.
//
// Nothing here is cosmetic: every number shown comes back from the loader, so a
// file that cannot be parsed says so here instead of silently changing the index.

import { useCallback, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  Database,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { EmptyState, ErrorState, LoadingState } from "../components/DataState";
import { usePageTitle } from "../hooks/usePageTitle";
import {
  useDataFiles,
  useDatabaseStatus,
  useDeleteDataFile,
  usePersistDataFiles,
  usePersistDemoData,
  useReloadDataFiles,
  useUploadDataFiles,
} from "../hooks/useApi";
import type { PersistenceReport, UploadResponse } from "../lib/types";

const ACCEPT = ".csv,.tsv,.txt,.json,.jsonl,.ndjson,.xlsx,.xlsm";

function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function PersistenceLine({ report }: { report: PersistenceReport }) {
  if (!report.persisted) {
    return (
      <p className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-700">
        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
        <span>
          Not saved to a database — {report.error ?? "no database configured"}. The file is still
          loaded and the dashboard is serving it; run “Push to database” once the database is reachable.
        </span>
      </p>
    );
  }
  const parts = [
    `${report.inserted.toLocaleString("en-IN")} inserted`,
    `${report.updated.toLocaleString("en-IN")} updated`,
  ];
  if (report.replaced) parts.push(`${report.replaced.toLocaleString("en-IN")} replaced`);
  return (
    <p className="mt-2 flex items-start gap-1.5 text-[11px] text-emerald-700">
      <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0" />
      <span>
        Saved to {report.backend === "postgresql" ? "PostgreSQL (Supabase)" : (report.backend ?? "database")}:{" "}
        {parts.join(" · ")} — matched on <span className="font-mono">observation_id</span>, so re-uploading
        these rows updates them instead of duplicating.
      </span>
    </p>
  );
}

export default function ImportData() {
  usePageTitle("Import Data");
  const { data, isLoading, isError, error, refetch } = useDataFiles();
  const upload = useUploadDataFiles();
  const remove = useDeleteDataFile();
  const reload = useReloadDataFiles();
  const database = useDatabaseStatus();
  const persist = usePersistDataFiles();
  const persistDemo = usePersistDemoData();

  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const send = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files);
      if (!list.length) return;
      setLocalError(null);
      setResult(null);
      upload.mutate(list, {
        onSuccess: (res) => setResult(res),
        onError: (err: unknown) =>
          setLocalError(err instanceof Error ? err.message : String(err)),
      });
    },
    [upload],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      send(e.dataTransfer.files);
    },
    [send],
  );

  const files = data?.files ?? [];
  const totals = data?.totals ?? {};
  const notes = data?.notes ?? [];
  const persistenceError = persist.error ?? persistDemo.error;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink-900">Import Data</h2>
          <p className="text-sm text-ink-500">
            Upload your fare exports — they replace the synthetic demo dataset on every screen.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`chip ${data?.active ? "bg-sky-50 text-sky-700" : "bg-amber-50 text-amber-700"}`}
            title={`Data directory: ${data?.data_dir ?? "…"}`}
          >
            <Database className="h-3 w-3" />
            {data?.active
              ? `${(totals.observations ?? 0).toLocaleString("en-IN")} observations · ${files.length} file(s)`
              : "no imported data — serving demo"}
          </span>
          <button
            onClick={() => reload.mutate()}
            disabled={reload.isPending}
            className="btn btn-sm btn-secondary"
            title="Rescan the data directory now"
          >
            {reload.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Rescan
          </button>
          <button
            onClick={() => persist.mutate(undefined)}
            disabled={persist.isPending || !data?.active}
            className="btn btn-sm btn-primary"
            title="Upsert every loaded observation into the database (matched on observation_id)"
          >
            {persist.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CloudUpload className="h-3.5 w-3.5" />}
            Push to database
          </button>
          <button
            onClick={() => persistDemo.mutate()}
            disabled={persistDemo.isPending}
            className="btn btn-sm btn-secondary"
            title="Seed the deterministic built-in APIx demo observations directly into the configured store"
          >
            {persistDemo.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
            Push demo data
          </button>
        </div>
      </div>

      {(data?.upload || result?.diagnostics) && (() => {
        const storage = result?.diagnostics ?? data?.upload;
        if (!storage) return null;
        const warning = !storage.writable;
        const temporary = storage.serverless || storage.ephemeral;
        return (
          <div className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-xs ${
            warning ? "border-red-200 bg-red-50 text-red-800" : temporary ? "border-amber-200 bg-amber-50 text-amber-800" : "border-sky-100 bg-sky-50 text-sky-800"
          }`}>
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">Upload storage diagnostic</p>
              <p className="mt-0.5">
                New files are staged in <code className="rounded bg-white/50 px-1 font-mono">{storage.upload_dir}</code>.
                {warning
                  ? ` It is not writable${storage.reason ? `: ${storage.reason}` : "."}`
                  : temporary
                    ? " This serverless directory is temporary, so use Push to database for durable storage."
                    : " The directory is writable."}
              </p>
              {storage.note && <p className="mt-1">{storage.note}</p>}
            </div>
          </div>
        );
      })()}

      {/* Upload ------------------------------------------------------------ */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        className={`card flex cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-sky-400 bg-sky-50/60" : "border-ink-200 hover:border-sky-300 hover:bg-sky-50/30"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            if (e.target.files) send(e.target.files);
            e.target.value = "";
          }}
        />
        {upload.isPending ? (
          <>
            <Loader2 className="h-7 w-7 animate-spin text-sky-600" />
            <p className="text-sm font-medium text-ink-700">Uploading and parsing…</p>
          </>
        ) : (
          <>
            <Upload className="h-7 w-7 text-sky-600" />
            <div>
              <p className="text-sm font-semibold text-ink-800">Drop fare files here, or click to browse</p>
              <p className="mt-1 text-xs text-ink-500">
                CSV, TSV, JSON, JSONL or Excel (.xlsx) — any column names. Files are added, never overwritten.
              </p>
            </div>
            <p className="font-mono text-[11px] text-ink-400">{ACCEPT}</p>
          </>
        )}
      </div>

      {localError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{localError}</span>
        </div>
      )}

      {/* Result of the last upload ------------------------------------------ */}
      {result && (
        <div className="space-y-3">
          {result.imported.map((f) => {
            const bad = f.errors.length > 0;
            return (
              <div
                key={f.name}
                className={`card p-4 ${bad ? "border-red-200" : "border-emerald-200"}`}
              >
                <div className="flex items-start gap-3">
                  {bad ? (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                  ) : (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink-900">{f.name}</p>
                    <p className="mt-0.5 text-xs text-ink-500">
                      {f.observations.toLocaleString("en-IN")} observations from {f.rows.toLocaleString("en-IN")} rows
                      {f.rejected > 0 && ` · ${f.rejected.toLocaleString("en-IN")} skipped as unusable`} · {formatBytes(f.size_bytes)}
                    </p>

                    {Object.keys(f.mapped).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {Object.entries(f.mapped).map(([field, column]) => (
                          <span key={field} className="chip bg-ink-50 text-ink-600" title={`your column "${column}"`}>
                            {column} → <span className="font-mono text-ink-800">{field}</span>
                          </span>
                        ))}
                      </div>
                    )}

                    {f.unmapped.length > 0 && (
                      <p className="mt-2 text-[11px] text-ink-400">
                        Not used: <span className="font-mono">{f.unmapped.join(", ")}</span> — map them in{" "}
                        <span className="font-mono">data/config.json</span> if you need them.
                      </p>
                    )}

                    {result.persistence && <PersistenceLine report={result.persistence} />}

                    {[...f.errors, ...f.warnings].map((message) => (
                      <p
                        key={message}
                        className={`mt-1.5 text-[11px] ${f.errors.includes(message) ? "text-red-700" : "text-amber-700"}`}
                      >
                        • {message}
                      </p>
                    ))}
                  </div>
                  <button
                    onClick={() => setResult(null)}
                    className="shrink-0 rounded-md p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-600"
                    aria-label="Dismiss result"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })}

          {result.refused.map((r) => (
            <div key={r.name} className="card border-red-200 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                <div>
                  <p className="text-sm font-semibold text-ink-900">{r.name} — not imported</p>
                  <p className="mt-0.5 text-xs text-red-700">{r.error}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Database ----------------------------------------------------------- */}
      <ChartCard
        title="Database"
        subtitle="Imports are upserted on observation_id — re-uploading the same rows updates them, never duplicates them"
        actions={
          <span
            className={`chip ${
              database.data?.available ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
            }`}
          >
            <Database className="h-3 w-3" />
            {database.data?.available
              ? database.data.backend === "postgresql"
                ? "supabase · connected"
                : `${database.data.backend ?? "store"} · local`
              : "not connected"}
          </span>
        }
      >
        {database.isLoading ? (
          <LoadingState variant="text" />
        ) : database.data?.available ? (
          <div className="space-y-2 text-sm text-ink-700">
            <p>
              <span className="font-semibold text-ink-900">
                {(database.data.counts.observations ?? 0).toLocaleString("en-IN")}
              </span>{" "}
              observations stored
              {database.data.counts.days_collected
                ? ` across ${database.data.counts.days_collected} day(s)`
                : ""}{" "}
              · {database.data.backend === "postgresql" ? "PostgreSQL (Supabase)" : database.data.backend}
              {database.data.durable ? "" : " (not durable — local/ephemeral store)"}
            </p>
            {database.data.note && <p className="text-xs text-amber-700">{database.data.note}</p>}
            <p className="text-xs text-ink-500">
              Uploading a file again replaces the rows that file wrote, so a corrected export updates
              your table instead of adding a second copy.
            </p>
          </div>
        ) : (
          <div className="space-y-2 text-sm text-ink-700">
            <p className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>
                {database.data?.reason
                  ? `No usable database: ${database.data.reason}`
                  : "No database configured."}{" "}
                Files still load and the dashboard still serves them — they just are not persisted.
              </span>
            </p>
            <p className="text-xs text-ink-500">
              Set <span className="font-mono">DATABASE_URL</span> to your Supabase connection string
              and ensure <span className="font-mono">APIX_IGNORE_DATABASE_URL</span> is not <span className="font-mono">1</span>, then press{" "}
              <span className="font-medium">Push to database</span>. See{" "}
              <span className="font-mono">docs/DEPLOYMENT.md</span>.
            </p>
          </div>
        )}
        {persist.data && (
          <div className="mt-3 border-t pt-3" style={{ borderColor: "rgb(var(--ink-900) / 0.07)" }}>
            <PersistenceLine report={persist.data} />
          </div>
        )}
        {persistDemo.data && (
          <div className="mt-3 border-t pt-3" style={{ borderColor: "rgb(var(--ink-900) / 0.07)" }}>
            <p className="text-xs font-semibold text-ink-700">Built-in demo seed</p>
            <PersistenceLine report={persistDemo.data} />
          </div>
        )}
        {persistenceError && (
          <p className="mt-3 text-xs text-red-700">
            {persistenceError instanceof Error ? persistenceError.message : String(persistenceError)}
          </p>
        )}
      </ChartCard>

      {/* What is loaded right now ------------------------------------------- */}
      <ChartCard
        title="Imported files"
        subtitle={
          <>
            Read from <span className="font-mono">{data?.data_dir ?? "…"}</span> — the loader re-reads
            automatically when a file changes
          </>
        }
      >
        {isLoading ? (
          <LoadingState variant="table" />
        ) : isError ? (
          <ErrorState message={error instanceof Error ? error.message : String(error)} retry={() => refetch()} />
        ) : files.length === 0 ? (
          <EmptyState
            title="No files imported yet"
            hint="Upload an export above (or drop it into the data directory) and every screen will switch from demo data to yours."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-ink-500">
                  <th className="pb-2 pr-4 font-medium">File</th>
                  <th className="pb-2 pr-4 font-medium">Rows</th>
                  <th className="pb-2 pr-4 font-medium">Observations</th>
                  <th className="pb-2 pr-4 font-medium">Skipped</th>
                  <th className="pb-2 pr-4 font-medium">Size</th>
                  <th className="pb-2 pr-4 font-medium">Modified</th>
                  <th className="pb-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.name} className="border-b border-ink-100 last:border-0">
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2">
                        {f.kind === "observations" ? (
                          <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-sky-600" />
                        ) : (
                          <FileText className="h-3.5 w-3.5 shrink-0 text-ink-400" />
                        )}
                        <span className="font-medium text-ink-800">{f.name}</span>
                        {f.kind !== "observations" && (
                          <span className="chip bg-ink-50 text-ink-500">{f.kind}</span>
                        )}
                      </div>
                      {f.errors.map((message) => (
                        <p key={message} className="mt-1 text-[11px] text-red-700">
                          {message}
                        </p>
                      ))}
                      {f.warnings.slice(0, 2).map((message) => (
                        <p key={message} className="mt-1 text-[11px] text-amber-700">
                          {message}
                        </p>
                      ))}
                    </td>
                    <td className="py-2.5 pr-4 tabular-nums text-ink-700">{f.rows.toLocaleString("en-IN")}</td>
                    <td className="py-2.5 pr-4 tabular-nums text-ink-700">{f.observations.toLocaleString("en-IN")}</td>
                    <td className={`py-2.5 pr-4 tabular-nums ${f.rejected ? "text-amber-700" : "text-ink-500"}`}>
                      {f.rejected.toLocaleString("en-IN")}
                    </td>
                    <td className="py-2.5 pr-4 tabular-nums text-ink-500">{formatBytes(f.size_bytes)}</td>
                    <td className="py-2.5 pr-4 text-ink-500">{f.modified_at?.replace("T", " ") ?? "—"}</td>
                    <td className="py-2.5 text-right">
                      <button
                        onClick={() => remove.mutate(f.name)}
                        disabled={remove.isPending}
                        className="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-red-50 hover:text-red-600"
                        title={`Delete ${f.name}`}
                        aria-label={`Delete ${f.name}`}
                      >
                        {remove.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* Notes from the loader ---------------------------------------------- */}
      {notes.length > 0 && (
        <div className="card border-amber-200 bg-amber-50/60 p-4">
          <h3 className="text-sm font-semibold text-amber-900">What the loader wants you to know</h3>
          <ul className="mt-2 space-y-1">
            {notes.map((note) => (
              <li key={note} className="flex gap-2 text-xs leading-relaxed text-amber-800">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Format help --------------------------------------------------------- */}
      <ChartCard title="What your file needs" subtitle="Three things per row; everything else is optional or derived">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wide text-ink-500">
                <th className="pb-2 pr-4 font-medium">You need</th>
                <th className="pb-2 font-medium">Accepted column names</th>
              </tr>
            </thead>
            <tbody className="text-ink-700">
              {[
                ["When the fare was seen", "collection_date, date, observed_on, snapshot_date, timestamp, …"],
                ["Which route", "route (DEL-BOM) — or both origin + destination / From + To"],
                ["How much", "total_fare, price, fare, amount, … — or base_fare + taxes + fees"],
              ].map(([need, columns]) => (
                <tr key={need} className="border-b border-ink-100 last:border-0">
                  <td className="py-2.5 pr-4 font-medium text-ink-800">{need}</td>
                  <td className="py-2.5 font-mono text-xs text-ink-600">{columns}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-ink-500">
          Dates accept <span className="font-mono">2026-09-06</span>, <span className="font-mono">06/09/2026</span>,{" "}
          <span className="font-mono">06-Sep-2026</span> and ISO timestamps. Fares may carry symbols and separators
          (<span className="font-mono">₹ 4,650.00</span>). Optional columns that are used when present: departure_date,
          lead_time_days, airline, flight_number, cabin, fare_class, source, currency, availability, seats_remaining,
          quality_status. Anything else is ignored and listed above, so you can see what was dropped.
        </p>
      </ChartCard>
    </div>
  );
}
