# AI capability and skill orchestration

This document defines the runtime AI boundary for Workflow Mode. It does not describe
Codex development skills. Runtime skills are versioned, application-owned orchestration bundles
that can compose only registered functions and interfaces. The durable execution substrate is the
state graph in `state_graph.md`; AI is a typed graph participant, never its controller.

## Interaction rule

AI participates through typed proposals, never by mutating a session or invoking an arbitrary tool
directly. Every request is bound to a stage, current snapshot hash, provider profile and an explicit
allowlist. The backend validates the response and presents its impact before any consequential
execution.

Each accepted AI request, validated proposal/review, approved invocation and immutable result is
represented by graph nodes and typed edges. `GraphService` owns readiness, checkpoints,
invalidation and active pointers. Provider adapters and capabilities cannot mark their own node
complete or advance the session.

The intended sequence is:

1. issue task-relevant grants to the complete actual data required by the stage;
2. select the task-specific capability allowlist;
3. call the provider through a typed AI port;
4. validate the structured proposal and referenced capability IDs;
5. show the proposal and downstream impact to the user;
6. execute registered functions only after the applicable approval gate;
7. persist proposal, invocation, attempt, result references and checksums in graph state and trace.

An unavailable capability is never simulated. A placeholder has `availability: planned`, no
executable handler and a human-readable reason. A required placeholder keeps the relevant Plan
item unresolved and blocks its execution checkpoint.

## Registry contracts

`CapabilityDescriptor` contains:

- stable capability ID and semantic version;
- kind: `connector`, `function`, `model`, `renderer`, `reviewer` or `skill`;
- supported stages and availability: `available`, `planned` or `disabled`;
- input/output JSON Schemas;
- data-access classification and permitted provider profiles;
- approval policy, timeout/retry policy and handler reference when available;
- provenance and code-package version.

`RuntimeSkillManifest` contains:

- skill ID/version and supported stages;
- typed skill input/output schemas;
- ordered or conditional required capability IDs;
- data-minimization and approval requirements;
- failure/partial-result policy;
- no executable model-generated code.

`CapabilityInvocationIntent`, stored in the Plan, contains:

- stage, capability/skill ID and version constraint;
- purpose and typed argument template;
- input references and expected output role;
- required checkpoint and current availability;
- dependency IDs and unresolved requirements.

The Plan UI may group these intents under Data Source, Transformation, Model, Output and Review,
but the durable representation is one inspectable invocation plan.

## Ports and implementation status

`CapabilityRegistry`, `SkillRegistry`, the fail-closed direct `CapabilityExecutor` and
`PlanningAssistantPort`, `DataAssistantPort`, `AnalysisAssistantPort`, `ArtifactAuthorPort` and
`OutputReviewPort` are implemented. Existing
stage-command and user-action capabilities retain
their typed service boundaries rather than becoming generic direct tools.

- `PlanningAssistantPort`: implemented clarification batch, Plan draft and Plan patch proposal via
  the DeepSeek-compatible structured adapter in the current runtime. The provider-neutral adapter
  source remains reusable, while the deterministic implementation is an injected test fake and the
  generic OpenAI adapter is not selectable. Provider output is validated locally and cannot call
  tools, approve the Plan or start acquisition. Its context also
  contains bounded, request-ranked `source-index-lite-v1` provider/dataset/indicator entries.
  Detailed dimensions remain outside the prompt; discovered datasets without an admitted connector
  are discovery-only and cannot become executable sources.
- `DataAssistantPort`: implemented DeepSeek Data Steward for local-file mapping and hygiene
  proposals using the actual upload/active snapshot and current handoff. Public connector execution
  remains a separate connector slice.
- `AnalysisAssistantPort`: implemented DeepSeek Analyst transformation-chain and model-job proposals using the
  approved dataset snapshot. A deterministic semantic postcondition enforces explicit requested
  operation types, exact indicator subsets and protected “keep unchanged” indicators before any
  provider proposal can be persisted. It also supports selectable replacement of existing forecast
  jobs and preserves explicit model kind, variable set, forecast horizon and “no transformations”
  constraints; empty safe refusals remain allowed.
