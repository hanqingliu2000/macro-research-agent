# Agent Mode development contract

2026-10-06 amendment: real autonomous implementation is tracked in
`agent_implementation_plan.md` (ADR 0033). Clarification submission grants a bounded versioned
run envelope. Registered execution and statistical cleaning proceed autonomously inside it;
scope/budget expansion and final freeze require user commands. Agent has independent durable
storage and full correlated diagnostic/audit evidence. The HTTP adapter is now implemented.
The legacy localStorage/mock flow is test-only; instant demo completion is not real evidence.

2026-10-07 fixed-build acceptance: `863c07e` completed 5/6 original browser journeys (single 2/3,
multi 3/3). One semantic report could not substantiate chart-compliance statements from its narrowed
artifact-metadata handoff; attempted concealment was rejected and recovery exhausted the task's
three physical calls without freeze. Strict A6 acceptance remains open. Hash-bound chart/table
inspection must reach report roles as well as the visual reviewer; this correction is planned,
not implemented by this acceptance run. See the fixed-version browser log.

Follow-up implementation now supplies `presentationEvidence` to author and semantic reviewer,
rebuilt through Agent-owned reads after every presentation revision. Exact SVG/spec, CSV header/
spec and limited workbook file/spec receipts retain artifact/spec/data hashes and context caps.
These are inspection evidence, not approval or proof of every workbook cell. Numerical evidence
continues through complete dataset/model-result grants. Missing evidence stops before Output
Editor; `repair_evidence` advice rejects scope-answer/Resume/retry/re-review shortcuts. Preserved
failed and completed runs are not migrated into passes; a new fixed-build cohort is still required.

## Product flow

1. The user creates an Agent session with a research question and optional XLSX, CSV or JSON files.
2. Local inspection stores the attachment and issues an Agent-owned, read-only checksum-bound grant
   so the model can inspect its actual values.
3. The model asks bounded clarification (at most two batches, including the first).
4. Submitting answers creates a versioned authorization envelope. Agent controllers validate
   scope, registered capabilities, dependencies, hashes and budget before autonomous execution.
5. The final chat response contains conclusions, caveats, charts, data previews, downloadable
   artifacts and copyable Python/Stata code.
6. Codex-local must approve the current hash-bound report/artifacts after two author checks.
   The user confirms the final delivery before freezing a manifest.
7. Follow-up explanations are read-only. New research creates a linked new run; neither operation
   mutates Workflow sessions or frozen scientific results.

## Status

| Status | Meaning |
|---|---|
| requested | Question and attachment references are captured. |
| clarifying | User input is required before routing. |
| queued | Authorized work is waiting for a worker. |
| running | Current phase identifies route/acquire/prepare/model/output/check/review work. |
| waiting_for_user | Scope/data/error intervention awaits a concrete answer. |
| paused | No new tasks scheduled; checkpoints/counters retained. |
| budget_exhausted | Partial results retained; no completion claim. |
| awaiting_final_confirmation | AI-approved current delivery awaits explicit human freeze. |
| completed | User-confirmed artifacts and reproduction manifest are frozen. |
| failed | A classified failure stopped the run. |
| cancelled | The user stopped the run. |

## Nodes

Agent node kinds are independent of Workflow node kinds:

- agent_request
- attachment_inspection
- clarification_batch
- route_decision
- data_acquisition
- transformation
- model_execution
- report_generation
- final_response

Node records use the common operational fields (ID, status, attempt, timestamps, dependencies,
artifact references and errors) but are stored in the Agent repository only.

## Frontend routes

- /agent: create an Agent session and list only Agent sessions.
- /agent/:agentSessionId: isolated Agent chat and results.

Workflow routes remain / and /sessions/:sessionId. Agent and Workflow providers are mounted in
separate route trees. Neither provider is an ancestor of the other.

## Agent Workbench UI contract

Agent Mode uses the shared Slate Workbench chrome but adapts it only from Agent state:

- the Activity Bar switches between Workflow and Agent without converting sessions;
- Agent Explorer lists only Agent sessions from the Agent provider;
- Home presents an editor-style question composer and optional attachment list;
- Chat presents a labelled message log beside high-level autonomous route steps;
- clarification is a bounded form inside the conversation;
- the final result contains conclusion, chart, semantic data table, copyable code, artifact list,
  sources and caveats;
- redundant Explorer headings/footers and the status bar are hidden; Agent status remains available
  in Agent-owned session and route surfaces.

