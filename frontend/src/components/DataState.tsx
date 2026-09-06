// Uniform loading / empty / error / stale states so no chart renders blank.

import { AlertTriangle, Inbox } from "lucide-react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-3 text-ink-400">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-ink-200 border-t-brand-500" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 text-center text-ink-400">
      <Inbox className="h-7 w-7" />
      <p className="text-sm font-medium text-ink-600">{title}</p>
      {hint && <p className="max-w-sm text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 text-center">
      <AlertTriangle className="h-7 w-7 text-amber-500" />
      <p className="text-sm font-medium text-ink-700">Unable to load this view</p>
      <p className="max-w-md text-xs text-ink-400">{message}</p>
      {retry && (
        <button
          onClick={retry}
          className="mt-1 rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-600 hover:bg-ink-50"
        >
          Retry
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
  children,
}: {
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyHint?: string;
  retry?: () => void;
  children: React.ReactNode;
}) {
  if (isLoading) return <LoadingState />;
  if (isError)
    return <ErrorState message={error instanceof Error ? error.message : "An error occurred"} retry={retry} />;
  if (isEmpty) return <EmptyState title={emptyTitle ?? "No data available"} hint={emptyHint} />;
  return <>{children}</>;
}
