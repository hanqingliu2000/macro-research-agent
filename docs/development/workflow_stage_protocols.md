# Workflow stage protocols

This document is the authoritative communication contract between Workflow stages, UI feature
stores, LLM planning/output ports and implemented FastAPI commands. Accepted inputs and outputs
become nodes, typed edges and immutable references in the durable graph defined by `state_graph.md`.

## Route and layout contract

| Stage | Route | Primary workspace | Preview workspace |
|---|---|---|---|
| Plan | `/sessions/{id}/plan` | current editable Plan or clarification context | right-hand Plan conversation, before and after a draft exists |
| Data | `/sessions/{id}/data` | sources, queries, provenance and import | data preview and preparation controls |
| Transformation | `/sessions/{id}/transformation` | transformation pipeline and model jobs | selected-step data preview |
| Output | `/sessions/{id}/output` | deliverable controls and Output chat | artifact preview and export |

Reached stages may be revisited. A future route is guarded until its prerequisite snapshot exists.
The UI redirects to the latest reachable stage and explains why. A compact four-stage navigator
replaces the old progress stepper; there is no Steps panel.

## Shared command envelope

Every mutation carries `command_id`, `idempotency_key`, `session_id`, `expected_stage`,
`expected_snapshot_hash`, `actor` and UTC `requested_at`. A stale expected stage/hash is a conflict,
not a last-write-wins update.

Commands return the updated session projection, created snapshot references, invalidated node IDs
and a concise user-visible outcome. The frontend never writes session status directly.
`GraphService` revalidates dependencies and records node/edge/pointer changes transactionally;
stage services do not maintain a second implicit workflow state.

## Clarification and Plan

The LLM planning port receives the research request, clarification answers, current Plan, registered
capabilities and read-only grants for the actual values in relevant attachments. A bounded first
page may be supplied inline; the model can page across the complete attachment rather than infer
from a schema or sample. Every grant is session/stage/checksum-bound and disclosure-checked.

Allowed responses are `ClarificationBatch`, `PlanDraft` and `PlanPatchProposal`. A proposal includes
typed field changes, a plain-language summary and its predicted downstream impact. It cannot
advance the workflow or run a connector.

Every clarification question has two to six model-proposed options plus a separate, labeled custom
answer input owned by the UI. The submitted contract remains `answers: Record<question_id, string>`;
the backend does not require the selected answer to equal a proposed option.

The current Plan contains:

- objective and natural-language geography intent;
- start/end period and frequency;
- resolved countries or country-group definitions;
- data-source queries;
- transformation and model intents;
- selected deliverables, including Research Report;
- a versioned capability invocation plan for intended connector, function, model, renderer,
  reviewer and runtime-skill calls, including availability and approval gate;
- assumptions, warnings and unresolved requirements.

A country-group resolution records member codes, membership source, effective-period policy,
aggregation method, weight series/source, missing-data policy and coverage threshold. Member
country data is acquired first and aggregated locally through the registered aggregation
function. An unresolved group or aggregation method blocks Plan Next.

Manual Plan edits and accepted chat patches use the same command. The user sees one current Plan;
the backend retains immutable snapshots and hashes.
An AI response first creates a non-authoritative proposal node targeting the exact current Plan
hash. Apply is a separate user command that may create a superseding Plan node.

`unresolved requirements` contains only choices that genuinely prevent Plan approval or registered
data acquisition. Explicitly non-blocking discovery alternatives, generic Source Index limitations
and connector bookkeeping cannot disable Plan Next. A deterministic classifier removes that
plumbing and keeps only current, material interpretation risks under warnings. Dataset contents,
observation gaps, exact period coverage and current provider availability are not inferred from the
Source Index and cannot appear as Plan blockers, cautions or factual premises in clarification
questions. A known missing/disabled connector or missing credential remains a valid blocker. The
same rule is applied to new model output and legacy saved Plans before approval.

