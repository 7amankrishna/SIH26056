// Uniform loading / empty / error / stale states so no chart renders blank.
// Loading uses skeleton placeholders (shimmer) shaped like the content, not
// spinners — see Skeleton.tsx.

import { AlertTriangle, Inbox, RotateCcw } from "lucide-react";
import { SkeletonChart, SkeletonTable, SkeletonText } from "./Skeleton";

export type LoadVariant = "chart" | "table" | "text" | "block";

export function LoadingState({ variant = "block" as LoadVariant }: { variant?: LoadVariant }) {
  if (variant === "table") return <SkeletonTable />;
  if (variant === "chart") return <SkeletonChart />;
  if (variant === "text") return <SkeletonText />;
  return (
    <div className="flex h-full min-h-[120px] flex-col justify-center gap-2 py-4" aria-hidden>
      <SkeletonText lines={2} />
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-center text-ink-500"
      style={{ borderColor: "rgb(var(--ink-900) / 0.12)" }}>
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-100">
        <Inbox className="h-5 w-5 text-ink-500" />
      </span>
      <p className="text-sm font-medium text-ink-600">{title}</p>
      {hint && <p className="max-w-sm text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50">
        <AlertTriangle className="h-5 w-5 text-red-600" />
      </span>
      <p className="text-sm font-medium text-ink-800">Unable to load this view</p>
      <p className="max-w-md text-xs text-ink-500">{message}</p>
      {retry && (
        <button onClick={retry} className="btn btn-sm btn-secondary mt-1">
          <RotateCcw className="h-3 w-3" /> Retry
        </button>
      )}
    </div>
  );
}

// Wraps children with loading/error fallbacks while keeping layout stable.
export function DataBoundary({
  isLoading,
  isError,
  error,
  isEmpty,
  emptyTitle,
  emptyHint,
  retry,
  variant = "block",
  children,
}: {
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyHint?: string;
  retry?: () => void;
  variant?: LoadVariant;
  children: React.ReactNode;
}) {
  if (isLoading) return <LoadingState variant={variant} />;
  if (isError)
    return <ErrorState message={error instanceof Error ? error.message : "An error occurred"} retry={retry} />;
  if (isEmpty) return <EmptyState title={emptyTitle ?? "No data available"} hint={emptyHint} />;
  return <>{children}</>;
}
