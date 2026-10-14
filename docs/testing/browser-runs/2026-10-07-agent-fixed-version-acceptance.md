# Agent fixed version acceptance

Result: **FAIL for the strict six-completion gate: 5 PASS / 1 FAIL**. Single-source 2/3;
multi-source 3/3. This new cohort ran on `863c07e`; it does not replace historical failures.
A6 remains Experimental and unaccepted. Evidence collection: 2026-10-07 18:21–18:57 UTC.

## Fixed build and protocol

Application: `863c07e5708d4538d3c21ebc686b1aac4dd5df41`. Source tree was clean at entry.
Backend was restarted from that commit before the first creation; no active jobs were present.
Python 3.10.10, Node 24.14.1, agent-browser 0.24.0, codex-cli 0.160.1.
DeepSeek roles inherit `deepseek-flash`; Codex-local uses its configured default and existing
ChatGPT login. Public/user data access enabled, licensed remote disclosure disabled. All default
budgets and two author checks/three formal reviews remain unchanged. No provider fallback.
Dependency SHA256: pyproject.toml
`34ae729cdfd34481015fa02f0a433f52212cc974cdde64e05959934023622d3b`;
frontend/package-lock.json
`a3951ac44700f00ce57bb2315aff52c7241fc2093955385612f436de9d0b5200`.

Use the two verbatim prompts and confirmed frames in
`2026-10-06-agent-a6-reacceptance.md`, three times each. China annual 2010–2024;
phase means 2010–2019 / 2020–2021 / 2022–2024, annual paths and 2019 versus 2024 endpoints.
Single: WDI female/male unemployment only. Multi: IMF WEO debt/GDP and WDI real GDP growth only.
Descriptive only, no forecasts/causality/proxies/derived gaps. Two separate line charts, phase
table, underlying data, report and Python; no Stata or dual axes. Disclose missing source-bound
status/vintage and interpretation limits. Custom answers map to the actual generated questions.

Only normal browser controls create/authorize/intervene/finalize. Read-only diagnostics verify
snapshots, real model calls, review history, budgets, manifest hashes and offline numerical replay.
No browser screenshots, database/artifact edits, code/configuration changes or counter resets.
No linked replacement is counted as an original cohort pass. Explicit retries, if eligible, stay
inside the same run and are recorded. Completion requires two real author checks, independent
Codex visual/semantic approval, user confirmation, frozen manifest, reload and matching offline
numerical replay with zero external replay calls. Only the publication placeholder advisory
may remain with explicit acknowledgement.

## Runs and outcomes

| Repeat | Session | Run | Current outcome |
|---|---|---|---|
| Single 1 | agent-session-750489a8ed384834892a896ad5aa8d4a | agent-run-85fc297a808047a3b4556057070effd8 | PASS: review/freeze/reload/replay |
| Multi 1 | agent-session-13faffdbbc064d459297469d3605cebd | agent-run-ec7767594a47462fb1ba7a97b6fbf98a | PASS: review/freeze/reload/replay |
| Single 2 | agent-session-ae8e8cd04f874ff5a3fca6c80904a1ad | agent-run-a03abb22868342efbd39dc60f0c5f8e3 | FAIL: semantic handoff gap; Output Editor stopped at physical-call 3/3, no manifest |
| Multi 2 | agent-session-b27f338fa9474e018ab1c9a96b3e5a0b | agent-run-43cb4cf43da84d2f8127898525b8bf34 | PASS: review/freeze/reload/replay |
| Single 3 | agent-session-ad2ff2659c9f4dff8cb7cb032ce40022 | agent-run-4ef643af9bc045c8b1be3638775d77af | PASS: review/freeze/reload/replay |
| Multi 3 | agent-session-478be44734634ab59640874b0255779b | agent-run-29c1e57cc15f41629c7fe9816d687273 | PASS: review/freeze/reload/replay |

First pair: custom answers used the fixed research frame; each route required one attempt,
acquired its correct source(s), assessed actual data and executed five descriptive windows.
Each reached two passing author checks and Codex semantic pass at candidate/review 1/3, with
only the publication placeholder advisory. Seven post-acquisition checks were retained in the
single-source route, including coverage/status/vintage/units; no pre-fetch metadata intervention.

