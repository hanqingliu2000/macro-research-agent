# API contract

All routes are versioned beneath /api/v1. Session routes use separate /workflow and /agent
namespaces; there is no shared session endpoint. This is a single-user local application: bind
the API and web client to loopback only. There is no application authentication, tenant boundary
or authorization layer protecting the administrative endpoints from other network clients.
`actor=user`, ownership checks and CORS are product/state controls, not login or network access
controls. Do not expose this API, diagnostics or the development server to a public/shared network.

Implementation status: shared foundation, durable Workflow, Plan/upload, conversational Plan AI,
local Data, typed Pipeline/model execution, generated code and governed `publication-v1` Output endpoints
are mounted. DeepSeek Data/Analysis proposal assistants use the existing typed stage command
endpoints; deterministic equivalents are test-only. Structural checks and the production
Codex-local Output reviewer use the Output command endpoint.
Codex-local uses direct artifact renders and strict structured observations. New reviews use the
active `academic-publication-placeholder-v1` rubric with its version/hash: substantive visual
failures block Finish, while the placeholder-scope advisory may be explicitly acknowledged.
Final project-specific creative direction and journal print certification remain deferred;
neither missing final guidance nor the placeholder waives an actual defect. Registered public
IMF CPI/annual WEO, World Bank annual WDI, OECD monthly CLI, Eurostat monthly all-items HICP,
ADB annual national accounts, ECB monthly euro reference rates, BIS monthly policy rates and UN SDG
8.1.1 acquisition are active. Codex-local multimodal review is the admitted production path; other
remote multimodal adapters remain planned. Independent Agent persistence/APIs are implemented;
their Experimental live acceptance is tracked separately.
The backend Plan provider is fixed to DeepSeek and requires server-side credentials; the capability
response always reports `llm_provider=deepseek`. Clients cannot select another Plan provider, and
missing credentials fail backend startup rather than activating a deterministic fallback.
Data/Analysis stage assistance uses role-scoped DeepSeek adapters and fails closed without its
inherited or role-specific model configuration.
A future approved remote profile is deferred and has no current runtime selector or credential
endpoint. Future profile policy would be server-side only; clients may inspect safe status but may
never submit a provider endpoint, model policy or credential. The generic adapter code is not an
environment-selectable production OpenAI provider. See `provider_profiles.md`.
The current session/node endpoints are a compatibility projection over the graph foundation.
Phase 1E-0 has added normalized graph persistence, graph-derived public projections,
administrative read APIs and a transactional `GraphService` command boundary as described in
`state_graph.md`.

## Shared foundation endpoints

- GET /health: liveness, version and runtime mode.
- GET /capabilities: executable and separately listed planned connectors, models and exports, plus
  the fixed planning and Output review providers. Output review reports `codex-local`, its optional
  model override and no project API credential because authentication belongs to the local Codex
  login. This describes the client authentication path, not offline inference: approved artifact
  images and analytical context may be processed remotely by its model provider.
- GET `/data-source-knowledge?q={research intent}&limit={1..50}`: versioned, checksum-addressed and
  bounded high-level source knowledge ranked for planning. This endpoint reads only the reviewed
  local catalog, returns no observations and does not contact providers. It remains a transitional
  v1 compatibility endpoint; Plan AI itself now uses the generated `source-index-lite-v1` provider/
  dataset/indicator projection.
- GET `/source-index/providers`: provider snapshot status, versions and catalog/value counts.
- GET `/source-index/search?q={intent}&provider={optional}&executable_only={bool}&limit={1..50}`:
  bounded cross-dataset and cross-dimension discovery from local `source-index-v2`.
- GET `/source-index/providers/{provider_id}/datasets?offset={n}&limit={1..500}`: paginated dataset
  inventory with coverage and executable state.
- GET `/source-index/providers/{provider_id}/dimensions/{dimension_id}`: paginated/searchable
  provider-wide values such as World Bank topics, geographies and income/lending groups.
- GET `/source-index/providers/{provider_id}/datasets/{dataset_id}/dimensions/{dimension_id}`:
  paginated/searchable dimension values, including labels, hierarchy attributes and aggregate state.

