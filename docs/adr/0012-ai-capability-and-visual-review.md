# ADR 0012: typed AI capability orchestration and visual output review

Status: accepted

Date: 2026-08-25

Amended: 2026-09-12 — add the opt-in Codex-local direct-render adapter while explicitly recording
the project-specific visual authoring and acceptance rubric as missing.

Amended: 2026-09-13 — lock production Output review to Codex-local and remove the configurable
deterministic fallback.

Amended: 2026-09-28 — adopt one fixed Nature-inspired academic placeholder for the bounded
three-round chart acceptance experiment; preserve final creative-direction/print-profile gaps.

## Decision

Runtime AI is introduced through stage-specific typed ports and versioned capability/skill
registries. AI responses are proposals. They cannot advance workflow state, call an unregistered
function, execute arbitrary code or bypass the Plan, Run or Finish approval gates.

Every AI request, proposal, review, approved invocation and result is represented in the durable
research state graph from ADR 0013. AI adapters cannot move current pointers or complete execution
nodes; GraphService and typed user commands own those transitions.

Workflow Plans include a durable `CapabilityInvocationIntent` list so connector, function, model,
renderer, reviewer and runtime-skill calls are visible before execution. Missing tools are recorded
as non-executable placeholders and never represented as successful calls.

Output adds an independent Review AI for the complete selected ArtifactSet. Deterministic
structural/hash/completeness checks run first. The model reviews actual underlying data through ADR
0014 grants together with package summaries and metadata for cross-artifact consistency; a
multimodal model additionally reviews direct chart/table renders against a versioned guideline.
Reports receive a separate semantic evidence review, not a report-page visual rendering. The
reviewer returns a typed, rule-addressed `OutputReviewReport`.
Corrections are typed specification patches and are applied by deterministic renderers only after
user approval. The visual model does not paint final artifacts and cannot freeze the artifact set.

Visual artifact review is distinct from browser visual testing. The reviewer receives the artifact
render, not a screenshot of the application. Routine UI tests continue to avoid model-driven
browser screenshots.

## Privacy decision

ADR 0014 generalizes model access beyond rendered values. Output review may receive both the exact
artifact render and read-only access to its underlying immutable data. Provider profile and data
classification policy must permit the disclosure; licensed data fails closed by default. The trace
records artifact/dataset hashes and an access receipt without copying values. Without authorization,
remote model review fails closed. Structural or human checks do not replace the formal review
approval required by the current Finish gate.

The production `codex-local` profile invokes the locally authenticated Codex runtime in an ephemeral,
read-only temporary directory. It receives only checksum-bound direct renders, their typed
specifications and the stage-bound underlying-data context; application secrets and repository
contents are excluded. Workflow reviews use the Output command, including approved-revision
reassessment; Agent may schedule bounded review inside its user authorization envelope. Neither
role can finalize.
Failure, missing login or timeout fails closed; the deterministic structural reviewer remains an
internal automated-test fake and is never selected as a production fallback.

The active interim rubric is `academic-publication-placeholder-v1`; its single-source rationale,
operational rules, severities and exclusions are recorded in
`guidelines/academic-publication-placeholder-v1.md`. The same typed subset reaches author/reviewer
context. Each new review records rubric version/hash/status; the manifest includes that review.
Historical records remain unchanged. `VISUAL-RUBRIC-PLACEHOLDER` is a scope advisory only; all
substantive visual failures must be resolved. Codex cannot author executable patches or replace
Finish. Final creative direction and journal-specific print certification remain unprovided.
Other remote API-provider configuration remains inactive until separately implemented and approved.

## Consequences

- Provider-native tool calling is always narrowed through registry schemas and server-side policy.
- Function, interface, skill, model and renderer versions become reproduction-manifest inputs.
- Review findings and approved patches are durable nodes; private chain-of-thought is never stored.
- Live-model quality evaluation is separate from deterministic CI and uses approved fixture sets,
  cost limits and privacy-safe artifacts.
