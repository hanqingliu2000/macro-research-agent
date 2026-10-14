# Implementation plan

Current public-development boundary (2026-10-14): use
[current status](current_status.md) for present capabilities and [the README](../../README.md)
for supported local setup. Earlier phase sections record historical implementation slices; their
then-disabled features do not override later delivery. Workflow is review-gated, Agent is
implemented but Experimental with strict A6 fixed-cohort acceptance still open (latest 5/6).
Additional provider profiles remain deferred, and no HTTP authentication/hosted deployment is
implemented. See ADR 0034 for the public-distribution and documentation-alignment decision.

Updated: 2026-09-28

## Agent autonomous development (approved 2026-10-06)

The independent A0–A6 delivery plan is tracked in `agent_implementation_plan.md` and ADR 0033.
Agent clarification submission authorizes bounded execution; final freeze remains user-only.
This does not resume Phase 4 or remove Workflow's three gates. Transactional audit, complete
redacted diagnostic evidence and persistent budgets are prerequisites for real Agent calls.

## Phase 0 — repository and governance

- [x] Create an independent Git repository on main.
- [x] Establish backend, frontend, documentation, guideline and CI directories.
- [x] Record product context and contributor rules.
- [x] Record dataset-acquisition and testing boundaries as ADRs.
- [x] Add architecture, connector, API, trace and data-source documents.
- [x] Add minimal FastAPI and React scaffolds.
- [x] Establish the remote development repository and push the baseline.

Exit criterion: a new contributor can understand the scope, boundaries, directory structure and next milestone without relying on chat history.

## Phase 0.5 — frontend interaction prototype

- [x] Define authoritative session status, research-node lifecycle and invalidation rules.
- [x] Define frontend routes and separate standard research routes from backend admin trace.
- [x] Build Home/Sessions, Research Workspace and Settings routes.
- [x] Build the initial persistent-conversation prototype (superseded and removed in Phase 0.7).
- [x] Implement deterministic mock sessions with localStorage persistence.
- [x] Implement clarification batches, plan revisions and three version-targeted approval gates.
- [x] Show concise research-step progress instead of detailed trace events.
- [x] Add component and workflow tests without browser screenshots.

Exit criterion: a user can review the complete intended interaction and approval flow without a
live data connector, LLM provider or workflow API.

## Phase 0.6 — isolated Agent Mode prototype

- [x] Decide that Workflow and Agent sessions are separate and non-convertible.
- [x] Define Agent status, node, router, route and policy contracts.
- [x] Create isolated frontend and backend Agent namespaces.
- [x] Build Agent-only session storage and provider.
- [x] Build Agent session list, attachment composer, clarification and final-result chat.
- [x] Add mock autonomous routing steps and artifacts.
- [x] Add cross-mode isolation and Agent workflow tests.

Exit criterion: a mock Agent session can proceed from question and attachment metadata through
clarification to a complete research package without reading or mutating Workflow sessions.

## Phase 0.7 — four-stage Workflow interaction prototype

- [x] Replace the five-step workspace with Plan, Data, Transformation and Output subroutes.
- [x] Move Workflow frontend code into an isolated workflow namespace.
- [x] Define stage I/O, chat command, country-group aggregation and invalidation contracts.
- [x] Build Plan patch review, direct Plan editing and controlled Plan Next.
- [x] Build Data sources, preview, reversible preparation and XLSX mapping mock interactions.
- [x] Build the ordered transformation pipeline and separately targeted model jobs.
- [x] Build Output controls, stage-scoped revision chat, artifact preview and selective export.
- [x] Add route guards, upstream impact confirmation, stale projections and structural tests.

Exit criterion: the deterministic mock UI supports the complete four-stage review loop, including
returning upstream and invalidating dependent work, without reading or mutating Agent sessions.

## Phase 0.8 — Slate Workbench visual system

This records the initial Workflow-only rollout; Phase 0.9 promotes the visual system to both modes.

- [x] Scope a dark Slate token system to Workflow Mode without changing Agent Mode.
- [x] Replace the Workflow shell with an Activity Bar, Research Explorer and editor toolbar; remove
  redundant Explorer headers/footers and the Workflow status bar after annotated review.
- [x] Present the four stages as compact editor tabs whose icons, labels and semantic attributes
  convey current, completed, stale and locked states without repeated state captions.
- [x] Standardize stage panels, forms, chat, data grids, operation lists and artifact previews.
- [x] Add local SVG icons, a skip link, visible focus, dialog focus management and reduced motion.
- [x] Support a resizable desktop split and stacked narrow-screen layouts.
- [x] Document the visual and accessibility contract and extend DOM accessibility tests.

Exit criterion: Workflow Mode reads as one coherent research developer tool, remains fully keyboard
operable, passes component/lint/build checks and does not import or restyle Agent Mode.

## Phase 0.9 — global Research Workbench rollout

- [x] Move shared tokens and the SVG icon family from Workflow into a neutral `ui/` namespace.
- [x] Build a stateless Workbench shell shared by Workflow and Agent adapters.
- [x] Apply the Slate editor and Explorer language to Agent Home and Chat, then remove redundant
  Explorer headings/footers and the Agent status bar after annotated review.
- [x] Add Agent attachment inspection/removal, textual route states, semantic result tables and code-copy controls.
- [x] Remove obsolete unscoped Workflow/Agent rules from the global stylesheet.
- [x] Add the local application mark and document the offline font/asset policy.
- [x] Enforce that shared UI cannot import either mode's domain or state.
- [x] Extend DOM/accessibility and mode-isolation tests without browser screenshots.

Exit criterion: Workflow and Agent present one coherent developer-tool design while their providers,
session types, route state, storage and future API repositories remain separate.

## Phase 0.10 — responsive and ultrawide hardening

- [x] Add bounded Workflow, Agent and Home surfaces for 2560–3840 px viewports.
- [x] Replace unbounded percentage/fixed splits with clamped control and route-outline widths.
- [x] Apply readable measures to chat, report and analytical-result prose.
- [x] Preserve wider, independently scrollable contracts for tables, data grids and code.
- [x] Remove the 901 px split-layout cliff and the 561–681 px session-table clipping range.
- [x] Add screenshot-free numeric layout contracts for 1440, 1920, 2560 and 3840 widths.

Exit criterion: 4K layouts retain developer-tool density without stretched prose or disproportionately
narrow side panels, while tablet and mobile layouts continue to collapse without root overflow.

## Phase 0.11 — component composition hardening

- [x] Split the shared Workbench shell into Activity Bar, Explorer and Status Bar components.
- [x] Move shared shell display contracts into a presentation-only type module.
- [x] Reuse a typed Workflow section heading across stage panels.
- [x] Reuse one controlled Workflow chat composer for Plan and Output threads.
- [x] Keep Agent attachments and all mode-specific commands inside their existing feature namespaces.
- [x] Add structural tests for component composition and mode-domain isolation.

Exit criterion: reusable UI primitives own markup and accessibility behavior while route components
continue to own commands, domain state and stage-specific orchestration.

## Phase 1 — thin vertical slice

Phase 1 is split into dependency-ordered increments. Phase 1A through Phase 1D-4, the local
portion of Phase 1C and the deterministic/local portions of Phase 1E are complete. Bounded live IMF
acquisition is now implemented as an early Phase 3 slice. Broader live-provider evaluation and
authorized remote multimodal review remain separate deferred acceptance slices.