Shared UI modules are stateless and live under `frontend/src/ui`. They cannot import Agent or
Workflow domain/state modules. Agent-specific surfaces live under `frontend/src/agent`, are scoped
below `.research-workbench-agent`, and never read Workflow context.

The interface provides a skip link, visible keyboard focus, textual progress states, an announced
file validation error and a reduced-motion path. Narrow-screen forms use 16 px control text and the
progress panel stacks above the conversation. Automated UI tests use DOM and accessibility
assertions, not model-driven browser screenshots.

## API namespace

Implemented Agent endpoints are isolated under /api/v1/agent:

- GET /sessions
- POST /sessions
- GET /sessions/{agent_session_id}
- GET /sessions/{agent_session_id}/runs/{run_id}
- POST /sessions/{agent_session_id}/runs/{run_id}/attachments
- POST /sessions/{agent_session_id}/runs/{run_id}/commands
- GET /sessions/{agent_session_id}/runs/{run_id}/events (SSE, sequence cursor)
- GET /sessions/{agent_session_id}/runs/{run_id}/artifacts/{artifact_id}

Full Agent trace is reserved for
`GET /api/v1/admin/agent/sessions/{agent_session_id}/runs/{run_id}/trace`, not ordinary chat.
Diagnostics, attempt detail, checksum-verified payloads, debug bundles and network-free replay
are read-only sibling routes. Commands include idempotency key, expected version and actor=user:
start, answer_clarification, pause, resume, cancel, resolve_intervention, extend_budget,
finalize, message and new_run. Duplicate commands do not reset budget or rerun work.

`retry_review` is a user-only, artifact-hash-bound command for a new review of the unchanged
current delivery. It consumes remaining formal rounds and two new author checks; it never
resets attempts or adds a candidate merely for reassessment. Review history remains accessible.
`GET /sessions/{id}/runs/{run}/data-preview?offset=&limit=` pages an owned active snapshot.
The normal UI shows actual period/value/unit first, source/indicator details and data pages.

During pre-handoff self-correction, an author may propose `report_directives` for current report
section IDs only. The controller requires envelope-authorized report delivery, unchanged evidence
refs and no upstream-gap concealment. Formal-review findings still use Codex directives. Both
paths share the same three-candidate/three-review limits and cannot touch data/results/code.
When a candidate changes figures/tables and report sections together, both reviewer patches and
directives are applied; directive preserved IDs/hashes use the same verified replacement map as
report refs. Original review/directive history stays immutable. A report-only fast path must not
discard simultaneous visual patches or ask the new report to preserve superseded artifact IDs.

Agent author-check protocol `agent-author-check-v7` separates package semantic inspection
(round 1: reports/evidence/model results use the report publication guideline) from rendered
chart/table structure and artifact ID/name/hash mapping (round 2). Visual rules apply only to
charts/tables, not report headings. Both rounds read authorized full data and remain real model
calls; formal Codex semantic and pixel review is still required. Neither round grants approval.
The controller exposes current editable IDs, fixed package source note and field limits in the
Output Editor schema, then independently validates every returned patch/directive. Export
manifest includes candidate status/lifecycle; snapshots/model results have separate identities.
Table specifications are keyed by file ID, allowing CSV/XLSX representations of one table.
Chart wording receives all rows of the exact indicator/entity/unit selection, not unrelated
package indicators. Delivery-round exhaustion offers linked-run recovery, not budget extension
that cannot increase the fixed three-candidate/three-review caps.
Exact report-title character counts are supplied to self-checks; title length is enforced by
author contract validation/its one repair before persistence. Agent title suggestions use that
same publication limit, avoiding unrepairable long headings under section-only revision.
Author and Reviewer receive `agent-reproduction-evidence-v1`: owned checksum-verified generated
scripts (40 KB each maximum), typed recipe/hash and explicit not-yet-frozen manifest status.
Scripts are inspection evidence only, never executable authority or a replay-success claim.