At approximately 18:28–18:33 UTC, read-only run/replay requests timed out at 20/40 seconds and
health also timed out at 10 seconds. Reloaded pages remained “Loading saved Agent run…”.
The first finalization clicks were not committed according to a **read-only** SQLite query;
they were not counted as freezes. Subsequent DOM inspection found the final button at y=4500
in a 633-pixel viewport: the browser driver did not scroll before clicking. Normal explicit
scroll-into-view followed by clicking the button successfully froze both outputs. That missed
click was an operator/driver limitation, **not** a proven application-finalization defect.
The separate health/list/replay timeouts remain a responsiveness observation.

Read-only process sampling found backend CPU about 103%, physical footprint about 1.0 GB;
host swap used 11876.75 of 12288 MB. Thirteen automation browser sessions were open, seven from
earlier tests; each Agent page subscribes to all active runs, not just its current page.
The async SSE path reads SQLite synchronously. These are possible load contributors, not yet a
proven single cause. A native stack sample was retained locally; its machine-specific path is not
part of this public test record.
Only old owned automation windows were closed first; no user browser or research was deleted.
Health subsequently answered. Current waiting windows were also closed to inspect runs sequentially
through the remaining two browser sessions; all six run IDs/counters remained intact. No backend
restart, code/configuration change, budget expansion or direct data/state mutation occurred.

Fixed-build regression: backend 409 passed / 4 optional live tests skipped; frontend 128 passed,
lint/mypy/TypeScript/build passed. The backend suite took 136.10 seconds under concurrent host
load. These regressions do not establish completed real-provider outcomes.

## Verified first pair deliveries

Each passed two actual author checks, Codex semantic/visual review at round 1 (only placeholder
advisory), explicit browser acknowledgement/final confirmation, Completed after reload and a
visible frozen manifest link. Offline replay recomputed all five result/sample hashes exactly;
external_calls=0, integrity_issues=[], 11 reconstructable requests each. No model retry, scope
change, linked run, general-budget extension or research-counter reset was used.

- Single 1: artifact set `sha256:14b86871feddca0f409317476ee42e87aa4a7d86b3759b07ce7e87aac8290726`;
  manifest `agent-blob-00afd03e67cb4c3e9a5d544231dad4f4`, hash
  `sha256:e21857e81485a88ae622ce487c24f1b25485ff81e8b00f6cf5c2ccb6806fec2f`.
  11 calls, 135275 known tokens, 120000 unknown tokens reserved, 5 fits, 1 candidate/review,
  19 nodes, 243.50 active seconds. WDI snapshot 30 rows, hash
  `sha256:6aba18a28470e61ca98c52227f500c1a908c2dbf91969ae9c9855ac69395dde9`.
- Multi 1: artifact set `sha256:3c528291e7efa86d83f12df73b028a05d19cfe3c58f0f5ab3efb4af1a3f08b8b`;
  manifest `agent-blob-20338c35f65b46eb962e3562034e723c`, hash
  `sha256:1c34d3d72e9c2b5d4acc06c7a01ea529e44aad58dc37f58a7de31994b1a44f5a`.
  11 calls, 132434 known tokens, 120000 unknown tokens reserved, 5 fits, 1 candidate/review,
  20 nodes, 250.53 active seconds.

## Remaining outcomes and full audit

All six used the exact original prompts and answered actual generated questions with the same
confirmed frame. All acquired correct source snapshots and completed five descriptive analysis
windows. Routes required one attempt each; no pre-acquisition metadata intervention occurred.
Acquisition-check counts in table order: 7 / 5 / 6 / 5 / 8 / 8; every run retains a source-bound
Data Steward assessment ref. No scope expansion or rerouting to alternative indicators occurred.

All five successful runs passed two real author checks and Codex semantic/visual review at
candidate/review 1/3, with only `VISUAL-RUBRIC-PLACEHOLDER`. Each was acknowledged/finalized
through the visible browser button and reloaded Completed with its frozen manifest link.
All five manifests were fetched and their SHA256, run ID, artifact-set hash and finalized_by=user
verified. All six runs, including the failed one, replayed five result/sample hashes exactly
with external_calls=0 and no diagnostic/replay integrity issues. Diagnostic ZIP CRC checks
passed for all six: 25 / 25 / 43 / 25 / 25 / 25 entries. No budget violations or false completion.

