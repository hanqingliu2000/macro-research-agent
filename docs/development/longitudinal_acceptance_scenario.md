# Longitudinal Workflow acceptance scenario

Updated: 2026-09-12

Status: normative test specification. The local Phase 2 `T0`/`T1` subset was executed on
2026-09-07 and is recorded in `phase2_acceptance_report.md`; a bounded live Plan integration slice
is recorded in `plan_ai_acceptance_report.md`. Phase 3 connector slices are recorded in
`phase3_acceptance_report.md`; the complete Phase 0–3 baseline revalidation is recorded in
`phase0_to_phase3_acceptance_report.md`. Unchecked `T2`, the deferred additional remote provider profile `T3`
gates and full `T4` steps are not accepted.

Scenario ID: `LRS-001`

This document preserves the full realistic Workflow Mode acceptance scenario to run after the
required product slices are complete. It also defines smaller slices that can be run at the end of
each development phase. It is a test specification, not a test execution record.

The scenario deliberately spans several working days and several rounds of human/AI disagreement.
It tests whether the product supports research as an iterative, inspectable process rather than a
single prompt followed by a final answer.

## 1. Scope and governing contracts

`LRS-001` covers Workflow Mode only. Agent Mode remains a separate product path, session store and
test suite. The scenario follows:

- `workflow_stage_protocols.md` for stage inputs, outputs and chat ownership;
- `state_graph.md` for graph authority, checkpoints, invalidation, retries and recovery;
- `workflow_status_and_routes.md` for status and route projection;
- `ai_capability_orchestration.md` for typed AI proposals and allowlisted execution;
- `trace_and_reproducibility.md` for administrative evidence;
- ADR 0005 for screenshot-free routine testing and ADR 0012 for direct artifact visual review.
- `../testing/browser-runs/README.md` for browser-run completion and evidence logging.

The full scenario does not relax the dataset-acquisition boundary. Recorded provider fixtures or
approved connector functions supply analytical data. Web search, browser navigation, scraping and
arbitrary URLs are never used to acquire observations.

## 2. Test levels

The same scenario is executed at different levels. A phase may pass its available slice without
pretending that later capabilities exist.

| Level | Purpose | Permitted dependencies |
|---|---|---|
| `T0` deterministic CI | Schema, graph, reducer, API, numeric and artifact assertions | Fixed files, fake clock, recorded AI responses and deterministic capability handlers |
| `T1` restart/time | Cross-day resume, process recovery, concurrency and idempotency | Temporary durable runtime, fake clock and controlled process restart |
| `T2` manual UAT | Human usability of Excel round trip and final visual quality | A person using the local app and Excel; no model-driven browser screenshots |
| `T3` opt-in live evaluation | Provider behavior, research quality, cost and latency | Accepted connector contract or an explicitly authorized provider profile; OpenAI use in the deferred Phase 4 requires `approved_remote` gates `W0`–`W3` first |
| `T4` final longitudinal acceptance | The complete `LRS-001` journey and evidence package | All required capabilities accepted at their earlier levels |

`T0` and `T1` must be repeatable without network access. `T3` is never part of routine CI and must
record provider/model/fixture versions, authorization, cost and latency separately.

### 2.1 Browser-driven realistic runs

Interactive browser runs are a separate UAT/evaluation activity, not routine automated CI. A run
that claims end-to-end coverage begins with the research question and ends only after the current
ArtifactSet passes deterministic preflight and the configured Review AI, then freezes successfully
with a reproduction manifest. Review findings must be resolved and reviewed again through the UI;
the operator cannot repair backend state to force the session forward. Every run is recorded under
`docs/testing/browser-runs/` using its normative status definitions and template.

## 3. Persona and research request

The user is an applied macroeconomist who works on a project intermittently, exports data to Excel,
changes the research design after seeing intermediate results and expects reproducible Python and
Stata deliverables.

Initial request:

> Compare post-pandemic inflation persistence and monetary-policy responses in the United States,
> Japan and the euro area from 2018Q1 through 2025Q4. Explain differences across economies and
> produce charts, tables, clean underlying data, Python, supported Stata and a research report.

The deliberately underspecified request does not settle:

- headline versus core inflation;
- whether monthly observations should be transformed before or after quarterly conversion;
- what “euro area” means over time;
- whether an official euro-area series or a locally aggregated member-country series is required;
- the aggregation weight, missing-data policy and minimum coverage;
- the exact persistence and policy-response model;
- whether the report is descriptive or makes causal claims.

The system must surface these decisions rather than silently choosing them.

## 4. Planned fixture pack

The fixture files do not need to be built until the relevant test is automated. Once created, they
become versioned test assets with a manifest containing row counts, schemas, checksums and expected
golden results.

### 4.1 User file

`lrs001_policy_events_dirty.xlsx` contains supplementary local observations and annotations with:

- country names and mixed aliases such as `United States`, `US`, `Japan`, `DE`, `Germany` and
  provider codes;
- quarterly and monthly-looking period strings in one source column;
- numeric values plus `..`, `NA` and one numeric string;
- one duplicate logical key;
- one row the user later decides to exclude;
- an extra `analyst_note` attribute;
- one formula cell in the variant used to test rejected reimport;
- no executable macro and no instructions that the application should follow.

Plan-provider input includes a read-only checksum-bound grant and a bounded first page of actual
cell values. The provider can request all remaining pages; it must not be forced to infer from only
the schema or a sample. Ordinary API responses and trace reference hashes rather than echoing values.

### 4.2 Recorded provider data

