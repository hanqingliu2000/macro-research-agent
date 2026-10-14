# Agent A6 record audit and frozen-build reacceptance — 2026-10-06

Status: two frozen builds failed; follow-up contract fixes require separate verification. A6 not accepted.

## Record audit and adjustments

The prior `2026-10-06-agent-autonomous-acceptance.md` contains eight development runs,
including a six-repetition cohort with three completions. Code changed between attempts;
it establishes exercised paths, not a frozen-version success rate. All failures, attempts,
unknown-token reservations and original states remain unchanged. Single C historically remains
`waiting_for_user` with `task_attempt_limit`, not a retroactively migrated `failed` run.

Adjustments: author-check v4 separates round-1 package semantics (report publication policy)
from round-2 rendered chart/table structure (visual rubric). Both read complete authorized data;
formal Codex semantic/pixel approval is unchanged. Manifest IDs/names/hashes prevent ambiguous
artifact identities. Editor schema exposes editable IDs, field limits and immutable source note.
Hard task limits reject Resume/intervention retries; diagnostics remain available, and an explicit
linked request is possible even without prior outputs. No limits or finalization gates relaxed.

Offline regression: 356 backend passed / 4 opt-in skipped; 120 frontend passed.
Backend lint/mypy, frontend lint/TypeScript/build passed. Frontend suite used two workers to avoid
resource-contention timeouts. Optional skips are not counted as real-model passes.

## Frozen cohort protocol

Before the first creation, record commit/dependency fingerprints and restart the backend from
that commit. Same runtime/settings/providers throughout; no credentials in this record.
Only ordinary browser controls advance runs; GET diagnostics are read-only. No direct data,
artifact or state edits, no screenshots. Manual custom clarification answers are normal user input.
Keep all failures, not only successful completions. A patch after cohort start invalidates that
cohort as fixed-build evidence and requires a separate retained record, not silent replacement.

Single prompt (repeat three times verbatim):

> I keep hearing China's labor-market recovery helped everyone, but I am unsure women benefited as much as men. Was the improvement after COVID sustained or a temporary rebound? Use World Bank data only and provide useful historical comparisons, two charts, a short evidence-bound report and reproducible Python.

Confirmed frame: CHN; WDI SL.UEM.TOTL.FE.ZS and SL.UEM.TOTL.MA.ZS only, annual 2010–2024.
Phase means 2010–2019 / 2020–2021 / 2022–2024, annual paths, 2019 vs 2024 endpoints.
Descriptive only: no trend/regression/correlation/forecast/causality or derived gap. Two separate
line charts, phase table, data/report/Python; no Stata or dual axes. Units are % female/male labour
force. Disclose absent status/vintage, never confuse retrieval with vintage, and participation/job
quality caveats. Map answers to each actual question without changing this frame.

Multi prompt (repeat three times verbatim):

> I worry China's public debt is rising without a convincing post-COVID growth recovery. Investigate whether recovery looks sustained or temporary using IMF WEO general-government gross debt/GDP and World Bank WDI real GDP growth. Provide historical phase comparisons, separate charts, an evidence-bound report, data and reproducible Python, without causal claims.

Confirmed frame: CHN; WEO GGXWDG_NGDP and WDI NY.GDP.MKTP.KD.ZG exactly, annual 2010–2024.
Same phases and annual paths; descriptive only, no regression/correlation/forecasts/proxies or
causality. Exclude later WEO projections; source-bound status/vintage or explicit absence.
Two separate line charts, phase table, data/report/Python; no Stata/dual axes/rebased index.

For each run: record session/run IDs, source hashes, calls/tokens/reservations/fits/candidates/
formal rounds, both author-check results, actual Codex status and semantic status, artifact hash,
user finalization, manifest hash, reload and offline numeric replay/integrity. A complete pass
requires actual review approval within unchanged bounds and user freeze, not merely usable data.

## Frozen build 1: ef52502907ce254346953f8ba76344ffce855e0f

Backend restarted from the submitted commit; no code/config/counter changes during these runs.
Python 3.10.10, Node 24.14.1, agent-browser 0.24.0, codex-cli 0.160.1. DeepSeek roles:
`deepseek-flash`; formal reviewer `codex-local` / `codex-configured-default`.
Dependency fingerprints: pyproject.toml SHA256
`34ae729cdfd34481015fa02f0a433f52212cc974cdde64e05959934023622d3b`;
frontend/package-lock.json SHA256
`a3951ac44700f00ce57bb2315aff52c7241fc2093955385612f436de9d0b5200`.
An operator submitted during service restart before readiness; no session was created. Retried
the ordinary create control once the service was ready. This is not a completed research run.

