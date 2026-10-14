# Phase 2 acceptance report

Date: 2026-09-07

Scope: Workflow Mode through the end of Phase 2, using the closest currently executable local
version of `LRS-001`. This is an execution record, not a replacement for the normative scenario in
`longitudinal_acceptance_scenario.md`.

## Verdict

**Local deterministic Phase 2: PASS.** The supported local workflow, Phase 2 statistical models,
publication outputs, durable state and portable continuation meet their documented exit criteria.

**Complete longitudinal `T4`: NOT YET ACCEPTED.** Manual Excel/visual UAT (`T2`), opt-in live model
and connector evaluation (`T3`) and the connector-backed acquisition portion of `LRS-001` have not
run. No model/provider/API configuration is present, so this report makes no claim about remote
planning quality, remote multimodal review, latency, cost or external-source reliability.

## Near-real journey executed

The integrated acceptance test starts through the normal product API with the `LRS-001` research
question rather than injecting a finished session. It uploads a quarterly CSV containing 193 rows
across the United States, Japan and Germany, CPI and policy-rate series from 2018Q1 through 2025Q4,
one missing value and one prompt-like cell that must remain inert data.

The user journey then:

1. answers clarification questions, requests a Plan proposal, accepts only one proposed field,
   confirms geography and approves the Plan;
2. lets Data AI inspect actual snapshot values, selectively applies typed cleaning, verifies the
   missing row was removed, exports XLSX, rejects a formula-bearing reimport, maps a renamed period
   column, validates and commits the corrected workbook;
3. requests and applies an Analysis AI proposal, executes the typed pipeline and verifies CSV,
   XLSX, SVG, Python and Research Report artifacts;
4. verifies that Finish is blocked before review, runs Output Review, applies a typed chart-title
   revision, verifies that the comparison is presentation-only and that analytical values did not
   change, then completes the final human gate;
5. restarts the application, verifies frozen hashes and monotonic trace sequence, checks all three
   graph checkpoints, imports a checksum-verified archive and forks a new working child while the
   completed source remains unchanged.

The integrated journey is implemented in `backend/tests/test_phase2_acceptance.py`. Specialized
tests separately cover Phase 2 ADF, ARIMA/SARIMAX and VAR/IRF behavior, reviewed conversion and
frequency semantics, workbook linting, Output review and portable archives.

## Contract and component alignment

| Area | Result | Evidence |
|---|---|---|
| Plan and human/AI revision | Pass | Repeated clarification, hash-bound proposal, selective field acceptance and explicit Plan gate use the documented command contracts. |
| Data and human cleaning | Pass | AI reads actual values through grants; typed cleaning and controlled XLSX reject formulas and require explicit remapping/validation. |
| Transformation and models | Pass | Registered operations and model jobs execute from approved snapshot refs with hashes, lineage, diagnostics and independent failure handling. |
| Output and Review AI | Pass locally | Publication specs, workbook lint, render inspection, typed revisions, comparison and exact reviewed-set Finish gate are implemented. Remote multimodal judgment remains unavailable. |
| State graph and recovery | Pass | Durable graph checkpoints, stale/hash preconditions, restart trace continuity, immutable completion, verified import and lineage-linked fork are exercised. |
| Frontend/service contract | Pass | HTTP remains authoritative; mock fixtures now obey the same review-before-Finish invariant. Completed UI exposes review evidence and continuation without a contradictory Finish prompt. |
| Responsive/accessibility structure | Pass for automated scope | Desktop DOM has named controls and one main heading structure; prior 375 px checks found no page-level horizontal overflow. Component tests cover the completed-state semantics. Human aesthetic approval remains `T2`. |
| Documentation | Pass after correction | README, current status, implementation plan and longitudinal test plan now distinguish the accepted local scope from deferred `T2`/`T3`/`T4` work. |

## Defects found and corrected

1. A realistic long research question was reused as a publication title and could exceed typed
   title limits, causing Output generation to return an internal error. Publication titles are now
   normalized and word-bounded to the active chart/table/report guideline; the full research scope
   remains preserved in the report.
2. The completed frontend seed skipped Output Review, while old completed mock state displayed both
   “not run” and “frozen”. The seed and immutable-state helper now review before Finish, the mock
   storage version was advanced, and completed export controls no longer show a Finish prerequisite
   or Finish action.
3. `current_status.md` still described Output revision and post-Finish continuation as future work.
   Those statements now match the implemented HTTP revision and fork contracts.

## Automated evidence

- Near-real and specialized Phase 2 backend slice: 35 passed.
- Full backend suite: 113 passed.
- Full frontend suite: 66 passed.
- Python lint, static typing, dependency consistency, frontend lint and production build: passed.
- Browser DOM check: completed seed shows a passing review, no Finish action and an available
  “Continue in a new session” action. A new external browser-runner session could not be created
  because of local tool quota, so no additional browser-runner claim is included.

## Deferred acceptance gates

- `T2`: a person must inspect Excel round-trip ergonomics, native workbook/chart appearance and
  final visual quality in the app and Excel.
- `T3`: configure an explicitly approved planning provider, remote multimodal reviewer and relevant
  connector credentials; record model/provider versions, authorization, latency, cost and rubric
  results.
- Connector-backed `LRS-DATA-02` through `LRS-DATA-04`: at the time of this Phase 2 decision, IMF
  remained planned and Phase 3 public connectors were not part of the accepted local path.
- `T4`: run the complete multi-day scenario only after the preceding gates and the open decisions
  in `longitudinal_acceptance_scenario.md` are resolved.

## Acceptance decision

Phase 2 may be marked complete for its implemented local deterministic product boundary. At the
time of this decision, the next development phase could begin without reopening Phase 2, while
release-level claims still needed to say that real external acquisition, live-model quality and
human visual/Excel acceptance were pending. The dated update below narrows only the external IMF
acquisition portion of that statement.

## Post-acceptance Phase 3 update — 2026-09-10

This section records later progress without rewriting the evidence or pass decision above. The
Phase 3 P0/P1 has since completed for its admitted slices. Registered public IMF CPI/annual WEO,
World Bank WDI, OECD CLI, Eurostat HICP, ADB DF_NA, ECB EXR, BIS WS_CBPOL and UN SDG 8.1.1
acquisition pass bounded live smoke tests. Reuse tests demonstrate independent session-owned raw
evidence and normalized provenance; each provider also passes its own pagination, DSD/rate-limit,
JSON-stat/crosswalk/update, conditional-response, availability or release/disaggregation gate.

Accordingly, the admitted Phase 3 connector subsets of the earlier connector-backed `T3` deferral
are now complete.
The remaining `T3` live-model evaluation is now governed by the deferred, task-specific
`approved_remote` gates in `provider_profiles.md`; the existing generic OpenAI adapter and
bounded DeepSeek run do not satisfy them. Human `T2`, complete multi-day `T4` and additional
provider dataset admissions remain open. The planned Phase 3 P1 connector slices were completed on
2026-09-10, but this does not retroactively add them to the original Phase 2 acceptance result.