The connector-enabled fixture set represents:

- IMF consumer-price and annual WEO series;
- World Bank population weights;
- ECB official euro reference-rate series used for comparison, not silent substitution;
- BIS central-bank policy-rate series;
- UN SDG per-capita growth observations when that admitted annual slice is exercised;
- a time-varying euro-area membership table, including Croatia's effective membership date;
- one transient member-series failure followed by a successful idempotent retry;
- one missing member-period that exercises the selected coverage threshold.

Recorded fixtures remain the repeatable `T0`/`T1` authority. Phase 3 connector implementations now
cover the listed admitted public-data slices; `T3` runs must use their typed acquisition contracts,
record exact provider/release identities and never label fixture execution as live evidence.

### 4.3 AI and review fixtures

Recorded typed responses cover:

- two clarification batches, a Plan draft and two Plan patch proposals;
- malformed planning output followed by bounded recovery;
- Data mapping/cleaning proposals, including one proposal the user rejects;
- an Analysis proposal with ordered operations and two model jobs;
- an Output authoring proposal and a rule-addressed visual review report;
- a delayed proposal whose target hash becomes stale before Apply;
- provider timeout and rate/cost-limit responses.

No fixture contains hidden chain-of-thought. It stores the exact allowed input, structured output,
model/provider metadata and concise rationale.

### 4.4 Golden analytical and output results

The future fixture manifest must lock:

- canonical row/key counts after each accepted Data operation;
- euro-area membership/coverage results by period;
- transformation values for representative boundary periods;
- model sample accounting, coefficients, covariance choice and result hashes;
- chart/table source values and specifications;
- workbook sheets, named ranges, chart XML and required metadata;
- Python/Stata support decisions and reproduced numerical results;
- final selected artifact and reproduction-manifest hashes.

## 5. Non-negotiable journey invariants

These assertions apply at every step.

1. Viewing an upstream stage never changes a node, pointer, checkpoint, status or hash.
2. A saved upstream change invalidates only its graph descendants and never reruns work
   automatically.
3. Every user or AI proposal targets an exact current snapshot/hash. A stale proposal cannot apply.
4. AI can propose but cannot cross Plan Next, Transformation Run or Output Finish.
5. AI cannot invoke unregistered connectors, arbitrary URLs, browser tools, filesystem paths,
   Python, shell or Stata.
6. Raw files stay in session-owned storage. Planning/Data/Analysis/Output AI may read complete
   relevant values only through stage/snapshot-bound grants and classification policy under ADR
   0014. A visual reviewer receives the direct artifact, not a browser screenshot.
7. Every accepted material change creates immutable state and append-only trace evidence. Undo
   moves a pointer; it does not erase history.
8. Idempotent replay creates no duplicate node, attempt, provider call, cost or artifact.
9. A current UI route and public projection can be reconstructed from durable graph state after
   restart.
10. Workflow and Agent sessions never appear in or mutate one another's stores.

## 6. Longitudinal timeline

Use a fake clock in automated tests; no test waits for real days.

| Simulated time | User activity | Required persisted checkpoint |
|---|---|---|
| Day 1 morning | Create research, attach file, clarify scope and review draft Plan | Current Plan thread, attachment metadata and unresolved Plan snapshot |
| Day 1 afternoon | Reject/accept AI suggestions, edit manually, resolve geography and approve Plan | Approved Plan snapshot and acquisition checkpoint |
| Day 2 morning | Resume after backend restart, acquire/inspect data and use quick cleaning | Source runs, provenance, immutable snapshots and active pointer |
| Day 2 afternoon | Export for external cleaning and close the app | Round-trip package, source snapshot/hash and instructions |
| Day 3 morning | Reimport invalid then corrected XLSX and approve Data | Validation findings, imported checksum, new dataset root and Data checkpoint |
| Day 3 afternoon | Build and edit transformation/model proposal, preview and Run | Pipeline spec, run checkpoint, attempts and AnalyticalBundle |
| Day 4 morning | Review Output, discover an upstream data issue and return to Data | Prior analytical/output nodes preserved as stale after confirmed correction |
| Day 4 afternoon | Rerun analysis, review/regenerate selected artifacts and Finish | Frozen ArtifactSet, reviews, code, data and reproduction manifest |
| Day 7 | Resume completed session and export again | Identical frozen hashes; no hidden rerun or provider call |

## 7. Detailed test flow

### 7.1 Session creation and Plan — `LRS-PLAN`

