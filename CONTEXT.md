# Project context

Aligned with the public development implementation on 2026-10-14. See
[current status](docs/development/current_status.md) for acceptance and limitations.

## Goal

Build a local macroeconomic research agent that collaborates with an economist. It clarifies a request, proposes an explicit plan, collects data through controlled functions, cleans and models the data, produces governed charts/tables, and exports a complete reproducibility package.

## Confirmed decisions

- Independent public source distribution named macro-research-agent, with no open-source license
  grant. It is not affiliated with or endorsed by its data providers.
- Localhost web application using FastAPI and React.
- Local single-user deployment in the first release.
- Raw files remain in session-owned local storage, while approved AI providers may read actual
  values through read-only, stage/session/checksum-bound grants under ADR 0014. Licensed remote
  disclosure fails closed; credentials and arbitrary filesystem/query access never reach the model.
- Executable data sources include local CSV/JSON/XLSX and explicitly admitted dataset slices from
  IMF Data, World Bank, OECD, Eurostat, ECB, BIS, UN SDG and ADB. Wider discovery is not permission
  to execute an unregistered connector or dataset.
- Active data-source scope is limited to P0 and P1. P0 is local files plus IMF Data; P1 is World Bank, OECD, Eurostat, ECB, BIS, UN SDG and ADB.
- Experimental Agent Mode runs beside Workflow Mode with separate sessions, state, routes and
  persistence. The modes share only stateless research capabilities.
- Public and licensed sources are added through the same connector protocol.
- Reviewed typed specifications generate Python reproduction code and supported Stata do-files
  for external use. Stata does not cover all registered model/operation families.
- Excel is a supported publication format; immutable snapshots, typed results and state graphs,
  not an editable workbook, remain the authoritative research record.
- Canonical country/entity identity starts with IMF codes, with explicit crosswalk versions.
- Workflow uses four routed stages—Plan (including clarification), Data, Transformation and
  Output—and three human approval gates.
- Reached stages may be reviewed freely; confirmed upstream changes preserve old results as stale
  snapshots and never trigger an automatic rerun.
- Full user-auditable trace is required.
- The application has no HTTP authentication, including diagnostics. Keep it loopback-only and
  single-user; local adapter execution does not imply offline AI inference.
- Agent authorization permits bounded autonomous execution, not unrestricted scope or final
  freeze. Its strict fixed-version acceptance remains open at five of six completed journeys.
- Dataset acquisition cannot use web search or browsers.
- Web search remains available for non-acquisition research when approved and cited.
- Automated testing cannot use model-driven browser screenshots.

## Open inputs from product owner

- Final creative/icon standards and any target-journal print requirements; the active academic
  placeholder already governs substantive chart-review findings.
- Additional approved Excel templates beyond the registered research-workbook-v1 contract.
- Explicit policies and task acceptance before enabling any additional remote provider profile.
- Separate prioritization and entitlement design before licensed connector development.
- Explicit admission and tests for datasets beyond the current registered slices.

## Runtime provider strategy

Real research uses DeepSeek planning, stage assistance, authoring and author checks, with
Codex-local formal semantic/visual review. Role-specific model overrides are server configuration;
there is no production deterministic fallback or arbitrary provider selector. Offline mocks are
fixtures, not research completion evidence. Workflow's frontend must select its HTTP adapter for
real sessions. Each provider call retains safe attribution, grants and bounded failure evidence.

A bounded synthetic-data Plan integration passed historically. Broader quality/cost,
cross-day/manual and Agent fixed-cohort acceptance remain separately tracked; offline regression
does not close them. A future provider distribution must omit policy-disallowed components and
pass task-specific disclosure, contract, usage and revocation gates.

## Non-goals for the foundation release

- Fully autonomous research without review.
- General internet scraping for datasets.
- Remote multi-user collaboration or cloud data storage.
- Executing arbitrary model-authored code.
- Replacing licensed data agreements.
