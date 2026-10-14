# ADR 0010: Generated reproduction code

Status: accepted

Date: 2026-08-25

## Decision

Phase 1D-3 generates reproduction files only from the reviewed typed Pipeline and ModelJob JSON.
The Python entrypoint embeds that canonical specification and calls a versioned deterministic
runtime shared with backend transformation/model implementations. It accepts canonical CSV,
Parquet or an XLSX Data sheet and writes analytical Parquet plus model-result JSON.

The Stata generator is capability-gated per operation and model semantics. It currently supports
lag, lead, difference, period/year growth and log operations plus explicit descriptive/correlation
jobs and OLS with nonrobust or HC1 covariance. It refuses unsupported translations, including the
entity/frequency-blocked HAC estimator, rather than silently substituting a different estimator.

Generated files are stored outside the session document. The document contains artifact IDs,
language, filename, specification hash and content checksum. Preview and download revalidate the
file checksum and Workflow-session ownership.

## Execution boundary

Generated code is never executed by the backend and cannot be supplied as a Pipeline operation.
Automated acceptance may execute backend-generated Python in an isolated test subprocess solely to
assert equality with the reviewed backend result.

## Consequences

- Python reproduction requires the matching `macro_research_agent` package/runtime version.
- The future reproduction manifest must pin that package version and artifact checksums.
- Unsupported Stata output is explicit in bundle warnings and represented by a null code ref.
- Editing or rerunning analysis archives prior code refs together with prior bundle/results.
- Output packaging can consume these immutable code refs without regenerating them silently.