| Scenario | Session | Run | Final outcome |
|---|---|---|---|
| Single 1 | agent-session-b1a4f514d9ce46fe8d6849d691999ac5 | agent-run-7910483df9f44e69ac47bd49b824a171 | budget_exhausted; not finalized |
| Multi 1 | agent-session-373aeb5e6faa4fa1a4b37f3f493056aa | agent-run-656319492eb54ac394474f683dcf01dd | budget_exhausted; not finalized |

Single: 17 model calls, 247,562 known tokens, 5 fits, 3 candidates, 1 formal review,
27 nodes, 244.61 active seconds. Codex found genuine percent-versus-percentage-point ambiguity
and issued a section-bound revision. After correction, author check falsely treated CSV/XLSX
representations sharing a table specification as forbidden duplication; three candidates were
exhausted. Final set `sha256:ed8341fcc82c8cfe208fe4b578b2b5e6b09101292bc4a820418077ad5282503c`.
Actual data preview begins period/value/unit. No freeze/manifest or final acceptance claimed.

Multi: 21 calls, 356,039 known tokens, 5 fits, 3 candidates, no formal review, 31 nodes,
302.84 active seconds. Chart wording initially described both indicators on single-series plots;
automatic correction repaired titles. Then author check falsely required snapshot refs to appear
in the export-artifact manifest, and later could not verify generated-candidate status because
the manifest projection omitted status. Final set
`sha256:402bb3fd0780f876fe89f8f4f93587606457728d2d622f36f1af2be20b2eb47b`.
Both stopped without bypass, frozen outputs or counter resets. Unknown usage remains reserved.

The planned remaining four runs on this build were not executed after these actionable failures;
this incomplete failed cohort is retained, not replaced or counted as six successful attempts.
Corrections for the next build: exact-indicator/entity/unit chart context (all selected rows),
separate snapshot/model/export identity namespaces, artifact lifecycle/status and ID-keyed table
specifications. UI must not imply that adding execution budget adds delivery rounds.

## Corrected frozen build and outcomes

Corrected-build regression: 357 backend passed / 4 opt-in skipped; 121 frontend passed;
lint/mypy/TypeScript/build passed. Absolute percent-rate differences are explicitly identified
as percentage-point changes in author context; this does not alter verified numerical evidence.

Frozen build 2: `b632ebf831190de702c38511e32dcb3beeeabc6c`, same dependency/runtime fingerprints
and providers as build 1. Backend restarted before first creation; no code or configuration
changes until all six runs reached a terminal/intervention/paused checkpoint. Runs were created
and answered through browser controls; navigation to other sessions did not interrupt execution.
Third pair waited behind earlier work, then automatically started. Budgets were never reset.

| Repeat | Session | Run | Recorded outcome |
|---|---|---|---|
| Single 1 | agent-session-3a04a3eedaac4017be03bf862b10dae5 | agent-run-2fd9db044e9141fda129829047a77d4b | budget_exhausted, report sample description rejected |
| Multi 1 | agent-session-d49225c44d0546fbb9e477581e860619 | agent-run-6746f9c8ad6d4e21a7fcec03076ce963 | completed, review/freeze/reload/replay passed |
| Single 2 | agent-session-a862734ef0cf47359f110ad6388b5474 | agent-run-269171df774940d3846a41795edcbeef | waiting_for_user / no_progress, long title unchanged |
| Multi 2 | agent-session-5eb9f03ec9194e78a4353450d04729f7 | agent-run-24f687546718405cb95bed8420c557bc | waiting_for_user / no_progress, long title unchanged |
| Single 3 | agent-session-a8cf588b449b4af09ce8e93968ccceaa | agent-run-898e0e6fd37c4e678f482714adff58c0 | operator-paused after second review; title still over limit |
| Multi 3 | agent-session-5327a6da60ec4585a2c61f27a642d630 | agent-run-9c492d29a61f4db2b027c31feca36554 | waiting_for_user / invalid_model_contract after reproduction-evidence gap |

Exactly **one of six completed**. Semantic report pass alone is not acceptance when publication
findings remain, a run is paused, or user freeze/manifest/reload have not occurred.

| Repeat | AI calls | Known tokens | Fits | Candidates | Formal rounds | Nodes | Active seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single 1 | 24 | 333989 | 5 | 3 | 2 | 30 | 441.74 |
| Multi 1 | 11 | 115638 | 5 | 1 | 1 | 20 | 147.33 |
| Single 2 | 27 | 384239 | 5 | 3 | 3 | 31 | 456.10 |
| Multi 2 | 24 | 272584 | 4 | 3 | 3 | 31 | 352.90 |
| Single 3 | 17 | 200403 | 5 | 2 | 2 | 25 | 264.77 |
| Multi 3 | 13 | 151156 | 4 | 1 | 1 | 20 | 227.14 |