Source Index routes are read-only and never contact providers. Provider synchronizers populate the
local index out of band and atomically. A clean runtime starts with explicit `seed` records; running
the harvest command replaces them with complete snapshots. The 2026-09-12 development runtime has
complete snapshots for all eight providers. A discoverable v2 record is not an acquisition
capability.

The internal Plan context does not serialize those routes' full records. It locally searches the
checked-in 20.3 MB facts-only lite projection and supplies no more than eight dataset candidates and five
indicator matches per dataset, including executable state and provider snapshot identity.

The capability response also publishes the four Workflow stage IDs and the derived Workflow
status vocabulary so clients do not infer them from labels.

Versioned registry discovery is implemented separately so the compatibility summary remains small:

- GET /registry/capabilities?stage={stage}&availability={state}
- GET /registry/skills?stage={stage}&availability={state}
- GET /admin/registry (complete descriptor/manifest inspection)

## Agent namespace (Experimental)

Root `/api/v1/agent`: session list/create/get, run get, run attachments, typed run commands,
checksum-bound artifact download and cursor-based progress SSE. See `agent_mode.md` for paths.
Agent IDs must be Agent-owned; Workflow IDs fail closed. Command CAS conflicts return 409;
invalid scope/contract/budget commands return classified errors rather than fabricated results.
Finalization requires the exact current artifact-set hash, two successful author checks, formal
review approval and semantic report approval. Only actor=user can authorize the final freeze.
`resume` and `resolve_intervention` return `task_attempt_limit` without state/budget mutation
when that run has exhausted a task's physical-call ceiling. This applies to legacy waiting runs
as well as failed runs; an explicit linked new run never erases the original audit.
Stopped delivery ceilings reject Resume/intervention with `delivery_round_limit`; remaining
execution budget cannot add candidate/review rounds. Report admission reports `$.title` /
`report_title_too_long` during the existing bounded repair, before saving an invalid draft.
Reproduction inspection evidence is an owned/checksummed handoff field, not a new execution tool.
Joint visual/report revisions translate preserved refs to the accepted replacement IDs/hashes;
the original directive remains in audit, while the executable revision targets the current set.
Agent model-side report revision accepts `report-section-edits-v1`, not a replacement full draft:
directive ID, exact authorized section bodies/associated claim text, optional authorized global
limitations. No title, evidence/citation or artifact-ref edits are accepted. The server assembles
and validates ReportDraftV1; public command and freeze contracts are unchanged.
Author-check v7 findings include category, current artifact ID and available evidence refs.
Numeric receipt contradictions use bounded contract repair; receipt contents/hashes are retained
in diagnostic payloads and ordinary audit events carry references only.
The `863c07e` cohort exposed lost presentation bindings in report semantic conversion. The
follow-up implements additive `presentationEvidence` on `ReportAuthorRequestV1` and
`ReportReviewRequestV1`: up to 24 `PresentationEvidenceV1` records containing artifact ID/hash,
canonical UTF-8 sorted-JSON specification hash, data hash, format, specification and inspectionScope.
SVG includes exact verified contents (up to 64000 bytes); CSV includes verified headers, not copied
observation rows; XLSX carries owned-file hash/spec evidence, not a claim that every cell was read.
The combined serialized evidence has a 160000-character cap. Reproduction inputs are excluded
from publication-table inspection. Current file reads use session-owned ports; no arbitrary path,
URL or execution tool is exposed. Revisions refresh the bindings after presentation replacement.
Legacy request records default to an empty list for read compatibility; provider invocation
requires complete current presentation coverage. Missing/corrupt evidence fails closed before
author/reviewer calls; it does not silently omit required artifacts or fall back to another model.
Agent grant row/page hashes bind round-trip numeric values, not ten-decimal rounded projections;
nonfinite values remain null and snapshot bytes/hashes are unchanged.

Agent run projections additionally expose optional derived `recovery`:
`code`, `message`, `action` (`retry_failed_task`, `provide_input`, `extend_budget`,
`start_linked_run`, `repair_evidence`), `can_retry`, `requires_provider_confirmation`, `failed_step`,
`preserves_history` and `remaining` (task calls/attempts, phase attempts, model calls, tokens,
active seconds, Output candidates and formal reviews). Unknown task counts are null; remaining
run budgets subtract consumed **and reserved** usage. This projection does not rewrite errors.

