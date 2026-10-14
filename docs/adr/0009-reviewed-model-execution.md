# ADR 0009: Reviewed model execution

Status: accepted

Date: 2026-08-25; amended 2026-09-05 for Phase 2A-1 and Phase 2A-2; amended 2026-09-06 for Phase 2A-3

## Decision

Phase 1D-2 executes model jobs only through a backend registry. The initial registry contains
descriptive statistics, listwise correlation and OLS with nonrobust, HC1 or HAC covariance. A job
must identify the approved dataset or a logical output created by the reviewed typed pipeline.
Logical refs are resolved to immutable physical snapshots before execution.

Every result records the physical input snapshot and hash, a canonical specification hash, sample
observations and dropped rows, structured estimates, diagnostics, warnings and a canonical result
hash. Results are stored independently in SQLite and referenced by the session AnalyticalBundle.

HAC covariance is accumulated within entity/frequency blocks. This prevents the end of one entity's
series from being treated as adjacent to the beginning of another. Model results are analytical
consumers and cannot implicitly become inputs to ordinary transformations.

Phase 2A-1 adds the Augmented Dickey-Fuller unit-root test. One reviewed indicator is tested
independently for every entity/frequency series; series are never concatenated. The typed
specification fixes deterministic terms (`c`, `ct`, `ctt` or `n`), lag selection (`AIC`, `BIC`,
`t-stat` or fixed) and maximum lags. Results retain the statistic, MacKinnon p-value, selected lag,
effective observations, critical values, information criterion where applicable and the explicit
unit-root null hypothesis. Failure to reject at five percent is a warning, not an execution error.

Phase 2A-2 adds ARIMA and SARIMAX estimation. Each entity/frequency series is estimated separately
from one reviewed dependent indicator. ARIMA rejects exogenous and seasonal terms; SARIMAX may use
reviewed seasonal orders and registered exogenous indicators. The specification bounds ordinary
and seasonal orders, forecast horizon and confidence level, and explicitly selects trend,
stationarity and invertibility enforcement. SARIMAX forecasting with exogenous indicators fails
closed unless every future exogenous row already exists in the approved snapshot. Results include
fit criteria, convergence state, parameters, forecast means and confidence intervals. Forecast
rows are exported as a dedicated CSV and workbook sheet.

Phase 2A-3 adds vector autoregression for an ordered list of at least two endogenous indicators.
Each entity/frequency system is estimated independently. A reviewed specification selects a fixed
lag or a bounded AIC/BIC/HQIC/FPE search, deterministic terms, an optional bounded forecast horizon
and whether to produce IRFs. VAR forecasts retain the target variable, period, step, mean and
confidence interval for every endogenous series. IRFs
explicitly record the selected impulse variables, horizon, confidence level and orthogonalized or
reduced-form shock semantics. Recursive orthogonalized shocks preserve the user-reviewed variable
ordering. Results include equation coefficients and uncertainty, fit criteria, stability, and—when
requested—IRF estimates and asymptotic confidence bounds. IRF rows are exported to a dedicated CSV
and workbook sheet.

## Staged checkpoint behavior

Transformation Run can execute transformations, model jobs, or both, then creates the governed
Output draft for review. Python reproduction uses the same evaluator and specification. Stata ADF
and ARIMA/SARIMAX/VAR generation remain unavailable until panel/time declaration,
future-exogenous, shock-ordering and IRF-persistence semantics have reviewed mappings; this is
reported rather than approximated.

## Consequences

- Unsupported model kinds are hidden in the HTTP-backed UI and rejected by the backend.
- Correlation requires explicit indicator selection; OLS requires one dependent and at least one
  independent indicator.
- ADF requires exactly one indicator and produces separate results for each entity/frequency group.
- ARIMA/SARIMAX require exactly one target; SARIMAX future exogenous data is never generated or
  silently extended.
- VAR requires at least two ordered indicators; selected IRF impulses must belong to that system.
  Its reviewed forecast horizon is zero (disabled) or 1–60 periods.
- Editing any pipeline or model specification archives current results and clears the active bundle.
- Generated code must later consume these same typed specifications and parameters.
- ADR 0014 permits AI assistance to inspect the actual immutable model input through a read-only,
  hash-bound grant. Model execution itself still accepts only reviewed typed specifications.
