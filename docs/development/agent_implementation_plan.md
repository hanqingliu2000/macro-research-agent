# Agent autonomous execution and diagnostics implementation

Approved: 2026-10-06. Base: 70fd7a7. Experimental; Phase 4 remains deferred.

Agent clarification submission authorizes autonomous registered execution under a versioned
run envelope. Final delivery is reviewed by Codex-local and frozen only by the user. Workflow's
three approval gates and data isolation remain enforced.

## Milestones

- [x] A0 implementation: immutable Plan revision, compact default tables, evidence/reference consistency,
  analysis window contracts, code capability checks and recursive diagnostic redaction.
- [x] A1 core: Agent-owned SQLite state graph, immutable snapshots/envelopes, task leases,
  transactional audit/budget ledger, payload storage, JSONL recovery and diagnostics APIs.
  Repository diagnostic queries/bundles are implemented; HTTP admission is integrated with A2/A6.
  Contract/property tests cover lease claims, stale completions, restart recovery, idempotency,
  concurrent budget reservations, unknown token retention, redacted payloads and context replay.
- [x] A2 implementation: real DeepSeek clarification/planning with source-index and admitted capabilities,
  strict task routes, bounded repair and complete response/context receipts.
- [x] A3 implementation: eight admitted connector slices and local CSV/JSON/XLSX; baseline-preserving
  complete-case (5%), single-gap interpolation (20 observations/5%) and winsorization
  (100 observations, fixed 1%/99%, max 5% changes), with holdout isolation.
- [x] A4 implementation: typed registered analysis, explicit sample windows, predeclared evaluation,
  candidate comparison, bounded route revision and intervention.
- [x] A5 implementation: evidence-bound chart/report/package authoring, two author checks per handoff,
  coordinated revisions, three formal reviews, user freeze and reproduction manifest.
- [x] A6 implementation: HTTP frontend, cursor-based/coalesced SSE, monotonic reloads,
  controls/history/diagnostics, paged preview and offline numerical replay.
- [ ] A6 full repeat-cohort acceptance: all three single-source and three multi-source outcomes
  must satisfy final delivery criteria under a fixed release version. The b632ebf cohort finalized
  one of six; 9599d39 initially completed three before HTTP 402. After API restoration five original
  runs completed, the exhausted sixth stayed cancelled and a linked seventh delivered its scenario.
  Historical development successes and later smoke tests do not replace
  this gate. Failures/interventions/operator pause remain in the log, not reclassified as passes.
  The fresh `863c07e` six-run cohort completed five and retained one failed report-handoff /
  Output Editor recovery. Single 2 was not replaced. The strict gate remains open; see
  `../testing/browser-runs/2026-10-07-agent-fixed-version-acceptance.md`.

### Next acceptance corrections

- [x] Carry hash-bound chart/table specifications and necessary content/inspection receipts to
  Report Author and the separate semantic Reviewer; test claims about series/indicator/unit/axes
  against actual current artifacts, not metadata alone.
- [x] Distinguish missing handoff/upstream prerequisites from schema-repair failures. Do not spend
  model repair or suggest retry for a rejected attempt to conceal absent evidence. Keep hard limits.
- [ ] Separate failed correction attempts/review checkpoints from distinct candidate versions in UI.
- [ ] Harden multi-session initialization/SSE: bound subscriptions and pending refreshes, avoid
  expensive all-run projections on every page and add load/response-cancellation tests.
- [ ] After corrections, run a new unchanged-build single-source ×3 / multi-source ×3 cohort.

Implementation follow-up: additive `presentationEvidence` reaches both Report Author and the
separate Codex semantic Reviewer in Workflow and Agent. It contains owned-file/spec/data hashes,
full bounded SVG/spec content, verified CSV headers/specs and explicitly limited workbook
file/spec evidence. Revisions rebuild it from current artifacts; reproduction inputs use their
separate evidence port. Missing/corrupt/foreign/oversized evidence fails closed before AI calls.
`presentation_handoff_incomplete` and `requires_upstream_stage` stop Agent delivery before Output
Editor/format repair. Recovery advice `repair_evidence` blocks Resume, scope replies, retry and
re-review while preserving the original run. UI explains the required evidence repair. Regression:
431 backend passed / 4 opt-in skipped, 130 frontend passed, lint/mypy/build passed. Recorded-provider
tests reproduce the successful bridge, stale-reference replacement and failed prerequisite path;
they do not close the fresh real-model six-run acceptance gate. History/SSE corrections remain open.

Fixed-cohort evidence: five successful runs passed two author checks, actual Codex review, freeze,
reload, manifest hash verification and offline replay. All six replayed five result/sample hashes
and passed diagnostics; zero budget breaches/false freezes. One known handoff gap stopped at three
Output Editor calls after one explicit user retry. Regression: 409 backend / 4 optional skips,
128 frontend, lint/mypy/build passed. No code fix was made inside the cohort. A6 is not accepted.