User-only `retry_failed_task` uses the normal command ID/idempotency key/expected version envelope
in waiting/failed/paused states. Payment/access/configuration failures require
`arguments.confirm_provider_ready=true`; `provider_credentials_missing` still fails if the
runtime key is absent. The command preserves answers, authorization, task inputs, attempts and
all counters; it clears the call failure and queues only an eligible step. Otherwise it returns
`retry_not_available` or `provider_action_required`. Resume/scope-answer commands cannot bypass
new classified call-failure recovery. General `extend_budget` remains explicit and may not lift
fixed task/phase/candidate/review ceilings. Provider codes include `provider_payment_required`
(402), `provider_authentication_failed` (401/403), `provider_credentials_missing`,
`provider_rate_limited`, `provider_timeout`, `provider_server_error`,
`provider_connection_failed` and `provider_request_rejected`; malformed schemas keep their
separate contract codes. Existing generic historical errors are not retrospectively classified.

Agent `presentation_handoff_incomplete` (missing/corrupt/over-budget presentation bindings) and
`requires_upstream_stage` (required upstream evidence) expose recovery.action=`repair_evidence`,
can_retry=false. Delivery stops before Output Editor, with no format-repair call. Resume,
scope-answer, failed-task retry and re-review commands cannot substitute missing evidence.
Results/findings/budgets remain readable; repaired inputs or handoff require a new authorized run.
This is distinct from an unanswered human choice in Plan's existing `handoff_incomplete`.

`AgentTaskPlanV1.acquisition_checks` is an additive optional list (maximum 20). Metadata/status/
vintage exposure and data-coverage checks move here from speculative unresolved guidance before
admission, while genuine human choices/access prerequisites remain unresolved. After retrieval,
Data Steward receives the checks and actual data/source-metadata receipts. Agent-owned
`data.acquisition_checks` records requests, `state=assessed_against_acquired_evidence`, assessment
reference and source-snapshot references, not a fabricated metadata-availability verdict.

Root `/api/v1/admin/agent/sessions/{id}/runs/{run}`: paginated `/trace` supports event_type,
role, task_id, attempt_id and error_code filtering; `/attempts/{id}` correlates full attempt
events; `/diagnostics` verifies evidence and summarizes metrics; `/payloads/{id}` reads complete
redacted content; `/debug-bundle` exports ZIP; `/replay?verify_numerics=true` reconstructs recorded
requests/responses and re-evaluates pinned numerical results with zero external calls.
Querying replay is not a live model rerun or new scientific selection.

Agent public commands additionally expose hash-bound `retry_review`; remaining rounds and two
fresh author checks apply, with no candidate/budget reset. Owned `/data-preview?offset=&limit=`
pages the current immutable snapshot; period/value/unit are first. Public progress includes the
actual stage role, provider/model and state without exposing credentials or complete prompts.

## Workflow namespace

The endpoints below are rooted at /api/v1/workflow.

Registered IMF connector discovery is exposed without creating a Session:

- `GET /connectors/imf`: local list of admitted IMF dataflow contracts.
- `GET /connectors/imf/{dataset}`: official metadata for one admitted dataflow.
- `GET /connectors/world-bank`: local WDI contract summary.
- `GET /connectors/world-bank/indicators/{indicator}`: source-2 indicator metadata.
- `GET /connectors/oecd`: pinned CLI 4.1 query and official DSD metadata.
- `GET /connectors/eurostat`: bounded HICP index contract and reviewed country crosswalk.
- `GET /connectors/adb`: bounded DF_NA contract, version, period and reviewed economy crosswalk.
- `GET /connectors/ecb`: pinned EXR monthly reference-rate contract and currency crosswalk.
- `GET /connectors/bis`: pinned WS_CBPOL monthly contract and reference-area crosswalk.
- `GET /connectors/un-sdg`: pinned SDG 8.1.1 series, paging bounds and M49 crosswalk.

Observation acquisition itself remains Plan-gated and creates session-owned raw evidence,
provenance and an immutable normalized snapshot. Another session may reuse a fresh verified public
response, but never another session's state or snapshot.