- `ArtifactAuthorPort`: production uses `DeepSeekChartAuthor` for chart wording and two
  pre-handoff author checks, with complete snapshot paging through an audited author-specific
  grant. Numerical plotting, table construction and typed selective regeneration remain controlled
  by reviewed specifications and deterministic renderers. The deterministic author is an injected
  offline-test fake, not an alternate production model.
- `ReportAuthorPort`: implemented DeepSeek `ReportAuthorRequestV1` → `ReportDraftV1` authoring and
  section-only revision. An `EvidenceClaimV1` ledger binds claims to approved dataset/result hashes;
  deterministic validation and rendering own the final Markdown. The deterministic author is an
  offline injected test double only.
- `OutputReviewPort`: production uses the Codex-local adapter alongside deterministic preflight
  against the guideline version, including checksum-bound PNG byte loading/pixel decoding,
  package-wide hash/guideline/unit/source consistency and atomic cosmetic patch groups. The adapter
  invokes the locally authenticated Codex runtime with direct PNGs, complete controlled data
  context, read-only ephemeral isolation and strict structured observations. It also performs a
  separate `ReportReviewRequestV1` semantic review and returns findings plus non-mutating,
  section-bound directives. Other API adapters and live quality/cost evaluation remain
  unimplemented. The standalone deterministic reviewer is an offline-test fake, not a production
  substitute for semantic or visual model approval.
- `DatasetAccessPort`: read actual immutable values through session/stage/hash-bound grants.
- `CapabilityRegistry` and `SkillRegistry`: list and resolve versioned descriptors/manifests.
- `CapabilityExecutor`: execute only available, registered handlers after authorization.
- `ArtifactRenderer`: deterministically render reviewed chart/table specifications.

Provider adapters may expose native function/tool calling, but provider tool names are mapped to
registry IDs. The provider never receives a general network, filesystem, Python, shell, Stata or
browser tool.

Plan proposals are persisted as proposal-authority graph nodes. The current implementation supports
multiple clarification rounds, field-level patch acceptance, explicit rejection and target-hash
checks after manual edits. Ordinary provider receipts record profile, model, prompt version,
schema, attempt, latency and failure code without copying prompts or observation rows. Agent's
separate administrative diagnostics additionally retain complete redacted final responses and
reconstructable request/context payloads; they must not be treated as public-safe ordinary logs.
DeepSeek credentials are required at
startup and there is no runtime fallback; deterministic reviewed fixtures remain the network-free
Phase 1E-2 test authority.

The Phase 1E-3 ports now use role-scoped DeepSeek adapters in production; deterministic adapters
remain injected network-free test fakes only. Each Data/Analysis request permits at most two total
provider attempts, including the first, then exposes Retry/manual typed controls without fallback.
Data and Analysis proposals have independent
target hashes and proposal-authority nodes, support selective Apply/reject and become unusable after
manual state changes. Applying a proposal calls existing typed services but never Data Next, Run or
an unavailable connector. Filter and aggregate value reads are registered operations on the same
grant; their trace receipts contain specifications and hashes, never returned values.
The deterministic Analysis adapter also avoids automatically growth-transforming series whose code
or metadata already identifies a growth/rate measure. Its proposal summary names the input snapshot,
proposed output step, exact target codes and unit interpretation.
Explicit model-replacement requests are compiled into typed model-removal plus model-addition items;
the existing pipeline target hash protects both sides of the change from stale application.

## Initial capability inventory