Plan Next outputs an `ApprovedPlanSnapshot` and authorizes only its listed acquisition requests.
It does not authorize later Analysis, rendering or review calls. Each intent is revalidated against
the registry and its stage checkpoint when execution is reached. A required `planned` or `disabled`
capability remains unresolved and blocks that execution checkpoint.

## Data

Data consumes the approved Plan snapshot and produces `DataWorkspaceState` with source runs,
provenance, raw/normalized snapshot references, the active dataset, schema, quality diagnostics,
mapping records, data-preparation operations and a paginated preview reference.

The Data preview prioritizes entity, indicator, period, value, unit and frequency so the first view
is sufficient to inspect an observation. `missingShare` means the percentage of observation rows
whose canonical `value` is null. Nullable descriptive metadata such as entity name, provider status
or attributes is excluded. Connector failures, empty results and actual coverage gaps are reported
here after acquisition rather than predicted during Plan review.

Open-ended Plan endings such as `latest available year` remain part of the approved research
intent. At acquisition they resolve to a concrete current-date query upper bound in the requested
frequency. Source runs and trace retain both values and label the concrete period as an upper bound,
not proof of provider availability; returned observations determine actual coverage (ADR 0028).
For annual World Bank, ADB and UN SDG queries, consecutive fiscal labels are visibly mapped to
their ending calendar years before acquisition. Requested and resolved start/end values remain in
the source run and trace; malformed fiscal ranges fail before a provider call.

Data preparation is restricted to filter, keep/drop, rename/map codes, type cast, missing-value
rules, deduplication and sorting. Each accepted operation produces an immutable dataset snapshot.
Undo changes the active pointer to a prior snapshot; it does not delete history.

Data AI receives a read-only grant to the complete active snapshot so it can diagnose real missing
patterns, codes, duplicates and suspicious values. It returns typed proposals only; reads cannot
change the active pointer and accepted operations still use the registered preparation commands.
Explicit preservation/negation constraints are fail-closed: “keep missing” or “do not filter/delete”
forbids missing-value removal, while “only sort” forbids every other mutation. Missing diagnostics
identify bounded entity/indicator/period locations or state a typed limitation, and the UI separates
these read-only findings from selectable mutating operations.

When an approved Plan names multiple executable public sources, Data runs each connector
independently and retains one source run, normalized snapshot and provenance receipt per source.
It then prepares a canonical long-form union with row-level connector, dataset and source-snapshot
lineage. The union preserves source frequency, units and missing observations, and rejects
overlapping canonical identities. A `data_merge` graph node and the Data merge-review card expose
these policies; `approve_data_merge` is required before Data Next. This is not an implicit
horizontal join or an activation of the analytical `merge` transformation.

### XLSX round trip

The workbook contains:

- `Data`: the editable named table;
- `Schema`: columns, logical roles, types, required flags and key fields;
- `Provenance`: source and snapshot references;
- `Instructions`: supported edits and import requirements;
- `_MRA_MANIFEST`: hidden, locked metadata containing the session, source snapshot, schema and a
  checksum of the canonical manifest fields.

On import, the mapping wizard detects source columns and maps them to required logical roles.
Renames, compatible type changes, row deletion, value edits and valid new records are permitted.
Extra columns are retained as attributes. Dataset-specific key uniqueness, periods, frequencies,
numeric values and required roles must validate before commit. Formula cells in the Data table
must be materialized as values.

A successful import becomes a new active dataset root. Provider snapshots remain preserved. The
exported and imported workbook checksums are recorded outside the workbook together with the
verified manifest checksum, avoiding a self-referential workbook checksum. Copy/paste is outside
the round-trip contract.

