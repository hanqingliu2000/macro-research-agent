# ADR 0028: Open-ended Plan periods at acquisition

Status: accepted

Date: 2026-09-12

## Context

Research intent commonly asks for data “through the latest available year”. That is valid Plan
language, but registered connectors require concrete period keys. Passing the phrase directly made
an approved World Bank WDI Plan fail only after acquisition started.

## Decision

The approved Plan keeps the user's open-ended wording. Immediately before a registered connector
query, the Data service resolves `latest`, `latest available`, `latest available period`,
`latest available year` and `present` to a concrete current-date upper bound in the Plan frequency:

- annual: `YYYY`;
- quarterly: `YYYY-Qn`;
- monthly: `YYYY-MM`.

This value is a query upper bound, not a claim that the provider has published an observation for
that period. Returned observations and their provenance remain authoritative for actual coverage.
The source run exposes the requested and resolved ends, while a value-free
`data.period_bound_resolved` trace records the connector, dataset, resolution time and semantics.
Explicit period keys pass through unchanged and connector-specific range limits still apply.

Annual calendar-year connectors (`world_bank`, `adb` and `un_sdg`) also accept reviewed fiscal-year
labels such as `2011-12` or `FY2011/12`. The Data service maps both query bounds to the fiscal
year's ending calendar year before connector validation (`2012` in this example). The Plan editor
previews that concrete query period; the source run retains requested and resolved start/end values
with `periodResolution=calendar_year_mapping`. Non-consecutive labels fail before any provider
request. This mapping is a query convention, not a claim that fiscal and calendar observations are
economically identical.

## Consequences

- Plan and acquisition accept the same open-ended research intent.
- Every provider request remains bounded and conforms to its registered period syntax.
- Users can see why the concrete provider query differs from the approved Plan wording.
- Data coverage gaps are assessed from returned observations, not predicted during Plan review.
- A fiscal-year label is never sent raw to a calendar-year connector.