V7 structural inspection independently rebuilds the typed chart selection from authorized rows,
verifies SVG/spec/dataset hashes, metadata, tick labels and series coordinates, and persists a
`chart-geometry-receipt-v1` through the existing `output.review.structural` capability. Receipts
are read-only calculation evidence, never a reviewer fallback or approval. Native failure or
unverifiability cannot be approved by an AI pass. Author findings bind current artifact IDs and
evidence refs; a numeric defect contradicting passing receipts triggers the same single bounded
contract repair, then stops if still invalid. Full final responses/repairs remain inspectable.
Both real DeepSeek self-checks and formal Codex approval remain mandatory. Compact result facts
project per-variable/window counts and existing endpoint results, with references to complete
observed paths; they do not invent new comparisons or tests. Scope controls travel to self-checks
and Output Editor rather than relying only on the original exploratory question.
Granted numeric scalars retain snapshot round-trip precision; dates/nulls remain JSON-safe.
Ten-decimal pandas truncation must not change AI-visible values or create false receipt conflicts.

Agent DeepSeek report revision uses `report-section-edits-v1`: exactly the approved section IDs
and associated claim IDs, with body/statement/uncertainty/limitation text only. The controller
copies original headings, IDs, title, citation/evidence/artifact refs and untargeted text and
validates the assembled ReportDraft. Global limitations are editable only under a limitations
directive. One repair and all original call/candidate/review ceilings apply. Workflow's existing
full-draft revision contract stays compatible; no production provider fallback is introduced.

`task_attempt_limit` is a non-resumable hard stop, including historical waiting interventions.
`resume`/`resolve_intervention` reject it without changing state or budget. The UI retains
diagnostics and partial results and directs users to an explicit linked new run (cancel first
for legacy waiting runs). Failed runs without outputs can still enter a linked-run request.
`delivery_round_limit` similarly rejects Resume/intervention for a stopped delivery at its fixed
candidate/review ceiling, including legacy `no_progress` waiting states. A general token/time
exhaustion on an otherwise unfinished valid candidate remains eligible for user budget extension.

Workflow endpoints move under /api/v1/workflow when implemented. No endpoint accepts session IDs
from both modes.

## Autonomous route contract

After-acquisition metadata/status/vintage/coverage checks belong in optional
`AgentTaskPlanV1.acquisition_checks`, not unanswered human decisions. They are assessed using
actual acquired rows and source metadata receipts, with persisted assessment/snapshot refs.
Missing metadata may be disclosed, never invented. Choice of methodology/vintage, unconfigured
credentials and unadmitted sources remain genuine prerequisites. Safe normalization uses a
neutral planning facade; Agent does not import Workflow state or access its sessions.

Call failures use an explicit user-only `retry_failed_task` command rather than a fabricated
research-scope answer. Billing/access/configuration requires confirmation of restoration; absent
runtime credentials cannot be confirmed away. Inputs, answers, failed attempts and used/reserved
budget remain unchanged. Derived recovery advice displays remaining task calls/attempts, phase
attempts and general/candidate/review limits; exhausted hard ceilings require a linked run.
General execution-budget extension does not lift those ceilings. Historical generic errors stay
generic; complete redacted request/response evidence remains inspectable in diagnostics.

The AgentRouter returns a typed decision containing:

- selected registered connector IDs or attachment IDs;
- normalized indicator/entity/time selections;
- deterministic transformation specifications;
- allowed model specifications;
- report and artifact specifications;
- concise assumptions and unsupported requirements.

Policy validation occurs before execution. Invalid capability IDs, arbitrary URLs, free-form code,
unavailable licensed sources and data access outside an Agent-owned hash-bound grant are rejected.

Phase 1E introduces the shared stateless `CapabilityRegistry` and `SkillRegistry`. Agent Mode may
autonomously propose routes through available registered handlers, but stores its route decisions,
invocations and approvals only in the Agent repository. A `planned` placeholder cannot be selected
as executable. Provider-native function calls are narrowed to the current Agent task allowlist.

Agent stage AI is not limited to attachment schemas or samples. It may page/filter/aggregate across
complete relevant attachment and result snapshots through the same stateless data-access contract,
but grants and receipts are persisted only in the Agent repository. It cannot read a Workflow
grant, filesystem path, credential or arbitrary query target. Licensed remote disclosure fails closed.

Agent-produced charts/tables use the same deterministic renderer and may request the same structured
Review AI. Remote review follows Agent-session data-classification policy and records the render and
underlying snapshot hashes; it never reads a Workflow artifact or uses a browser UI screenshot.

## Frontend trace boundary

The Agent chat shows only:

- Clarify request
- Inspect inputs
- Route approved tools
- Run analysis
- Build research package

Full route decisions, prompts, tool parameters, hashes and execution logs remain in backend
administrative trace and reproducibility exports.
