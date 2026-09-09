// Aviation hero banner — the dashboard's institutional front door.
// Fixed navy gradient treatment (both themes), subtle flight-path motif.

import { Plane } from "lucide-react";

export function HeroBanner() {
  return (
    <section
      aria-label="APIx — India's airfare intelligence"
      className="hero-panel relative overflow-hidden rounded-2xl text-white shadow-pop"
    >
      {/* flight-path motif */}
      <svg
        viewBox="0 0 420 170"
        preserveAspectRatio="xMaxYMid meet"
        className="pointer-events-none absolute inset-y-0 right-0 h-full w-[62%] max-w-[560px]"
        aria-hidden
      >
        <path
          d="M12 150 C 120 44, 268 30, 402 62"
          fill="none"
          stroke="rgba(125,211,252,0.45)"
          strokeWidth="1.5"
          strokeDasharray="2 9"
          strokeLinecap="round"
        />
        <circle cx="12" cy="150" r="3" fill="#38bdf8" opacity="0.8" />
        <circle cx="402" cy="62" r="3" fill="#e0f2fe" />
      </svg>
      <Plane
        className="absolute right-6 top-6 h-9 w-9 rotate-45 text-[#bae0fd] drop-shadow-[0_6px_16px_rgba(56,189,248,0.45)] sm:right-10 sm:top-8 sm:h-11 sm:w-11"
        aria-hidden
      />

      <div className="relative px-6 py-6 sm:px-8 sm:py-7">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-300">
          India&apos;s Airfare Intelligence
        </p>
        <h2 className="mt-2 max-w-xl text-2xl font-extrabold leading-tight tracking-tight sm:text-[28px]">
          Real-Time Airfare Price Index for India
        </h2>
        <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-300">
          High-frequency airfare intelligence for CPI augmentation — collected
          transparently, indexed reproducibly, published for everyone.
        </p>
        <p className="mt-4 hidden text-xs font-medium text-[#bae0fd]/90 sm:block">
          Track. Understand. Inform a fairer tomorrow.
        </p>
      </div>
    </section>
  );
}