| ID | Human/AI interaction | Expected visible behavior | Durable/API assertion |
|---|---|---|---|
| `LRS-PLAN-01` | User creates the session, enters the request and attaches the dirty XLSX. | The app enters `/plan`; the attachment shows a schema summary, not observation values. | One Workflow request node and local upload record exist; Agent storage is unchanged. |
| `LRS-PLAN-02` | User selects Start Planning. | Planning AI asks a bounded first clarification batch about measure, frequency, group meaning and analytical goal. | A proposal/input node targets the request hash; no connector or execution node starts. |
| `LRS-PLAN-03` | User answers only measure and frequency and asks AI to retain both official and constructed euro-area comparisons. | A second batch requests aggregation weight, membership treatment, coverage and causal-language limits. | Both messages persist; provider values use the attachment grant, while trace records only its receipt/hashes. |
| `LRS-PLAN-04` | AI returns a Plan draft with the aggregation method still unresolved. | The right-side Plan is reviewable, but Plan Next is disabled with the exact unresolved item. | The Plan proposal has proposal authority and cannot authorize acquisition. |
| `LRS-PLAN-05` | AI proposes dropping Stata because one future operation may be unsupported. User rejects that change but accepts a clearer objective. | Patch review supports field-level acceptance/rejection; rejected fields do not change the Plan. | Apply creates a new immutable Plan snapshot containing only accepted fields. |
| `LRS-PLAN-06` | Before applying a second AI patch, the user manually changes the start period from 2019Q1 to 2018Q1. | The UI shows downstream impact if applicable and saves the manual edit. Applying the older patch is rejected as stale. | The old proposal retains its target hash and history; it cannot move a pointer or overwrite the new Plan. |
| `LRS-PLAN-07` | User asks AI to revise the current Plan again. | A new patch targets the new Plan and explains high-level impact without executing anything. | Provider request includes only allowed Plan context and capability descriptors. |
| `LRS-PLAN-08` | User confirms time-varying euro-area membership, population-weighted aggregation, available-member renormalization and an 85% coverage threshold. | Geography editor shows member codes, effective dates, membership source, weight source and missing policy. | A versioned geography resolution and aggregation specification are linked to the Plan. |
| `LRS-PLAN-09` | User selects chart, table, clean data, workbook, Python, supported Stata and Research Report. | Unavailable/planned deliverables are identified honestly; no placeholder file is promised. | Capability intents record versions, availability and future approval gates. |
| `LRS-PLAN-10` | User selects Plan Next. | A concise confirmation identifies acquisition scope and cost-bearing calls. | Exact Plan hash is approved; acquisition checkpoint is recorded once. Repeating the command is idempotent. |
| `LRS-PLAN-11` | User closes the browser and backend at the end of Day 1. | No special save action is required beyond accepted commands. | Restart reconstructs the same Plan thread, active Plan, stage, reachable routes and checkpoint. |

Plan rejection branches:

- An unresolved group member set, aggregation method or required unavailable capability blocks Next.
- A malformed AI response is never rendered as a valid Plan; bounded retry or a clear provider error
  is shown without changing state.
- A model suggestion that implies causality from the descriptive design must appear as a warning or
  require a revised model intent.
- A second browser tab holding the pre-edit Plan hash receives a typed conflict, refreshes current
  state and does not silently merge.

### 7.2 Data acquisition and preparation — `LRS-DATA`

| ID | Human/AI interaction | Expected visible behavior | Durable/API assertion |
|---|---|---|---|
| `LRS-DATA-01` | User resumes on Day 2. | The session opens at Data/acquiring or Data review according to durable graph state. | Projection, pointers and reachable stages equal the pre-shutdown state plus completed durable work. |
| `LRS-DATA-02` | Approved connector/capability runs fan out by member country. One recorded provider call fails transiently. | Source status distinguishes completed, failed and retryable work; aggregation waits. | Every attempt is recorded; the fan-in node is not ready until required parents satisfy policy. |
| `LRS-DATA-03` | User authorizes Retry. | Only failed work retries; completed members are not fetched again. | New attempt number is appended. Reusing the idempotency key creates no duplicate call or cost. |
| `LRS-DATA-04` | User inspects provenance, diagnostics and several preview pages. | Pagination and sorting are stable; viewing rows does not mutate the dataset. | Raw/normalized hashes, query/version, retrieval time and mapping records are retained locally. |
| `LRS-DATA-05` | Data AI reads the complete active snapshot and suggests code mappings, numeric cast and duplicate removal. User accepts mappings/cast, edits one alias and rejects dropping `analyst_note`. | Proposal diff allows selective acceptance and parameter edits. There is no Data chat pretending that discussion itself changed data. | Accepted items call registered typed operations; rejected items create no dataset snapshot. Reads use a stage/hash-bound grant and access receipt; embedded cell instructions are ignored. |
| `LRS-DATA-06` | User manually applies filter missing, deduplicate and sort. | Each result is previewable and appears in operation history. | Each operation creates one immutable snapshot with parent ref, typed parameters and row diagnostics. |
| `LRS-DATA-07` | User realizes the missing-value filter was too broad and selects Undo twice, then reapplies a narrower rule. | Preview follows the active pointer and redo is represented by a new accepted operation, not hidden file mutation. | Old snapshots remain addressable; Undo only moves the active pointer. Downstream work does not yet exist. |
| `LRS-DATA-08` | User exports the active dataset for external cleaning. | One `Export for external cleaning` action downloads the controlled workbook. | Package binds session, source snapshot, schema ID and manifest checksum. |
| `LRS-DATA-09` | User closes the app and edits the workbook overnight. | No server session must stay open. | The package and source root remain verifiable after restart. |
| `LRS-DATA-10` | First reimport contains a formula in `value`. | Import is rejected with sheet/cell-level findings and instructs the user to paste values. It does not partly commit. | No new active root or pointer move occurs; rejected file checksum and validation result are traced. |
| `LRS-DATA-11` | A tampered/wrong-session manifest variant is uploaded. | It is rejected before mapping and cannot replace any data. | Session/snapshot/schema/checksum mismatch is classified; no raw data is attached to another session. |
| `LRS-DATA-12` | User reimports a corrected values-only workbook that renamed `period` to `quarter`, removed the duplicate, edited values and retained `analyst_note`. | Mapping wizard requires `quarter → period`, shows type/key validation and preserves the extra column as an attribute. | Canonical required roles, frequency, period, numeric value and unique key pass before commit. |
| `LRS-DATA-13` | User confirms the mapping and replacement. | The corrected dataset becomes current while connector data remains inspectable as prior lineage. | Imported workbook checksum and normalized snapshot hash create a new active dataset root. Any proposal targeting the export source is now stale. |
| `LRS-DATA-14` | User selects Data Next. | The checkpoint summary identifies the active root, schema and preparation recipe. | `ApprovedDatasetRef` binds the exact dataset/schema/hash and enables Transformation. |
| `LRS-DATA-15` | An annual WDI Plan uses `2011-12` through `latest`. | Plan shows the concrete connector query convention; Data shows requested and resolved bounds. | WDI receives `2012` through the current year, never the raw fiscal label; malformed fiscal ranges fail before network access. |
| `LRS-DATA-16` | User asks where values are missing, says to preserve every missing row and permits only a deterministic sort. | A read-only diagnostic lists missing entity/indicator/period locations separately from one selectable sort; no removal is shown or preselected. | The semantic guard rejects any provider proposal containing missing-value removal or mutations beyond sort; applying nothing cannot change the snapshot. |
| `LRS-DATA-17` | User pages through Data previews containing 9, 56, 100 and 101 rows. | Each page label and paginator report the eight rows actually rendered, with global row numbers and a truthful loading state. | Offsets advance by eight; automated UI coverage verifies the first and last visible row of every page so no observation is skipped. |