- GET /sessions: list resumable Workflow sessions.
- POST /sessions: create a Workflow session from `{ "request": "..." }`. The backend creates the
  minimal authoritative state and immediately returns its first clarification round; product
  clients cannot seed source runs, datasets, pipelines or artifacts.
- GET /sessions/{id}: current state and review requirements.
- GET /sessions/{id}/nodes: versioned Workflow nodes and dependency status.
- GET /sessions/{id}/projection: active stage, reachable stages and current snapshot references.
- POST `/sessions/{id}/{plan|data|pipeline|output}/commands`: domain-owned command dispatch. It
  applies idempotency plus expected-stage/hash checks and returns the persisted session, projection,
  created snapshot references, invalidated node IDs, outcome and typed graph-transition summary.

The backend computes the canonical SHA-256 hash of each persisted session document. Clients use the
hash returned in the projection as the next command's `expected_snapshot_hash`; clients do not
declare the resulting durable hash.

Every successful mutation response may include `graph_transition` with `created_node_ids`,
`created_edge_ids`, `created_checkpoint_ids`, per-role `pointer_changes` and
`invalidated_node_ids`. An idempotent replay returns the stored outcome without fabricating a new
transition. This concise summary is intended for conflict handling, administration and trace; the
standard stage UI does not render the complete graph.

## Reserved future convenience endpoints

- POST /sessions/{id}/data/assistant/proposals
- POST /sessions/{id}/pipeline/assistant/proposals
- POST /sessions/{id}/output/assistant/messages
- POST /sessions/{id}/geographies/resolve
- POST /sessions/{id}/checkpoints
- POST /sessions/{id}/retries
- POST /sessions/{id}/sources/queries
- GET /sessions/{id}/outputs
- POST /sessions/{id}/outputs/revision-proposals/{proposal_id}/apply
- POST /sessions/{id}/outputs/regenerate
- POST /sessions/{id}/outputs/reviews
- GET /sessions/{id}/outputs/reviews/{review_id}
- POST /sessions/{id}/outputs/reviews/{review_id}/patches/{patch_id}/apply
- POST /sessions/{id}/outputs/finalize
- GET /sessions/{id}/artifacts

AI requests carry the shared command metadata plus provider profile, task ID, target snapshot/hash,
explicit allowed capability/skill IDs and one or more internal read-only data grants. Grants bind
session, stage and immutable checksum/hash and support bounded paging over complete relevant values;
they are not public arbitrary-query endpoints. AI responses are typed proposals or review reports;
they never include a client-computed session or generic graph mutation. The response is persisted
as a non-authoritative proposal/review node. Apply endpoints revalidate proposal target hash,
capability availability and approval policy before calling existing typed services.

An Output review request identifies the ArtifactSet plus selected artifact/specification and
underlying-dataset hashes, data grants, guideline version, deterministic-preflight ref and applicable
review-render refs. Remote vision requests also include the recorded disclosure-policy decision.
Responses contain package-level and
artifact-level rule-addressed findings and typed patch refs, not private reasoning. Render bytes
are obtained by the provider adapter from the local artifact store and are not accepted as an
arbitrary URL.

## Phase 1B implemented endpoints

- POST /sessions/{id}/plan/commands
- GET /sessions/{id}/plan/snapshots
- POST /sessions/{id}/sources/uploads
- GET /sessions/{id}/sources/uploads
- POST /geographies/resolve

Plan command requests contain only `meta` and the typed Plan command payload. The temporary Phase
1A generic compatibility endpoint has been removed: no Workflow mutation endpoint accepts a
client-computed session. Plan, Data, Pipeline and Output commands resolve through their owning
typed endpoint and become an internal checksum-bound `GraphTransitionPlan` behind `GraphService`.

Phase 1E-2 extends the existing Plan command endpoint with `request_plan_clarification`,
`propose_plan_patch`, `apply_plan_patch` with optional `acceptedFields`, and `reject_plan_patch`.
Repeated clarification, draft and patch responses are schema-validated. AI proposal nodes have no
approval/execution authority; only explicit user Plan commands can save fields or cross Plan Next.
Apply revalidates the proposal's target Plan hash, so a manual save makes an older proposal stale.

