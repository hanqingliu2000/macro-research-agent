# Agent A6 reliability improvement and acceptance — 2026-10-07

Status: API restored; six research scenarios have reviewed/frozen/reloadable deliveries, including one linked replacement. Original cohort is 5 completed / 1 cancelled, not retrospectively 6/6. Strict cohort gate remains open. Earlier failures remain in
2026-10-06-agent-a6-reacceptance.md and are not relabelled successful.

## Planning and failure-recovery follow-up verification

The user's next request selected two implementation tasks, not another live six-run cohort.
On the working-tree follow-up to `2251f06`, source metadata/status/vintage/coverage checks were
moved into a bounded post-acquisition field; real definition/vintage choices and access/admission
prerequisites remain blockers. The Data Steward sees acquired rows/source receipts, and the
assessment references persisted source snapshots. No historical plan, dataset or counter changed.

Safe provider errors now distinguish credit (402), authentication (401/403), missing credentials,
rate limiting, timeouts, service/connection failures and rejected configuration from invalid
model/report output. Explicit typed retry preserves answers, input refs, attempts, budgets and
unknown-use reservations. Credit/access/configuration confirmation and actually missing-key
rejection are server-side. UI displays cause/action/remaining limits with accessible alerts and
disabled-until-confirmed controls, guided by the UI/UX error-recovery guidance. General budget
enlargement is explicit; hard phase/task/candidate/review ceilings remain fixed.

Offline verification: 29 targeted guidance/recovery tests; full backend **409 passed / 4 optional
real-model tests skipped**; frontend **128 passed**, lint/mypy/TypeScript/build passed.
Coverage includes original WEO wording, real blockers, post-fetch assessment refs, 402 through
the real adapter with exactly one recorded physical request/no fallback, secrets excluded from
public errors, idempotent retry, unchanged inputs/answers, missing keys, reserved tokens, active
time, phase/task/version/review exhaustion, and Resume/scope-answer bypass rejection. Two new
test-fixture setup errors (frozen Settings mutation and unauthorized route claim) were fixed
before the final successful full suite; application constraints were not relaxed.

After confirming no requested/queued/running Agent jobs, the local backend was restarted with
the existing private configuration (PID 54612); frontend remained on port 5173. Read-only browser
DOM/API inspection, with no screenshots, no POST and no model calls:

- `agent-session-a2fa0cecf5e1431cae43fc4c90d9e88d` /
  `agent-run-0cbaab109dcc494c976d20357397b263`: historical `invalid_report_contract`,
  `report_revision:2:dir-chart1-axis-tick-disclosure`. Recovery showed 1 remaining physical call,
  2 attempts, 27 run calls, 1 Output candidate and 3 formal rounds. Retry failed step was present;
  scope-change response was absent. Retry was **not** clicked; original failed evidence retained.
- `agent-session-a862734ef0cf47359f110ad6388b5474` /
  `agent-run-269171df774940d3846a41795edcbeef`: retained `no_progress` at review 3. Recovery
  instructed cancel-if-waiting then linked run; no failed-step retry or scope-answer button.
  Remaining general calls did not make an exhausted delivery resumable. No command submitted.

These offline/DOM checks validate the two repairs, not live author/reviewer success on a new
cohort. Original fixed cohort remains 5 completed / 1 cancelled plus one successful child.
Strict A6 repeat acceptance is still open; next task is an unchanged-build six-run browser cohort.

## Improvements and offline evidence

- Native SVG inspection reconstructs registered selection/rendering from authorized complete
  rows and typed spec, binds file/spec/dataset hashes and calculates tick values using gridline
  coordinates (text baseline minus its offset). Corrupt ticks/curves or missing/bad hashes fail
  or remain unverifiable. A receipt explicitly is not approval or a substitute reviewer.
- Self-check v7 returns evidence-bound typed findings. A numeric false positive contradicting
  a passing receipt enters one contract repair; two wrong outputs stop. Native failure cannot
  be silently approved. Both actual model checks and independent Codex review remain mandatory.
- Approved plan/confirmed decisions and compact typed result facts travel across author/check/
  editor/reviewer roles. Per-phase sample counts and endpoint samples are distinguished; complete
  observed paths remain available through registered reads, not a sample-only substitute.
- Agent report revision returns exact approved section/associated claim text edits only. Server
  preserves all immutable IDs/refs/citations/title/untargeted sections and validates the result.
- 377 backend passed / 4 optional live skips; 122 frontend passed; lint/mypy/types/build passed.
  New tests reproduce the prior 76.11/61.80/47.49 tick false positive, actual geometry corruption,
  bounded repair/no fallback and protected-field/section/claim edits. Tests use temporary stores.

## Fixed protocol