Data Next outputs `ApprovedDatasetRef`, its schema/hash and its preparation recipe. It also creates
a reviewable Pipeline draft from enabled transformation intents and `ModelIntentV2`. Historical
periods use frequency-aligned `YYYY`, `YYYY-MM` or `YYYY-Qn` forms (with `latest` allowed only as
the end), while forecasts use a separate `ForecastHorizon`. Ordered model variables carry explicit
roles; `targetIndicators` is derived only for compatibility. Draft selectors and model variables
must occur in the approved snapshot; unsupported or disabled intents are not invented. Output later
validates forecast delivery against these reviewed model-job variables and horizons, not the full
acquired indicator set. If the Plan requests no data
transformations, the operation chain explicitly says so and model jobs may read `active_dataset`
directly. Time-window or pre/post sub-period summaries are not compiled as cross-entity
`group_aggregation`. That operation is generated only for a confirmed multi-member country-group
resolution with an explicit aggregation policy; its reviewed members and policy are copied into
the typed operation. Every generated operation/model reference is validated before the draft is
returned. Data Next does not execute analytical transformations or cross the Run approval gate.

## Transformation and models

Transformation consumes the active dataset. It exposes a Power Query-inspired ordered operation
list without M language or arbitrary code.

Plan-derived jobs use explicit Plan variable roles and structured forecast horizons. The compiler
does not parse narrative labels/objectives for executable parameters. Remaining model settings use
registered bounded defaults, and users review and may revise the draft before Run. A completed
Pipeline displays a completed, disabled checkpoint; editing after a
run is initially read-only. The user must choose `Revise analysis` and confirm that current Output
will become stale before any editor is enabled. That typed transition preserves the prior bundle,
model/code results and Output artifacts in history, moves the active stage back to Transformation,
marks Output stale and restores an explicit `Run updated analysis` action. Direct post-completion
mutation commands fail closed until this transition has been accepted.

Transformation and model-assistance ports may inspect the actual approved input and relevant
immutable outputs through snapshot-bound grants. Their proposals still contain allowlisted typed
operations/model specifications and cannot execute arbitrary expressions.

Each operation contains an allowlisted operation ID, input/output references, target selector,
typed parameters, enabled state and execution status. Target selectors may identify indicators,
entities/groups, fields, period, frequency and a prior pipeline output. Reorder is accepted only
when dependencies and schemas remain valid.

The Phase 1D-1 registry implements lag/lead, difference, year-on-year and period-on-period growth,
log, rebasing/indexing, down-frequency conversion, rolling mean and controlled group aggregation.
Deflation, per-capita conversion, analytical merge/join and seasonal rules remain contracted but unavailable
until their additional input/schema contracts are implemented.

Phase 2 harmonization adds `unit_conversion` with reviewed `sourceUnit`, `targetUnit`, `factor` and
`offset`. Selected rows must carry one matching unit; execution updates values and unit metadata
together. `frequency_conversion` accepts one source frequency and records `calendar`, optional
`fiscalYearEndMonth`, and `incompletePeriod: keep | drop | error`. Retained partial periods carry
`frequency_coverage`; fiscal monthly inputs are relabelled against the reviewed year end. Every
executed operation adds an immutable lineage entry with logical refs, input/output snapshot IDs and
hashes, a typed specification hash and row counts. In-memory preview creates no lineage entry.

Models are separate jobs on the same screen. Each selects a pipeline output and typed model
specification. Multiple independent jobs may run in parallel. Model results cannot implicitly feed
ordinary transformations.

Pipeline edits maintain model bindings as part of the same state transition. Deleting an operation
rebinds any model that read its output to the nearest surviving upstream output (or
`active_dataset`), records a visible notice and preserves the pre-edit graph for Undo. The Run
boundary validates every model input against the current operation graph and fails with a named
deleted-reference error rather than attempting an unresolved snapshot.

The Phase 1D-2 registry supports descriptive statistics, listwise correlation and OLS with
nonrobust, HC1 or HAC covariance. Descriptive jobs may explicitly select indicators or use all
available indicators. Correlation requires at least two indicator codes. OLS requires exactly one
dependent indicator and one or more independent indicators. HAC accumulation is bounded within
entity/frequency blocks so adjacent entities are never treated as one time series.