### Phase 1A — durable Workflow spine and HTTP adapter (complete)

- [x] Reconcile frontend Workflow types and backend Pydantic contracts with explicit serialization
  fixtures for statuses, stages, snapshot hashes and command envelopes.
- [x] Add a SQLite repository for Workflow sessions/projections behind a Workflow-owned port; keep
  the Agent repository contract and future tables separate rather than introducing a shared session
  table or endpoint.
- [x] Add an append-only JSONL trace writer with monotonic per-session sequence allocation,
  redaction hooks and checksum references.
- [x] Implement Workflow session list/create/get, node list and projection endpoints.
- [x] Implement idempotent command dispatch with expected-stage/expected-hash checks and HTTP 409
  conflict responses.
- [x] Evolve the synchronous mock `WorkflowService` into async query/command methods with explicit
  loading, failure and 409-conflict results in the provider.
- [x] Add a typed HTTP adapter while retaining a Promise-based deterministic mock adapter for
  component tests and offline UI development.
- [x] Add restart/recovery, duplicate-command and stale-write ASGI tests.

Exit criterion: a Workflow session created through FastAPI survives process restart, exposes an
append-only trace and can be resumed by the existing routed frontend without losing mock-test
determinism.

Acceptance completed with backend restart/idempotency/conflict/trace tests and frontend
serialization/409/DOM/reducer tests. The HTTP adapter is enabled with
`VITE_WORKFLOW_ADAPTER=http`; the default remains the deterministic mock adapter for offline UI
development.

### Phase 1B — backend-owned Plan and local-file intake

- [x] Implement XLSX/CSV/JSON upload storage and metadata/schema inspection; after ADR 0014, add a
  controlled checksum-bound path that gives the planning provider actual values.
- [x] Add the common planning-provider interface, JSON-Schema structured-output validation and
  provider request builders. Use a deterministic provider for Phase 1B acceptance; API-key-backed
  OpenAI/DeepSeek execution and model-quality evaluation remain deferred.
- [x] Implement clarification batches, Plan drafts/patches, immutable Plan snapshots and Plan approval.
- [x] Implement the controlled geography resolver and versioned entity/group membership records.
- [x] Persist Plan chat and approval events while keeping administrative trace out of the normal UI.

Exit criterion: a real uploaded-file schema and research request can produce a reviewed, approved
Plan snapshot through the existing Plan route using the deterministic provider. Upload-inspection
responses and Plan trace events do not echo values, while the provider receives them through a
read-only grant. The later Data workspace may return a bounded local preview to the research UI.

Phase 1B explicitly does not fetch external economic data, normalize observations, execute a live
LLM request or evaluate model quality. Those concerns begin only after the local-file and Plan
contracts have passed acceptance.

The original Phase 1B acceptance was completed with schema-only CSV/JSON/XLSX tests, path and
media-type validation,
backend-owned Plan command tests, stale-write protection, immutable snapshot/approval assertions,
controlled geography resolution, trace raw-value exclusion and frontend HTTP/mock adapter tests.
ADR 0014 supersedes only the provider-input restriction; checksum-bound actual-value access and
paging tests now cover the revised boundary.

### Phase 1C — P0 data workspace

Phase 1C is split so the local data contract is accepted before any network connector is added.
The completed 1C-local slice remains the execution baseline. The IMF connector was expanded on
2026-09-10 from its initial CPI slice to an explicit multi-dataflow contract.

- [x] Implement the local CSV/JSON/XLSX loader and canonical normalized observation schema.
- [x] Implement provenance, quality diagnostics, entity/indicator crosswalks and paginated previews.
- [x] Implement typed Data hygiene operations, immutable snapshots, active-pointer undo and approval.
- [x] Implement real controlled XLSX export/import, manifest validation, schema mapping and active
  dataset replacement.
- [x] Implement bounded public IMF SDMX 2.1 slices for CPI and annual WEO: per-dataflow metadata
  and dimension contracts, typed query validation, per-member retry, checksum-verified shared
  public-response caching, session-owned raw copies, canonical normalization, provenance, Plan
  constraints and immutable Data snapshot creation.
  The repeatable admission procedure is documented in
  [`imf_dataflow_onboarding.md`](imf_dataflow_onboarding.md).

1C-local exit criterion: an approved Plan can produce a reviewed `ApprovedDatasetRef` from a local
file, with checksums and reproducible preparation lineage. This criterion is complete. The IMF
connector's registered CPI and WEO slices satisfy the same snapshot/provenance contract. Additional
IMF dataflows are not implicitly trusted: each must add a reviewed registry entry, real metadata
fixture, normalization test, bounded live smoke test and Plan contract before activation.

The IMF connector's separate acceptance also runs the connector-specific `LRS-DATA-02` through
`LRS-DATA-04` slice from `longitudinal_acceptance_scenario.md`: confirmed queries fan out over
resolved members, aggregation waits for its declared parents, retry does not duplicate completed
calls, coverage policy is explicit, and raw/normalized/provenance hashes survive restart. This
connector gate is independent of Phase 1E-0. Recorded tests cover member fan-out, a transient
failure, completed-member reuse and stable raw/normalized hashes; live public acceptance confirmed
CPI and WEO metadata and structure-specific data responses without credentials. Cross-session tests
also prove that a second session avoids the provider request while retaining its own raw evidence.
Full longitudinal user UAT remains part of the final acceptance run.

Live CPI smoke acceptance (2026-09-10): a DeepSeek-assisted Plan for China all-items CPI generated
a concise session title and the typed `CPI`/`CHN`/`_T`/monthly query. After explicit geography and
Plan approval, public IMF acquisition produced a three-row January–March 2025 Data snapshot. The
test caught and fixed IMF's `2025-M01` versus canonical `2025-01` period representation; the retry
reused the already checksummed raw member response.

### Phase 1D — execution and governed output

#### Phase 1D-1 — typed transformation execution

- [x] Persist backend-owned Pipeline commands with expected-stage/hash and idempotency checks.
- [x] Implement typed editing, legal reorder, enable/disable, delete, target/parameter update and
  active-pointer edit undo.
- [x] Implement real previews plus immutable analytical Parquet snapshots for lag/lead, difference,
  year-on-year and period growth, log, rebasing, rolling mean, frequency conversion and controlled
  group aggregation.
- [x] Record Pipeline execution approval, operation-to-snapshot lineage, diagnostics and trace events.
- [x] Connect the Transformation HTTP adapter while retaining deterministic mock tests.

#### Phase 1D-2 — reviewed model execution

- [x] Add typed descriptive-statistics, correlation and OLS model specifications.
- [x] Support nonrobust, HC1 and entity/frequency-blocked HAC covariance for OLS.
- [x] Resolve every job input to the approved dataset or a registered pipeline-output snapshot.
- [x] Rebind model inputs atomically when their source operation is deleted, preserve that edit in
  undo history, expose the repaired binding, and reject any unresolved legacy reference before Run.
- [x] Persist sample counts, input/specification/result hashes, diagnostics and result payloads.
- [x] Expose model configuration and structured result previews in Transformation.
- [x] Verify numerical results, invalid specifications, idempotent replay, trace and restart recovery.

Phase 1D-2 keeps the session in Transformation after analysis completes. It does not generate code,
create Output artifacts or present mock Output as a real downstream result.

#### Phase 1D-3 — generated reproduction code