Commit/dependency/runtime fingerprints are recorded before the first browser creation. No code,
configuration or limits change during a cohort. A mid-cohort fix requires a separate retained
build record. Only normal browser controls advance runs; diagnostics are GET-only. No screenshots,
direct database/artifact edits, counter resets or provider fallback. Two actual model checks,
formal Codex semantic/visual approval, explicit user freeze, manifest, reload and offline numeric
replay are required for completion. Unknown reviewer tokens remain reserved, not counted as zero.

Use the same two prompts and confirmed frames in 2026-10-06-agent-a6-reacceptance.md, three times
each: China/WDI female and male unemployment, annual 2010–2024; and China/IMF WEO debt/GDP plus
WDI growth, same window. Fixed phases 2010–2019, 2020–2021, 2022–2024, annual paths and 2019–2024
endpoints. Descriptive only; no forecasts, causality, proxies, derived gender gaps or extra models.
Two separate charts, phase table, data/report/Python, no Stata/dual axes. Disclosure of absent
status/vintage and limited interpretation is mandatory. Custom answers map to actual questions.

## Build and outcomes

First build: `9a0503b2e6f317e60a26ec40bff6830b32b15a28`. Python 3.10.10, Node 24.14.1,
agent-browser 0.24.0, codex-cli 0.160.1. Same providers: DeepSeek `deepseek-flash`, Codex-local
configured default. Dependency SHA256: pyproject.toml
`34ae729cdfd34481015fa02f0a433f52212cc974cdde64e05959934023622d3b`; frontend/package-lock.json
`a3951ac44700f00ce57bb2315aff52c7241fc2093955385612f436de9d0b5200`.

- Single 1: `agent-session-d8426e40c1fa4057835ee485a6caea45` /
  `agent-run-e7e5a63cb9374902b125b4f7619df819`. Plan initially blocked on coverage that is
  "confirmed only after acquisition". Normal browser intervention retained scope, rerouting
  used route 2/3 and proceeded. Real section-edits revision of Results succeeded; two checks
  and Codex round 2 passed. Explicit confirmation/reload completed. Five offline result/sample
  checks matched, zero external calls, integrity clean. 19 calls, 267599 known tokens, 5 fits,
  2 candidates/2 formal rounds, 25 nodes, 320.12 active seconds. Artifact set
  `sha256:2bef6683dd634322ec45f1fde59ab1fa43a4f5604e1a12199fb12785290008b4`;
  manifest `agent-blob-3e8a475bcbda4be1b016c493f3320899`, hash
  `sha256:b5e955b32f7b1c5203e20d8148e313eff2739e6c957762fb87b7bc1267e96c41`.
- Multi 1: `agent-session-952f2e750a9c41f68a8e93ee758cc42f` /
  `agent-run-acb9f5ab9a9e4a8d9be13f0b669ac77c`. Native receipt found minimum/maximum mismatch:
  raw SVG 2.33950385203023 / 10.5916903885704 versus model grant rows truncated to ten decimal
  places. Both model findings correctly cited failed receipt checks. Output Editor could not
  repair protected coordinates, stopped requires_upstream_stage. No review/freeze claimed.
  12 calls, 207972 known tokens, 5 fits, 1 candidate, 20 nodes, 142.96 active seconds. Set
  `sha256:bbc68eadd751a3bd89061a669f7ee33f5302981a23188c3f88a1436fcb9b344e`.
- Second-pair drafts were created but not authorized; both cancelled through normal browser
  controls after this concrete defect. Single `agent-session-5ffa9d5903974b5c8e883187e8c7adc3` /
  `agent-run-dce04c91f0d9425da06a9349905c50d4` used one clarification call/6099 tokens;
  multi `agent-session-5f56664301484e52bcf0cf968690158b` /
  `agent-run-392613b4d4ad4c7d9f8ff3227e39c8b3` used one/5677 tokens. Not E2E passes.

This incomplete cohort is retained. Follow-up fixes preserve Python round-trip numeric scalars
in granted rows (including tiny values, integer precision and null/nonfinite handling) without
editing snapshots. Explicit post-acquisition confirmation wording is not a prerequisite;
credential/admission failures remain blockers. Three new regression tests cover these cases.

## Corrected fixed build

Build `9599d3999c6eb508ce64995614a95f4b430fe7d5`, same dependency/runtime fingerprints and
providers as the first build. Backend restarted before creation. No code/settings/limits changed
during this cohort. Custom answers used the fixed frame; interventions did not expand scope.