Implementation checkmarks are not live acceptance. A6 requires three completed single-source
and three completed multi-provider browser runs; all failed development attempts remain retained.
Earlier automated evidence before the planning/recovery follow-up: 380 backend passed / 4 opt-in skipped;
122 frontend tests, lint/types/build passed. Regression includes scoped two-round inspection,
controller-owned editor schema, hard-stop command rejection and linked-run recovery without outputs.
Follow-up contracts cover pre-persistence title repair, owned/hash-bound reproduction inspection
and non-resumable delivery ceilings. Actual Author/check/Reviewer semantic reliability still needs
improvement; budget/permission/freeze safeguards did not permit incomplete results to finish.
Latest two-scenario smoke completed the single-source journey, but multi-source stopped on a
model arithmetic false positive and stale joint-revision refs. Joint chart/report patches and
directive ref translation are now covered by an integrated regression. This is not six new
successful fixed-build runs; the acceptance gate remains open.
Live evidence is recorded separately in `../testing/browser-runs/2026-10-06-agent-a6-reacceptance.md`.
The next fixed-build cohort is tracked in `../testing/browser-runs/2026-10-07-agent-a6-reliability.md`.
Its prerequisites include read-only geometry calculation receipts, evidence-bound self-check
findings/repair, confirmed scope and typed-result fact handoff, plus section-only report edits.
These reduce arithmetic/copy failures without waiving true defects, semantic review or budgets.
After user-confirmed API restoration, two stopped runs recovered within unchanged budgets and
one exhausted run used normal Cancel → Start linked research run. Six scenario deliveries passed
author checks/Codex/freeze/reload and offline numerical replay. Original failed parent/counters
remain intact: original cohort 5 completed / 1 cancelled plus one successful child, not a clean
6/6 original cohort. Strict fixed-cohort acceptance stays open; restoration/linked-run closure
is verified separately. That earlier build could still trigger unnecessary Planner input for
post-acquisition metadata; the later `863c07e` cohort had no such intervention in all six runs.

Real single-source and two-provider generation → self-check → Codex approval → user confirmation
→ frozen manifest → reload → offline numerical replay have passed. Single case used 3/3 candidates
and 3/3 formal rounds; two-provider case used 2/3 candidates and 1/3 formal rounds. The fixed
three-times-each reliability exit gate stays open; see the complete browser-run log.

## Defaults

2026-10-07 follow-up implementation: planning separates after-acquisition metadata/coverage
checks from true human/access prerequisites; acquisition assessment persists snapshot-bound
references. Failure recovery classifies DeepSeek credit/access/transport/contract errors, presents
actual remaining limits, and offers a typed retry without changing research decisions or task
inputs. Billing/access/configuration confirmation, existing-key validation and non-resettable
task/phase/candidate/review limits apply on the server. Explicit execution-budget extension is
available even for a waiting failed task. Historical failures remain intact. Offline evidence:
409 backend passed / 4 opt-in skipped, 128 frontend passed, lint/mypy/build passed. The next
acceptance task remains a fresh unchanged-build single-source ×3 / multi-source ×3 cohort;
these regressions are not six new real-provider completions or A6 acceptance.

2 clarification batches; 3 routes/analysis candidates/output candidates; 3 transport attempts
per task and one format repair within that limit; 2 author checks; 3 formal reviews;
40 model calls, 1,000,000 tokens, 80 task nodes, 16 fits, 300 physical connector requests,
45 active minutes, concurrency 2. Counters survive pauses, restarts, revisions and failure.
Two successive non-improving corrections interrupt the run. Budget enlargement is user-only.

## Diagnostics

All successful, failed, rejected, cancelled and recovered attempts are retained, correlated by
session/run/task/node/attempt/trace/span/command IDs. State and budget changes commit with audit
events. Prompts are reconstructable from templates and immutable context refs; final model
responses (including malformed JSON), repairs, stacks and tool receipts live in checksum-bound
redacted payload storage. Never persist hidden reasoning, credentials or redundant observation
rows in ordinary trace. Retain until explicit deletion, with local diagnostic bundles and
network-free replay. Missing evidence is an integrity failure, never a successful step.

## Acceptance

Contracts, graph properties, leases, concurrent/idempotent commands, transport/schema/provider
faults, budgets, statistical boundaries, pause/cancel/late results, restart/cross-day recovery,
log redaction/recovery/replay and mode isolation must pass. Single/multiple-provider browser
journeys each repeat three times; all attempts are logged. A successful run requires Codex
approval, explicit finalization, manifest and reload. Each milestone is separately committed
and synced, with evidence distinguishing fixtures from real-provider acceptance.