Additional Data branches:

- Importing a workbook exported from an older active root after intervening Data edits must show an
  impact/conflict decision; it may not silently overwrite the newer root.
- A coverage result below 85% blocks the constructed group aggregate or requires explicit Plan/Data
  revision. It cannot be silently accepted by the AI.
- Provider metadata embedded with instructions is treated as untrusted data, not as a system prompt.
- If a required connector is still `planned`, the UI remains blocked/unresolved instead of creating
  fixture-looking “real” data.

### 7.3 Transformation and models — `LRS-TRANSFORM`

| ID | Human/AI interaction | Expected visible behavior | Durable/API assertion |
|---|---|---|---|
| `LRS-TRANSFORM-01` | Analysis AI proposes an ordered chain: frequency conversion, CPI growth, euro-area aggregation, policy-rate lag and rolling persistence summary. | Proposal names input, target selector, parameters and output role for every step. | It is a proposal node targeting the approved dataset hash; no operation runs on proposal creation. |
| `LRS-TRANSFORM-02` | User accepts only part of the proposal, changes quarterly method, narrows the period target, disables rolling mean and deletes an unnecessary rebase. | Pipeline list reflects explicit accepted operations and leaves model jobs separate. | Each accepted edit creates typed immutable specification history; rejected items never become execution nodes. |
| `LRS-TRANSFORM-03` | User tries to move CPI growth before its required frequency-conversion input. | The reorder is rejected with the missing dependency/schema reason and the previous order remains. | No pointer/hash changes on invalid reorder. |
| `LRS-TRANSFORM-04` | User previews before/after values at two intermediate steps and changes a target selector. | Preview labels its input/output and does not claim that the full pipeline ran. | Preview creates no approved analytical snapshot, model result or Run checkpoint. |
| `LRS-TRANSFORM-05` | User adds descriptive statistics, correlation and OLS/HAC jobs; each selects an explicit pipeline output. | UI prevents ambiguous or unsupported model specifications and shows sample requirements. | Models cannot become implicit transformation inputs. Specification and input hashes are recorded. |
| `LRS-TRANSFORM-06` | A delayed AI proposal arrives after the user changes the target selector. | Apply is disabled/rejected as stale; the user may request regeneration against current state. | Stale proposal remains traceable and cannot mutate the pipeline. |
| `LRS-TRANSFORM-07` | User selects Run Pipeline. | Confirmation lists enabled operations, models and exact active dataset. | Run checkpoint targets the current dataset and pipeline/model hashes; no prior Plan approval is reused as Run authority. |
| `LRS-TRANSFORM-08` | One independent model job fails while another succeeds. | Partial results and classified failure are visible; retry does not rerun successful siblings. | Attempts are append-only, fan-in follows declared partial-result policy and duplicate cost is prevented. |
| `LRS-TRANSFORM-09` | User corrects the failed model specification and reruns. | New results replace only the current failed branch; prior attempt remains inspectable. | `AnalyticalBundle` maps operation/model IDs to immutable outputs with diagnostics and warnings. |
| `LRS-TRANSFORM-10` | User adds an ADF test for one indicator and reviews deterministic terms and lag selection. | Results are shown separately for every entity/frequency series with the unit-root null stated explicitly; non-rejection is a warning rather than proof. | The typed specification, group samples, statistic, p-value, selected lag, critical values and hashes are reproducible; Stata unavailability is explicit. |
| `LRS-TRANSFORM-11` | User configures an ARIMA forecast and a SARIMAX scenario with approved future policy-rate values. | Ordinary/seasonal orders, trend, horizon and confidence are reviewable; fit diagnostics and forecast intervals are shown separately per entity/frequency. Missing future exogenous values block only the affected model. | Specifications and group results are hashed; forecast rows retain periods and bounds and are exported to CSV/workbook; no future exogenous value is invented. |
| `LRS-TRANSFORM-12` | User configures an ordered VAR system, reviews bounded lag selection and optionally enables IRFs for selected policy shocks. | Equation diagnostics and stability are visible per entity/frequency. IRF controls disclose that recursive orthogonalized shocks depend on variable order; results show impulse, response, horizon and bounds. | Systems never join entities/frequencies; impulses must belong to the model; typed coefficients and IRFs are hashed and exported to CSV/workbook. |
| `LRS-TRANSFORM-13` | User converts a percent series to basis points, then aligns monthly observations to a June fiscal year and chooses how incomplete quarters are handled. | Source/target units, factor/offset, fiscal year end and keep/drop/error policy are explicit. Retained partial periods show coverage and a warning. | A unit mismatch fails closed; each step records logical refs, input/output snapshot IDs and hashes, specification hash and row counts. Preview creates no persistent lineage. |
| `LRS-TRANSFORM-14` | User downloads generated Python and supported Stata and compares them with the reviewed configuration. | Unsupported Stata semantics produce an explicit warning and no misleading partial file. | Generated code embeds the same typed specification; Python reproduction matches golden analytical/model results. |
| `LRS-TRANSFORM-15` | User asks Analysis AI to keep an existing growth-rate series unchanged and first-difference only two percent-of-GDP share indicators. | The proposal shows Difference, the exact two-code target, percentage-point output and named input/output; the growth-rate series is explicitly preserved. | Provider output is rejected if it substitutes another operation, includes an excluded indicator or widens an explicit subset. Applying the accepted proposal changes only the selected values and units. |
| `LRS-TRANSFORM-16` | User asks Analysis AI to replace existing forecast jobs with one VAR over four named variables for exactly two annual periods, retain descriptive/correlation jobs and add no transformations. | The review shows the existing forecast jobs as explicit removals and one fully specified VAR addition; no operation appears. | The semantic guard rejects a changed model kind, variable set, horizon, protected-job removal or any forbidden transformation. Applying all selected items atomically retains the protected jobs and replaces only the forecasts. |
| `LRS-TRANSFORM-17` | An India-only Plan requests pre/post-pandemic sub-period averages but its model-supplied intent ID says `group_aggregation`. | Transformation opens with an executable descriptive comparison draft and no cross-entity aggregation error. | The compiler drops the semantically incompatible group operation; only a confirmed multi-member country group with a reviewed policy can emit `group_aggregation`, and the complete generated draft validates before persistence. |
| `LRS-TRANSFORM-18` | After reaching Output, the user returns to Transformation and wants to change an operation target. | Editors remain read-only until the user chooses `Revise analysis` and confirms the impact; the page then shows Output as stale and enables edits plus `Run updated analysis`. | Direct mutations from Output fail closed. The explicit revision transition archives current results, invalidates downstream graph nodes, persists accepted edits and survives reload without silently discarding a save. |

