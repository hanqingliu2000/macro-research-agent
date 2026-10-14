# Phase 0–3 overall acceptance report

Date: 2026-09-11

Application tree tested: the Phase 0–3 baseline plus Issues #1–#3 changes in the Git commit that
contains this report.

## Decision and boundary

**Phase 0 through Phase 3 accepted for the documented local, review-gated Workflow baseline and
the explicitly registered public-data slices.** No blocking defect was found in this run.

Phase 4 is deliberately excluded, not failed and not implicitly accepted. This report makes no
claim about a separately approved remote provider profile, its distribution, live-model quality, remote
multimodal Output review or gates `W0`–`W6`. The existing generic OpenAI adapter and the earlier
bounded DeepSeek development run do not change that boundary.

This is also not the final human `T2` or full cross-day `T4` sign-off. Native Excel ergonomics and
final visual judgment still require a person; Agent persistence, additional dataset admission and
licensed Bloomberg/Haver integrations remained outside that historical acceptance. Agent
persistence/APIs were later implemented independently; current A6 acceptance is still open.

## Near-real workflow coverage

The full backend suite includes the `LRS-001`-derived Phase 2 journey rather than only isolated unit
tests. It starts with a research request and uploaded dirty macro data, then exercises:

1. repeated clarification, a typed Plan proposal, selective application, geography confirmation
   and the Plan human gate;
2. full approved-value access, Data assistance, reversible cleaning, XLSX export/reimport,
   formula rejection, remapping, validation and the Data gate;
3. typed transformations and statistical model jobs, numerical execution and the Run gate;
4. CSV/XLSX/SVG/code/report generation, review-before-Finish enforcement, a selective Output
   revision and the Finish gate;
5. application restart, trace continuity, frozen checksums, archive import and continuation in a
   new session without mutating the completed source.

Specialized tests additionally cover graph invariants, concurrent idempotency, stale proposals,
provider failures, complete model-data paging, output comparison, session deletion/restoration and
all registered connector drift/refusal contracts.

## Automated and running-service evidence

| Check | Result |
|---|---|
| Backend tests | 208 passed |
| Python lint | passed |
| Python strict typing | passed for 84 source files |
| Python dependency consistency | passed; no broken requirements |
| Frontend tests | 77 passed in 14 files |
| Frontend lint | passed |
| Production TypeScript/Vite build | passed; 122 modules transformed |
| Direct API health | HTTP 200, version `0.1.0`, development environment |
| Frontend-to-API proxy health | HTTP 200 |
| Capability projection | deterministic LLM; nine executable connectors including local file; no planned connector/model incorrectly advertised as executable; remote Output review unconfigured |
| Data-source knowledge | schema `data-source-knowledge-v1`, catalog `1.2.0`, checksum present; inflation and government-debt requests rank relevant executable slices first |

The running-service checks used the normal FastAPI application and the frontend HTTP adapter. They
did not enable an external LLM, disclose Session values to a model or mutate an existing Session.

## Public-connector live smoke evidence

Each registered public connector executed one bounded read against its official provider on
2026-09-11. The test retained raw responses only in a temporary acceptance directory outside the
project and recorded no observation values in this report.

| Connector and admitted slice | Query period | Normalized rows | Result |
|---|---:|---:|---|
| IMF Data CPI, China all items, monthly | 2025-01–2025-02 | 2 | pass |
| World Bank WDI population, China, annual | 2023–2024 | 2 | pass |
| OECD CLI 4.1 leading indicator, United Kingdom, monthly | 2024-01–2024-03 | 3 | pass |
| Eurostat all-items HICP, Germany, monthly | 2024-01–2024-03 | 3 | pass |
| ADB DF_NA 1.0 GDP, Philippines, annual | 2023–2024 | 2 | pass |
| ECB EXR 1.0 USD per EUR monthly average | 2025-01–2025-02 | 2 | pass |
| BIS WS_CBPOL 1.0 policy rate, United States, monthly | 2025-01–2025-02 | 2 | pass |
| UN SDG 8.1.1 real GDP per-capita growth, China, annual | 2021–2022 | 1 | pass |

The UN provider returned only a 2021 observation for the requested interval. The connector
preserved the missing 2022 period rather than fabricating a value, which is the expected behavior.

## Interface and mode-isolation evidence

DOM-only checks were run against the live frontend; no browser screenshots or model visual
comparison were used.

- Workflow Home and Agent Home each expose one named main heading, a skip link, named navigation,
  labeled inputs and semantic session/run regions.
- The Plan route exposes independently named `Current Plan` and `Plan conversation` regions with
  native form controls and disabled-state enforcement.
- At a 375-pixel viewport, Workflow Home, the Plan route and Agent Home each had document
  `scrollWidth` equal to the viewport width; no root horizontal overflow was present.
- Existing component tests verify the Plan drafting busy state/status announcement, pending command
  disabling, focus/accessibility structure and the 1440/1920/2560/3840 layout contracts.
- Workflow and Agent routes retained separate providers, storage and domain state.

Human assessment of native Excel and final artifact aesthetics remains `T2`; this structural check
does not replace it.

## Contract and documentation alignment

- Runtime capability IDs match the capability registry, connector catalog and Plan knowledge
  catalog for the admitted Phase 3 slices.
- Public acquisition remains limited to typed connector queries. Arbitrary URLs, scraping and
  model-authored downloads remain unavailable.
- AI output remains proposal/review only and cannot cross Plan, Run or Finish gates.
- At the time of this report, a generic development adapter was distinct from Phase 4 acceptance.
  Current runtime provider selection is locked to DeepSeek for research/author roles and
  Codex-local for formal review; `LLM_PROVIDER=openai` is not a supported runtime selector.
- README, current status, implementation plan, longitudinal scenario and Phase 3 report all point
  to this acceptance result while preserving the deferred/manual boundaries above.

## Acceptance conclusion

Phase 0–3 may be used as the current accepted development baseline. Development can continue on
separately prioritized post-Phase-3 work without reopening this baseline, provided a change that
touches the graph, connector, data-access, provider, output or approval contracts reruns its
affected tests.

Phase 4 remains skipped until an explicit resume decision and the governance inputs required by
`provider_profiles.md` are available.

## Issue follow-up — 2026-09-11

GitHub Issues #1–#3 were reproduced and corrected after the baseline run:

- the no-Plan clarification state now retains the same left Plan/right conversation geometry as
  the populated Plan state on desktop, while preserving the existing narrow-screen stack;
- Plan blockers and cautions now share one `Plan readiness` notice with distinct subsections and a
  single accessible announcement;
- source-knowledge catalog `1.2.0` adds WEO government-finance/debt concepts and live-verified
  China `GGXWDG`/`GGXWDG_NGDP` seeds. Connector `2.1.0` supplies their reviewed labels and units
  when the IMF observation response omits unit text.

The post-fix full suite produced the counts recorded above. Bounded IMF metadata and observation
queries returned both debt series for China throughout 2016–2025 without modifying the user's
existing Session.