| Capability ID | Kind | Initial state | Notes |
|---|---|---|---|
| `geography.resolve` | function | available | Controlled registry only. |
| `aggregation.apply` | function | available | Registered methods and missing-data rules. |
| `connector.local_file` | connector | available | CSV/JSON/XLSX intake. |
| `connector.imf_data` | connector | available | Registered CPI and annual WEO slices only. |
| `connector.world_bank` | connector | available | Annual WDI/source 2 only. |
| `connector.oecd` | connector | available | Monthly CLI 4.1 `LI` only. |
| `connector.eurostat` | connector | available | Monthly all-items ECOICOP v2 HICP index only. |
| `connector.adb` | connector | available | Annual DF_NA 1.0 GDP/value-added only. |
| `connector.ecb` | connector | available | EXR 1.0 monthly euro reference-rate averages only. |
| `connector.bis` | connector | available | WS_CBPOL 1.0 monthly end-of-period policy rates only. |
| `connector.un_sdg` | connector | available | Current-release SDG 8.1.1 / NY_GDP_PCAP annual only. |
| `data.prepare` | function | available | Registered hygiene-operation dispatch. |
| `transformation.apply` | function | available | Typed analytical-operation dispatch, including reviewed unit/calendar/frequency harmonization and hash-linked lineage. |
| `model.descriptive/correlation/ols/adf/arima/sarimax/var` | model | available | Reviewed specifications only; time-series systems run per entity/frequency, SARIMAX future exogenous values must be approved data, and VAR shock ordering is explicit. |
| `code.generate` | function | available | Typed Python/Stata reproduction generation. |
| `artifact.chart.render` | renderer | available | Deterministic `publication-v1` SVG/XLSX rendering with accessible color and line-pattern encoding. |
| `artifact.table.render` | renderer | available | Workbook/table output. |
| `artifact.report.generate` | renderer | available | DeepSeek draft plus deterministic evidence validation/rendering. |
| `artifact.report.revise` | function | available | User-approved, section-bound report directive only. |
| `output.review.structural` | reviewer | available | Deterministic guideline and workbook checks. |
| `output.review.visual` | reviewer | available | Direct-render inspection; production model findings come from Codex-local. |
| `output.review.semantic_report` | reviewer | available | Codex-local evidence-bound report review. |
| `output.review.remote_visual` | reviewer | available | Production is locked to the locally authenticated Codex runtime and failures are explicit. |
| `artifact.regenerate` | function | available | Apply an approved typed artifact patch. |
| `manifest.freeze` | function | available | Final selected artifact manifest. |

The implemented registry, not this table, is authoritative. Discovery is available through
`/api/v1/registry/capabilities`, `/api/v1/registry/skills` and `/api/v1/admin/registry`.

Production Output review is fixed to `codex-local`, using the Codex/ChatGPT login rather than an API
key. The API publishes only safe provider/model/status fields. The deterministic reviewer is a
network-free test fake, not a selectable production fallback. Other providers stay handler-less until their adapter,
approval, disclosure authorization and live evaluation are complete.
Codex-local describes where the authenticated client runs, not offline model inference. Approved
artifact images and context may leave the computer for provider processing under the same
disclosure policy as other AI requests.

New reviews use the fixed `academic-publication-placeholder-v1` (Nature-inspired) rules and
severity policy. The typed subset and its hash accompany direct renders; review history and the
manifest retain the identity. `VISUAL-RUBRIC-PLACEHOLDER` records scope, while substantive failures
remain blocking. Codex produces observations, not executable patches or final human acceptance.
Final project creative direction and journal print certification remain deferred.
DeepSeek chart authoring uses the existing endpoint/key and `DEEPSEEK_MODEL`; two separate
snapshot-bound author checks precede every chart-bearing handoff, including regenerated artifacts.
The second inspects SVG structure, not pixels. Both must pass before Codex is invoked; failures
remain visible and do not consume formal review rounds. No self-check approves changes or Finish.
See ADR 0032 for the immutable source selection, bounded repair and audit contract.

A future approved remote profile would be a deployment-policy envelope over these task ports,
not a new autonomous agent. Each role would require its own adapter, disclosure authorization and
acceptance evidence. Profile selection cannot change capability availability or either mode's
human authorization policy. This future profile is not an alternative runtime selector today.
See `provider_profiles.md`.

## Output authoring and Review AI

Review targets the complete selected `ArtifactSet`. Deterministic checks cover underlying data,
workbook, chart/table, report, code and manifest consistency. Review AI receives package-level
metadata, summaries and limitations to assess completeness and cross-artifact consistency. Direct
PNG inputs support chart/table visual inspection; the Markdown report receives a separate semantic
review. This is not a claim that report-page rendering or final journal print certification exists.

Chart generation remains specification-driven and reproducible:

1. `ArtifactAuthorPort` proposes a typed `ChartSpec` using the actual underlying values through a
   read-only snapshot grant, plus result summaries, schema and guideline rules.
2. The registered renderer binds that spec to an approved dataset/result reference and produces
   SVG/XLSX plus a fixed-size PNG review render.
