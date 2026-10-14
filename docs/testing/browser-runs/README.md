# Browser-driven acceptance run log

Updated: 2026-10-14

Status: logging and completion contract for realistic browser-driven research tests. The Workflow
steps below use explicit stage approvals; Agent runs use their recorded authorization envelope
for autonomous execution and still require review plus user-only final freeze.

Historical revision, issue, session and hash labels in these summaries identify original test
evidence; they are not links to issues or Git objects in this public repository. Full runtime
records, private diagnostics and development-host paths are not distributed. Historical successes,
failures and partial results are preserved, not new acceptance of the public release.

This directory records concise evidence from interactive browser tests. These runs imitate a real
user through the public UI and API. They complement deterministic CI; they do not replace component,
contract, numerical or state-graph tests.

## End-to-end completion rule

A browser run may be recorded as `PASS` only when it completes all of the following through normal
product controls:

1. Start from a user research question and complete any required clarification and Plan revision.
2. Approve the Plan, acquire data through registered connectors or an intentional local-file path,
   review/prepare the data, configure Transformation and run the pipeline.
3. Generate the requested Output artifacts and run the configured Review AI against the direct,
   checksum-bound artifacts and underlying data—not browser screenshots.
4. Resolve every Review AI `fail` through the supported review/revision flow and rerun review until
   the current selected Research Report receives semantic `pass`. Deterministic preflight must have
   no blocking findings for selected artifacts. Advisory warnings may remain only when product
   policy explicitly permits final human acknowledgment. The existing maximum review-loop count
   remains enforced.
5. Finish and freeze the exact reviewed ArtifactSet, obtain its reproduction manifest, reload the
   session and confirm the completed state and frozen artifacts remain available.

Reaching Output, generating files or merely starting Review AI is not an end-to-end pass. A run is
`BLOCKED` when a required external capability or product decision is unavailable, `FAIL` when an
implemented path behaves incorrectly, and `PARTIAL` when the run intentionally tests only a bounded
slice. An unavailable Review AI, an unresolved blocking finding or a missing final manifest cannot
be labeled `PASS`. New runs use `academic-publication-placeholder-v1`: all substantive visual
findings must be resolved within at most three rounds. Only the `VISUAL-RUBRIC-PLACEHOLDER` scope
advisory may remain for explicit acknowledgment; it does not replace semantic report approval.
The former `VISUAL-RUBRIC-MISSING` allowance applies only to historical runs before 2026-09-28.

The browser operator may discover a defect but must not mutate the database, artifact files or
backend state to force progress. Fixes are implemented and tested separately, then the browser run
is restarted or resumed through the UI.

## What each log records

Create one Markdown file per research journey from `TEMPLATE.md`. Keep it brief but include:

- date, application commit and run status;
- research question, session ID and intended single-/multi-provider coverage;
- provider/model profile used by Plan AI and Review AI, without credentials;
- major human/AI interactions, including rejected proposals, manual data changes, pipeline edits,
  upstream returns and cross-day resume when they are part of the scenario;
- acquired providers/datasets, row counts and snapshot hashes without copying raw research values;
- each Output review iteration, finding disposition and resulting artifact-set hash;
- final review status, frozen manifest identity and post-reload result;
- observed defects and links to GitHub issues or fixing commits.

Do not include API keys, tokens, full model prompts/responses, licensed values or large console/API
dumps. Use UTC timestamps where exact ordering matters.

## Run index

The chart-only repair and real-model delivery tests on 2026-09-28 are documented separately in
`../chart-delivery-2026-09-28.md`: those use isolated synthetic-data API fixtures, not browser E2E,
and do not change the historical results below.

| Date | Scenario | Scope | Result | Notes |
|---|---|---|---|---|
| 2026-10-07 | Agent fixed-version 863c07e cohort | Single-source ×3 / multi-source ×3 | `FAIL` strict gate | `2026-10-07-agent-fixed-version-acceptance.md`; 5 complete, 1 retained report-handoff/Editor failure; all six numerical replays and diagnostic bundles pass. |
| 2026-09-28 | India unemployment and the academic visual placeholder | Single-provider full-journey attempt | `FAIL` | `2026-09-28-india-wdi-visual-placeholder.md`; 3/3 reached; unit-label revision empties chart, with upstream/report/code defects remaining. |
| 2026-09-28 | Brazil debt/growth with IMF WEO and WDI | Multi-provider full-journey attempt | `FAIL` | `2026-09-28-brazil-multi-visual-placeholder.md`; charts clear on round 1, but report/required code and upstream revision fail. No Finish/manifest. |
| 2026-09-13 | Issue #25 Report Author recovery and governed finish | Full single-provider journey | `PASS` | `2026-09-13-issue-25-report-generation-recovery.md`; exercised real DeepSeek failure/retry, bounded DeepSeek revisions, Codex-local semantic pass, Finish, manifest and reload. |
| 2026-09-13 | China WDI Report Author regression rerun | Full single-provider journey | `FAIL` | `2026-09-13-china-wdi-report-author-rerun.md`; Plan/Data/Transformation contracts passed, but DeepSeek Report Author failed after repair before Codex-local review. |
| 2026-09-13 | China WDI rebalancing and share forecast | Full single-provider journey | `FAIL` | `2026-09-13-china-wdi-rebalancing-e2e.md`; earlier baseline stopped after three deterministic review iterations. |
| 2026-09-12 | Issue #17 explicit analysis revision | Output→Transformation slice | `PARTIAL` | `2026-09-12-issue-17-analysis-revision.md`; browser verified the read-only gate and impact dialog, while API/component tests cover persistence and graph invalidation. |
| 2026-09-12 | Issue #15 forecast-contract regression | Transformation slice | `PARTIAL` | `2026-09-12-issue-15-forecast-contract.md`; UI and executable contract verified, not a new full journey. |
| 2026-09-12 | India Output review gate regression | Output-only | `PARTIAL` | `2026-09-12-india-output-review-gate.md`; review became runnable, but the wide-table finding remained unresolved. |
