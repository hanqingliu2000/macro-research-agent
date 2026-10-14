# Phase 3 P0/P1 acceptance report

Date: 2026-09-10

## Decision

Phase 3 passes for the explicitly admitted P0/P1 dataset slices. This is not approval for arbitrary
provider URLs, whole catalogs, undocumented series, regional aggregates or additional dataflows.
Every new slice still requires the admission checklist and its own provider-specific contract.

## Accepted scope

- reusable typed connector, checksum cache, session evidence and Plan knowledge foundation;
- IMF CPI and annual WEO, including live-verified China general-government gross-debt indicators
  `GGXWDG` and `GGXWDG_NGDP` added to planning knowledge on 2026-09-11;
- World Bank annual WDI/source 2;
- OECD CLI 4.1 monthly `LI`;
- Eurostat monthly all-items HICP `TOTAL`, `I25`;
- ADB DF_NA 1.0 annual GDP/value-added;
- ECB EXR 1.0 monthly euro reference-rate averages;
- BIS WS_CBPOL 1.0 monthly end-of-period policy rates;
- UN SDG 8.1.1 / `NY_GDP_PCAP` annual observations from the resolved current release.

## Provider-specific evidence added in the final slice

- ECB: exact `M.CURRENCY.EUR.SP00.A` scope, explicit quote direction, production values only,
  returned-dimension checks and checksum-verified Last-Modified/ETag revalidation where 304 means
  unchanged data rather than an empty result.
- BIS: exact v2 flow and dimension contract, preflight availability constraint tied to WS_CBPOL
  1.0, bounded keys/rate budget, source/compilation preservation and non-endorsement attribution.
- UN SDG: current series metadata and release identifier, reviewed M49 crosswalk, complete bounded
  paging, composite raw manifest and distinct keys for every preserved reporting/disaggregation and
  attribute combination.

Bounded live reads passed on 2026-09-10 for ECB USD/EUR January–February 2025, BIS United States
policy rates January–February 2025 and UN SDG China 2022–2023. The UN endpoint reported current
release `2026.Q2.G.02`; the requested interval contained one available China observation (2022),
which was preserved without fabricating 2023.

## Automated acceptance

- Backend: Ruff passed; mypy passed for 84 source files; 206 tests passed.
- Frontend: 73 tests passed; ESLint passed; production TypeScript/Vite build passed.
- Contract coverage includes typed-query refusal, schema/scope/version drift, duplicates, media and
  response bounds in the connector suite; final-slice tests additionally cover ECB conditional
  reuse, BIS availability and UN release/pagination/disaggregation behavior.
- Capability, Plan semantic, knowledge-index, contract-route and Plan-source-to-session-snapshot
  tests confirm that the three final providers are available only through reviewed contracts.

## Remaining work outside Phase 3 acceptance

- manual cross-day `T2`/full `T4` product acceptance;
- deferred additional remote provider profile governance, packaging, live Plan evaluation and longitudinal
  gates `W0`–`W4`/`W6`; the generic OpenAI adapter and bounded DeepSeek run are not acceptance;
- separate `W5` acceptance for each additional-profile Data/Analysis or remote multimodal
  Output task, including its disclosure and privacy authorization;
- Agent persistence and runtime APIs (historical deferral; implemented later in A1–A6, whose strict
  repeat-cohort acceptance remains open);
- any additional dataset/dataflow admission.

Additional dataset admissions and licensed Bloomberg/Haver work remain separate backlog, not
Phase 4 deliverables. The Agent entry records its status at this report's historical date.

## Cross-phase revalidation — 2026-09-11

The Phase 0–3 baseline was revalidated after Phase 4 was explicitly deferred and rescoped. After
the Issue #1–#3 follow-up, all 208 backend tests, 77 frontend tests, lint, strict typing, dependency
checks and the production build
passed. Running HTTP/UI checks passed under the deterministic profile, and one bounded live query
passed for every registered public connector slice. No Phase 4 capability was configured or counted.

See `phase0_to_phase3_acceptance_report.md` for the complete evidence and preserved exclusions.
