# ADR 0030 — Executable Plan model contract

Status: accepted and implemented for issue #22 on 2026-09-12.

## Decision

The approved Plan is an executable contract, not a source of prose to be heuristically interpreted.
`ResearchPeriod` accepts only `YYYY`, `YYYY-MM` or `YYYY-Qn` values matching its frequency. Only
`end` may be `latest`; acquisition resolves that open bound and records the resolution.

Forecasting uses `ForecastHorizon { steps, unit: periods, confidenceLevel }`. Model requests use
`ModelIntentV2` with a capability ID, enabled state, purpose and unique, contiguous ordered
variables. Every variable binds a planned indicator code to one of `system`, `descriptive`,
`dependent`, `independent` or `exogenous`. `targetIndicators` is a server-derived compatibility
projection and is never a second source of truth.

Model-specific validation is fail-closed:

- VAR has at least two `system` variables;
- descriptive and correlation have one or more `descriptive` variables;
- OLS has exactly one dependent and one or more independent variables;
- ADF and ARIMA have one or more dependent variables, compiled as separate jobs per target;
- SARIMAX has exactly one dependent and one or more exogenous variables;
- enabled model indicators must occur in enabled Plan data sources and in the approved dataset.

The Pipeline compiler consumes only these structured fields. Objective, assumptions, labels and
other narrative text cannot supply variables, roles or forecast horizons. Provider repair feedback
uses machine-readable `code`, `path` and `message` entries. Public errors distinguish invalid model
contracts, unavailable providers/connectors, incomplete handoffs and deterministic test-contract
violations.

## Evaluation

The checked-in Plan model evaluation corpus contains 24 representative Chinese, English and mixed
language scenarios. It covers single/multiple sources, frequency-aligned and open dates,
forecasting, Plan patches, role exclusion, adversarial prose and malformed fields. CI repeats every
scenario three times. The current recorded fixture result is 91.7% initial validity and 100% after
one bounded repair; invalid objects are validated before persistence and therefore have a 0%
persistence rate. Live DeepSeek quality, latency and cost evaluation remains opt-in and must not be
inferred from deterministic fixtures.

## Consequences

Changing source indicators and changing model variables are one contract change and must be saved
together. Legacy target-only Plans remain readable through the compatibility projection, but their
inferred roles remain subject to the issue #23 handoff confirmation rule before AI reuse. The user
still reviews the compiled Pipeline and explicitly authorizes Run.