### 7.4 First Output review and upstream correction — `LRS-BACKTRACK`

| ID | Human/AI interaction | Expected visible behavior | Durable/API assertion |
|---|---|---|---|
| `LRS-BACKTRACK-01` | User reaches Output and notices a country-code mapping anomaly in a table. | Navigating back to Data alone changes nothing. | All current pointers, hashes and checkpoints remain unchanged. |
| `LRS-BACKTRACK-02` | User edits the mapping rule and saves. | Impact dialog names Transformation and Output work that will become stale; no rerun starts. | Confirmed edit creates a new Data snapshot/root, stales dependent analytical/output nodes, clears current downstream pointers and preserves old artifacts read-only. |
| `LRS-BACKTRACK-03` | User revisits the stale Output route before rerunning. | It is visibly historical/stale and cannot be exported as the current result or satisfy Finish. | Stale artifacts retain original hashes and lineage but cannot satisfy a new checkpoint. |
| `LRS-BACKTRACK-04` | User returns to Transformation. | Existing typed configuration may be reused only after dependency/hash revalidation. | A new Run checkpoint targets the corrected dataset; old approval cannot authorize it. |
| `LRS-BACKTRACK-05` | User reruns and returns to Output. | Corrected previews replace current Output while previous versions remain historical. | Unaffected Plan/Data history is preserved and new lineage reaches the corrected root. |

Invalidation branches should start from saved scenario checkpoints so each rule is isolated:

| Branch | Saved change | Must become stale | Must remain current |
|---|---|---|---|
| `LRS-INV-PLAN-SCOPE` | Plan objective, geography, period or source | Data, Transformation and Output | Prior snapshots remain historical |
| `LRS-INV-PLAN-ANALYSIS` | Plan transformation/model intent | Transformation and Output | Approved Data |
| `LRS-INV-PLAN-DELIVERABLE` | Plan deliverable selection only | Output and manifest | Data and AnalyticalBundle |
| `LRS-INV-DATA` | Active dataset/preparation | Transformation and Output | Approved Plan |
| `LRS-INV-PIPELINE` | Operation/model specification | Output | Plan and Data |
| `LRS-INV-ARTIFACT` | One artifact specification | Named artifact, its review and manifest | Unaffected artifact hashes |

Every branch asserts that cancelling the Impact Dialog leaves the graph unchanged.

### 7.5 Output authoring, Review AI and revision — `LRS-OUTPUT`