Unknown reviewer token use remains reserved. Both author checks passed on each current candidate,
but this did not predict formal approval. No failed/interrupted run has a frozen manifest.

Source hashes (same across this build's relevant repetitions): single World Bank
`sha256:6aba18a28470e61ca98c52227f500c1a908c2dbf91969ae9c9855ac69395dde9`;
multi IMF `sha256:95b4abbf00500641e905a016efea0ae3a16befcd6aed9df3cda384cf9c5530da` and
World Bank `sha256:774ba6fbd675717d4fa098db1843f1f05b40fb9afa964f423df8032b7fe82e37`.

Current output-set hashes, in table order:

- Single 1: `sha256:c05ea9d1c0aba632c6d8f876dfe5f19e2f0c6c26501da0b9810c39dfdf826094`
- Multi 1: `sha256:9d6f18e0234d6d1d30ca050e1cf011d88eb2c3282ff98a77092344bea2b8efb4`
- Single 2: `sha256:6847af4e5620d4cdb0ca7b8d09c08c25f8e60a11cbfcc40d72fcdc82040331de`
- Multi 2: `sha256:20f11575b341e387b3a91ac69483249042f3f6a18e1c2b3a7d72f63e4dbfc61c`
- Single 3: `sha256:17b4fec39427df5d7619a1b6f133753cccfa2a0a2b26e082745f262e83e4a3fa`
- Multi 3: `sha256:0289568cb1fe3826435de94a2605086f71a139e4353cabcf3f98f6e7b06774eb`

Multi 1: two checks passed, formal Codex semantic pass with only the interim-standard advisory;
browser acknowledgement/final confirmation, Completed after reload and frozen manifest download
link verified. Manifest `agent-blob-93e49ad543044cc18dc14085be6a6bae`, hash
`sha256:ed8e227820ca36abdfbfb46a84ed98adc0cd82c93b0eb9b06c2f4292650d7eed`.
Offline replay: five result/sample checks matched, zero external calls, integrity issues empty,
11 reconstructable requests. Diagnostic ZIP: 23 entries, ZIP integrity passed.

## Findings and classification

1. Single 1 author check falsely claimed a 132-character title exceeded 120; actual title is
   115 characters, unchanged in all candidates. Formal Codex later correctly rejected unsupported
   asymmetry/persistence claims and unauthorized arithmetic. Section revision then introduced a
   false sample statement: the baseline phase has ten observations per sex, not two/three.
   These are model author/check/revision quality failures, not absent data or connector errors.
2. Single 2/Multi 2 titles actually have 148/151 characters. Agent supplied up to 150 characters
   of objective as the title suggestion, while publication-v1 allows 120. Author admission did
   not enforce that rule, and section-only revision protects title. Three reviews correctly
   retained warnings, then no-progress stopped both runs. This is a code/contract mismatch.
3. Single 3 title has 123 characters. Initial formal review also found overclaimed persistence
   and misleading annual-path direction; normal section revision repaired semantics. The operator
   requested Pause through the browser; it took effect after the in-flight second review, retaining
   counters/checkpoint. Semantic pass is not completion; its remaining title warning was not waived.
4. Multi 3 reviewer could not substantiate preparation-once/manifest claims from code metadata
   alone. Review handoff omitted script contents and typed reproduction specification. It correctly
   requested upstream evidence; Output Editor failed its one repair and stopped. A later Pause
   probe found no Pause control because intervention had already stopped it; no pause command
   occurred. This is an evidence-handoff gap, not missing observations.
5. At delivery ceilings, the waiting/no-progress UI still offered an impossible intervention.
   Follow-up guards must reject such commands without resets and direct to an explicit linked run.

## Follow-up contract fixes (not retroactive cohort passes)

Enforce report title length during author contract validation/repair before persisting a draft;
bound Agent's suggested title by the same publication policy. Supply author/reviewer with owned,
checksum-verified generated scripts, typed recipe/hash and explicit not-yet-frozen manifest state;
static inspection is not numerical execution. Reject Resume/intervention when a stopped delivery
has exhausted its fixed rounds, without preventing a legitimate general-budget extension for
an otherwise unfinished valid delivery. Preserve all six original checkpoints and evidence.
All six diagnostic integrity checks returned no issues. Reserved unknown-token amounts in table
order: 360000 / 120000 / 360000 / 360000 / 240000 / 120000. These are not zero consumption.
Follow-up regression: 362 backend passed / 4 opt-in skipped, 122 frontend passed; lint/mypy/
TypeScript/build passed. Author-check v6 adds exact title counts; title repair tests cover success
and two invalid responses with no fallback. Reproduction tests cover checksum, ownership and
context-budget failure before any model call.

## Follow-up live smoke (separate build, not cohort replacement)

Build `0666f699232e8b63891cff4fbca13af911d73407`, same providers/dependency fingerprints;
backend restarted before creation. One single-source and one multi-source journey used ordinary
browser controls and the same research frames. These verify integration, not the repeat-cohort gate.

- Single: session `agent-session-cd87dd08951c4cb883ebe7ad2f78874f`, run
  `agent-run-868a9d4dd0a54082861139d5015152cf`. Title 68 characters; both self-checks pass,
  Codex formal/semantic pass (only placeholder advisory), explicit browser acknowledgement/freeze,
  reload Completed and manifest link verified. Four result/sample hashes matched in offline
  replay, zero external calls, no integrity issues, 11 reconstructable requests.
  11 model calls, 112634 known tokens, 120000 unknown tokens reserved, 4 fits, 1 candidate,
  1 formal round, 18 nodes, 165.93 active seconds. Output set
  `sha256:ee42f02935f1a5b43df2a15b77ab48f260e8dd0fc4db4719a74301080ba1aa07`;
  manifest `agent-blob-bcbef80fea5a4608ad09d9904f5d86a0`, hash
  `sha256:1081b3d88c109b4d97e80cf2747dc891151c548f3b2913a5c3a5546d41dd65fc`.
- Multi: session `agent-session-a2fa0cecf5e1431cae43fc4c90d9e88d`, run
  `agent-run-0cbaab109dcc494c976d20357397b263`. Title 96 characters, first check passed;
  second check incorrectly claimed chart-axis arithmetic mismatch. Output Editor proposed a
  figure caveat and report disclosure, then report revision failed after one repair with
  'removed an evidence reference that must be preserved'. Stopped waiting_for_user,
  13 calls, 255304 known tokens, no unknown reservations, 5 fits, 2 candidate attempts, no formal
  reviews, 22 nodes, 264.65 active seconds. No freeze/manifest or pass. Current set
  `sha256:141398032b497e83b5e7f67b5ccc0e2a7e472ab15e7fc4bb4d32960398e7d859`.

Read-only SVG proof: metadata minimum 33.184085, maximum 90.421028, top 64, plot height 364,
tick-text baseline offset 4. Text baselines 159/250/341 correspond to gridlines 155/246/337;
`maximum - (gridline_y - top) / plot_height * (maximum - minimum)` gives **76.11 / 61.80 /
47.49**, exactly the rendered labels. Self-check's claimed 75.76 / 58.74 / 41.71 are model
arithmetic errors, not a chart/data bug. Neither coordinates nor values were edited to satisfy it.

Further code diagnosis: chart patch regeneration rebinds report evidence refs to a new chart ID,
but did not rebind the directive's preserved refs. Thus the report-revision failure was an
impossible stale directive, not necessarily an author deleting original evidence. Follow-up
translation now updates directive IDs/hashes with the same verified replacement map. The new
joint chart/report regression also exposed the formal-report fast path discarding simultaneous
visual patches; it now carries validated reviewer patches and directives together in one candidate.
Original review/proposal history remains unchanged. The offline integrated test passes two review
rounds and verifies new chart IDs in report refs plus old IDs retained in original history.

Operator safeguard: a combined confirmation/inspection command was blocked over suspected
session mix-up. Read-only URL/run/hash checks proved cd87dd was the approved single-source run;
the subsequent guarded confirmation targeted that exact page only. No failed multi-source output
was confirmed, and no database/artifact edit or alternative freeze API bypass was used.

Final follow-up regression: 363 backend passed / 4 opt-in skipped; 122 frontend passed;
lint/mypy/TypeScript/build passed. The joint-ref fix is covered by the integrated offline test,
not a new real-model completion. Remaining priority: model arithmetic/semantic self-check errors
and author/revision quality; a fresh full fixed-build cohort is still required.

A6 remains Experimental. Its fixed-version three-single/three-multi completion gate is **not
passed**. Follow-up smoke tests, if successful, verify those repairs only; they do not substitute
for a new complete fixed-version repeat cohort. Author/reviewer semantic reliability remains open.
Workflow Phase 0–3 and deferred Phase 4 acceptance are unchanged.