| Repeat | AI calls | Known tokens | Unknown tokens reserved | Fits | Candidates | Formal rounds | Nodes | Active seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Single 1 | 11 | 135275 | 120000 | 5 | 1 | 1 | 19 | 243.50 |
| Multi 1 | 11 | 132434 | 120000 | 5 | 1 | 1 | 20 | 250.53 |
| Single 2 | 15 | 263438 | 120000 | 5 | 1 | 1 | 20 | 397.89 |
| Multi 2 | 11 | 133256 | 120000 | 5 | 1 | 1 | 20 | 518.01 |
| Single 3 | 11 | 141237 | 120000 | 5 | 1 | 1 | 19 | 320.72 |
| Multi 3 | 11 | 138143 | 120000 | 5 | 1 | 1 | 20 | 460.98 |

Shared source snapshots: all single runs WDI 30 rows,
`sha256:6aba18a28470e61ca98c52227f500c1a908c2dbf91969ae9c9855ac69395dde9`;
all multi runs IMF WEO 15 rows,
`sha256:95b4abbf00500641e905a016efea0ae3a16befcd6aed9df3cda384cf9c5530da`,
and WDI 15 rows,
`sha256:774ba6fbd675717d4fa098db1843f1f05b40fb9afa964f423df8032b7fe82e37`.
Existing registered connector cache/metadata receipts are retained, not fabricated acquisitions.

Remaining finalized sets/manifests:

- Multi 2 set `sha256:d5d55b8898af5bdf12b46a0f4f464481986593fcd4c03220d943f23c5bef5bf6`;
  manifest `agent-blob-48e19d5711de427dbd24a316aeac2e47`, hash
  `sha256:99398781dd45031e6d40f812d78274d24d7628ac21876bc246f3ff1a9576d8b6`.
- Single 3 set `sha256:31d26fe7eb52b86a48d359a4234c935fa7c5b505c5836276d362a70f5137b19e`;
  manifest `agent-blob-d9c6b305bcf94bac9de5a3cb57b9e9cf`, hash
  `sha256:896f02611e11398ba5182ccb2bfb109af57b9ea23a0e99b6322335770fa13809`.
- Multi 3 set `sha256:ec17931684dbcda06e9b68af8d97f3f3eba4cb80af7251241523913fd823d0c8`;
  manifest `agent-blob-28414d253eb34c62951d42f02b0d4e44`, hash
  `sha256:7a29e47231f7c6d8bf8f3e048e7037a8dfda60b363fffe7d447adbc3e8e83e3a`.

## Failed delivery diagnosis

Single 2: both author checks passed (round 1 needed its bounded schema/semantic repair), but
Codex formal round 1 returned `CODEX-REPORT-REPORT-EVIDENCE-SUFFICIENCY`, semantic status
`requires_upstream_stage`. Report claim C10 asserted one series per chart/no dual axes while
acknowledging missing binding evidence. The report reviewer received selected-artifact metadata,
but not the bound chart specifications/contents needed to verify those assertions. This is not
missing WDI observations: all five numerical results match, and the chart artifacts/specs exist.

Code inspection confirms the narrowing point: `CodexLocalOutputReviewer._invoke_report` in
`workflow/codex_output_reviewer.py` constructs `ReportReviewRequestV1.selectedArtifacts` from
artifact metadata only; it does not carry `OutputReviewRequest.specifications` or chart content.
The independent visual reviewer receives specs/renders, but that evidence is not carried into
the separate report semantic request. Author/check success is therefore not proof of complete
cross-role evidence handoff. This real contract gap can surface depending on generated claims.