| ID | Human/AI interaction | Expected visible behavior | Durable/API assertion |
|---|---|---|---|
| `LRS-OUTPUT-01` | Current analysis generates the selected deliverables. | Artifact list distinguishes ready, warning, failed and stale without fabricating Research Report or Stata. | Each artifact binds its data/spec/guideline version and checksum. |
| `LRS-OUTPUT-02` | Deterministic preflight runs. | Findings identify exact rule IDs for value/spec equality, units, sources, labels, workbook structure, accessibility, code and manifest readiness. Findings do not disable the Review AI action needed for diagnosis. | Structural failures block Finish but cannot be waived by AI or user prose. |
| `LRS-OUTPUT-03` | User requests remote visual review without artifact-disclosure authorization. | The app explains the missing authorization and does not send the render. Structural or human inspection cannot substitute for the formal model approval required by Finish. | No remote provider attempt or cost is recorded without authorization, and Finish remains blocked. |
| `LRS-OUTPUT-04` | User authorizes the current chart/data disclosure and requests review. | Review AI sees the direct immutable render, guideline/spec and actual hash-bound underlying values—not a browser screenshot. | Authorization ref, artifact/render/dataset hashes, data-access receipt, provider/model/settings and structured result are traced. |
| `LRS-OUTPUT-05` | Review returns one required title/unit fix, one warning about crowded labels and one optional style patch. | Findings are rule-addressed; user accepts the title/unit patch, rejects the style patch and manually changes label selection. | Accepted/manual changes create typed artifact-spec revisions. Rejected patch creates no artifact. |
| `LRS-OUTPUT-06` | User regenerates selected affected artifacts. | Only named artifacts rerender; unaffected previews remain available. | Affected artifact/review/manifest nodes stale; unaffected artifact hashes remain byte-identical. |
| `LRS-OUTPUT-07` | Cross-artifact review finds a table/chart period mismatch. | The proposal names every affected artifact; user can accept only a coherent patch set or revise manually. | Invalidation follows all explicitly targeted artifacts and the package review/manifest, not unrelated files. |
| `LRS-OUTPUT-08` | ArtifactAuthor produces the Research Report using actual approved data plus summaries, diagnostics, limitations and citations. | Report distinguishes description from causal inference and references current figures/tables. | Data reads are snapshot-bound and the report receives its own compliance review. |
| `LRS-OUTPUT-09` | User asks Output Chat for another revision after an AI patch but before Finish. | Chat proposes a new typed diff against the current artifact hash; it cannot edit or Finish directly. | Iteration/cost limit is enforced and every proposal/review version remains durable. |
| `LRS-OUTPUT-10` | User selects a ready artifact for draft export before Finish. | Only selected current ready artifacts export; stale artifacts are never represented as current. | Draft export does not create or impersonate the final frozen manifest. |
| `LRS-OUTPUT-11` | User attempts Finish while a deterministic failure or requested deliverable is unresolved. | Finish is blocked with exact requirements; a warning requires an explicit documented policy decision. | No final checkpoint or frozen manifest is created. |
| `LRS-OUTPUT-12` | User resolves required findings and reruns Review AI against the regenerated current ArtifactSet. | Review history shows each immutable version and the current review reaches `pass`; a warning/fail is not treated as browser-run completion. | Final report targets the exact selected current hashes; deterministic preflight has no blocker and no proposal remains pending. |
| `LRS-OUTPUT-13` | A table exceeds the publication column limit; the user requests a compact table naming six available columns. | Duplicate findings appear once per artifact/rule/message; the proposal explicitly lists the selected columns, then preview/history/progress move to the new version. | Regeneration writes only the approved column subset, recomputes affected preflight, clears the proposal and rejects unknown/empty column selections with available-column guidance. |
| `LRS-OUTPUT-14` | User selects Finish after Review AI approval. | Final confirmation lists the exact selected ArtifactSet and limitations. | Final checkpoint freezes the set once; manifest references current Plan/Data/Analysis/review/artifact hashes and capability versions. |
| `LRS-OUTPUT-15` | DeepSeek authors the requested Research Report. | The preview shows deterministic Markdown built from typed sections, claims, limitations, citations and artifact references. | Every claim references only the granted dataset or typed result hashes; unknown evidence, citations and unsupported causal claims are rejected before an artifact is written. |
| `LRS-OUTPUT-16` | Codex-local finds a wrong direction/number, omitted forecast or unsupported causal statement. | The finding names the affected report section and evidence; any correction appears as a directive with acceptance criteria, not replacement prose. | `ReportReviewRequestV1` is hash-bound. The reviewer cannot mutate files, and selected reports cannot Finish until semantic status is `pass`. |
| `LRS-OUTPUT-17` | User approves one report directive and rejects another. | Output identifies the sections that will change and the evidence refs that must remain; approval creates a new version and starts the next review automatically. | DeepSeek changes only approved sections. Untargeted sections, data/model/code/manifest outputs and their hashes remain unchanged; removed evidence or new unapproved citations fail closed. |
| `LRS-OUTPUT-18` | Reviewer determines that a promised comparison or forecast has no upstream result. | Output says to return to Data or Transformation and does not offer wording-only repair. | Status is `requires_upstream_stage`, no report directive is applicable, and the shared three-round limit plus downstream invalidation remain enforced. |

### 7.6 Cross-time, concurrency and recovery — `LRS-RECOVERY`

