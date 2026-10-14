# Agent autonomous browser acceptance — 2026-10-06

Status: partial live acceptance; complete repeat-cohort acceptance remains open.
Baseline 70fd7a7; milestone commits 3035a7e, 7ea0e1c, d481738, 78efba0,
7fddbe2, 04e1bad and 6e862c1, followed by acceptance-driven fixes.
Real HTTP frontend, real DeepSeek roles and Codex-local reviewer. No direct database/artifact
edits are used to force a research session forward. All interactions use normal browser controls;
diagnostics are read-only.

## Fixed scenarios

Single provider: unclear concern about China's post-COVID labour-market recovery for women versus
men. World Bank female/male unemployment, annual 2010–2024, baseline 2010–2019, disruption
2020–2021, recovery 2022–2024. Descriptive phase statistics, two separate charts, report/data/Python.

Two providers: unclear concern about China's public-debt increase alongside growth recovery.
IMF WEO GGXWDG_NGDP and WDI NY.GDP.MKTP.KD.ZG; same annual window and phases, no causal
claims/projections/proxy debt measures. Separate charts, phase statistics, report/data/Python.
Each scenario had three development repetitions; failed attempts are preserved in this record.
The code changed between repetitions. This is historical debugging evidence, not a frozen-build
acceptance cohort or a model reliability estimate.

## Development-run evidence

- Single 1: session `agent-session-f28b3cefbaad43b19386f42869ba89eb`, run
  `agent-run-c909c99fe7014d44a88e4b6cab16442b`. Real clarification accepted six custom answers.
  Autonomous acquisition/analysis succeeded; 8 model fits. Report author attempt 1 included
  undefined `sections[2].evidenceRefsNote`; its single repair then contained an unknown claim
  reference. Stopped before formal review: 9 model calls, 1 route, 1 output candidate, 0 reviews.
  Correlated diagnostic events exposed both failures. Added a structural preflight that collects
  extra fields and invalid claim/citation references together, and reasoning for Agent report
  authoring. Repair count remains one.
- Multi 1: session `agent-session-5a09dae7600041d098c41f1def84dc90`. Real clarification accepted
  explicit custom scope/method/source/output answers. Planner put acquisition-dependent coverage/
  vintage verification in `unresolved_items`, stopping before acquisition. Added the existing
  deterministic guidance normalization to Agent routing and the new wording pattern to the
  shared classifier. Actual availability and vintage are checked after acquisition.
- Browser automation context expired to `about:blank` during development work. Reopening the
  persisted Agent session restored questions and counters; this is an operator/tool event, not
  product data loss.

### Further development failures (retained, not acceptance passes)

- Single 1 recovery: report attempt 1 truncated at its output limit; its one repair omitted the
  required reproduction-manifest statement. Candidate budget retained (2/3). Added bounded report
  length and explicit literal requirements, with increased per-call output allocation only.
- Multi 1 recovery acquired both sources and reached formal Codex review. It correctly found
  unsupported status/vintage disclosure and inadequate annual-path interpretation. A prior
  presentation patch had also introduced inconsistent package source notes. Fixed metadata-absence
  receipts and unified immutable source-note constraints; did not waive reviewer findings.
- Single 2: session `agent-session-8d3d437084d84eb78d8c8e2bc3eabb85`, run
  `agent-run-2dba0c35b67543988c3d88baf70c6c20`. An existing health test used the live default runtime
  directory and recovered the in-flight clarification. Isolated all those tests with temporary
  directories. Browser Resume retained the first call and generated a second clarification.
  Six custom answers then authorized execution. Six fits succeeded; Analyst invented `output`
  parameters to request endpoint-table presentation and was rejected. Added registered ordered
  descriptive observations/endpoints and validation inside the Analyst's one-repair boundary.
- Multi 2: session `agent-session-9ad05b3a47a84916ba9b7f3949ff4e92`, run
  `agent-run-9df936d08e814f10abc3423f818689e8`. Same test-directory recovery/resume; acquisition and
  eight fits succeeded. Author check incorrectly rejected a shared package source note on a
  single-provider chart. The correction also exceeded the 500-character alt-text contract and
  stopped before formal review (candidate 2/3). Added package-source semantics to self-checks
  and full patch-schema validation before candidate execution; maximum rounds unchanged.

## Historical development cohort (all attempts, including failed recovery)

| Scenario / repetition | Session | Run | Outcome |
|---|---|---|---|
| Single A | agent-session-8d3d437084d84eb78d8c8e2bc3eabb85 | agent-run-2dba0c35b67543988c3d88baf70c6c20 | Preserved failure/recovery; not a completion. |
| Single B | agent-session-415cbe2179fc46e5ad0b4d5035e09921 | agent-run-6433500cbe7d452eba4ef2309a579434 | Completed, manifest and reload verified. |
| Single C | agent-session-d2bf37a7bd3b4fbf833293037b88d669 | agent-run-be0342401bb74287b0e4c59f09ddafed | Planning recovered; Output Editor reached the physical-call ceiling. Partial results preserved, not complete. |
| Multi A | agent-session-9ad05b3a47a84916ba9b7f3949ff4e92 | agent-run-9df936d08e814f10abc3423f818689e8 | Preserved self-check/patch failure; not a completion. |
| Multi B | agent-session-f358b0e0f4fe44ff8cc60f6156224585 | agent-run-a5b774952665443fac7ecbbdcd10fb3e | Completed after preserved clarification/Plan recovery; manifest/reload verified. |
| Multi C | agent-session-018f5fd035a14ad29381d2a497ad4237 | agent-run-587bc24a3f9f4b4db87b8113e373da23 | Completed, manifest and reload verified. |