| Repeat | Session | Run | Outcome |
|---|---|---|---|
| Single 1 | agent-session-867715d1ebd040bbab9d19aef08df596 | agent-run-089b26c4fc1a4c44b3ff1795b2997de4 | completed after one report revision; review 2/3 |
| Multi 1 | agent-session-dfffff2efabf4972967a2aa947a114a0 | agent-run-c147cf8f554b44fc87d3950d09391573 | waiting_for_user; 402 at Analyst |
| Single 2 | agent-session-fa6692dc06854a4cb265bd1b3ca38a6e | agent-run-050f5ca718a6440ab89a3da775e95bed | completed; candidate/review 1/3 |
| Multi 2 | agent-session-a57ed65d78f043e6b47014c30ccd3e51 | agent-run-d7bbb3f94721478ead6ac08a30c7b16b | completed; candidate/review 1/3 |
| Single 3 | agent-session-3c03102be2ca48308f2194ebc614fb7e | agent-run-7f7395b1bf7b4b43baadf7ce9c1ccc83 | waiting_for_user; 402 at Planner |
| Multi 3 | agent-session-fa6e3af705974c1aba20111d9ac0fb7b | agent-run-030f932eaf224445bcab68b0d94b7ab8 | waiting_for_user; 402 at clarification, including user retry |

| Repeat | Calls | Known tokens | Reserved unknown tokens | Fits | Candidates | Reviews | Nodes | Active seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Single 1 | 16 | 193264 | 240000 | 5 | 2 | 2 | 24 | 253.07 |
| Multi 1 | 6 | 48641 | 129936 | 4 | 0 | 0 | 13 | 97.74 |
| Single 2 | 11 | 137613 | 120000 | 5 | 1 | 1 | 19 | 206.86 |
| Multi 2 | 11 | 128096 | 120000 | 5 | 1 | 1 | 20 | 165.56 |
| Single 3 | 2 | 5856 | 44445 | 0 | 0 | 0 | 2 | 10.95 |
| Multi 3 | 2 | unavailable | 66172 | 0 | 0 | 0 | 1 | 2.31 |

All six diagnostic integrity queries returned no issues. Missing token receipts are retained
as reservations, not inferred zero consumption. Multi 3 consumed its two clarification batches;
restoring credit does not authorize resetting that ceiling. Future completion may require an
explicit linked run/new fixed cohort, preserving this blocked evidence.

Completed runs each passed two real DeepSeek checks, actual Codex visual/semantic review with
only the interim-publication advisory, explicit browser acknowledgement/final confirmation,
reload Completed and five offline numerical/sample checks (all matched; zero external calls).
Current output sets and manifests:

- Single 1 set `sha256:57371b963b203a807dfdfab0ade9632b6001dcbd7dfb0158c9c5f85cf5f536a4`;
  manifest `agent-blob-cf53d367c46e44aa9edeaacc55142286`, hash
  `sha256:9a779808224a88c9b2947a76214923df7f4c5be0d9cb5682348b801656e9d2b2`.
- Single 2 set `sha256:b91980a0bea2025eb89b1670fc507d7fa74b5ffa88045f009c1167d4bb5aad83`;
  manifest `agent-blob-de149b6c43234b04b2e60ebbfd2abbd3`, hash
  `sha256:31baf51c56399cf896d6d8aea1b600d7ccfae57e5346d2d8d1245fa67f283135`.
- Multi 2 set `sha256:c6f444337dcd5cc3df53b2b0555650cd2e6d1d54dd7015ead15f59fb8bb99a1b`;
  manifest `agent-blob-820966b7168643a19c572d3daaa2bcac`, hash
  `sha256:b2a389a0c941273521fbfa94c03917839819c3e653880dac0ed2ee127ffb2a3d`.

Source hashes were unchanged across relevant repetitions: single WDI
`sha256:6aba18a28470e61ca98c52227f500c1a908c2dbf91969ae9c9855ac69395dde9`;
multi IMF `sha256:95b4abbf00500641e905a016efea0ae3a16befcd6aed9df3cda384cf9c5530da`
and WDI `sha256:774ba6fbd675717d4fa098db1843f1f05b40fb9afa964f423df8032b7fe82e37`.

## Remaining observations and external blocker

- Multi 1's Planner initially treated source estimate/status/vintage exposure as an unresolved
  human decision. Normal browser reply restated the existing disclosure policy without scope
  changes; route 2 proceeded and acquired both sources. Planning admission still needs more
  robust distinction between human prerequisites and post-acquisition metadata checks.
- Automatic permission review timed out once on a read-only browser operation; its permitted
  single retry succeeded. Browser automation later returned OS error 35 / daemon unresponsive.
  Only owned automation contexts were closed/reopened; backend runs/IDs/budgets were unchanged.
  API and frontend proxy queries stayed healthy; no JS exceptions were reported after recovery.
  This is recorded as operator/tool recovery, not a silent successful browser test.