Plan model output uses `ModelIntentV2`: `capabilityId`, `enabled`, `purpose`, ordered
`variables[{indicatorCode, role, order}]` and optional
`forecastHorizon{steps, unit: "periods", confidenceLevel}`. `targetIndicators` is returned only as
a derived compatibility projection. Period start/end formats are frequency-specific and only end
may be `latest`. Rejected Plan commands may return a structured 422 detail with `code` and
`message`; recognized categories are `invalid_model_contract`, `provider_unavailable`,
`connector_unavailable`, `handoff_incomplete` and `deterministic_contract_violation`.

## Phase 1C-local implemented endpoints

- GET /sessions/{id}/data
- GET /sessions/{id}/data/preview?offset={offset}&limit={limit}
- POST /sessions/{id}/data/commands
- POST /sessions/{id}/data/roundtrip/imports
- GET /sessions/{id}/data/roundtrip/packages/{package_id}

Data commands cover source-schema mapping, registered hygiene operations, undo, round-trip export,
round-trip column mapping/validation/commit and the Data approval checkpoint. Every mutation uses
the same idempotency and expected-stage/hash preconditions as Plan commands. Preview responses are
bounded and paginated; session responses include only a small preview, not the complete dataset.
Phase 1E-3 adds `propose_data_assistance`, `apply_data_assistance` and
`reject_data_assistance`. Proposals contain selectable source mappings or registered hygiene
operations and bind to the upload checksum or active dataset hash.

## Phase 1D implemented endpoints

- GET /sessions/{id}/pipeline
- GET /sessions/{id}/pipeline/preview?operation_id={id}&offset={offset}&limit={limit}
- POST /sessions/{id}/pipeline/commands
- GET /sessions/{id}/pipeline/code/{artifact_id}
- GET /sessions/{id}/pipeline/code/{artifact_id}/download
- GET /sessions/{id}/output
- POST /sessions/{id}/output/commands
- GET /sessions/{id}/output/artifacts/{artifact_id}
- GET /sessions/{id}/output/artifacts/{artifact_id}/download

Pipeline commands cover registered operation add/reorder/toggle/delete, edit undo, selection,
target/parameter update, model add/input/specification/delete and the Transformation Run checkpoint.
They also accept user-only `retry_output_generation` after a recoverable Report Author failure.
Preview executes only through the typed local runner and does not persist an analytical snapshot.
Run creates one immutable analytical snapshot per enabled operation, resolves model inputs through
the bundle output map, executes registered descriptive/correlation/OLS/ADF/ARIMA/SARIMAX/VAR jobs
and records durable model results and an `AnalyticalBundle`. Registered transformations include
reviewed affine unit conversion and calendar/fiscal down-frequency conversion with explicit
incomplete-period policy. `operationLineage` records each operation's logical refs, immutable input
and output IDs/hashes, specification hash and row counts. Forecast results contain group fit
diagnostics plus target/period-labelled means and confidence intervals; ARIMA/SARIMAX return one
target and forecast-enabled VAR returns every endogenous target. Output adds a forecast CSV when
such rows exist and preflight blocks Finish when the approved Plan's target/period contract is not
fully represented. Optional VAR impulse responses contain explicit impulse/response/period rows and
confidence bounds; Output adds an IRF CSV when such rows exist. The Phase 1D-3 Run also records checksum-addressed Python
and, when fully supported, Stata code references. Code endpoints verify Workflow-session ownership
and file checksum. Generated content is not accepted by any execution endpoint. Run generates the
selected `publication-v1` artifacts and advances into Output Review. Output commands own artifact
selection and final approval; final approval creates and freezes the reproduction manifest. Typed
HTTP Output revision commands selectively regenerate only user-approved affected artifacts.

