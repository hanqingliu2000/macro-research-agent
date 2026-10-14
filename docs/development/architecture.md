# Architecture

## Shape

The application is a local modular monolith with explicit ports:

       shared Research Workbench chrome
          /                         \
    Workflow UI adapter       Agent UI adapter
         |                         |
    Workflow API       Agent API
         |                 |
 durable state graph   authorized task graph
         |                 |
    gated executors    bounded autonomous executor
          \               /
       shared stateless capabilities
      /       |        |        \
 connectors  data    models   reporting
                |
     local files / approved provider APIs

LLM providers are separate ports used for clarification, planning, typed stage proposals,
artifact authoring and output review. They receive task-relevant real data through a stage-specific,
read-only grant bound to an immutable upload checksum or dataset snapshot hash, plus an allowlist;
they never receive unrestricted application tools, filesystem paths, credentials or generic SQL.
An approved visual-review request may send the exact rendered analytical artifact/hash and its
underlying data through the same disclosure policy under ADR 0012 and ADR 0014.

Workflow and Agent session stores are intentionally separate. Shared capability packages cannot
read either session type. See ADR 0006 and repository_structure.md.

The frontend shares only stateless Workbench chrome, tokens and SVG assets. Each adapter reads its
own provider and formats display props for the common shell; the common shell cannot read session
state directly.

## Workflow state graph and derived state machine

The durable typed state graph is the Workflow source of truth. Research intent, immutable
specifications and results, capability executions, reviews, attempts and checkpoint approvals are
nodes connected by typed dependency, consumption, production, authorization, review,
supersession and invalidation edges. `active_stage`, status, reachable routes and current refs are
cached projections; routes and chat never set them directly. See `state_graph.md` and ADR 0013.

The user-facing status projection is:

1. CLARIFYING: ask a bounded set of questions inside the Plan route.
2. PLAN_REVIEW: edit the current Plan and resolve country groups.
3. ACQUIRING: call only registered local-file or provider connector functions after Plan Next.
4. DATA_REVIEW: inspect provenance, prepare data or replace the active dataset through controlled
   XLSX round trip.
5. PIPELINE_EDITING: configure ordered typed transformations and separate model jobs.
6. PIPELINE_RUNNING: execute only after the user selects Run.
7. OUTPUT_GENERATING and OUTPUT_REVIEW: build, preview and selectively revise artifacts.
8. COMPLETED: freeze a reproduction manifest and artifact hashes.
9. FAILED or CANCELLED: retain trace and partial artifacts.

The routed stages are Plan, Data, Transformation and Output. See workflow_stage_protocols.md.
Transitions into ACQUIRING, PIPELINE_RUNNING and COMPLETED require recorded human approval.

Session status is a derived workflow cursor. `GraphService` validates commands and target hashes,
computes readiness/invalidation, moves active pointers transactionally and preserves prior attempts.
See `workflow_status_and_routes.md` for the status vocabulary and `state_graph.md` for the
authoritative execution model.

## Data layers

- raw: immutable provider response or uploaded file, checksum-addressed.
- normalized: a provider-neutral long-form schema.
- analytical: ordered typed transformations plus independently targeted model jobs.
- results: model outputs with diagnostics and exact inputs.
- publication: workbooks, figures, tables, narrative and code packages.

## Key boundaries

- Routes validate and delegate; they do not contain domain logic.
- `GraphService`, not an HTTP route, UI reducer, chat thread or AI provider, owns graph mutation and
  derives execution readiness.
- Connectors own network access, provider semantics and raw provenance.
- Cleaning operations are declarative and replayable.
- Model runners accept reviewed specifications, not arbitrary code.
- Report Authoring builds a typed claim/evidence ledger from approved results and a versioned style
  guide; deterministic rendering alone writes the report file.
- `CapabilityRegistry` and `SkillRegistry` describe versioned functions and runtime orchestration
  bundles. A runtime skill can compose only registered handlers; a placeholder has no executable
  handler and cannot report success.
- AI ports return schema-validated proposals. Workflow execution requires the applicable human
  gate and expected-stage/hash validation. Agent's controller validates the immutable run envelope,
  dependencies, input hashes and remaining budgets before applying a registered action; scope or
  budget expansion and final freeze remain explicit user commands.