These were development runs across successive fixes, not a clean fixed-version reliability
benchmark. Do not report six successful completions or an established model pass rate.

### Single B delivery evidence

- Snapshot `sha256:6aba18a28470e61ca98c52227f500c1a908c2dbf91969ae9c9855ac69395dde9`.
- Current artifact set `sha256:5fe92283d2b401c0cbb19c2e506262a26f6e6b53560ecff708102e7c18847cb7`.
- DeepSeek `deepseek-flash`: two independent author checks passed. Codex-local semantic report
  review passed at formal round 3/3, with only the academic placeholder advisory remaining.
- A legacy English keyword heuristic incorrectly warned despite complete typed artifact refs.
  Fixed the shared rule, retained old reviews, and used the normal "Retry current review" command
  for two new checks and round 3. Candidate count remained 3/3; no budget reset/extra candidate.
- Explicit browser acknowledgement → Confirm final delivery → reload: completed.
- Manifest `agent-blob-fe4f5f3a2b2c436da3871bf9f8e65ce4`,
  hash `sha256:a54d7eab4a189ec8ccacf452fa0a9db6470317c0cae57cab11846a0fe94d1a4f`.
- 26 model calls, 428,948 known tokens, 4 fits, 30 nodes, 611.86 active seconds. Codex usage
  without actual token receipts remains conservatively reserved, not treated as zero.
- Offline replay: zero external calls; all four result and sample hashes matched; no integrity issues.

### Multi C delivery evidence

- IMF snapshot `sha256:95b4abbf00500641e905a016efea0ae3a16befcd6aed9df3cda384cf9c5530da`;
  WDI snapshot `sha256:774ba6fbd675717d4fa098db1843f1f05b40fb9afa964f423df8032b7fe82e37`.
- Artifact set `sha256:710783f69f966eff4f0acbb5be5701ebfc193fda7fb4359fda623a8726784044`.
- Two author checks passed; formal Codex review round 1/3, semantic report pass. Only publication
  placeholder scope advisory remains. Generation/self-revision used 2/3 output candidates.
- Explicit browser acknowledgement → final confirmation → reload: completed.
- Manifest `agent-blob-396b3d0e0eb04306be9cf045329c88e7`,
  hash `sha256:773e700688579a396d283b5984793d28f29eedda84cfaf452cbc4d0a0aa5c86b`.
- 14 model calls, 164,249 known tokens, 4 fits, 23 nodes, 168.19 active seconds; unknown Codex
  token consumption remains reserved. Offline replay matched four numerical results with no
  external calls or integrity issues.

### Additional issues found and addressed

Multi B recovered through normal intervention controls and completed two checks, round 1 Codex
semantic/visual approval, user acknowledgement/freeze and reload. Artifact-set hash:
`sha256:dbfa1075f43b9c5a125928dfa408ca3002c882665327fb162b2e611c83d99f36`.
Manifest `agent-blob-34d72f71e27d45739040a5472d49558b`, hash
`sha256:f59f29c5f0d2d1769c6e832dea518ab34486d4f80f9a6c5d85cb2d3f0a889ab9`.
Counts: 19 model calls, 249,304 known tokens, 4 fits, 2 routes, 2 candidates, 1 review,
333.82 active seconds. This recovery is a pass, not a first-try success.

Single C's second author check included false positives about defined CHN labels, endpoint
axis ticks, wrapped title text and normal decimal rounding. Output Editor then attempted a
noncanonical source note and a report ID in chart/table patches. Both were rejected; after
three actual calls its task stopped. Added typed section/evidence-bound report self-revision
before formal review (inside the existing run authorization), explicit editable IDs and immutable
source-note hints. Do not reset this historical task's ceiling to force completion. A task whose
physical-call ceiling is reached now transitions to failed, retaining partial outputs and allowing
an explicit linked new run, rather than advertising an impossible retry.

Record audit: Single C itself retains its historical `waiting_for_user` state and
`task_attempt_limit` error; its persisted record was not migrated to `failed`. The transition
above describes new executions. The subsequent A6 adjustment blocks both historical intervention
retry and new-run Resume when this hard ceiling is exhausted. Cancelling the historical run and
creating a linked run are explicit user operations; no counters or failed evidence are erased.

- Strict new route admission accidentally prevented older records from loading. New executable
  validation is separate from historical reads; historical data were not edited to force progress.
- Self-check reasoning consumed entire 8k/24k output budgets without final JSON; now structured
  self-inspection uses the same DeepSeek model without hidden reasoning, strict pass/empty-issues
  schema, complete truncation/repair records and unchanged actual-call/round limits.
- Intervention text was incorrectly treated as submitted clarification; UI now uses actual run
  authorizations, with a regression test.
- SSE replay bursts triggered redundant full-run queries. Cursors, Last-Event-ID, 750 ms coalescing
  and monotonic frontend projection versions prevent storms/stale overwrites.
- CSV previews now prioritize period/value/unit and page actual rows; loading history no longer
  briefly claims a run does not exist. Candidate output is not labelled completed/ready prematurely.
- Production has no environment-selectable deterministic Agent author/reviewer. Offline ports
  are explicitly injected only in tests. Codex shares the authorized disclosure policy.

## Final acceptance condition

Record all six run IDs, source snapshot hashes, model role/provider/model, author checks,
candidate/review hashes, failures and corrections, budget usage, final manifest and reload.
Only review-approved, user-finalized, reloadable results count as successful E2E.
