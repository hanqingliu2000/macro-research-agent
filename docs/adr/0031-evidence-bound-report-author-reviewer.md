# ADR 0031 — evidence-bound Report Author and Report Reviewer

Date: 2026-09-12
Status: accepted

## Context

Research Reports were previously assembled by a deterministic prose template and received only
structural checks. Codex-local reviewed chart pixels but skipped semantic report review. The Output
revision boundary admitted chart/table specification patches only, so a report finding could not
be resolved without going upstream or bypassing the governed workflow.

## Decision

Production Report Authoring uses the existing DeepSeek credential and endpoint, with
`MRA_REPORT_AUTHOR_MODEL` as an optional role override. It receives `ReportAuthorRequestV1` and
actual approved values only through a grant whose registered operations are `read_rows`,
`filter_rows` and `aggregate_rows`, plus the registered `read_model_results` broker. The current
author request materializes bounded, paginated `read_rows` and model-result reads; persisted request
metadata retains the grant rather than row values. Traces retain operation names, counts, grants
and hashes, never ordinary-log copies of values. Malformed output receives at most two
schema/semantic attempts and then fails closed. The deterministic author is an injected offline
test double, not a runtime fallback.

The analytical bundle and typed model results are committed before Report Authoring begins.
Report Author contract/provider failure therefore moves the session to an Output recovery state
instead of failing the combined Pipeline command. No partial ArtifactSet is committed. A user may
issue `retry_output_generation`, which reuses the hash-bound bundle and reruns Output generation
only; model execution is neither repeated nor silently substituted. The attempt and safe
field-path diagnostics are persisted in `pipeline.outputGeneration`, graph state and trace.
DeepSeek output uses a 12,000-token base budget, and a provider `finish_reason=length` receives one
contract-repair attempt with a doubled budget so truncated JSON is distinguishable from an invalid
field contract.

DeepSeek returns `ReportDraftV1`, not a file. Its sections, `EvidenceClaimV1` ledger, limitations,
citations and artifact references are checked against the approved Plan, handoff, dataset hash and
typed model-result hashes. Model-result hashes are recomputed before either authoring or review;
unsupported evidence/citation references, changed citation bindings and unsupported causal claims
are rejected. A deterministic renderer alone creates Markdown.

Codex-local receives a separate `ReportReviewRequestV1` and acts only as Report Reviewer. It checks
question coverage, numerical/directional/interval/sample consistency, promised comparisons and
forecasts, causal boundaries, uncertainty, limitations and sources. Its structured response may
contain findings and `ReportRevisionDirectiveV1`; a directive identifies existing sections,
required evidence references and acceptance criteria but contains no replacement prose and has no
mutation authority.

A user must approve a directive. DeepSeek may then rewrite only its named sections. Local
post-validation projects the untrusted response onto the authorized body/claim text fields while
reapplying immutable section structure, evidence/citation bindings, artifact references and
untargeted content. It then rejects missing preserved evidence or a no-op revision. This avoids
granting mutation authority merely because a model reserialized immutable arrays differently. The
new Markdown is an immutable report artifact and is automatically reviewed again. Report revision
is the sole explicit exception to the previous chart/table-only Output revision rule; it still
cannot alter data, model results, code or manifests.

Author and reviewer requests distinguish complete typed model-result record hashes from each
record's nested numerical-result hash; those scopes are expected to differ and are not an upstream
integrity conflict. Report contracts also state that generated artifacts are candidates, not frozen
manifest members: selection and frozen membership occur only at the user's Finish command.

Chart, table and report review share the existing hard maximum of three rounds. A missing dataset
or model result is `requires_upstream_stage` and creates no rewrite directive. A selected Research
Report must have semantic status `pass` before Finish. As of 2026-09-28, new visual reviews use
`academic-publication-placeholder-v1` and emit `VISUAL-RUBRIC-PLACEHOLDER` as an independent scope
advisory (historical missing-rubric records remain unchanged). The final Finish gate is bound to current
hashes. Artifact-bound preflight findings apply only to the selected package during review and
Finish; package-wide findings still apply regardless of selection.

## Consequences

- Report prose is editable through a narrow, evidence-preserving approval flow.
- The evidence ledger and immutable report versions make semantic review reproducible and visible.
- Provider outage or invalid output cannot silently fall back to canned production prose.
- A recoverable author failure preserves completed analysis and is independently retryable and
  idempotent.
- Codex-local still uses the locally authenticated Codex account; no OpenAI API key is introduced.
- A report cannot conceal missing upstream work through better wording.
