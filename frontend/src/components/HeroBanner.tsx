// Aviation hero banner — the dashboard's institutional front door.
// Fixed navy gradient treatment (both themes), subtle flight-path motif.

import { Plane } from "lucide-react";

export function HeroBanner() {
  return (
    <section
      aria-label="APIx — India's airfare intelligence"
      className="relative overflow-hidden rounded-xl border border-[#e2e8f0] shadow-sm flex items-center min-h-[140px] sm:min-h-[150px] lg:h-[155px] bg-[#f0f5fa]"
    >
      {/* Right-side HD artwork: starts from extreme right (0 gap) and extends till half (50%) */}
      <div className="pointer-events-none absolute inset-y-0 right-0 w-full sm:w-[52%] lg:w-1/2 overflow-hidden z-0">
        <img
          src="/banner_artwork_hd.png"
          alt="Commercial airplane flying over city skyline"
          className="w-full h-full object-cover object-[right_30%] select-none opacity-50 sm:opacity-100 transition-all"
        />
        {/* Soft linear fade on the left edge of the half-banner graphic */}
        <div className="absolute inset-y-0 left-0 w-24 sm:w-32 bg-gradient-to-r from-[#f0f5fa] via-[#f0f5fa]/80 to-transparent"></div>
      </div>

      {/* Top-right tagline: anchored cleanly in the sky on the far right */}
      <div className="hidden md:flex flex-col items-end text-right text-xs sm:text-[13px] text-[#091b38] font-medium leading-snug absolute top-4 sm:top-5 right-5 sm:right-8 z-20 pointer-events-none">
        <span>Track. Understand.</span>
        <span>Inform a fairer tomorrow.</span>
      </div>

      {/* Mobile contrast overlay */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#f0f5fa] via-[#f0f5fa]/95 to-transparent sm:hidden z-[1] pointer-events-none"></div>

      {/* Foreground Content on the left half */}
      <div className="relative z-10 w-full h-full px-5 py-4 sm:px-8 sm:py-5 flex flex-col justify-between max-w-full sm:max-w-[48%]">
        
        {/* Top kicker */}
        <div>
          <p className="text-[10px] sm:text-[11px] font-semibold uppercase tracking-[0.2em] text-[#2b6cb0]">
            India's Airfare Intelligence
          </p>
        </div>

        {/* Main Title Area */}
        <div className="flex flex-wrap items-baseline gap-2 sm:gap-3.5 my-2 sm:my-auto">
          <h1 className="text-3xl sm:text-4xl lg:text-[45px] font-extrabold text-[#091b38] tracking-tight leading-none">
            APIx
          </h1>
          <h2 className="text-base sm:text-xl lg:text-[23px] font-bold text-[#091b38] tracking-tight leading-snug sm:leading-none">
            Real-Time Airfare Price Index for India
          </h2>
        </div>
        
        {/* Subtitle */}
        <div>
          <p className="text-xs sm:text-[13.5px] font-normal text-slate-500 leading-tight">
            High-frequency airfare intelligence for CPI augmentation
          </p>
        </div>
      </div>
    </section>
  );
}