`run_pipeline` persists the completed `AnalyticalBundle`, model results and analysis handoff before
Report Authoring. If authoring fails, the command returns the updated session at `activeStage=output`
with `status=failed` and `pipeline.outputGeneration={status, attempt, bundleId, retryable, error}`.
The error contains a stable code plus bounded field-path issues and never raw model output. Retry
must target that same completed bundle, creates no model invocation receipt, cleans any uncommitted
files and is idempotent under the standard command key. Successful retry creates one ArtifactSet
and advances to Output Review.
Report author/reviewer requests label `resultHashes` as hashes of complete typed result records and
`modelResults[].resultHash` as hashes of nested numerical result payloads; equality is not expected.
Artifact metadata also distinguishes generated candidates, current export selection and frozen
manifest membership. Approved report revision responses are projected onto authorized body/claim
text fields; section structure, evidence/citation bindings, artifact references and untargeted text
remain immutable. At final approval, artifact-bound preflight failures are filtered by the exact
selected IDs, while package-wide findings remain applicable.

New chart/table specifications use `mra-output-spec-v2`; the parser retains read compatibility for
immutable `mra-output-spec-v1` history, but `publication-v1` preflight requires v2.

Since 2026-09-28, Codex Output review records additionally expose nullable `visualRubricVersion`,
`visualRubricHash` and `visualRubricStatus` (`placeholder`). New reviews use
`academic-publication-placeholder-v1`; the exact record is included in the reproduction manifest's
`outputReview`. Historical records may omit these fields. The temporary standard is a fixed
Nature-inspired operational baseline, not a claim of journal certification. Substantive failures
remain blocking; only its scope advisory may be acknowledged. The three-round ceiling is unchanged.

Chart specs also support immutable nullable `source_unit`, distinct from patchable display `unit`.
Old specs migrate their original selection before a presentation patch. `output.chartSelfChecks`
records the two DeepSeek checks before each chart-bearing review request: provider/model,
ArtifactSet and evidence hash, chart IDs, round results/issues, status and UTC time. A blocked
handoff returns persisted self-check findings with no current `reviewReport` and no increment to
`reviewIteration`; it creates no completed review node. The user can retry or approve a correction.
The manifest includes these receipts. `/api/v1/capabilities` exposes `chart_author_provider`,
`chart_author_model` and `chart_author_self_check_rounds` (2). No new credential is required.
Generated Output state also exposes `workbookTemplateVersion: research-workbook-v1`; the frozen
manifest records the same identifier. Workbook lint failures appear in `preflightFindings` with
stable `WORKBOOK-*` rule IDs; blocking findings prevent finalization but remain available to Review
AI for diagnosis and correction guidance.

`GET /api/v1/workflow/sessions/{session_id}/output/artifacts/{current_artifact_id}/compare/{baseline_artifact_id}`
compares two visible current/historical artifacts owned by the same Workflow session. It returns
`mra-artifact-comparison-v1`: file-hash change, typed specification field changes and a structured
value summary. CSV summaries include row/column counts and added/removed row counts; XLSX summaries
include changed sheet names; rendered artifacts compare their specification-bound data hashes. The
endpoint does not return analytical cell values and rejects internal or cross-session artifacts.

New Research Reports bind to `mra-report-spec-v2` (with v1 read compatibility), including title,
source note, observation/model-result counts, citation references, required section names,
causal-boundary/reproduction requirements, guideline/data hash, draft hash and evidence-ledger
hash. `ReportAuthorRequestV1` provides the current handoff, approved Plan, snapshot grant, complete
typed model results/hashes, artifacts, citations and guideline. DeepSeek returns `ReportDraftV1`;
deterministic validation recomputes result hashes and rejects unknown evidence/citations, changed
citation bindings or unsupported causality before it renders Markdown. Persisted author-request
metadata retains only the data grant, not its initial row page.

Codex-local receives `ReportReviewRequestV1` and returns semantic status `pass`, `fail` or
`requires_upstream_stage`, rule-addressed findings and optional `ReportRevisionDirectiveV1`
records. A directive contains existing section IDs, issue, preserved evidence refs and acceptance
criteria—not replacement prose. `CHART-*` and `TABLE-*` findings continue to cover source labels
and exact series/column correspondence with the complete approved snapshot.

Pipeline commands also accept `propose_analysis_assistance`, `apply_analysis_assistance` and
`reject_analysis_assistance`. The proposal binds to the approved dataset plus current operation and
model state. Apply only edits typed specifications; `run_pipeline` remains a distinct human action.