Phase 2A-1 adds ADF for exactly one selected indicator. The reviewed specification fixes
deterministic terms, automatic or fixed lag selection and maximum lags. Execution runs separately
for each entity/frequency series and returns the statistic, p-value, selected lag, effective sample,
critical values, information criterion where applicable and explicit five-percent decision. A
non-rejection is reported as a warning rather than relabeled as proof of a unit root.

Phase 2A-2 adds ARIMA and SARIMAX for one dependent indicator per entity/frequency series. Typed
parameters cover ordinary order `(p,d,q)`, seasonal order `(P,D,Q,s)`, trend, forecast horizon,
confidence level and stationarity/invertibility enforcement. ARIMA rejects seasonal and exogenous
terms. SARIMAX may select exogenous indicators, but forecasting requires complete values for every
future period in the approved snapshot. Execution returns parameters, AIC/BIC/HQIC, log likelihood,
convergence state and period-labelled forecast means/lower/upper confidence bounds. Forecast rows
also become a governed CSV and workbook sheet. Unsupported frequency labels, invalid periods,
insufficient samples and missing future exogenous values fail the affected model branch explicitly.

Phase 2A-3 adds VAR for an ordered list of at least two indicators. Lag selection is either a fixed
reviewed order or an AIC/BIC/HQIC/FPE choice bounded by `maxLags`; deterministic terms are explicit.
Each entity/frequency system is complete-case estimated independently. Results return equation
coefficients with standard errors, test statistics and p-values, selected lag, AIC/BIC/HQIC/FPE,
log likelihood and stability. A reviewed 0–60-period forecast horizon produces period-labelled
means and confidence bounds for every endogenous variable. Optional IRF generation fixes impulse indicators, horizon,
confidence and orthogonalized versus reduced-form semantics. Orthogonalized shocks use the visible
indicator order, which must be reviewed before Run. An impulse outside the system, zero-lag IRF,
insufficient sample or failed estimation fails that model branch. IRF rows become a governed CSV
and workbook sheet.

The Plan compiler derives an explicit forecast-period count from the approved, frequency-aware
forecast horizon. A plural univariate ARIMA intent becomes one typed job per promised target, while
a joint/multivariate forecast intent becomes a forecast-enabled VAR rather than a one-target
SARIMAX without future exogenous values. Output preflight checks that every promised target and step
exists before Finish and reports `FORECAST-DELIVERABLE-001` when the contract is incomplete.

Transformation Run is the execution checkpoint. It records an `AnalyticalBundle` containing the
final dataset snapshot, logical-to-physical output refs, per-operation lineage, model-result IDs,
diagnostics and warnings, then Phase 1D-4 generates selected outputs and advances to Output Review.
Each model result records its input
snapshot/hash, specification hash, sample accounting, structured estimates and result hash.
Runtime failures are isolated per model job: successful siblings remain current, the bundle records
failed branches as limitations/warnings, and a corrected retry reuses compatible successful
results instead of rerunning them.

Phase 1D-3 adds immutable `CodeArtifact` references to the bundle. Python embeds the canonical
reviewed operation/model specification and calls the versioned deterministic reproduction runtime;
it writes analytical Parquet and model-result JSON. Stata is emitted only when every selected
operation and model has a semantics-preserving translation. A missing Stata reference plus bundle
warning is expected for unsupported combinations, not a partial do-file.

Code preview/download validates the stored checksum. Generated code is never accepted as a Pipeline
input and is never executed by the backend. Output packages immutable copies of selected code refs.

## Output

Output consumes the current Plan, approved dataset, AnalyticalBundle, selected deliverables and
guideline version. It creates an `ArtifactSet` containing charts, tables, optional Research Report,
underlying data, workbook, Python/Stata code, provenance, limitations and reproduction manifest.

The production `ArtifactAuthorPort` uses DeepSeek chart wording and author checks, while
deterministic specifications/renderers control numerical plotting and table construction. It
receives chart/table specifications, result summaries, guideline rules, preview metadata and a
read-only grant to relevant underlying data. It
can inspect complete values by bounded paging rather than relying on summaries. It returns an
`OutputRevisionProposal` naming affected artifacts and typed specification patches. The user
applies the proposal before selective deterministic regeneration.

