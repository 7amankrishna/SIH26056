// Methodology — a standalone statistical explanation of the APIx calculation.
// Formulae are rendered from LaTex with KaTeX instead of duplicating the API
// reference page, so reviewers can read the full method without opening docs.

import katex from "katex";
import "katex/dist/katex.min.css";
import { AlertTriangle, CheckCircle2, Sigma } from "lucide-react";
import { ChartCard } from "../components/ChartCard";
import { LoadingState } from "../components/DataState";
import { useMethodology } from "../hooks/useApi";
import { usePageTitle } from "../hooks/usePageTitle";

function Formula({ math, label }: { math: string; label?: string }) {
  let markup = math;
  try {
    markup = katex.renderToString(math, {
      displayMode: true,
      throwOnError: false,
      strict: "ignore",
    });
  } catch {
    // The source is maintained in this file; retain readable LaTex if a future
    // edit is malformed rather than making the entire methodology page fail.
  }

  return (
    <figure className="rounded-xl border border-brand-100 bg-brand-50/50 px-4 py-5 text-center dark:border-brand-900/50 dark:bg-brand-950/20 min-w-0 max-w-full overflow-hidden">
      {label && <figcaption className="mb-3 text-left text-xs font-semibold uppercase tracking-wide text-brand-700">{label}</figcaption>}
      <div className="overflow-x-auto text-ink-900 max-w-full" dangerouslySetInnerHTML={{ __html: markup }} />
      <code className="mt-3 block overflow-x-auto text-left text-[11px] text-ink-500 max-w-full">\[{math}\]</code>
    </figure>
  );
}

const FALLBACK_STEPS = [
  ["Define the observation", "A fare quote is retained with its source, collection time, route, departure date, carrier, booking conditions and gross INR fare."],
  ["Validate and classify", "Required fields are checked; unavailable, non-positive, duplicate and stale quotes are retained for audit but excluded from the index."],
  ["Construct route-day prices", "For each route and collection day, APIx uses the median of index-eligible fare observations instead of a mean."],
  ["Establish a fixed base", "The route base is the mean of route-day medians observed during the base window. Each route is therefore comparable to its own starting level."],
  ["Aggregate with weights", "Route relatives are combined using normalized provisional route weights. On a partially observed day, weights are renormalized only across reporting routes."],
] as const;

