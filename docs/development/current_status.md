# Current implementation status

Updated: 2026-10-14. Scope: the public development implementation, not an organization-specific
deployment. Historical acceptance records keep their original dates, revision labels and outcomes;
editing this summary is not a new live acceptance run.

## Release boundary

Version 0.1.0 is local, single-user, experimental research software. The application has no HTTP
user authentication, including for administrative trace and diagnostic routes. Bind backend and
frontend to loopback; CORS and command actor fields are not authentication. Public hosting and
multi-user deployment require separate security work. See [SECURITY.md](../../SECURITY.md).

Workflow's four-stage implementation and its admitted connector baseline have historical
acceptance. Agent's autonomous implementation exists, but strict A6 reliability acceptance is
open. The most recent fixed-build cohort delivered five of six original runs: single-source 2/3,
multi-source 3/3. A failed report-evidence handoff was retained as a failure, without freeze or
budget bypass. Subsequent fixes do not retroactively change that result.

## Implemented capabilities

| Area | Current implementation |
| --- | --- |
| Workflow control | Durable typed state graph; Plan, Data, Transformation and Output; explicit Plan/Run/Finish gates; data review; immutable versions; invalidation, retries and recovery. |
| Planning | DeepSeek clarification, drafts and selective patches; manual answers; frequency-valid periods; structured variable roles and forecast horizons; bounded source discovery. |
| Stage assistance | Separate DeepSeek Data Steward and Analyst; actual snapshot values through bounded grants; typed proposals, never implicit Workflow execution. |
| Handoff | Immutable decision envelopes, confirmed/inferred/unresolved status, four stage-local conversations and compatibility projections; explicit confirmation for uncertain legacy decisions. |
| Acquisition | Local CSV/JSON/XLSX and the eight providers' admitted slices; independent multi-source snapshots, provenance, bounded retries and reusable public response evidence. |
| Data | Immutable normalized Parquet, pagination, mapping, filtering/reshaping, reversible preparation and validated XLSX cleaning round trip. |
| Analysis | Reviewed transformation chains; descriptive/correlation/OLS-HAC/ADF/ARIMA/SARIMAX/VAR; explicit windows; supported forecasts and IRFs; typed results and hashes. |
| Reproduction | Controlled Python generation and supported Stata specifications. Stata does not implement all model/operation families. |
| Output | CSV/SVG/XLSX, internal PNG review renders, versioned specifications, Markdown Research Reports, claim/evidence references, selected-artifact review and frozen manifests. Charts currently use the registered line-chart specification. |
| Review | Two DeepSeek checks before chart-bearing Workflow handoffs and every Agent delivery review; independent Codex-local semantic/direct-render review; at most three shared formal rounds; scoped report/presentation revision and upstream repair stops. |
| Continuation | Checksum-verified Workflow archives/import under new identity; frozen originals; linked child sessions for continued research. |
| Agent | Separate SQLite graph/files/grants, authorization envelopes, durable budgets, leases/checkpoints, intervention, recovery, real HTTP/SSE frontend and user-only final freeze. |
| Diagnostics | Agent full redacted final outputs and repairs, owned payload references, integrity checks, attempt comparison, diagnostic export and network-free numerical replay. |

The [source catalog](../data_sources/source_catalog.md) lists exact executable dataset contracts.
Discovery beyond those contracts is not acquisition permission. The packaged lightweight index
contains identities from eight September 2026 provider snapshots: 10,832 datasets and 50,758
indicator concepts, with provider-local deduplicated indicator sets. It does not include the full
dimension database or observations. Description prose/contact details are excluded from the public
projection; current metadata and coverage are checked at acquisition, not inferred from a snapshot.

## Runtime providers and data disclosure

Public development composition uses DeepSeek for Plan, Data, Analysis, chart/report authoring,
author checks and Agent research roles. Codex-local is the formal visual/semantic reviewer.
Production failures do not select a deterministic fallback. Test fakes remain offline fixtures;
`MRA_ENVIRONMENT=test` is an automated-test mode, not a supported real-research setup.