The production `ReportAuthorPort` is a separate DeepSeek role. It receives the approved handoff,
Plan/deliverables, snapshot-bound reads, complete typed results/hashes, diagnostics, forecasts,
artifact refs, citations and guideline. It returns a structured draft and EvidenceClaim ledger;
deterministic validation renders Markdown. Codex-local independently reviews report semantics and
may return only a section-bound directive. A user must approve that directive before DeepSeek can
rewrite named sections. A missing dataset/model result returns `requires_upstream_stage` instead.
Author and semantic Reviewer also receive owned, hash-bound presentation evidence for the current
artifacts: bounded SVG/spec contents, verified CSV headers and explicitly limited workbook
file/spec receipts. This context does not certify every workbook cell or visual quality. Revisions
refresh the bindings; missing/corrupt evidence fails closed before another author/reviewer call.

Output review covers the complete selected ArtifactSet and its underlying data. Deterministic preflight validates
data/spec equality, workbook/chart/code/manifest structure and hashes, deliverable completeness,
labels, units, sources, formats and accessibility metadata. `OutputReviewPort` receives package
metadata/summaries for cross-artifact review and may use multimodal capability to inspect direct
renders against the same versioned guideline. It returns a rule-addressed `OutputReviewReport`
with pass/warning/fail findings and optional typed patches. It cannot edit pixels, waive
deterministic failures, invoke Finish or modify an artifact without user approval.
The deterministic local implementation reads the render artifact by session-scoped reference,
verifies its checksum, decodes the PNG pixels and blocks malformed, undersized or blank renders.

Analytical charts are partitioned by indicator and reported unit before rendering. Entities become
series only within that homogeneous view; multiple indicators produce separate SVG artifacts and
workbook chart-data sheets. The chart spec records the indicator and unit, and deterministic review
compares those fields with the complete approved rows and checks that no approved indicator was
silently omitted. Long SVG titles wrap within the fixed render and large axis values use compact
suffixes while retaining exact values in the underlying table/workbook.

The local package review also requires one underlying data hash and guideline version across
comparable selected artifacts. Source-note differences produce coordinated patch groups; unit
consistency is evaluated inside each indicator-specific chart because distinct indicators may
legitimately use different units. The user selects or rejects each complete correction group.

A remote vision call requires an approved provider profile and disclosure authorization
because the rendered chart may expose plotted labels and values. Otherwise only deterministic,
local-vision or human review runs. The render is an artifact, never a browser UI screenshot.
The implemented Codex-local adapter uses the locally authenticated client, not an offline vision
model; it may send approved direct PNGs and context to its provider. Structural checks or a human
inspection cannot silently replace the formal model approval required by the current Finish gate.

For any future approved remote profile, Plan access and remote visual access remain separate
acceptance scopes. Enabling a planning adapter cannot authorize artifact or underlying-data
disclosure. See `provider_profiles.md` for the future profile boundary.

Output Finish first displays the exact selected artifact names and recorded limitations, then
freezes that set and its manifest after explicit confirmation. Earlier downloads are labeled as
draft exports and cannot impersonate the frozen package.

When an artifact has a compatible historical version, Output exposes a read-only comparison of
file hash, specification changes and structured-value hashes/counts. The comparison distinguishes
presentation-only edits from data changes and never copies analytical cell values into the API.