- [x] Generate Python entrypoints from the exact reviewed operation/model JSON specifications.
- [x] Reuse the deterministic execution runtime for backend runs and generated Python reproduction.
- [x] Generate Stata do-files only for transformations and covariance semantics with equivalent
  translations; record an explicit warning when a reviewed job is outside that support boundary.
- [x] Persist code files, specification hashes, content checksums and bundle references.
- [x] Add checksum-validating preview/download endpoints and Transformation code review UI.
- [x] Verify generated Python analytical data/model results against backend outputs and restart.

Phase 1D-3 generated files are review/download artifacts and are never executed by the backend as
arbitrary code. Phase 1D-4 now packages them after a successful reviewed run.

#### Phase 1D-4 — governed basic output

- [x] Generate a checksum-addressed analytical CSV and SVG chart from the final dataset snapshot.
- [x] Export an XLSX workbook with analytical data, model results, provenance, diagnostics, chart
  data and a native Excel chart under the fixed `basic-v1` guideline.
- [x] Package immutable Python and supported Stata refs without silently regenerating code.
- [x] Advance successful Pipeline Run into Output Review and replace real HTTP Output selection and
  final approval with backend-owned typed commands.
- [x] Freeze selected artifacts and create a JSON reproduction manifest at final approval.
- [x] Add checksum-validating preview/download, workbook-cell/chart-XML, idempotency and restart
  acceptance tests.

At this historical Phase 1D-4 milestone, Research Report generation and model-driven/selective
Output revision were disabled for real HTTP sessions. They were subsequently implemented in
Phase 1E and evidence-bound report hardening; see current status rather than this historical limit.

#### Remaining Phase 1D

- [x] Generate equivalent Python from the same typed transformation/model specifications.
- [x] Implement descriptive statistics, correlation and OLS/HAC from reviewed specifications.
- [x] Generate supported Stata do-files from the same typed specifications.
- [x] Export an Excel workbook with normalized/analytical data, provenance, diagnostics and a basic
  guideline-controlled chart/table.
- [x] Implement artifact hashes, final approval and reproduction manifest.
- [x] Implement typed, selective artifact regeneration from reviewed Output patches.
- [x] Replace current Workflow execution/approval paths with the HTTP service while retaining fixture
  adapters for deterministic tests.

Local-file exit criterion: one approved request can move from an uploaded dataset to a reproducible
reviewed workbook and code package. This is complete. The later IMF connector slice is also active
for its registered CPI and annual WEO contracts.

## Phase 1E — human-in-the-loop AI and capability orchestration

Phase 1E connects AI to the real Workflow without weakening the typed execution and approval
boundaries completed in Phase 1. See `state_graph.md`, `ai_capability_orchestration.md`, ADR 0012
and ADR 0013. `longitudinal_acceptance_scenario.md` preserves `LRS-001`, the cross-day realistic
research journey used as the final large acceptance test and as phase-specific slices below. The
document defines tests only; a slice is not accepted until its implementation and evidence exist.

### Phase 1E-0 — durable research state graph

- [x] Add versioned `ResearchNode`, `GraphEdge`, `NodeAttempt`, `Checkpoint` and `ActivePointer`
  contracts over the existing session-node and immutable-snapshot foundation.
- [x] Add SQLite graph tables behind `ResearchGraphRepository`, graph validation/impact/readiness
  services and administrative graph/node/attempt inspection endpoints without requiring a graph
  database or external workflow framework.
- [x] Backfill existing Plan/Data/Pipeline/Output legacy nodes into typed nodes, dependency/
  consumption/production/authorization edges, checkpoints and active pointers while retaining
  compatible session/projection API responses.
- [x] Move accepted stage mutations into a transactional `GraphService` command boundary; routes
  and stage services no longer call the low-level repository commit directly.
- [x] Replace the temporary `result_session` compatibility materialization with graph-native typed
  transition plans, then regenerate the legacy session document strictly as a projection.
- [x] Add `WorkflowProjectionService` and derive status, active/reachable stages, current refs and
  review requirements from current non-stale graph nodes/pointers where represented; route
  navigation remains read-only.
- [x] Stop normal projections from reading legacy exceptional/transition fields whenever the graph
  contains a current node; persist node stage so failed/cancelled projections are also graph-derived.
- [x] Reject Plan, Data, Transformation and Output mutations after completion so the frozen session
  remains an immutable audit record; a future continue/fork flow must create a separate lineage.
- [x] Remove the explicit empty-graph migration fallback after the legacy-session compatibility
  window closes.
- [x] Implement graph-level dependency-aware descendant invalidation, unaffected-sibling
  preservation and durable `invalidates` edges.
- [x] Route existing upstream typed commands through graph invalidation and transactional active-
  pointer movement; keep their current impact dialogs and exact previews.
- [x] Implement idempotent atomic node claim/complete/fail/cancel, retry as a new attempt and orphan
  recovery primitives so interrupted AI or capability calls cannot corrupt graph state or duplicate
  cost.
- [x] Implement typed multi-parent readiness and fan-in tests for future country-member acquisition,
  independent model jobs and artifact generation/review.
- [x] Add the bounded scheduler/executor that claims ready fan-out work and releases fan-in nodes.
- [x] Add explicit record/proposal/execution/review node authority and reject proposal nodes from
  execution claim or checkpoint authorization.
- [x] Persist actual Plan/Data/Analysis AI proposals with proposal authority and exact input hashes.
- [x] Persist Output AI authoring proposals and reviews with proposal/review authority.
- [x] Add initial graph contract/invariant, cycle, dependency-impact, checkpoint-readiness,
  persistence/backfill, immutable-terminal-ref, append-only-attempt and restart tests.
- [x] Add transactional duplicate-claim, gate-authorization, retry/orphan recovery and fan-in
  readiness tests. Initial graph-projection equivalence is covered across Plan, Data,
  Transformation and Output states.
- [x] Add proposal execution/authorization rejection tests.
- [x] Return typed graph-transition summaries for created nodes/edges/checkpoints, pointer changes
  and invalidated nodes; record the same summary in the command trace event.
- [x] Add stale-target AI proposal rejection before proposal persistence.
- [x] Add full command/projection equivalence tests as the command authority migrates.
- [x] Invoke startup orphan recovery using a configured cutoff while preserving prior attempts and
  leaving capability execution explicitly triggered rather than automatic.

Phase 1E-0 exit criterion: the four-stage UI and existing typed execution paths are projections over
one durable graph whose readiness, invalidation, retries and checkpoints can be reconstructed and
tested independently of routes, chat and LLM providers.

`LRS-001` Phase 1E-0 acceptance slice:

- closing/restarting at every stage reconstructs the same current pointers, reachable route,
  checkpoint and public projection from durable graph state;
- viewing upstream does not mutate state, while confirmed Plan/Data/Pipeline edits stale exactly
  their descendants, preserve old snapshots and never rerun automatically;
- concurrent stale writes return typed conflicts, repeated commands are idempotent, and failed,
  cancelled, retried and orphaned attempts remain append-only;
- the bounded executor releases fan-out/fan-in work only when dependencies and the exact Plan, Run
  or Finish checkpoint are satisfied;
- graph-native commands and compatibility projections are equivalent at every non-AI scenario
  checkpoint available in this phase, including failure/cancellation and restart. These criteria
  map to `LRS-RECOVERY`, `LRS-BACKTRACK` and `LRS-INV-*`.

