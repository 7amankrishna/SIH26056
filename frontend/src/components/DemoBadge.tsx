// Which data the dashboard is serving right now. The label is derived from the
// *effective* mode reported by the API, not from what the user clicked: asking
// for live data before anything has been collected must not print "LIVE".
//
// Three origins, three badges, and none of them may be mistaken for another:
//   demo   — the deterministic synthetic dataset
//   custom — the user's own imported files (this is real data, not a demo)
//   live   — fares the collection engine actually scraped

import { Link } from "react-router-dom";
import { Database, FlaskConical, Radio } from "lucide-react";
import { useDataSource } from "../hooks/useDataSource";
import { useOverview } from "../hooks/useApi";

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return (
    // Clicking through to the import screen: the badge is the honest way to say
    // "these numbers are synthetic", so it should also say how to change that.
    <Link
      to="/import"
      className="chip border border-amber-200 bg-amber-50 text-amber-700 transition-colors hover:bg-amber-100"
      title="Deterministic synthetic dataset for offline demo — click to import your own data"
    >
      <FlaskConical className="h-3 w-3" />
      DEMO DATA
    </Link>
  );
}

/** Replaces the demo badge once real data — scraped or imported — is served. */
export function DataModeBadge() {
  const { isLive, isCustom, dataFiles, counts, daysCollected } = useDataSource();
  const { data: overview } = useOverview();

  if (isCustom) {
    const coverage = overview?.index_coverage;
    const files = dataFiles?.files ?? [];
    const observations = dataFiles?.totals?.observations ?? 0;
    const skipped = dataFiles?.totals?.rows_skipped ?? 0;
    const names = files.map((f) => f.name).join(", ") || "no files detected";
    return (
      <span
        className="chip border border-sky-200 bg-sky-50 text-sky-700"
        title={
          `${observations.toLocaleString("en-IN")} observations imported from ${files.length} file(s): ${names}` +
          (coverage && !coverage.complete
            ? ` · latest day covers ${coverage.routes}/${coverage.basket_routes} routes (${Math.round(coverage.weight * 100)}% of basket weight)`
            : "") +
          (skipped ? ` · ${skipped.toLocaleString("en-IN")} row(s) skipped as unusable` : "") +
          (dataFiles?.weight_basis === "observation_share"
            ? " · route weights are provisional (share of observations)"
            : "")
        }
      >
        <Database className="h-3 w-3" />
        YOUR DATA
        {files.length > 0 && <span className="opacity-70">· {files.length} file{files.length > 1 ? "s" : ""}</span>}
        {coverage && !coverage.complete && (
          <span className="opacity-70">· partial day</span>
        )}
      </span>
    );
  }

  if (!isLive) return <DemoBadge />;
  return (
    <span
      className="chip border border-emerald-200 bg-emerald-50 text-emerald-700"
      title={`${counts?.observations ?? 0} observations collected across ${daysCollected || counts?.days_collected || 0} day(s) by the background collection engine`}
    >
      <Radio className="h-3 w-3" />
      LIVE · SCRAPED DATA
    </span>
  );
}
