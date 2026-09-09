// Skeleton loading primitives — shimmer blocks that mirror the shape of the
// content they replace, so async loads never jolt the layout.

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

/** Bar chart / area chart placeholder. */
export function SkeletonChart({ className = "h-[320px]" }: { className?: string }) {
  const bars = [38, 62, 45, 70, 55, 80, 48, 66, 58, 74, 42, 68];
  return (
    <div className={`flex flex-col justify-end gap-2 ${className}`} aria-hidden>
      <div className="flex flex-1 items-end gap-2">
        {bars.map((h, i) => (
          <div key={i} className="skeleton flex-1" style={{ height: `${h}%` }} />
        ))}
      </div>
      <Skeleton className="h-3 w-full" />
    </div>
  );
}

/** Table placeholder: header strip + N rows. */
export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      <div className="flex gap-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className={`h-3 ${i === 0 ? "w-1/4" : "flex-1"}`} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton
              key={c}
              className={`h-5 ${c === 0 ? "w-1/4" : "flex-1"} ${r % 2 ? "opacity-70" : ""}`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/** KPI strip placeholder. */
export function SkeletonStats({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6" aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-4">
          <Skeleton className="h-2.5 w-16" />
          <Skeleton className="mt-3 h-7 w-20" />
        </div>
      ))}
    </div>
  );
}

/** A few lines of text (cards, panels). */
export function SkeletonText({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}