3. Deterministic preflight validates series values, titles, units, source note, number formats,
   dimensions, accessibility metadata and guideline rule IDs.
4. Two author checks must pass before formal review: the first inspects the data/specification,
   and the second inspects final SVG structure, not pixels. Failures are retained and do not spend
   a formal review round. `OutputReviewPort` with visual capability then receives the render,
   chart spec, preflight findings, result summary and relevant guideline subset. It returns
   `OutputReviewReport`.
5. A proposed correction is a typed `ChartSpecPatch`; it cannot edit pixels or execute code.
6. The user approves the patch before selected regeneration. The local loop is bounded to three
   review iterations; remote adapters must additionally enforce configured latency/cost limits
   before the human performs final publication approval.

`OutputReviewReport` contains review ID, provider/model, target artifact/hash, guideline version,
overall result (`pass`, `warning` or `fail`), rule-addressed findings, severity, affected artifact
IDs and optional typed patches. Review AI cannot freeze
artifacts or waive deterministic failures. It also records package-level findings such as a missing
requested deliverable, missing indicator chart coverage, an indicator-specific unit mismatch,
inconsistent source metadata, unsupported code coverage or limitations absent from the Research
Report.

The local `publication-v1` reviewer checks chart series and table columns against the complete
approved snapshot, requires explicit source labels and useful chart alternative text, and reads the
checksum-bound Research Report artifact itself. Report rules cover the typed report specification,
required sections, observation count, source note, causal-inference boundary, reproduction-manifest
binding, selected figure/table references and citation references.

Research Report authoring and revision follow an additional evidence boundary:

1. DeepSeek receives the current handoff, approved Plan/deliverables, snapshot grant, typed model
   results/diagnostics/forecasts and current artifact references. Both author and separate semantic
   reviewer receive owned, hash-bound `presentationEvidence`: bounded SVG/spec contents and
   verified CSV headers; workbook evidence explicitly covers file/spec identity, not every cell.
2. Dataset and model-result values enter provider context only through registered, bounded reads;
   trace stores grants, counts and hashes without ordinary-log value copies.
3. `ReportDraftV1` sections and every `EvidenceClaimV1` reference are validated before deterministic
   Markdown rendering.
4. Codex-local checks question/result coverage, numerical and directional consistency, forecast
   intervals/samples, causal wording, uncertainty, limitations and sources.
5. Only a user-approved `ReportRevisionDirectiveV1` can trigger a rewrite, and only named sections
   may change. Missing upstream evidence emits `requires_upstream_stage` instead; missing or
   corrupt presentation handoff is `presentation_handoff_incomplete`. Neither can be concealed
   by report wording or an ineffective Output Editor repair loop.
6. Chart, table and report review share three rounds; selected reports need semantic `pass` before
   the user can Finish.

Visual review uses the generated artifact itself, never a screenshot of the web application. A
remote vision provider may receive a rendered analytical artifact only under an approved provider
profile and explicit session authorization because plotted labels and values leave the local
runtime. Without that authorization the remote review fails closed. Structural or human
inspection remains useful but cannot satisfy the formal Review AI approval required by Finish.

## Stage context limits

- Plan: request, answers, current Plan, registry metadata, ranked source knowledge and complete
  relevant attachment values.
- Data: Plan, provenance, diagnostics and complete active-snapshot values.
- Transformation: complete approved input/relevant output values, diagnostics and typed catalogs.
- Output authoring: underlying values, artifact specs, results, diagnostics, citations and rules.
- Visual review: approved render, underlying values, spec, metadata and deterministic findings.

Actual values are exposed only through `DatasetAccessPort`/`WorkflowModelDataAccessService`: a
read-only grant bound to session, stage, source reference and immutable content hash. The first page
is bounded, but the contract permits paging over the full relevant dataset; typed filter/aggregate
operations use the same grant rather than arbitrary SQL.
Remote disclosure is checked by provider profile and classification; licensed data is denied unless
explicitly allowed. Access receipts record ranges, filters, counts and page hashes without copying
the values into trace. No AI port receives credentials, arbitrary file paths, hidden reasoning,
generic SQL/network/code execution or unrestricted tools. Data content is untrusted and cannot
issue instructions to the model or runtime.
