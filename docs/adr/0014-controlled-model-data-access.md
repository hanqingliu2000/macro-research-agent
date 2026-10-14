# ADR 0014: controlled model access to actual workflow data

Status: accepted

Date: 2026-08-26

## Context

The earlier privacy boundary limited planning and stage AI to schemas, summaries, diagnostics and
small approved excerpts. That prevents the model from checking real missingness, code anomalies,
time-series behavior, transformations and whether outputs faithfully represent the underlying
evidence. It also makes human/AI revision loops less useful because the model must reason from an
incomplete view.

## Decision

AI at Plan, Data, Transformation/Analysis and Output may inspect the actual relevant values. Access
is provided only by a model-data service that issues a read-only grant bound to:

- one Workflow or Agent session and one stage;
- one immutable upload checksum or dataset/result snapshot hash;
- a declared classification (`user_supplied`, `public` or `licensed`);
- bounded page reads (with typed filter and aggregate reads added only when registered); and
- provider-profile disclosure policy.

The first provider request may include a bounded page of actual values. The model can request
subsequent pages over the complete relevant dataset; the contract is not schema-only and not
sample-only. Typed filter or aggregate reads may be introduced behind the same grant, but are not
part of the current implementation. The service revalidates the content hash for each read and
rejects unknown, stale, wrong-session or changed sources.

The grant never provides arbitrary filesystem paths, SQL, URLs, browser/network access, credentials
or generic code execution. Data is untrusted page content: instructions embedded in cells, column
names or provider text have no authority. AI outputs remain typed proposals and cannot mutate data,
execute capabilities or cross the Plan, Run or Finish gates.

User-supplied and public values may be sent to an approved remote provider when the configured
profile permits it. Licensed values are denied by default and require explicit confirmation that
both the provider profile and source license allow remote disclosure. A local model may use the same
grant without remote disclosure permission.

Each model-data request produces an access receipt with provider/model, grant ID, session/stage,
classification, source/hash, selected columns, filters or page range, row count, page hashes and
policy version. Trace, logs and ordinary API responses do not duplicate observation values merely
to prove access.

## Consequences

- ADR 0001's schema-only disclosure sentence and ADR 0009's no-LLM observation rule are superseded.
- All new stage AI ports must accept grants from their mode-owned service implementing the shared
  access contract; bespoke sample-only prompt construction is not an acceptable substitute.
- Provider adapters must enforce remote disclosure before serializing any page into a request.
- Output authoring and visual review can compare renders, specifications and actual underlying data.
- Deterministic tests cover full paging, checksum binding, unknown grants, classification denial,
  wrong-session isolation, access receipts and prompt-like cell text treated as data. Restart,
  changed-source and live-provider coverage remain implementation-plan acceptance work.
- Local storage, controlled acquisition, typed execution and the three human approval gates remain
  unchanged.