### ADR 0014 cross-cutting model-data access

- [x] Replace the schema/sample-only model boundary with Workflow-owned read-only grants bound to
  session, stage and immutable upload/snapshot hashes.
- [x] Wire planning context to actual upload values with a bounded first page and complete paging.
- [x] Enforce wrong-session/stage rejection and deny licensed remote disclosure by default while
  retaining an explicit local-provider path.
- [x] Add deterministic tests for actual values, full paging, prompt-like cell text, grant binding
  and licensed denial without echoing values in normal API responses.
- [x] Persist provider/model access receipts and policy versions in append-only trace for each
  implemented Plan attachment page read.
- [x] Add typed filter/aggregate reads and use snapshot grants in Data, Transformation and Output
  ports.
- [ ] Add restart/changed-source, column/filter scope, large-dataset and opt-in live-provider tests.

The strategy changes what AI may inspect, not what it may execute: the three human gates, typed
capability registry, acquisition allowlist and prohibition on arbitrary code/network/filesystem
access remain unchanged.

### Phase 1E-1 — capability, function and skill registry

- [x] Implement versioned `CapabilityDescriptor`, `RuntimeSkillManifest` and
  `CapabilityInvocationIntent` contracts.
- [x] Register existing geography, aggregation, local-file, Data operation, Transformation, Model,
  renderer and manifest functions with JSON-Schema inputs/outputs and approval policies.
- [x] Add `planned` placeholders for IMF, Research Report, structural reviewer, visual reviewer and
  selective regeneration; placeholders have no handler and fail closed.
- [x] Add stage-filtered capability/skill discovery APIs and an admin registry inspection view.
- [x] Persist capability/skill versions, validated-argument checksums, result refs, latency, provider and
  failure state in trace and the reproduction manifest.
- [x] Add policy tests proving an AI cannot invoke arbitrary network, browser, filesystem, Python,
  shell or Stata tools.

Phase 1E-1 exit criterion: every currently executable function used by `LRS-001` has one versioned,
schema-valid descriptor with stage and approval policy; future Report/reviewer functionality is
an honest handler-less `planned` capability; stage discovery is filtered correctly; unavailable or
unsafe invocation fails closed; and each accepted invocation records version, argument checksum,
attempt, latency and immutable result refs without requiring a live LLM.

### Phase 1E-2 — conversational Plan AI

- [x] Implement typed planning adapters behind `PlanningAssistantPort`; retain the deterministic
  adapter only as an injected automated-test fake.
- [x] Generate validated `ClarificationBatch`, `PlanDraft` and `PlanPatch` outputs; reject prose or
  tool calls outside the active response schema.
- [x] Extend the Plan with a visible capability invocation plan covering intended Data Source,
  Transformation, Model, Output and Review calls, including availability and required gates.
- [x] Keep Plan Chat proposal-only: Apply/manual Save creates the immutable snapshot; the model
  cannot approve the Plan or start acquisition.
- [x] Add prompt/version fixtures, malformed-output fail-closed recovery, provider retry/cost
  limits, privacy assertions, model-data access receipts and task-level quality evals against
  reviewed scenarios.
- [x] Add a versioned, machine-readable public-source knowledge index and bounded topic retrieval to
  Plan context. Keep broad provider holdings separate from registered executable dataset slices.

Phase 1E-2 exit criterion: `LRS-PLAN-02` through `LRS-PLAN-09` pass with deterministic AI fixtures.
Across multiple simulated days, a user can answer two clarification rounds, partially accept/reject
AI patches, edit the Plan manually and obtain a new proposal against the current hash. Stale or
malformed proposals cannot Apply, unresolved geography/aggregation blocks Next, no raw attachment
values appear in normal API/trace payloads, provider data access stays bound to the exact attachment
checksum, and no AI action can approve the Plan or start acquisition. Opt-in live
provider quality/cost evaluation is reported separately from this deterministic gate.

Implementation evidence: deterministic test-fixture acceptance covers two clarification rounds, proposal graph
authority, field-level Apply/reject, stale-target rejection, provider/tool/malformed-output failure,
bounded retry and two reviewed task-quality fixtures. Product/development Plan requests are locked
to DeepSeek; no live provider quality/cost result is claimed without configured credentials and a
separate run.

Live integration follow-up (2026-09-09):

- [x] Lock the backend Plan provider and public capability contract to DeepSeek; remove runtime
  deterministic/OpenAI selection and fail startup when `DEEPSEEK_API_KEY` is absent. Preserve only
  the explicit offline test fake so CI remains network-independent (2026-09-12).

- [x] Update opt-in DeepSeek Plan configuration to the official `deepseek-flash` alias
  (V4.1 Flash, 2026-09-10); retain prior acceptance evidence and existing human gates.
  Verification: 9 planning-adapter tests passed; a live synthetic China-inflation
  clarification request returned 6 schema-valid questions, each with selectable options.
  This migration smoke test does not replace the full end-to-end acceptance run.
- [x] Run configured DeepSeek v4 Flash through two clarification rounds, Chinese Plan revision,
  partial Apply, stale rejection, manual rejection, Plan approval and a local forecast/output journey.
- [x] Validate source/transformation/model namespaces and catalog stages before accepting live
  output; ground versions, availability and gate policy in the server registry.
- [x] Preserve current answers, questions, recent conversation and reference date in planning context;
  expose Plan assumptions/blockers and retain failed revision input.
- [x] Let every clarification question accept a separately labeled custom answer; render nested
  Plan Patch values as structured fields rather than raw JSON; deterministically remove explicitly
  non-blocking discovery/index bookkeeping from blockers and cautions.
- [x] Prevent Plan AI from asserting observation-level gaps or dataset absence before acquisition;
  reject clarification questions with unverified coverage premises and defer empty/missing/coverage
  findings to the connector result. Prioritize period/value/unit in Data preview and define
  `missingShare` over canonical observation values rather than optional metadata cells.
- [x] Keep model-supplied geography confirmation from satisfying the human approval requirement.
- [ ] Expand the live corpus and measure research quality, variability and token/cost accounting.
- [x] Translate enabled Plan transformation/model intent IDs into a reviewable Transformation draft
  at Data Next, persist and bind ordered `ModelIntentV2.variables` to indicators actually present in the
  approved snapshot, and preserve the explicit Transformation Run gate. Output forecast
  completeness follows reviewed model-job variables/horizons rather than all source indicators. An intentionally empty operation
  chain is represented as “no data transformation required,” not as a loading or transfer failure.