Codex-local invokes an authenticated local runtime; it is not an offline-model guarantee.
Actual public/user data values may be disclosed by default through read-only snapshot-bound grants.
Licensed values default to denied. Local retention, redaction and grants are not substitutes for
the operator's authority to disclose data to a provider. Detailed contracts are in
[provider profiles](provider_profiles.md) and [trace and reproducibility](trace_and_reproducibility.md).

## Recent behavior corrections

- Report Author and the separate semantic Reviewer receive current, owned, hash-bound
  presentation evidence. SVG/specification and verified CSV headers are inspectable; workbook
  file/spec receipts do not prove inspection of every cell or final visual quality.
- Missing, corrupt, foreign or over-budget evidence fails as `presentation_handoff_incomplete`
  before AI author/revision calls. `repair_evidence` prevents Resume, scope answers, retries and
  re-review from disguising an upstream prerequisite as a prose-edit problem.
- Provider credit/authentication/rate/timeout/service/contract failures have distinct recovery
  actions. Explicit retry preserves consumed and unknown/reserved usage, task attempts and all
  hard phase/candidate/review limits.
- Statistical cleaning retains a raw baseline and protected validation windows; limited
  complete-case selection, internal single-gap interpolation and fixed winsorization are separate
  policies, not unconstrained model decisions.
- Public source-index projection retains only discovery identities/provenance and reuse links;
  long source descriptions are omitted from both SQLite rows and full-text search.

## Acceptance evidence

| Evidence | Meaning and limit |
| --- | --- |
| [Phase 0–3 baseline](phase0_to_phase3_acceptance_report.md) | Historical local Workflow/admitted-slice acceptance on 2026-09-11; not every later AI change or an Agent pass. |
| [Plan AI acceptance](plan_ai_acceptance_report.md) | Bounded synthetic-data/provider integration; not general research-quality certification. |
| [Source catalog acceptance](source_index_catalog_acceptance_report.md) | Reconciled historical metadata snapshots; not a claim of live completeness today. |
| [Fixed Agent cohort](../testing/browser-runs/2026-10-07-agent-fixed-version-acceptance.md) | Five completed and one failed; numerical replay/diagnostics passed for all six; strict A6 gate remains open. |
| [Agent milestones](agent_implementation_plan.md) | Implementation is separate from real-provider acceptance; earlier failures/linked recovery are not relabeled as a clean cohort. |
| [Release alignment](public_release_review.md) | Current code/document checks, public-copy minimization and offline regression scope; not new live research acceptance. |

Routine CI is network-free. Optional real-model tests and browser journeys require explicit
authorization and independent retained results. A browser E2E passes only after review of the
current artifact set, user Finish/freeze, manifest verification and successful reload. The active
academic publication placeholder blocks substantive defects but is not a final journal rubric.

## Remaining work

1. Separate distinct Output candidate versions from unsuccessful correction attempts in history.
2. Harden multi-session initialization/SSE and test cancellation/load behavior.
3. Run a new unchanged-build cohort: single-source ×3 and multi-source ×3, including two author
   checks, real review approval, human freeze, reload, diagnostics and offline replay for every run.
4. Complete Source Index refresh/drift fixtures and v1 API retirement/parity/rollback acceptance.
5. Complete manual Excel/visual UAT and the full multi-day longitudinal scenario. Individual
   successful journeys do not satisfy every longitudinal requirement.
6. Define final visual/icon standards; add further datasets or methods only through separate
   admission, implementation and acceptance.
7. Design authentication, network isolation and deployment hardening before any hosted/multi-user
   release. New provider profiles remain separately gated; deferred Phase 4 is not accepted.

See the [implementation plan](implementation_plan.md), [Agent plan](agent_implementation_plan.md)
and [longitudinal scenario](longitudinal_acceptance_scenario.md) for ordered development and exits.