| ID | Condition | Expected result |
|---|---|---|
| `LRS-RECOVERY-01` | Browser and backend close after each day boundary. | Resume uses durable server state, not stale page/local reducer state; messages, proposals, operation history and current previews agree with the graph. |
| `LRS-RECOVERY-02` | Two tabs load one snapshot; Tab A saves, then Tab B submits. | Tab B receives typed 409/current projection and cannot overwrite Tab A. A deliberate retry uses refreshed state and a new command ID. |
| `LRS-RECOVERY-03` | Process stops after a capability node is claimed but before completion. | Startup policy marks the attempt orphaned after its cutoff and exposes retry; it does not mark success or duplicate external cost. |
| `LRS-RECOVERY-04` | The same command is retried after client timeout. | Stored idempotent outcome and original graph-transition receipt return; no duplicate node/artifact/call is created. |
| `LRS-RECOVERY-05` | AI response arrives after its target was superseded on another day. | Response may be preserved as stale history but cannot Apply or move the session cursor. |
| `LRS-RECOVERY-06` | UTC day changes or local timezone changes between commands. | Event ordering uses monotonic sequence and UTC timestamps; no snapshot is reordered by display timezone. |
| `LRS-RECOVERY-07` | Provider data may have been revised since retrieval. | Resume does not silently refetch. A refresh is a new explicit acquisition command with new provenance and downstream impact. |
| `LRS-RECOVERY-08` | User resumes the completed session on Day 7 and exports again. | Frozen bytes and hashes match Day 4; no model, connector, renderer or reviewer reruns. |
| `LRS-RECOVERY-09` | User tries to edit the completed session. | Direct mutation is rejected because the final ArtifactSet is frozen. Continue creates a separate child at Output Review with immutable source lineage and requires a new review/Finish gate. |
| `LRS-RECOVERY-10` | User exports the session, moves the archive to another supported runtime and imports it. | Manifest/database/file checksums and safe paths are verified; a new session identity is assigned while uploads, snapshots, code, artifacts, graph and trace remain usable. |
| `LRS-RECOVERY-11` | User imports a modified, incomplete or path-traversing archive. | Import fails atomically; no session row or file tree remains and no existing session is overwritten. |

## 8. Component and contract decomposition

These are test responsibilities, not instructions to expose administrative graph detail in the
normal UI.

### 8.1 Plan surface

- `PlanChat`: ordered cross-day messages, pending/error/retry state and stage-bound command types.
- `PlanPatchReview`: exact diff, partial accept/reject, stale-target rejection and no direct Apply by AI.
- `PlanEditor`: manual save, dirty state, validation and Impact Dialog.
- `GeographyResolutionEditor`: members/effective dates/source/aggregation completeness.
- `CapabilityLists`: available/planned/disabled state and blocking unresolved intents.
- `StageNavigation` and checkpoint control: route guards and Plan Next authorization.

### 8.2 Data surface

- `SourceRunPanel`: registered source identity, progress, partial failure, retry and provenance.
- `DatasetPreview`/`PreviewTable`: stable pagination, schema/role display and no mutation on view.
- `QuickCleanToolbar`: typed parameters, immutable result, disabled invalid action and clear error.
- `OperationHistory`/Undo: active-pointer movement and preserved history.
- `RoundTripExport`: package identity and download recovery after restart.
- `SchemaMappingWizard`: formula/manifest rejection, role mapping, type/key validation and atomic commit.
- Data assistant proposal diff: selective Apply after controlled complete-snapshot reads.

### 8.3 Transformation surface

- `OperationCatalog`: only registered available operations.
- `PipelineList`: selection, enable/disable/delete, legal reorder and stale configuration state.
- `TargetSelector`/`ParameterEditor`: typed roles, entities, indicators, periods, frequencies and
  upstream outputs with schema propagation.
- `PipelinePreview`: deterministic prefix preview without formal execution state.
- `ModelJobList`: independent input refs, validation, partial failure and retry.
- Run checkpoint: exact dataset/pipeline/model hashes and no automatic execution after edit.
- Analysis assistant proposal diff: partial acceptance, parameter changes and stale-target behavior.

### 8.4 Output surface

- `DeliverableControls`: capability availability, requested/missing/ready state and selection.
- `ArtifactPreview`: current-versus-stale identity, rule findings and checksum-bound render.
- `OutputRevisionChat`: separate persisted thread, typed chart/table patches, section-bound report
  directives, target hashes and explicit user approval.
- deterministic preflight and Review panel: rule IDs, severity, affected artifacts and authorization.
- selective regeneration: only selected affected artifacts or approved report sections change hash.
- `ExportMenu`: current ready artifacts only; draft versus frozen package distinction.
- Finish checkpoint: blocking requirements, immutable final set and manifest.

### 8.5 Shared backend and graph

- command schema, expected stage/hash, idempotency and typed 409;
- graph-native node/edge/checkpoint/attempt/pointer writes and projection equivalence;
- descendant invalidation, unaffected siblings, stale history and exact transition receipt;
- bounded executor readiness, fan-out/fan-in, retry/cancel/orphan recovery and cost deduplication;
- per-stage hash-bound actual-data grants, proposal/review authority and allowlist enforcement;
- full paging, stale/unknown/wrong-session rejection, licensed remote denial and access receipts;
- prompt-like cell/column content remains inert untrusted data;
- append-only redacted trace, artifact ownership/checksum validation and restart reconstruction.

## 9. Test implementation map

| Concern | Primary automated test | Supporting evidence |
|---|---|---|
| Domain/schema | Pydantic/TypeScript contract and property tests | Versioned fixture JSON and invalid cases |
| Graph behavior | Invariant, state-transition, concurrency and projection-equivalence tests | Graph snapshots and transition receipts |
| FastAPI | In-process ASGI journey tests with durable temporary runtime | Status, response schemas, trace and restart reads |
| Frontend | Reducer, component, DOM, accessibility and adapter tests | Visible labels, control state, focus and command payloads |
| Data | Golden normalized/analytical snapshots and key/diagnostic assertions | Parquet/checksum and lineage records |
| XLSX | Workbook cell, table, hidden manifest, schema and formula inspection | Export/import checksums and validation findings |
| Transformation/models | Numeric golden tests and generated-code equivalence | Specification/input/result hashes and sample accounting |
| Charts/tables | Spec-to-source equality, SVG/PNG metadata and workbook chart XML | Direct artifact renders for manual/Review AI use |
| AI | Recorded structured responses, full-data paging and disclosure-policy tests | Prompt version, grant/source hash, access receipt, target hash and proposal trace |
| Live AI quality | Opt-in rubric-scored eval corpus | Reviewer scores, model/settings, cost and latency |
| Visual quality | Human review plus optional authorized Review AI | Direct artifact render, never a browser screenshot |