- In both Multi 1 and Multi 3, a normal user Retry was submitted before the exact payment cause
  was diagnosed. The raw, redacted provider response confirmed HTTP 402 and **Insufficient
  Balance**. No further model requests were initiated after that diagnosis; already approved
  deliveries were finalized/replayed without external calls. No alternate key/provider/fake was
  selected, no payment was made, and no run was forced complete. The user was asked to restore
  DeepSeek API credit. Single 3 was independently stopped by the same 402 at route generation.

Conclusion: code/contract improvements and 380 backend / 122 frontend regressions passed;
three real closed-loop deliveries passed within original limits, including semantic revision.
This is **3/6 complete**, not a six-run acceptance pass or an established model pass rate.
Restore the external API balance before more live testing. A6 remains Experimental/open;
Phase 4 remains deferred. Preserve this cohort when a new fixed-version cohort is run.

## After user-confirmed API restoration

No code/provider/settings/limits changed. Successful actual DeepSeek requests verified restored
access while continuing normal browser commands; no separate untracked model probe was used.
Already completed Single 1/Single 2/Multi 2 were not rerun. Original 402 attempts and conservative
token reservations remained in the ledger; refunds/resetting unknown usage were not inferred.

| Scenario | Recovery | Final calls / known tokens / reserved tokens | Fits / candidates / reviews | Active seconds |
|---|---|---|---|---:|
| Multi 1 | same run c147cf8f554b44fc87d3950d09391573; Analyst retried within remaining task ceiling | 14 / 147323 / 249936 | 4 / 1 / 1 | 281.09 |
| Single 3 | same run 7f7395b1bf7b4b43baadf7ce9c1ccc83; route retried, counters retained | 13 / 159545 / 164445 | 5 / 1 / 1 | 179.46 |
| Multi 3 | explicit linked run f87ca085c39e40f69b40e92f4b8e9c62 under the same session | 13 / 158167 / 120000 | 4 / 1 / 1 | 216.65 |

Multi 3's parent `agent-run-030f932eaf224445bcab68b0d94b7ab8` used 2/2 clarification batches.
The browser cancelled it and invoked **Start linked research run** with the same original prompt.
It remains cancelled with 2 calls/2 batches/2.31 active seconds, intact trace and no manifest.
Child `agent-run-f87ca085c39e40f69b40e92f4b8e9c62` records that exact parent ID; it is an explicit
new authorization/budget, not a reset or silent continuation of the exhausted parent.
Custom answers used the same China/IMF WEO/WDI annual 2010–2024 descriptive frame. Planner again
put estimate/status/vintage availability into unresolved_items; normal user reply restated the
already confirmed acquisition/disclosure policy, no scope checkbox, and route 2/3 proceeded.
This unnecessary intervention remains an open usability/role-alignment observation.

All three recovery deliveries passed both actual author self-checks, Codex visual/semantic
review (only publication placeholder advisory), explicit browser acknowledgement/final freeze,
Completed after reload, and offline numerical/sample replay (Multi 1: 4, Single 3: 5, linked
Multi 3: 4 results; all hashes matched, external_calls=0). Their diagnostics had no integrity
issues. Parent diagnostics also passed and retain cancelled/error evidence.

- Multi 1 final set `sha256:7a93fd17b8bd8245fde16f655c590cf8465c5c7123f55de6dec443b8078945af`;
  manifest `agent-blob-f967bc0f450d47f8be66e8befe069430`, hash
  `sha256:3a95a72d09bea12b08b86cccdf83751dd2321daa3da0fa7fb572e0e4a01ecb5b`.
- Single 3 final set `sha256:2f5eb072b0b1a82b81cd019113cca0c617fca4e6d940a1189938bec12ea28bb2`;
  manifest `agent-blob-ee9c417fdfd5491a96ab7805c8d44861`, hash
  `sha256:96fb3de9e6ecb12d4ce0f512bbc32bd3b57e3f31bdf99b31be1d73b0078b1df4`.
- Linked Multi 3 final set `sha256:3499c12357ef00a9e88dbdcb917a1310987b9d99c713925c082b3c323af985fa`;
  manifest `agent-blob-7fd99a5d88244673afac34b7444ca192`, hash
  `sha256:18698b9dca11cdd70ac42c5d56f75dba2d15bb3b279bc87e55fc58de66ddc23b`.

Updated conclusion: restored-provider recovery and linked-run functional closure passed; three
single-source and three multi-source scenario deliveries exist on unchanged implementation.
The original six-run cohort itself remains **5 completed / 1 cancelled**, with the linked child
recorded as a seventh attempt. Do not overwrite the parent failure, claim a clean 6/6 original
cohort or derive first-try reliability from this recovery. A6's strict fixed-cohort gate remains
open; future acceptance must distinguish clean cohort evidence from these recovery paths.
Phase 4 remains deferred; no additional capability or scope was enabled.