Output Editor attempted report rewriting instead of supplying the required upstream evidence.
Both original responses were correctly rejected: “Upstream evidence gaps cannot be concealed
by self-rewriting.” Diagnostic payloads `agent-blob-954679f68cfc4e8a96179a3d89a6c0da` and
`agent-blob-9b7edd5190f449b8893b25d03e257b64` preserve those errors. The UI classified the collapse
as `invalid_model_contract` and offered one remaining call. One explicit **Retry failed step**
was clicked, preserving answers/inputs/budgets. The third response could not repair the contract;
its rejection is retained in `agent-blob-3955cf9dd8d344c5b77393d4fd79c4d4`.
The format repair was blocked before a fourth call. Run ended `failed/task_attempt_limit`,
Output Editor physical_calls=3, two graph attempts, no manifest. Original set remains
`sha256:87c6c6fbd6f628d4941fbf99047d69e01f3199448124488eac7d3f6a6a5a1abc`.
No re-review lottery, linked replacement, source edit, scope expansion or freeze was attempted.

Recovery advice correctly became `start_linked_run`, can_retry=false, task_calls=0 despite
25 general model calls and two candidate/review rounds remaining. Complete failed evidence
is readable in the 43-entry diagnostic ZIP. The history panel counts retained correction
checkpoints as previous output versions, so failed retries show repeated “version 1”; this is
an additional presentation issue, not actual extra candidates or budget resets.

## Follow-up priorities

1. Provide Report Author/Reviewer with owned, hash-bound chart/table specifications and necessary
   content/inspection receipts, including indicator, series, unit and axis bindings. Add a regression
   that requires a semantic reviewer to substantiate a chart-compliance claim from this context.
2. Treat a known missing-handoff/upstream prerequisite as non-repairable by wording. Stop/route it
   distinctly rather than spending format repair and offering a schema retry for the same rejection.
   Preserve the strict no-concealment and physical-call ceilings.
3. Separate attempt/review checkpoints from distinct candidate versions in output history.
4. Investigate overlapping all-active-run SSE subscriptions and expensive list projections under
   multiple/historical sessions. Add bounded initialization/request cancellation and load tests;
   host memory pressure is a contributing observation, not proof that the application is fault-free.

No fixes were implemented during this cohort. After fixes, repeat all six on a new frozen build;
do not use a replacement successful run to erase Single 2's failed result.

## Conclusion

The fixed-version cohort completed five of six full journeys, with one retained semantic-handoff
and bounded-recovery failure. Data acquisition, typed analysis, numerical reproducibility,
diagnostics and non-bypassable freeze/budget guards worked in all six. Report handoff/recovery
is not yet reliable enough for the strict A6 gate. **A6 not accepted; remains Experimental.**
Workflow Phase 0–3 acceptance and deferred Phase 4 are unchanged. Only test records/status/docs
are updated after this frozen cohort; application code, configuration and dependency fingerprints
remain those of `863c07e` throughout the test.

## Post cohort implementation follow up

The user authorized repair after the retained 5/6 verdict. No original run was resumed, reset,
re-reviewed or changed into a pass. The new code adds typed `presentationEvidence` to author and
semantic-review contexts, using owned hash-verified files/specs rather than unbound descriptions.
Exact bounded SVG contents and CSV headers are included; workbook inspection explicitly remains
file/spec-only. Full dataset/model results remain accessible through existing registered grants.
Workflow staged generation and both modes' revisions refresh evidence from current artifacts.

Required upstream findings now stop before Output Editor, and missing/corrupt presentation
prerequisites are separately classified. `repair_evidence` recovery blocks Resume, scope replies,
task retry and re-review; no repair loops or budget resets are introduced. The UI alert/next steps
follow the UI/UX error-recovery guidance, without altering approvals or presenting a false retry.

Verification on temporary stores and recorded provider ports: backend **431 passed / 4 opt-in
skipped**, frontend **130 passed**, lint/mypy/TypeScript/build passed. New regressions cover
both report roles receiving exact bindings, missing spec/hash blocking both visual and semantic
AI calls, forged specs/content, foreign ownership, unsafe/oversized SVG, CSV headers and no copied
observation rows, reproduction-input separation, old records failing closed before authoring,
current binding refresh after joint chart/report revision, upstream findings with zero Editor
calls, and unchanged state/budgets on forbidden recovery. One initial recorded Codex runner
constructor error and a missing-spec classification edge were corrected before the passing suite.

This implementation/test evidence fixes the reproduced code paths; it is not a new live six-run
cohort or acceptance of A6. Distinct candidate history and multi-session SSE/list performance
remain separate backlog. The historical verdict above remains **5 PASS / 1 FAIL**.