## 10. Phase-slice mapping

The implementation plan contains the normative exit criteria. This map prevents later tests from
blocking earlier phases merely because a future capability is unavailable.

| Development slice | `LRS-001` cases unlocked |
|---|---|
| Phase 1E-0 | Journey invariants 1–4 and 7–9; all `LRS-RECOVERY`; backtrack/invalidation graph assertions; graph side of each gate |
| Phase 1E-1 | Capability availability/allowlist assertions in Plan/Data/Transformation/Output and invocation trace |
| Phase 1E-2 | `LRS-PLAN-02` through `LRS-PLAN-09`, complete attachment paging, malformed/stale/provider planning branches and cross-day Plan thread |
| Phase 1E-3 | `LRS-DATA-02` through `14`, complete snapshot access, Data assistant behavior and all `LRS-TRANSFORM` assistant/execution cases |
| Phase 1E-4 | All `LRS-OUTPUT`, underlying-data access, selective regeneration, report review and final human gate |
| IMF connector slice | CPI/WEO recorded and live acquisition parts of `LRS-DATA-02` through `04`, member fan-out, cross-session response reuse and provider retry; policy-rate data remains unregistered |
| World Bank connector slice | Annual WDI/source 2 recorded/live acquisition, complete pagination, provider update identity, null preservation, retry and cross-session response reuse; population-weight use in the full scenario remains a later integrated T3 run |
| OECD connector slice | Pinned CLI 4.1 monthly LI acquisition, DSD/dimension drift rejection, shared minute/hour budgets, missing/status preservation and Plan-to-Data execution |
| Eurostat connector slice | Monthly COICOP 2018 all-items TOTAL HICP index, reviewed ISO3 crosswalk, sparse JSON-stat/status preservation, update-drift rejection and session evidence |
| ADB connector slice | Annual DF_NA 1.0 GDP/value-added acquisition, ISO3-to-ADB economy mapping, unit multiplier/status preservation, conservative shared minute budget and Plan-to-Data execution |
| ECB connector slice | Monthly EXR 1.0 euro reference-rate averages, exact quote direction, conditional-response identity and Plan-to-Data execution |
| BIS connector slice | Monthly WS_CBPOL 1.0 policy rates, preflight availability, bounded keys/rate budget, source/compilation preservation and Plan-to-Data execution |
| UN SDG connector slice | Annual 8.1.1 / `NY_GDP_PCAP`, current-release resolution, complete paging, reviewed M49 mapping and disaggregation/status preservation |
| Deferred Phase 4 additional remote provider profile | `W0`–`W4` and `W6` from `provider_profiles.md`; `W5` separately for every additional enabled Data/Analysis/Output task, with Plan access never implying multimodal access |
| Phase 2+ | Advanced models, versioned template linting and portable cross-machine session transfer variants |

## 11. Final `T4` evidence package and pass rule

The final run preserves:

- fixture manifest and application commit;
- provider/capability/skill/guideline versions;
- simulated timestamps and restart points;
- command IDs, idempotency keys, snapshot hashes and graph-transition receipts;
- expected and actual row counts, numeric goldens and model sample accounting;
- rejected and accepted AI proposals with target hashes;
- round-trip export/import/normalized checksums and validation findings;
- all artifact specs, renders, reviews, patches, regenerated hashes and final manifest;
- a concise human UAT record for Excel ergonomics and visual quality.
- the browser-run log with session ID, provider/model profiles, review iterations, issue links and
  post-freeze reload result.

`T4` passes only when every required case is satisfied with no unexplained state mutation, stale
artifact presented as current, unapproved external/AI execution, missing provenance or numerical
mismatch. A waived warning must cite an approved rule/policy; deterministic structural failures
cannot be waived.

For a browser-driven `T4` run, the final selected ArtifactSet must receive Review AI `pass` before
Finish. Reaching Output, producing artifacts, obtaining an advisory-only review or freezing a set
that was not the exact reviewed version is not acceptance.

## 12. Decisions required before the final run

These are intentionally visible gaps rather than assumptions hidden inside tests:

1. **Stale-history access:** define whether old snapshots are visible in a standard read-only
   history surface, only in administration, or only in reproduction export.
2. **Draft export labeling:** implemented downloads use an explicit `Draft export` notice and
   `Download draft …` label. A future publication guideline may refine the visual treatment without
   changing the frozen-manifest contract.
3. **Package-level review impact:** a cross-artifact finding must enumerate all affected artifacts;
   the invalidation policy for package review nodes must be finalized.
4. **Live provider revisions:** define user-facing comparison/refresh behavior without automatic
   replacement of the approved dataset.
5. **Research quality rubric:** schema correctness is not research quality. Planning, narrative and
   visual quality need a versioned rubric and reviewed eval corpus before live-model acceptance.
6. **additional-provider governance:** before deferred Phase 4 can enter `W0`, record the approved tenant,
   endpoint, models, task allowlist, data classifications, retention/training terms, budgets and
   accountable owner. A generic OpenAI credential or the existing development adapter is not this
   approval.

These gaps do not block deterministic tests for already implemented lower-level contracts. They do
block claiming the complete longitudinal scenario as accepted.