- [x] Add frequency-aligned `ResearchPeriod`, structured `ForecastHorizon` and ordered
  `ModelIntentV2` variable roles. The compiler no longer derives variables or horizons from prose;
  `targetIndicators` is only a compatibility projection. Model parameters outside this Plan
  contract retain bounded registered defaults and remain reviewable before Run (issue #22).
- [ ] Extend governed output specs/review to forecast overlays and uncertainty charts; current
  forecast values and intervals are exported in CSV/XLSX, and charts show historical data.

The bounded integration evidence is in `plan_ai_acceptance_report.md`; it does not complete all
`T3` or the cross-day `T4` acceptance package.

### Phase 1E-3 — Data and Analysis assistants

- [x] Implement `DataAssistantPort` proposals for registered local-file acquisition context, schema mappings and
  hygiene operations using Plan, diagnostics and actual active-snapshot values through a read-only
  data-access grant.
- [x] Implement `AnalysisAssistantPort` proposals for ordered typed transformations, target
  selectors, model jobs and parameters with access to the actual approved inputs/relevant outputs.
- [x] Add structured proposal diff/impact UI to Data and Transformation; approved proposals call
  existing typed services and preserve normal undo/invalidation behavior.
- [x] Require explicit user approval before connector execution and Transformation Run; assistants
  cannot silently incur provider cost or rerun stale work.
- [x] Evaluate capability selection, parameter validity, unsafe tool refusal and recovery from
  unavailable placeholder capabilities.
- [x] Compile explicit Analysis requests into operation/subset/protected-indicator constraints and
  enforce those constraints after provider output. “Keep unchanged” indicators cannot enter a
  proposed transformation, an explicit Difference cannot be replaced by growth, already-rate
  indicators are excluded from automatic growth, and Difference may carry a reviewed output unit.
- [x] Enforce Data AI negation/preservation constraints after provider output. “Keep missing” blocks
  missing-value removal, “only sort” blocks other mutations, and requested missing diagnostics are
  returned as bounded entity/indicator/period findings distinct from selectable operations (issue 14).

Phase 1E-3 exit criterion: the Data and Transformation portions of `LRS-001` pass with deterministic
assistant/capability fixtures. A user can selectively accept, reject or edit typed AI proposals;
combine them with manual quick cleaning, Undo and a rejected-then-corrected XLSX round trip; build,
reorder, disable and retarget a typed operation chain; configure independent models; preview without
execution; and explicitly authorize Run. Every proposal is hash-bound, illegal reorder and stale
Apply fail without mutation, dataset replacement invalidates Analysis/Output, partial failures retry
without rerunning successful siblings, and AI has no uncontrolled data path. AI can
page/filter/aggregate across complete relevant snapshots, but cannot access arbitrary files,
other sessions, generic SQL/network tools or mutation commands.

Offline implementation evidence uses deterministic Data/Analysis fixtures to page across complete
immutable values, emit strict typed items and persist proposal-authority graph nodes. Current real
Data/Analysis assistance uses separate DeepSeek role adapters, not a deterministic runtime fallback. Local-file schema
mapping, cleaning, transformation and model items support selective Apply/reject; manual changes
make older proposals fail closed. Typed filter/aggregate reads share the same grant and value-free
receipt. Apply never runs a connector or Pipeline, and the existing Data Next/Run checkpoints remain
the Workflow execution authorities for those commands. Analysis summaries identify the input dataset, proposed output
step, target indicators and unit interpretation; a provider response that contradicts an explicit
operation, exclusion or subset fails closed before persistence. Public connector query execution
remains a separate connector slice and is represented honestly by unavailable registry entries.

Data preview pagination uses one shared eight-row page size from request through rendering. Page
ranges are derived from returned rows, row numbers remain global, navigation is locked while a page
loads, and 9/56/100/101-row UI cases prove that every observation is reachable (issue 16).

### Phase 1E-4 — visual artifact authoring and Review AI

- [x] Implement versioned `ChartSpec`, `TableSpec`, `OutputReviewRequest`, `OutputReviewReport`,
  rule-addressed findings and typed chart/table patch schemas.
- [x] Extend `ArtifactRenderer` to emit reproducible SVG/XLSX plus a fixed-size PNG review render
  bound to the same data/specification hashes.
- [x] Run deterministic preflight for series/value equality, title, unit, source note, number format,
  dimensions, accessibility metadata, workbook structure, code/manifest hashes, requested
  deliverable completeness and guideline rule IDs.
- [x] Add the Codex-local multimodal adapter behind the implemented `OutputReviewPort`. It
  invokes the locally authenticated Codex runtime with ephemeral/read-only isolation, a sanitized
  environment, checksum-bound direct PNGs and structured output. Missing executable/login, timeout,
  malformed output and unknown artifact references fail closed. Other remote API adapters remain
  unimplemented. The offline deterministic test port receives direct-render bindings,
  specification, actual underlying values through a snapshot grant, result summary, preflight
  findings and guideline subset—not a browser screenshot or arbitrary application data.
- [x] Lock production Output review to `codex-local` and publish a credential-free runtime status.
  It uses the local ChatGPT/Codex login without placing a token in project configuration. Missing
  executable/login and invocation failures remain explicit blockers; they never select the
  network-free deterministic test fake. The registry always exposes this admitted capability.
- [x] Introduce one fixed Nature-inspired `academic-publication-placeholder-v1` with source-backed
  guidance, operational rules and a version/hash-bound Codex review context (2026-09-28).
  `VISUAL-RUBRIC-PLACEHOLDER` replaces the missing-rubric advisory for new reviews.
- [x] Separate chart source-unit selection from display wording, wrap empty-state titles, and
  add DeepSeek chart wording plus two real author self-checks before each chart-bearing review handoff
  (ADR 0032). Persist pass/fail/error receipts and block handoff without consuming formal rounds
  unless both checks pass. Keep numerical rendering and approved patches controlled.
- [x] Verify the focused real-model delivery/revision cycle on explicit-unit and missing-unit
  synthetic-data fixtures: two self-checks per handoff, Codex approval, 2/3 formal rounds,
  Finish, manifest receipts and reload (2026-09-28). Preserve earlier false-positive attempts in
  `docs/testing/chart-delivery-2026-09-28.md`; this does not close the full E2E gate below.
- [ ] Accept the placeholder through two real browser journeys (single and multiple providers):
  resolve substantive visual findings within three Output rounds, obtain semantic report pass,
  then Finish, verify the manifest and reload. Record actual results, including failures, under
  `docs/testing/browser-runs`; never reset counters or mutate backend evidence to force success.
  Both journeys were executed on 2026-09-28; acceptance remains **not passed**. Brazil's two charts
  have no substantive visual findings at round 1, but report/approved-code failures prevent Finish.
  India exhausted round 3 after a unit-label correction incorrectly emptied its chart; unresolved
  units and upstream/report defects also prevent acceptance. The logs preserve all failures and
  normal UI recovery attempts; automated regression remains green.
- [ ] Replace the placeholder with final project-owner creative direction/target-journal print
  requirements when supplied. This is not required to test the current bounded review loop.
- [ ] Obtain and approve the product icon creation standard and icon acceptance checklist. Existing
  UI rules cover structural SVG/accessibility requirements only; visual grid, stroke/fill, optical
  sizing, state variants and reference examples are explicitly `missing`.
- [ ] Require approved provider profile and explicit session authorization before a future remote
  API vision provider receives an analytical render; retain human review when required by policy.
- [x] Let Review AI return pass/warning/fail plus typed correction proposals. Only user-approved
  patches trigger selective deterministic regeneration; Review AI cannot waive structural failures
  or Finish the session.
- [x] Extend the implemented complete-ArtifactSet review with coherent cross-artifact data-hash,
  guideline and source checks. Each chart is separately bound to one indicator and one homogeneous
  unit; differing legitimate units across charts are not “corrected” into a false common label.
  Cosmetic source corrections are emitted as atomic patch groups; appearance-specific title/series
  review remains on direct renders.
- [x] Split multi-indicator analytical output into indicator/unit-specific charts and workbook chart
  sheets, verify that generated charts cover the approved indicator set, validate each chart's unit
  against its underlying rows, use readable magnitude abbreviations and wrap long SVG titles.
- [x] Enforce the three-iteration render-review-regenerate bound in the backend, including automatic
  post-revision review; restrict direct typed patches to SVG charts and CSV/XLSX tables, with
  user-approved section directives as the sole Research Report exception; preserve typed
  review, revision and artifact replacement histories; and show rounds used/remaining plus the
  chronological history in Output UI. Data, model results, code and manifests remain read-only.
- [x] Support typed table-column selection in Output revision, physically regenerate CSV/XLSX
  analytical tables from the approved subset, recompute affected preflight, deduplicate findings by
  artifact/rule/message and render stable unique UI keys (issue 11).
- [ ] Add a Workflow-wide model usage/cost ledger beyond the existing request timeout and hard
  iteration bound. Agent already has its own durable reservation/usage budgets.
- [x] Add DeepSeek Research Report generation through `ReportAuthorRequestV1`, bounded registered
  reads and a validated EvidenceClaim ledger, followed by deterministic rendering and independent
  Codex-local semantic review. User-approved directives may rewrite only named sections.
- [x] Add opt-in live-model evals for both a direct PNG fixture and a complete generated-Output API
  review. Keep schema/rule, selective-regeneration and Finish-gate behavior deterministic in the
  routine suite; never use model-driven browser screenshots in routine tests.

Offline contract evidence: output generation binds versioned chart/table/report specs to the
approved data hash, emits accessible SVG/XLSX plus an internal 900×500 PNG with spec/data hashes,
and runs deterministic preflight before review. `ArtifactAuthorPort`, `ReportAuthorPort` and
`OutputReviewPort` page
across the complete approved snapshot through separate audited grants. The test structural reviewer loads and
decodes the checksum-bound PNG pixels rather than treating a hash as visual evidence. Users may
apply selected typed chart/table patches or report directives, or reject them; only affected
artifacts/sections are regenerated,
previous versions remain downloadable, and a visible timeline records each review and immutable
replacement. The backend permits at most three review rounds. Finish requires a current review plus
final confirmation of the exact export selection and limitations. Draft downloads are explicitly labeled. Structural and
visual review authority are persisted separately in the graph. Independent model failures preserve
successful siblings, and corrected reruns reuse compatible successful results. Current formal
semantic/visual review uses Codex-local; it is implemented and not an empty provider placeholder.
Additional API-provider adapters, Workflow-wide cost accounting, final creative standards and the
specified complete live acceptance journeys remain separate unfinished work.

Phase 1E-4 offline contract exit is covered by deterministic structural/value checks, complete
snapshot paging, direct render pixel inspection, typed patch review, selective regeneration,
bounded iterations, Research Report compliance review and final human confirmation. This does not
close the outstanding real-provider repeat/longitudinal gates. Codex-local is executable; additional
remote API profiles and their disclosure/cost/quality acceptance remain deferred.

Phase 1E exit criterion: a user can converse with AI to clarify and revise a Plan, approve typed
Data/Analysis proposals, and receive reproducible chart/table/report artifacts that have passed
deterministic preflight plus an inspectable Review AI proposal before final human approval. Every
function/interface/skill call is allowlisted, versioned and traceable as graph state, and missing
capabilities are shown honestly as unavailable.

## Phase 2 — research and publication depth

- [x] Phase 2A-1: add registered ADF unit-root testing per entity/frequency series with typed
  deterministic-term, autolag and maximum-lag options, hashed results, Python reproduction,
  capability receipts and explicit Stata unavailability.
- [x] Phase 2A-2: add per-entity/frequency ARIMA/SARIMAX estimation with bounded typed orders,
  approved future exogenous values, convergence diagnostics, confidence intervals, hashed Python
  reproduction, capability receipts and governed forecast CSV/workbook artifacts. Stata remains
  explicitly unavailable until its panel/time and future-exogenous mapping is reviewed.
- [x] Phase 2A-3: add per-entity/frequency VAR estimation with fixed or bounded criterion-based lag
  selection, ordered variables, stability and equation diagnostics, bounded multi-series forecasts,
  plus optional reviewed IRFs with explicit shock semantics and confidence bounds. Persist hashed
  Python reproduction, capability receipts and governed forecast/IRF CSV/workbook artifacts; keep
  Stata explicitly unavailable until panel/time and shock-ordering semantics are reviewed. The Plan
  compiler preserves approved forecast horizon/targets and Output preflight verifies delivery.
- [x] Add reviewed affine unit conversion, calendar/fiscal down-frequency alignment, explicit
  incomplete-period policy/coverage and hash-linked per-operation transformation lineage.
- [x] Promote chart/table rules from the placeholder to the approved, typed `publication-v1`
  guideline with accessible multi-series encoding, density/size limits, workbook table rules and
  rule-addressed deterministic preflight.
- [x] Register the typed `research-workbook-v1` template contract and run rule-addressed workbook
  linting for required sheets/columns, order, header freeze/filter behavior, formula-free data,
  external links, guideline metadata, conditional sheets and selected embedded charts.
- [x] Add same-session artifact comparison across file hashes, typed specification fields and
  privacy-preserving structured-value hashes/counts, with CSV row deltas, workbook sheet deltas and
  an Output UI summary against the latest compatible historical version.
- [x] Extend the Phase 1E reviewer with publication-specific chart source/alt-text/series-data,
  table source/column/title and Research Report specification/content/section/data/source/causal-
  boundary/reproducibility/citation rules; blocking findings remain non-waivable and cosmetic title
  corrections remain typed user-approved patches.
- [x] Preserve durable local resumability, stale-write conflict handling and partial model recovery.
- [x] Add checksum-verified portable Workflow session export/import across database records and all
  session-owned files. Import always creates a new session identity and records immutable lineage.
- [x] Add an explicit post-Finish continue/fork contract: only a completed session may be forked;
  the frozen source remains unchanged while the child reopens at Output Review, removes the old
  manifest from its current selection and requires a fresh review and Finish checkpoint.

Local exit criterion: supported deterministic research workflows are statistically validated and
outputs conform to the approved publication guide. This criterion passed on 2026-09-07; the
evidence and exclusions are recorded in `phase2_acceptance_report.md`. This accepts the local Phase
2 implementation, not the complete longitudinal `T4`: manual Excel/visual UAT, live-provider
evaluation and connector-backed acquisition remain separate gates.

## Phase 3 — public connector expansion

Status: **complete for admitted P0/P1 slices**. Activation is slice-specific; the remaining provider
catalogs are not implicitly supported.

### Phase 3-0 — reusable public-connector foundation

- [x] Retain the common typed connector, normalized observation, provenance, capability and Plan
  approval boundaries established in Phase 1.
- [x] Add an explicit IMF dataflow registry so structurally different datasets cannot be treated as
  interchangeable or accessed through arbitrary URLs/options.
- [x] Add checksum-verified, atomic public-response caching with a six-hour freshness limit and
  cross-session reuse.
- [x] Preserve isolation and portability by copying reused raw evidence into every consuming
  session and creating a new immutable normalized snapshot, provenance record and value-free trace.
- [x] Support reviewed multi-source acquisition: execute each registered source independently,
  preserve its immutable snapshot/provenance, prepare a lineage-bearing canonical union, reject
  overlapping identities and require an explicit Data merge approval before Data Next (ADR 0027).
- [x] Document a repeatable dataflow admission checklist covering metadata, dimensions, fixtures,
  normalization, Plan validation, live smoke tests, attribution and cross-session reuse.
- [x] Add `data-source-knowledge-v1` with provider scope, admitted datasets, frequencies, cadence,
  geography, metadata fields and indicator seeds; validate it at startup and index it into Plan AI.
- [x] Resolve reviewed open-ended period endings to frequency-valid current-date query upper bounds,
  retain requested/resolved values in source runs and trace, and defer real coverage conclusions to
  returned observations (ADR 0028).
- [x] Normalize consecutive fiscal-year bounds to ending calendar years for annual calendar-year
  connectors, preview the effective query in Plan and retain the full requested/resolved period in
  Data provenance; reject malformed ranges before provider access (issue 10, ADR 0028).

Phase 3-0 exit criterion: two sessions can consume one fresh public provider response without a
duplicate provider call, while remaining independently auditable and exportable. This passed with
live WEO `PCPI` data on 2026-09-10.
- [x] Expand catalog `1.2.0` after a real debt-planning run: add WEO government-finance/debt
  concepts plus `GGXWDG` and `GGXWDG_NGDP`, verify both against live China metadata/data, normalize
  their reviewed units and cover debt-specific ranking and Plan contracts.

### Phase 3-1 — IMF registered dataflows

- [x] Retain bounded CPI index-level acquisition for explicit countries, COICOP codes, frequencies
  and periods.
- [x] Add annual WEO acquisition using its distinct `COUNTRY · INDICATOR · FREQUENCY` contract.
- [x] Expose the local registered-dataflow catalog and per-dataflow official metadata routes.
- [x] Freeze further IMF dataflows until a concrete research requirement selects them and the
  [`imf_dataflow_onboarding.md`](imf_dataflow_onboarding.md) gate passes. Registration is not a
  claim that every IMF portal dataset is already supported; later admissions are new scope.

### Phase 3-2 — P1 provider connectors

P1 is the only active non-IMF public-connector expansion scope, in this order:

1. [x] World Bank Indicators: bounded annual WDI/source 2 contract, metadata/source validation,
   complete pagination, provider update markers, null/status preservation, provider-specific retry,
   shared fresh response reuse and independent Session evidence.
2. [x] OECD Data Explorer: pinned CLI 4.1 monthly `LI`, exact DSD/dimension validation, returned-key
   validation, status/attribute preservation, bounded retries, shared cross-process 20/minute and
   60/hour request budgets, cache/session evidence and Plan-to-Data acceptance.
3. [x] Eurostat: current ECOICOP v2 monthly all-items `prc_hicp_minr`/`TOTAL` index (`I25`), reviewed
   ISO3-to-Eurostat crosswalk, JSON-stat dimension/category validation, update-drift detection,
   sparse missing/status preservation, cache/session evidence and bounded live acceptance.
4. [x] ECB Data Portal: EXR 1.0 monthly euro reference-rate averages with reviewed
   ISO3-to-currency mapping, explicit quote direction, production-only values and conditional
   ETag/Last-Modified cache revalidation that distinguishes 304 from empty data.
5. [x] BIS Data Portal: WS_CBPOL 1.0 monthly end-of-period policy rates with exact v2 SDMX keys,
   ISO3-to-reference-area mapping, preflight availability constraints, bounded shared rate budget,
   compilation/source metadata and BIS non-endorsement text.
6. [x] UN SDG: current-release indicator 8.1.1 / series `NY_GDP_PCAP`, reviewed ISO3-to-M49
   mapping, release evidence, complete bounded pagination and lossless nature/unit/status/
   reporting-dimension preservation.
7. [x] ADB Key Indicators: API v5/SDMX 3.0 annual `DF_NA` 1.0 for registered GDP/value-added
   indicators and 2000–2024, reviewed ISO3-to-ADB mapping, 18/minute shared request budget,
   returned-version/scope checks, unit-multiplier preservation and cache/session evidence.

Each source requires a provider-specific ADR, contract tests, rate-limit policy, metadata mapping and license/attribution review before activation.
Every activation must also pass the common and provider-specific gates in
[`connector_robustness_standard.md`](connector_robustness_standard.md). A provider may be available
for one registered dataset slice while its remaining catalog stays unavailable.

All Phase 3 P1 providers passed their connector-specific gates only for the slices recorded in ADRs
0017–0020 and 0022–0024. Shared transport now supports checksum-verified conditional cache
revalidation, while World Bank pagination, OECD rate budgets, Eurostat JSON-stat, ECB revision
semantics, BIS availability and UN release/pagination behavior remain provider-owned contracts.

Phase 3 P0/P1 exit criterion: every listed slice is registered in capability and Plan knowledge,
has fixture and bounded live evidence, preserves a session-owned raw/normalized audit path and can
enter Data only after Plan approval. This criterion passed on 2026-09-10. New provider datasets are
future admission work, not unfinished Phase 3 scope.

The complete Phase 0–3 baseline was revalidated on 2026-09-11 with all automated suites, running
HTTP/UI checks and bounded live reads for all eight registered public connectors; see
[`phase0_to_phase3_acceptance_report.md`](phase0_to_phase3_acceptance_report.md).

### Phase 3-3 — complete Source Index v2

Status: **in progress after the 2026-09-11 product-scope change**. This extends discovery coverage;
it does not reopen or implicitly expand the accepted executable connector slices above. The
normative design is [`../adr/0026-complete-source-index.md`](../adr/0026-complete-source-index.md).

1. [x] Add a normalized SQLite/FTS schema for provider snapshots, datasets/dataflows, ordered
   dimensions, dimension values, hierarchies, aggregate flags, provider attributes, executable
   state and explicit coverage status. Do not store dimension Cartesian products.
2. [x] Add atomic provider replacement, cross-dimension full-text discovery, provider/dataset
   listing and paginated dimension-value APIs. Seed from v1 without presenting seeds as complete.
3. [x] Implement the World Bank synchronizer for all sources, per-source indicators, countries,
   aggregates, regions, income/lending groups and topics; reconcile API pagination totals.
4. [x] Implement shared SDMX synchronization primitives for dataflow, DSD, concept, codelist and
   content/availability constraint metadata with raw hashes, checkpoints and rate budgets.
5. [x] Use those primitives for IMF Data, OECD, ECB and BIS, retaining provider-specific agency,
   version and constraint semantics.
6. [x] Implement Eurostat Catalogue + SDMX synchronization for the main and Comext/Prodcom catalogs,
   including GEO/NUTS and reviewed EU/euro-area aggregate classification.
7. [x] Implement ADB KIDB dataflow/indicator/DSD/constraint synchronization under its 20/minute
   published limit, including counterpart and currency dimensions for trade flows.
8. [x] Implement UN SDG goal/target/indicator/series/geography/release/disaggregation synchronization
   and link reference metadata without treating every disaggregation value as an indicator.
9. [ ] Complete refresh operations and drift acceptance. Last-known-good atomic replacement,
   resumable hash-verified raw downloads, retry/rate budgets, completeness reconciliation and an
   initial eight-provider acceptance report are implemented. Scheduled refresh policy,
   provider-specific conditional-update coverage and repeat-run drift fixtures remain open.
10. [x] Switch Plan AI from the v1 seed to bounded provider/dataset/indicator retrieval over the
    generated `source-index-lite-v1` projection. The prompt candidates carry provider snapshot IDs,
    the planning receipt records the projection version/checksum, and executable state is enforced.
    The committed projection content-addresses and reuses identical indicator sets per provider.
    Retrieval removes conversational/geography noise, expands reviewed concept aliases and reserves
    indicator slots across separate requested concepts; the China expenditure-side regression
    covers executable WDI GDP growth, investment share and household-consumption share together.
11. [ ] Remove `data-source-knowledge-v1` only after search-parity, migration and rollback tests pass.

Phase 3-3 exit criterion: all eight providers report complete provider-derived catalog snapshots;
dataset and dimension counts reconcile to upstream manifests; full-index discovery resolves needed
frequency and geography/aggregate values; Plan AI quickly identifies one or more provider/dataset/
indicator candidates from the bounded lite projection; and no unregistered source becomes
executable.

UN Comtrade is not included in P1; its classification mapping and account/key workflow remain in the backlog. FRED, BLS, BEA, EIA, IDB, national APIs and licensed sources are also frozen until P0/P1 acceptance is complete.

## Post-Phase 3 AI workflow hardening — issues #22–#24

Status: **complete in the approved order #23 → #22 → #24**.

1. [x] **#23 cross-stage handoff and role alignment.** Persist immutable
   `StageHandoffEnvelopeV1` versions at stage boundaries, represent them as `stage_handoff` graph
   nodes with `CONSUMES` and `SUPERSEDES` edges, maintain stage-local conversations and expose
   user-only confirm/resolve commands. Production Data Steward and Analyst adapters use DeepSeek,
   share the controlled full-value grant, retry schema/semantic repair at most twice and fail closed
   to Retry/manual controls. Legacy sessions are lazily inferred and ambiguous roles block AI until
   confirmed. See ADR 0029.
2. [x] **#22 executable Plan contract and quality evaluation.** Add frequency-valid periods,
   structured forecast horizons, ordered typed model variables, model-specific validation, compiler
   removal of prose inference, machine-readable error codes and the 24-case repeated Plan eval.
   The deterministic corpus passes 91.7% initially and 100% after bounded repair over 72 runs;
   invalid contract persistence is zero. See ADR 0030.
3. [x] **#24 evidence-bound Report Author and Reviewer.** DeepSeek receives
   `ReportAuthorRequestV1` through bounded snapshot/model-result reads and returns a validated
   `ReportDraftV1` with an `EvidenceClaimV1` ledger for deterministic Markdown rendering.
   Codex-local independently checks report semantics and may issue section-only
   `ReportRevisionDirectiveV1` records. Only a user-approved directive can trigger DeepSeek to
   rewrite named sections; unchanged evidence and artifacts are enforced before the next automatic
   review. Missing evidence returns `requires_upstream_stage`. Chart, table and report review share
   the hard maximum of three rounds, and a selected report must reach semantic `pass` before
   Finish. See ADR 0031.
4. [x] **#25 independently retryable Report Author generation.** Persist analysis before report
   generation, fail into a visible Output recovery state with safe field-level diagnostics, clean
   partial artifacts and allow a user-only, idempotent Output retry without rerunning models.
   Provider length termination expands the bounded repair budget; selective review ignores
   artifact-specific findings for outputs the user did not select during both review and Finish.
   Report revision accepts only authorized text fields, preserves immutable evidence/citation
   bindings, and labels model-result hash scopes and artifact lifecycle states for cross-model
   alignment. Browser acceptance reached Codex-local semantic pass, Finish, frozen manifest and
   reload. See ADR 0031 and the Issue #25 browser log.

This hardening does not alter the three human checkpoints. AI roles create proposal, author or
review records only; Plan approval, Run and Finish remain user commands bound to current hashes.

## Phase 4 — additional approved provider profiles

Status: **deferred**. Resume only by an explicit roadmap decision. The public requirements are
[provider profiles](provider_profiles.md); no deployment-specific integration is distributed.

1. [ ] Define an explicit endpoint/model/task/data policy and accountable owner, including
   retention, disclosure, usage limits and revocation. Missing decisions fail closed.
2. [ ] Implement a server-owned versioned `approved_remote` profile behind the existing typed
   ports; never accept client credentials, arbitrary endpoints or model-authored permissions.
3. [ ] Accept Plan, Data/Analysis, authoring and multimodal review independently. Existing adapter
   source or a successful text request does not activate another capability.
4. [ ] Preserve snapshot-bound actual-value grants, classification controls, Workflow approval
   gates, Agent authorization envelopes and user-only finalization.
5. [ ] Produce a reproducible distribution and file/dependency inventory, omitting disallowed
   components where required. Deterministic implementations remain test doubles, never recovery
   providers in real research.
6. [ ] Verify classified failures, bounded retries, usage reservations, redaction, disable and
   rollback with offline fixtures before separately authorized live evaluations.
7. [ ] Pass W0–W4 and W6, plus W5 for every additional enabled task, with retained evidence.

This phase does not include new dataset admissions, licensed connectors or Agent persistence.
Agent persistence is already implemented in A1; its outstanding A6 reliability acceptance remains
tracked separately. Authentication and hosted/multi-user deployment need a separate design.

Exit criterion: the accepted profile completes its defined longitudinal slice with exact
provider/model/disclosure receipts and unchanged authorization/freeze boundaries. A credential
or single passing prompt is not acceptance.

## Review and test strategy

The preserved large acceptance plan is `longitudinal_acceptance_scenario.md`. Phase development
uses only its mapped slice; the complete cross-day `T4` journey runs after every required slice is
implemented. Executed evidence is recorded separately; the current local Phase 2 record is
`phase2_acceptance_report.md`, Phase 3 connector evidence is `phase3_acceptance_report.md`, and the
2026-09-11 cross-phase result is `phase0_to_phase3_acceptance_report.md`. Phase 4 is excluded from
that result; unchecked manual/live-model/full-longitudinal steps remain specifications.

- Python: unit, property, integration and golden-data tests.
- State graph: invariant/property, invalidation, concurrency, retry/recovery, checkpoint and
  projection-equivalence tests against durable storage.
- FastAPI: in-process ASGI tests; no browser required.
- React: unit/component/accessibility/DOM tests.
- Connectors: recorded provider fixtures plus opt-in live smoke tests.
- Capability/skills: registry/schema, availability, approval, unsafe-invocation refusal and trace
  assertions using deterministic handlers.
- AI ports: structured-output fixtures, provider-adapter contract tests and separate opt-in
  task-quality/cost evaluations; complete value paging, session/stage/hash binding, stale grants,
  licensed disclosure denial, access receipts and prompt-like data treated as inert content.
- Excel: cell formulas, named ranges, chart XML/specification and deterministic artifact inspection.
- Charts: compare source values, axes/series/style specifications and exported metadata.
- Review AI: direct artifact-render fixtures, rule-addressed report/patch assertions and separately
  authorized opt-in multimodal evaluations; never browser-page screenshots.
- Visual acceptance: manual review by a person in the app or Excel.
- Browser-driven realistic acceptance: operate only through the public UI/API from a new research
  question through Plan, Data, Transformation, Review AI correction loops and final freeze. A run
  passes only when deterministic preflight is clear, Review AI returns `pass` for the exact current
  ArtifactSet, Finish creates the manifest and reload preserves the completed state. Record every
  run in `docs/testing/browser-runs/`; never patch backend state to advance a test.

Routine automated testing must not use a model to browse the UI or take screenshots.
