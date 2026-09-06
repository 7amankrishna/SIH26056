# Backtesting / Validation

APIx includes a lightweight validation workflow so reviewers can assess how
well the index behaves over time.

## What is exposed

`GET /api/stats/overview` returns the most recent period's validation summary:

- `recent_mean` — average APIx over the most recent 7-day window.
- `prior_mean` — average APIx over the previous 7-day window.
- `mean_deviation` — percentage deviation between the two.
- `backtest.status` — always `demo` in the current build.
- `backtest.metrics` — `mae` and `correlation`.

## Intended drilldowns

The methodology supports 30-, 60- and 90-day backtests where data exists. The
validation metric set is:

- **MAE** — mean absolute error of the estimate vs the reference.
- **RMSE** — root mean squared error.
- **MAPE** — mean absolute percentage error.
- **Correlation** — correlation between observed APIx and the reference.
- **Mean deviation** — average bias.

## Honest limitations

- **No official benchmark.** There is no CPI-transport or official airfare
  benchmark series available, so the system does **not** manufacture official
  benchmark data to inflate its own scores.
- The `correlation` metric is currently `0.0` because a genuine benchmark series
  is unavailable; future work should supply a real reference series (e.g. a
  transport CPI component) and then re-run the backtest.
- In the demo, validation is relative to the prior-period mean — a relative
  measure, not an absolute validation against ground truth.

## Reproducibility

Because the demo dataset is deterministic, every backtest run produces identical
numbers, which makes the workflow auditable and repeatable.
