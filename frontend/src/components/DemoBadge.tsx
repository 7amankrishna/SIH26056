// Which data the dashboard is serving right now. The label is derived from the
// *effective* mode reported by the API, not from what the user clicked: asking
// for live data before anything has been collected must not print "LIVE".

import { FlaskConical, Radio } from "lucide-react";
import { useDataSource } from "../hooks/useDataSource";

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return (
    <span
      className="chip border border-amber-200 bg-amber-50 text-amber-700"
      title="Deterministic synthetic dataset for offline demo"
    >
      <FlaskConical className="h-3 w-3" />
      DEMO DATA
    </span>
  );
}

/** Replaces the demo badge once real collected data is being served. */
export function DataModeBadge() {
  const { isLive, counts, daysCollected } = useDataSource();
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