- `WorkflowModelDataAccessService` issues deterministic read-only grants and serves actual rows in
  bounded pages from one session-owned upload or immutable snapshot. Remote adapters must pass the
  provider/data-classification disclosure check before values enter a request.
- Chart/table authoring produces typed specifications. Deterministic renderers create final files;
  visual AI reviews direct artifact renders and returns typed patches rather than drawing pixels.
- Report Review is a separate Codex-local role. It returns findings and section-bound directives,
  never prose or mutations. User-approved directives may ask DeepSeek to rewrite only named report
  sections; missing evidence returns to Data or Transformation.
- Trace records reference immutable artifacts by checksum.
- The standard frontend shows concise research-step progress. Full trace events remain a backend
  administration and reproducibility concern.

## Storage

The storage design is local filesystem plus SQLite metadata. Workflow sessions, projections, nodes,
idempotency records and durable trace events live in a Workflow-only SQLite repository behind a
Workflow-owned port. Redacted JSONL trace files are materialized beneath the ignored
`runtime/workflow/sessions/{id}` path and missing records are recovered from SQLite at startup.
Canonical dataset versions are immutable Parquet files beneath the same session boundary; SQLite
records their hashes, schemas, lineage, Data operations, typed Pipeline runs and controlled
round-trip packages/imports. Analytical snapshots use the same checksum-addressed storage boundary
as normalized data but retain their operation ID and parent snapshot reference.
Agent uses a separate SQLite repository and `runtime/agent` files for its authorization envelope,
task graph, checkpoints, leases, immutable data/results/artifacts, budget reservations and complete
redacted diagnostic payloads. Critical state, budget and trace updates commit transactionally;
JSONL is a recoverable projection rather than a second state store. Restart preserves prior
attempts and budgets and pauses recoverable work rather than silently rerunning it. This runtime
is implemented but remains Experimental: the latest fixed-version cohort completed five of six
required journeys, and a new six-run acceptance is outstanding. The ports allow another metadata
or object store to replace the local implementation without changing HTTP or domain contracts.

## AI orchestration shape

Workflow proposal path:

       stage context + data-access grant
                  |
       task-specific AI port
                  |
       validated proposal graph node
                  |
        human review / approval
                  |
       graph readiness + checkpoint
                  |
 capability + skill policy resolver
                  |
       registered executor/renderer
                  |
 immutable result + trace + lineage

For Output, deterministic preflight and a direct artifact render feed `OutputReviewPort`. Its
structured findings return to the human review surface; only an approved typed patch can re-enter
the renderer. Every proposal, invocation, render and review is addressable in the state graph. See
`state_graph.md` and `ai_capability_orchestration.md`.

Agent uses the same typed capability and evidence boundaries, but a validated, user-authorized run
envelope replaces per-stage Workflow approvals. Its controller schedules bounded tasks, retains
all attempts, pauses for decisions outside that envelope and never grants itself final freeze.
Two author checks precede formal review; charts, tables and reports share at most three formal
rounds. See `agent_mode.md` and `agent_implementation_plan.md` for Agent state and budget contracts.

The data-access grant is not a sample contract. The initial request may contain one bounded page,
and the provider can page across the complete relevant dataset. Each access is hash-bound and
auditable; observation values are not redundantly copied into trace records. Typed filter and
aggregate reads are implemented with bounded, validated specifications and receipt-only audit
records.

## Deployment profiles

Development configuration and a future approved remote profile are different trust domains. The
provider-neutral ports and adapter source remain reusable, but the current product/development
Plan, Data and Analysis composition root binds only DeepSeek. The public capability API and
environment cannot select the deterministic test fake or generic OpenAI adapter, and missing
DeepSeek credentials fail startup.
Codex-local is the formal visual/semantic reviewer. Its locally authenticated client may send
approved context and direct artifact images to its model provider; "local" does not mean offline
inference or that analytical values never leave the computer. Missing credentials, login or a
provider capability fails closed, without deterministic production fallback.

A future approved remote profile would independently bind provider identity, endpoint, model/task
allowlists, data classification, disclosure, retention and budgets. No profile choice can turn a
handler-less capability into an executable one or change either mode's authorization rules.
Provider-specific packaging and live acceptance remain deferred. See `provider_profiles.md`.
