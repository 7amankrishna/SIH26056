// Storage health of the collection engine, shown wherever the scraper's own
// state matters. Two truths a reviewer must never have to guess at:
//
//   * unavailable — this deployment has no writable database, so a sweep can run
//     but nothing it collects can be persisted. The API keeps answering (it says
//     why) instead of 500-ing, and the UI says the same thing in plain words.
//   * ephemeral   — SQLite under /tmp on a serverless runtime. Scraping works and
//     the screens fill, but the history dies with the instance: cold start or
//     redeploy resets it. That is a property of the platform, not a bug, and it
//     is labelled as such rather than quietly pretending to be durable.

import { AlertTriangle, Database } from "lucide-react";
import type { StoreCounts } from "../lib/types";

export function StoreHealthBanner({
  store,
  note,
  className = "",
}: {
  store?: StoreCounts;
  /** Optional override/extra context (e.g. the note from the last mode switch). */
  note?: string | null;
  className?: string;
}) {
  const unavailable = store?.available === false;
  const ephemeral = !unavailable && store?.ephemeral === true;
  if (!unavailable && !ephemeral && !note) return null;

  const tone = unavailable
    ? "border-red-200 bg-red-50 text-red-800"
    : ephemeral
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-ink-200 bg-ink-50 text-ink-600";
  const Icon = unavailable ? AlertTriangle : Database;
  const title = unavailable
    ? "Collection store unavailable — scraped data cannot be persisted"
    : ephemeral
      ? "Ephemeral collection store (serverless /tmp)"
      : "Collection store";
  const detail = unavailable
    ? store?.unavailable_reason || store?.note ||
      "Set DATABASE_URL to a PostgreSQL database, or APIX_DATA_DIR to a writable path (on Vercel: /tmp/apix-data)."
    : ephemeral
      ? store?.note ||
        "Data is per-instance and is lost on a cold start or redeploy. Set DATABASE_URL for durable collection history."
      : (note ?? "");

  return (
    <div className={`flex items-start gap-2 rounded-lg border p-3 text-xs ${tone} ${className}`}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5 leading-relaxed">{detail}</p>
        {unavailable && note && note !== detail && <p className="mt-1 font-mono text-[11px]">{note}</p>}
      </div>
    </div>
  );
}

/** Chip explaining *when* a sweep runs on this runtime. */
export function SweepTimingChip({ requestScoped }: { requestScoped: boolean }) {
  return requestScoped ? (
    <span
      className="chip bg-violet-50 text-violet-700"
      title="No background loop survives on this runtime (serverless), so POST /api/collect/sweep runs the sweep inside the request and returns its result."
    >
      sweeps run in-request
    </span>
  ) : (
    <span
      className="chip bg-sky-50 text-sky-700"
      title="A background asyncio loop owns scheduled sweeps on this runtime."
    >
      background loop
    </span>
  );
}