The implemented `publication-v1` path creates analytical CSV, SVG, XLSX, optional governed Markdown
Research Report and selected Python/Stata files.
The workbook contains Analytical Data, Model Results, Provenance, Diagnostics and Chart Data plus a
native Excel chart when data are plottable. Output review produces a fixed-size PNG direct render,
rule-addressed structural/visual findings and human-selected typed regeneration. Remote
multimodal review through Codex-local is implemented; additional API-provider review adapters and
their independent acceptance are not implemented.
The active guideline permits line charts with at most six series, requires color plus line-pattern
encoding and an underlying accessible table, and fixes title, size, legend, metadata, missing-value,
filter and frozen-header rules. Unknown guideline versions and structural density violations fail
deterministic preflight before Finish.
Generated workbooks additionally bind to `research-workbook-v1`; its linter reports stable
`WORKBOOK-*` findings for required sheets/headers, filters, formula-free data, external links,
guideline metadata, conditional sheets and selected embedded charts.
The publication reviewer then binds chart series and table columns to the complete approved data and
reads the checksum-bound Research Report bytes to validate required sections, counts, source,
causal-inference boundary, reproduction statement, selected artifact references and citations.
Phase 1E has normalized the durable state graph, implemented the capability/skill registry and
completed the conversational Plan proposal contract. Plan supports repeated clarification, typed
draft/patch validation, field-level Apply/reject, proposal graph authority and stale-target checks.
Data and Transformation expose separate role-scoped DeepSeek assistant requests whose typed mapping,
cleaning, transformation and model items can be selected or rejected. Applying them preserves the
normal invalidation/Undo path and never performs Data Next or Run. Deterministic assistant
implementations remain injected offline-test fakes only. The graph-native transition migration,
controlled rendering and bounded Codex review loop are implemented; broader live-model reliability
and cross-day acceptance remain open. See `state_graph.md` and
`ai_capability_orchestration.md`.

Analysis assistance treats explicit operation names, indicator subsets and exclusions such as
“keep unchanged” as hard request constraints, not advisory prose. The provider-output boundary
fails closed if a response substitutes a materially different transformation, widens an explicit
subset or targets a protected indicator. An empty proposal is the permitted safe-refusal form.
Difference operations may carry a reviewed `outputUnit`; execution and generated Stata preserve the
same selected-row unit change.

Model-revision requests use the same hard-constraint boundary. A request that forbids
transformations cannot yield an operation proposal; an explicit supported model kind, variable set
and forecast horizon must be preserved exactly. Replacement proposals contain selectable typed
model-removal items alongside the new model specification, so Apply can atomically remove the named
forecast jobs and add their replacement while retaining explicitly protected jobs. The proposal is
still hash-bound to the current pipeline and never runs analysis implicitly.

## Invalidation matrix

| Saved change | Invalidated current work |
|---|---|
| objective, geography, period or source | Data, Transformation, Output |
| transformation/model intent in Plan | Transformation, Output |
| deliverable selection | Output |
| active dataset or preparation operation | Transformation, Output |
| transformation operation or model job | Output |
| one artifact specification | that artifact and manifest |
| one review-approved artifact patch | that artifact, its review result and manifest |

Before an invalidating save, the API returns or accepts an impact preview. Confirming the command
marks prior dependent nodes stale, preserves their artifacts and clears current downstream
pointers through graph descendant traversal. No connector, model or report reruns automatically;
unaffected sibling branches remain current.

A Pipeline edit after Output review also stales the Output compliance-review, visual-review and
semantic-report-review nodes. Those review nodes must not keep the projected active stage at Output
after the Pipeline has returned to `pipeline_editing`.

## Chat ownership

`stageThreads.plan/data/transformation/output` persist stage-local conversations; the older
`planThread` and `outputThread` fields remain compatibility projections. Clarification belongs to
the Plan thread. Messages bind to stage, target
snapshot/hash and an allowed command type. A stage chat cannot mutate another stage or the session
cursor. Full prompts and responses remain in administrative trace; the standard UI shows only the
user-visible thread.

Data and Transformation assistant proposals have their own stage-bound records and threads, not
one global conversation. Each stage displays the confirmed/inferred/unresolved research decisions
from the current immutable handoff, together with role/provider/model state. All assistant,
function and skill calls bind to the current snapshot/hash;
stale proposals cannot be applied. Chat messages are graph inputs or proposal references, not an
execution cursor or substitute for durable stage state.