export default function MethodologyPage() {
  usePageTitle("Methodology");
  const { data, isLoading } = useMethodology();
  const steps = data?.steps?.length
    ? data.steps.map((step) => [step.title, step.detail] as const)
    : FALLBACK_STEPS;
  const basePeriod = data?.base_period;

  return (
    <div className="space-y-5 min-w-0 max-w-full">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink-900">Index Methodology</h2>
          <p className="text-sm text-ink-500">A transparent, route-weighted price index for high-frequency airfare observations.</p>
        </div>
        <span className="chip bg-brand-50 text-brand-700 shrink-0">
          <Sigma className="h-3.5 w-3.5" /> {data?.version ?? "apix-1.0.0"}
        </span>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 min-w-0 max-w-full">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
        <p>
          <strong>Prototype statistical series.</strong> APIx demonstrates a reproducible method for CPI augmentation research;
          it is not an official MoSPI/NSO CPI series and its provisional route weights must not be interpreted as published weights.
        </p>
      </div>

      <ChartCard title="Estimator" subtitle="The calculation performed for every published index value">
        <div className="grid gap-4 xl:grid-cols-2 min-w-0 max-w-full">
          <Formula
            label="Route-day representative fare"
            math={String.raw`p_{r,t}=\operatorname{median}\left\{f_i\;\middle|\; i\in\mathcal{I}_{r,t},\ q_i\in\{\mathrm{VALID},\mathrm{SUSPICIOUS}\}\right\}`}
          />
          <Formula
            label="Route base-period price"
            math={String.raw`\bar{p}_{r,0}=\frac{1}{\lvert T_{r,0}\rvert}\sum_{\tau\in T_{r,0}}p_{r,\tau}`}
          />
          <Formula
            label="Route price relative"
            math={String.raw`I_{r,t}=100\times\frac{p_{r,t}}{\bar{p}_{r,0}}`}
          />
          <Formula
            label="Headline APIx"
            math={String.raw`\mathrm{APIx}_t=\sum_{r\in R_t}\tilde{w}_{r,t}I_{r,t},\qquad\tilde{w}_{r,t}=\frac{w_r}{\sum_{j\in R_t}w_j}`}
          />
        </div>
        <div className="mt-4 grid gap-3 text-sm text-ink-600 md:grid-cols-3">
          <p><code className="font-mono text-ink-900">f_i</code> is a normalized gross fare observation.</p>
          <p><code className="font-mono text-ink-900">r,t</code> denote route and collection date.</p>
          <p><code className="font-mono text-ink-900">R_t</code> is the set of routes that reported on day <em>t</em>.</p>
        </div>
      </ChartCard>

      <div className="grid gap-5 xl:grid-cols-5">
        <ChartCard title="Processing sequence" subtitle="From raw observation to published relative" className="xl:col-span-3">
          {isLoading ? (
            <LoadingState variant="text" />
          ) : (
            <ol className="space-y-3">
              {steps.map(([title, detail], index) => (
                <li key={`${index}-${title}`} className="flex gap-3 rounded-lg border border-ink-100 p-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
                    <p className="mt-0.5 text-xs leading-relaxed text-ink-600">{detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </ChartCard>

        <ChartCard title="Current publication settings" subtitle="Read directly from the active dataset" className="xl:col-span-2">
          <dl className="space-y-3 text-sm">
            <div className="rounded-lg border border-ink-100 p-3">
              <dt className="text-xs text-ink-500">Base period</dt>
              <dd className="mt-1 font-mono font-semibold text-ink-800">
                {basePeriod ? `${basePeriod.start} → ${basePeriod.end}` : "Loading active data…"}
              </dd>
            </div>
            <div className="rounded-lg border border-ink-100 p-3">
              <dt className="text-xs text-ink-500">Weight version</dt>
              <dd className="mt-1 font-mono font-semibold text-ink-800">{data?.weight_version ?? "provisional-dgca-v0"}</dd>
            </div>
            <div className="rounded-lg border border-ink-100 p-3">
              <dt className="text-xs text-ink-500">Observation rule</dt>
              <dd className="mt-1 text-xs leading-relaxed text-ink-700">Median over VALID and SUSPICIOUS observations; the latter remain explicitly flagged.</dd>
            </div>
          </dl>
        </ChartCard>
      </div>

      <ChartCard title="Treatment rules" subtitle="What is included, excluded and disclosed">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-800"><CheckCircle2 className="h-4 w-4" /> Included in the estimator</h3>
            <ul className="mt-2 space-y-2 text-sm leading-relaxed text-ink-600">
              <li>Gross, tax-inclusive fares with a usable route, collection date and positive price.</li>
              <li><span className="font-mono text-xs">VALID</span> observations and flagged <span className="font-mono text-xs">SUSPICIOUS</span> observations, using a median to limit their influence.</li>
              <li>Observed routes only; route weights are renormalized when coverage is partial so missing routes never look like zero prices.</li>
            </ul>
          </div>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800"><AlertTriangle className="h-4 w-4" /> Excluded but retained for audit</h3>
            <ul className="mt-2 space-y-2 text-sm leading-relaxed text-ink-600">
              <li><span className="font-mono text-xs">DUPLICATE</span>, <span className="font-mono text-xs">INVALID</span>, <span className="font-mono text-xs">SOLD_OUT</span>, <span className="font-mono text-xs">STALE</span> and <span className="font-mono text-xs">MISSING</span> observations.</li>
              <li>Missing quotes are never imputed as zero; a route contributes only when it has index-eligible observations.</li>
              <li>Raw provenance, quality status, sample counts and method/weight versions remain available through the API for reproducibility.</li>
            </ul>
          </div>
        </div>
      </ChartCard>
    </div>
  );
}
