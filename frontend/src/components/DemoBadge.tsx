import { FlaskConical } from "lucide-react";

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return (
    <span className="chip border border-amber-200 bg-amber-50 text-amber-700" title="Deterministic synthetic dataset for offline demo">
      <FlaskConical className="h-3 w-3" />
      DEMO DATA
    </span>
  );
}
