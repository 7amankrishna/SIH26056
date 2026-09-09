// Index Methodology explainer — transparent, reproducible, auditable.

import { AlertTriangle, ArrowRight } from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { DataBoundary } from "../components/DataState";
import { useMethodology } from "../hooks/useApi";
import { usePageTitle } from "../hooks/usePageTitle";

export default function Methodology() {
  const { data, isLoading, isError, error } = useMethodology();
  usePageTitle("Methodology");

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-ink-900">Index Methodology</h2>
        <p className="text-sm text-ink-500">Exactly how APIx is calculated — observable, reproducible and auditable.</p>
      </div>

      <DataBoundary isLoading={isLoading} isError={isError} error={error} isEmpty={!data} variant="text">
        {data && (
          <>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
                <div>
                  <p className="text-sm font-semibold text-amber-800">{data.status}</p>
                  <p className="text-sm text-amber-700">{data.disclaimer}</p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 text-sm">
              <span className="kpi-label">Methodology version</span>
              <span className="chip bg-brand-50 text-brand-700">{data.version}</span>
              <span className="kpi-label">Weights</span>
              <span className="chip bg-ink-100 text-ink-600">{data.weight_version}</span>
              <span className="kpi-label">Base period</span>
              <span className="text-ink-700">{data.base_period.start} → {data.base_period.end}</span>
            </div>

            {/* Formula */}
            <div className="card overflow-hidden">
              <div className="border-b border-ink-100 px-5 py-3.5">
                <h3 className="text-sm font-semibold text-ink-800">The Formula</h3>
              </div>
              <div className="bg-code-bg p-6">
                <code className="block text-center font-mono text-lg text-brand-300 sm:text-xl">
                  APIx(t) = Σ wᵣ × 100 × Price(r,t) / Base(r)
                </code>
                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {Object.entries(data.definitions).map(([k, v]) => (
                    <div key={k} className="rounded-lg bg-white/5 p-3 ring-1 ring-white/10">
                      <div className="font-mono text-sm font-semibold text-code-fg">{k}</div>
                      <div className="mt-0.5 text-xs text-ink-500">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Steps */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {data.steps.map((step) => (
                <div key={step.step} className="card relative p-4">
                  <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-sm font-bold text-brand-700">
                    {step.step}
                  </div>
                  <h4 className="text-sm font-semibold text-ink-800">{step.title}</h4>
                  <p className="mt-1 text-xs leading-relaxed text-ink-500">{step.detail}</p>
                  {step.step < data.steps.length && (
                    <ArrowRight className="absolute -right-2 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-ink-500 lg:block" />
                  )}
                </div>
              ))}
            </div>

            {/* Pipeline */}
            <ChartCard title="End-to-End Pipeline" subtitle="Raw fares -> trusted observations -> statistical index -> insight">
              <div className="flex flex-wrap items-center gap-2">
                {[
                  "Source", "Collection", "Raw storage", "Normalization",
                  "Quality engine", "PostgreSQL", "Index engine", "FastAPI", "React dashboard",
                ].map((s, i, arr) => (
                  <div key={s} className="flex items-center gap-2">
                    <span className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-1.5 text-xs font-medium text-ink-700">{s}</span>
                    {i < arr.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-ink-500" />}
                  </div>
                ))}
              </div>
            </ChartCard>
          </>
        )}
      </DataBoundary>
    </div>
  );
}
