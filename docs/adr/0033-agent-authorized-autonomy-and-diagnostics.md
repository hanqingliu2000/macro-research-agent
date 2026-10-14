# ADR 0033 — Agent run authorization, bounded execution and diagnostics

Date: 2026-10-06. Status: accepted for implementation.

Clarification submission grants an immutable, versioned Agent execution envelope. Controllers
may apply typed proposals inside its scope without Workflow approval commands. Scope/budget
expansion and final freeze remain user-only. Agent-owned repositories, grants, files and API
namespaces cannot accept Workflow IDs. Shared code consists of stateless numerical, connector,
rendering and model-provider functions plus explicit storage/audit ports.

Run graph, task leases and persistent budgets control execution. All attempts, model final
outputs and repair contexts are recorded; secrets and hidden reasoning are removed. Diagnostic
payloads and immutable data references permit inspection and offline replay without duplicating
observation values into ordinary logs. Audit failure prevents new external calls.

Implementation now includes isolated HTTP/SSE runtime and diagnostic APIs, registered data/model
execution, coordinated two-check/three-review delivery and user-only freeze. Neutral storage/data
ports wrap shared pure computation without constructing Workflow managers or accessing its store.
Fixed forecast evaluation declares its holdout before fitting (MAE/RMSE), masks held-out targets,
retains validation results, and distinguishes final full-history forecasts. Descriptive results
include ordered observations and exact endpoint differences, not promises parsed from prose.

Code implementation and real-provider acceptance are separate milestones. A6 requires three
single-source and three multi-provider browser completions with Codex approval, explicit final
freeze and reload. Failures and recovery retain their original counts and evidence. The fixed
test suite must use temporary storage, never the running development service's directory.
Implementation and acceptance are tracked in development/agent_implementation_plan.md.

A6 record audit distinguishes mixed-version development runs from frozen-build acceptance.
Author-check v6 uses report policy for package semantics in round 1 and visual policy for
rendered charts/tables in round 2. Independent Codex approval remains mandatory; two calls and
all original budgets remain unchanged. Hard-ceiling errors are non-resumable even in legacy
waiting records, with preserved diagnostics and an explicit linked-run recovery path.
The first complete frozen-build six-run cohort produced one finalized result, not A6 acceptance.
Follow-up admission enforces report title policy before persistence; read-only reproduction
script/recipe evidence aligns Author and Reviewer without executing code or pre-freezing a manifest.
All original failures/checkpoints remain intact, and later smoke passes cannot replace the cohort.

2026-10-07: author-check v7 uses the registered structural-review path to provide read-only,
independently reconstructed, hash-bound SVG calculation evidence and typed finding references.
Passing native receipts cannot silently approve an AI failure; contradictions get one repair.
Real author checks/Codex review remain mandatory. Agent report edits now use a small text-only
section/claim contract; immutable bindings are copied by the controller. This is not a provider
fallback, approval expansion or budget change. Fixed-version live acceptance is still separate.

2026-10-07 recovery amendment: source metadata/coverage questions that require retrieval are
retained as bounded acquisition checks and assessed after acquisition, not human prerequisites.
Access/admission and genuine human decisions still fail closed. Shared safe HTTP classification
distinguishes credit/access failures from transport/schema failures. Agent retry is a separate
typed user command preserving research answers, task inputs, attempts and used/reserved budgets.
Credit/access/configuration must be confirmed restored; missing runtime credentials still reject.
Recovery projections/UI explain cause, action and actual remaining limits. Scope answers/Resume
cannot erase call failures or lift fixed task/phase/candidate/review ceilings. General execution
budget extension remains explicit. Recorded-provider regressions are not live cohort acceptance,
and old diagnostic evidence is preserved rather than retrospectively reclassified.

2026-10-07 fixed-build evidence: `863c07e` completed five of six original browser runs, not A6
acceptance. One semantic report review lacked bound chart-spec/content evidence despite a passing
independent visual review. Upstream-concealing edits were rejected; one explicit retry exhausted
the same three-call task ceiling without freeze. Future correction must transmit current owned,
hash-bound presentation evidence to report roles and distinguish handoff failure from reparable
format failure, not relax review standards or permit rewriting to hide missing evidence. This
acceptance made no code/configuration changes; all original runs and diagnostics are retained.

2026-10-07 implementation follow-up: `PresentationEvidenceV1` is a bounded stateless bridge through
mode-owned artifact read ports. Report Author/Reviewer receive current artifact/spec/data hashes,
full SVG/spec evidence, verified CSV headers and honest file/spec-only workbook scope. Current
revisions rebuild bindings; numerical values remain in registered grants. It is neither a visual
approval nor a generic file/tool permission. Legacy records remain readable without silently
becoming provider-ready. Missing/corrupt evidence and required upstream results stop Agent
before Output Editor; repair advice blocks ineffective retry/scope/re-review paths without
altering old budgets or outcomes. UI error recovery explains the evidence repair instead of a
misleading format retry. Unit/integrated recorded-provider tests are not real-model A6 acceptance.