Phase 1E-4 adds `request_output_review`, `propose_output_revision`,
`apply_output_revision`, and `reject_output_revision`. Review reads the approved analytical
snapshot through a hash-bound grant, returns rule-addressed findings and typed patches, and cannot
Finish. `apply_output_revision` accepts explicit `acceptedPatchIds` and optional
`acceptedDirectiveIds`. Typed patches regenerate only named chart/table artifacts. A
user-approved report directive is the sole exception: DeepSeek may rewrite only its named report
sections, preserved evidence is revalidated and the new immutable report version is automatically
reviewed. Data, model results, code, manifests and other exports remain read-only. A
`requires_upstream_stage` finding cannot create a report rewrite. The backend enforces a shared hard
maximum of three review rounds, including automatic review after each accepted revision.
Session Output state exposes immutable `reviewHistory`, `revisionHistory` and `artifactHistory`
records so the UI does not infer provenance from filenames or array position.
Artifact-specific preflight findings apply only when their artifacts are selected; package-wide
findings with no artifact binding still apply to every selective export.
`finalize_output` requires a current review of the exact selected ArtifactSet; a selected Research
Report additionally requires `semanticReportStatus=pass`. Warnings require `acceptWarnings: true`.

Portable Workflow lifecycle routes use `mra-portable-session-v1`:

- `GET /api/v1/workflow/sessions/{id}/archive` returns a ZIP archive with `manifest.json`,
  `database.json` and checksum-addressed session-owned files under `files/`.
- `POST /api/v1/workflow/sessions/import` accepts that archive as multipart `file`, verifies paths,
  schema/table shape and every checksum, then returns a newly identified `StoredWorkflowSession`.
- `POST /api/v1/workflow/sessions/{id}/fork` accepts an optional `{ "title": string }`. It is valid
  only for a completed source. The source stays frozen; the child carries `lineage.relationship =
  "fork"`, reopens at Output Review and must pass a new review/Finish gate.

Imported sessions similarly carry `lineage.relationship = "import"`, source session/status,
source database checksum and creation time. Neither operation accepts a client-selected target ID.

Full trace is available from GET /api/v1/admin/workflow/sessions/{id}/trace and is not used
by the standard research frontend.

Phase 1E-0 administrative graph reads are implemented alongside trace:

- GET /api/v1/admin/workflow/sessions/{id}/graph
- GET /api/v1/admin/workflow/sessions/{id}/graph/nodes/{node_id}
- GET /api/v1/admin/workflow/sessions/{id}/graph/attempts

They expose typed graph state for administration, reproducibility and recovery diagnostics. The
standard research frontend continues to consume the concise session projection and does not render
the raw graph.

All mutation requests use the shared command envelope and identify the expected current stage and
snapshot hash. Impactful upstream commands identify the invalidation preview being confirmed. See
workflow_stage_protocols.md. Routes delegate graph changes to typed stage services and
`GraphService`; no endpoint allows a client or model to set derived status, active pointers or
arbitrary nodes/edges.

Phase 1B upload responses contain file identity, checksum and schema/shape summaries only. They do
not echo parsed observation rows. This response-minimization rule is distinct from the internal AI
contract: stage-provider inputs receive actual values through read-only, checksum-bound access
grants and bounded page/filter/aggregate operations. No public endpoint gives a model arbitrary
paths or generic dataset queries.

## Agent namespace

Agent endpoints are rooted at /api/v1/agent and are defined in agent_mode.md. Agent routes never
accept Workflow session IDs. Full Agent trace uses
`GET /api/v1/admin/agent/sessions/{id}/runs/{run_id}/trace`. "Administrative" indicates the
diagnostic purpose, not an implemented login requirement; loopback isolation is mandatory.
## Stage handoff API (v1)

- `GET /api/v1/workflow/sessions/{id}/handoffs` returns immutable handoff versions. For a legacy
  session with no stored handoff it returns an inferred read-only preview.
- `POST /api/v1/workflow/sessions/{id}/handoff/commands` accepts the normal command metadata plus
  `confirm_decisions {decisionIds[]}` or `resolve_decision {decisionId,value}`. Only `actor=user`
  is accepted. Every accepted command appends a superseding handoff; it never edits an older one.
- AI Data/Analysis requests fail with `handoff_incomplete` semantics while any required decision is
  `needs_confirmation`.
