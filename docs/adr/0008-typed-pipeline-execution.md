# ADR 0008: Typed local Pipeline execution

Status: accepted

Date: 2026-08-25; amended 2026-09-06 for Phase 2 harmonization and lineage; amended 2026-09-12 for Plan-derived drafts

## Decision

Phase 1D-1 executes analytical transformations only through a backend registry of typed operations.
The runner reads the reviewed `ApprovedDatasetRef`, applies explicit target selectors and parameters,
and writes an immutable analytical Parquet snapshot for every enabled operation. The session bundle
maps operation IDs and logical output refs to physical snapshot IDs.

The implemented registry is lag, lead, difference, year-on-year growth, period growth, natural log,
rebasing, rolling mean, down-frequency conversion and controlled group aggregation. Unsupported
catalog entries are not exposed in the HTTP-backed UI and are rejected by the backend. Weighted
group aggregation requires an explicit weight field; no aggregation method is selected silently.

Phase 2 adds affine unit conversion with an exact reviewed source unit, target unit, factor and
offset. Unit metadata is updated with the values and mismatched or absent unit metadata fails
closed. Down-frequency conversion now fixes calendar or fiscal-year convention, fiscal year-end
month and an explicit keep/drop/error policy for incomplete target periods. Retained partial
periods carry a numeric coverage field and a bundle warning. Stable attributes survive aggregation
only when every contributing row agrees.

Every executed operation records structured lineage containing its typed specification hash,
logical input/output refs, immutable input/output snapshot IDs and hashes, and input/output row
counts. Preview remains non-persistent and therefore shows no execution lineage.

Pipeline edits and Run use the standard command envelope, idempotency keys, expected-stage/hash
preconditions and append-only trace. Preview runs a reviewed prefix in memory and returns at most a
bounded page; it does not create a snapshot or execute arbitrary code.

Data Next now translates enabled, supported transformation and model intent IDs from the approved
Plan into a reviewable Pipeline draft. Indicator selectors are restricted to codes actually found
in the approved dataset, with requested Plan order preserved where possible. The current Plan
intent schema has no executable parameters or variable-role assignments, so the draft uses bounded
registry defaults and remains editable. This translation prepares configuration only: it does not
execute a capability or cross the Transformation Run approval checkpoint.

## Staged checkpoint behavior

Transformation Run records the second human approval and executes registered transformations.
Until Phase 1D-2 implements reviewed model jobs, a completed transformation run remains on the
Transformation route. Configured model jobs stay `not_run`, and the real HTTP path does not advance
into mock Output or claim that model/artifact generation succeeded.

## Consequences

- Raw and analytical files remain in local session storage. ADR 0014 permits AI ports to read their
  actual values through immutable, read-only snapshot grants; pipeline execution remains typed.
- Editing after a run preserves the prior bundle in history and clears the current bundle.
- Invalid parameters, downstream references and unsupported operations fail before execution.
- A Plan with no transformation intent has an explicit empty operation chain; model jobs read the
  approved dataset directly rather than requiring a placeholder operation.
- A single frequency-conversion operation accepts exactly one source frequency; mixed-frequency
  selections must be separated into reviewed operations.
- Python/Stata generation must later consume the same typed specifications; generated arbitrary
  code will not become an execution path.
- Workflow and Agent storage remain isolated.
