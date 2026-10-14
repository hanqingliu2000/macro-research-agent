# Durable research state graph

The durable research state graph is the source of truth for Workflow execution. The four routed
stages are user-facing projections over this graph; chat history, page location and `active_stage`
are not the workflow itself.

Phase 1E-0 now persists normalized graph nodes, typed edges, attempts, compatibility checkpoints
and active pointers, with startup backfill from existing sessions and administrative read APIs.
`GraphService` is the transactional command boundary for every current stage mutation, and public
Workflow state is derived from the graph before live AI is allowed to orchestrate capabilities.
Stage APIs accept only typed commands. Their owning service calculates the domain target state and
`GraphService` compiles an internal `GraphTransitionPlan` containing a checksum-bound compatibility-
data patch. The repository applies that plan atomically, validates the resulting graph, then
overwrites the legacy status, active-stage and reached-stage cursor from
`WorkflowProjectionService`. No API accepts a client-computed session.

## Graph objects

### Research node

A `ResearchNode` represents one typed unit of intent, execution, review or approval. It contains:

- node ID, kind, schema version and owning Workflow session;
- authority: record, proposal, execution or review;
- lifecycle state and attempt number;
- immutable input snapshot/artifact/specification references;
- immutable output references after completion;
- capability, function, model, renderer, reviewer or runtime-skill ID/version when applicable;
- required checkpoint and authorization reference;
- created/started/completed timestamps and classified error;
- concise user-visible rationale, never private chain-of-thought.

Node kinds include clarification, Plan, geography resolution, acquisition, preparation, external
round trip, stage handoff, transformation, model, capability invocation, artifact generation,
deterministic preflight, visual review, revision and manifest freeze.

### Edge

Edges are typed and durable:

- `depends_on`: downstream work requires a current upstream node;
- `consumes`: node reads an immutable snapshot/specification/artifact;
- `produces`: node created an immutable output;
- `authorized_by`: execution is covered by a checkpoint/hash;
- `reviews`: a preflight or Review AI report targets an artifact/specification;
- `supersedes`: a newly accepted node replaces a prior current node;
- `invalidates`: an accepted change makes a dependent result stale.

Edges reference IDs and hashes; they do not duplicate dataset rows or artifact bytes.

### Snapshot and active pointer

Plans, datasets, pipeline specifications, model results, artifact specifications, artifacts and
review reports are immutable snapshots. A small projection maintains the current pointer for each
logical role. Undo or upstream editing changes pointers and creates graph events; it never rewrites
or deletes old snapshots.

## Core invariants

1. A completed node's input/output references do not change.
2. Only a validated command may add nodes, edges or move a current pointer.
3. A node can run only when every required dependency is current and its checkpoint targets the
   same input/specification hashes.
4. Viewing a route or artifact never changes the graph.
5. Accepting an upstream change propagates `stale` only through dependent descendants and preserves
   all prior results for inspection.
6. Stale or superseded nodes cannot satisfy a checkpoint or final manifest.
7. Retry creates a new attempt linked to the failed/cancelled attempt; it does not overwrite it.
8. Idempotency keys prevent duplicate nodes and duplicate external cost.
9. AI proposals are nodes with no execution authority. Apply is a separate human/user command.
10. No scheduler or AI call may cross Plan, Run or Finish gates automatically.

## Command lifecycle

```text
user message / direct edit
          |
   typed proposal node
          |
 schema + policy validation
          |
 impact/stale preview
          |
     user applies
          |
 new immutable spec + graph edges
          |
 ready execution nodes
          |
 checkpoint authorization
          |
 registered capability execution
          |
 output snapshot + trace event
```

The command envelope binds `session_id`, `expected_stage`, `expected_snapshot_hash`, command and
idempotency IDs, actor and timestamp. GraphService revalidates all dependencies inside the same
transaction that records the command result.

## State and route projection

`active_stage`, session status, reached stages, stage health, current snapshot refs and review
requirements are derived from current graph nodes and checkpoints. They are cached projections for
fast UI reads and conflict responses. A frontend route can request a projection but cannot set it.

The normal frontend shows four stages and concise progress. Detailed graph/attempt/edge inspection
is an administrative and reproducibility surface, not a replacement for the research UI.

## Invalidation and upstream revision

Returning from current Output to inspect Transformation is read-only. `start_pipeline_revision` is
the explicit user-approved transition that reopens the analytical branch: it archives the current
bundle, model/code results and artifacts, marks dependent Output nodes stale, moves the active
pointer to Transformation and preserves all prior outputs as history. Pipeline mutation commands
issued while Output remains current are rejected, so an editor cannot appear to save while the
state graph discards the change.

When a user applies an upstream change, GraphService computes affected descendants before saving.
The UI presents this impact. On confirmation:

1. the new upstream snapshot/node becomes current;
2. dependent current nodes receive stale relationships/reasons;
3. downstream current pointers are cleared or point to explicit stale history;
4. no connector, model, renderer or AI reviewer reruns automatically;
5. unaffected siblings remain current.

Artifact-level patches invalidate only the named artifact, its review results and manifest.
Dataset replacement invalidates Transformation, Model and Output descendants. Merely viewing an
older stage has no effect.

## Parallelism and fan-in

The graph supports bounded parallel work without introducing conversational agent swarms. Examples:

- map one validated connector query over country members;
- run independent model jobs against registered pipeline outputs;
- render or review independent artifacts in parallel.

A fan-in node runs only after required parents complete and validates compatible schemas/hashes.
Country-group aggregation is a registered fan-in capability with explicit membership, weighting,
missing-data and coverage policies.

## AI relationship

AI is a graph participant, not the graph controller. Stage-specific AI ports may create typed
proposal or review nodes. GraphService, capability policy and human checkpoints decide whether a
proposal can be applied or executed. Model errors, retries and provider changes therefore remain
observable and do not corrupt the research state.

## Persistence and services

Implemented foundations:

- versioned graph contracts and SQLite tables behind `ResearchGraphRepository`;
- startup legacy-node backfill plus compatible `/sessions` and `/projection` responses;
- graph invariant, dependency-impact and readiness validation through `GraphService`;
- graph-first public projection for every represented state, including failed/cancelled node stage;
- administrative graph/node/attempt reads;
- immutable completed-node input/output refs and append-only attempt identity;
- atomic idempotent claim/complete/fail/cancel, retry, orphan recovery and descendant invalidation;
- multi-parent readiness and concurrent duplicate-claim protection;
- a bounded local `NodeExecutor` that claims ready fan-out work and re-evaluates readiness before
  releasing fan-in nodes;
- startup orphan recovery using a configured age cutoff without automatically rerunning work;
- stale-target proposal rejection before proposal persistence;
- transactional application of all current stage commands through `GraphService`, with post-change
  invariant validation and typed graph-transition summaries in API responses and trace events;
- internal checksum-bound `GraphTransitionPlan` compilation, retirement of the generic full-session
  mutation endpoint and graph-derived regeneration of the legacy Workflow cursor;
- command/projection equivalence coverage across the non-AI Plan, Data, Transformation and Output
  journey, plus failure, restart and idempotent replay coverage.

The first implementation may use SQLite transactions and the local artifact store. The domain
ports must not depend on a specific graph database or workflow framework. Existing session `nodes`
and rich stage payloads remain compatibility read projections while frontend contracts migrate;
they are not accepted as mutation authority.

## Testing

- graph invariant and property tests;
- stale-propagation and unaffected-sibling tests;
- idempotent duplicate-command and concurrent-write tests;
- retry/cancel/restart/orphan-recovery tests;
- gate-bypass and stale-proposal rejection tests;
- fan-out/fan-in readiness tests;
- projection equivalence tests between graph state and API session/status output.

No test uses model-driven browser screenshots. AI graph tests use deterministic typed provider
fixtures; live provider evaluation is separate.

## Stage handoff node

`stage_handoff` is a durable record node carrying schema version `mra-stage-handoff-v1`. Each node
`CONSUMES` its approved Plan, Dataset snapshot, AnalyticalBundle and ArtifactSet references that
exist at the source boundary. A new handoff node `SUPERSEDES` the prior version; the prior node and
envelope remain immutable. Handoff confirmation is a user command through `GraphService` and does
not satisfy a Plan, Run or Finish checkpoint.

## Independent Agent graph

Agent stores `AgentNodeV1` DAGs and attempt identities in `runtime/agent/agent.sqlite3`; it never
reads a Workflow graph. A typed task claim checks current authorization, state, input references,
concurrency, execution epoch and lease. Completed references are immutable. Replacement inputs
create versioned nodes and downstream invalidation; completed unrelated tasks are reusable.
Task start/result, budget reservation/settlement and correlated audit commit transactionally.
Cancellation fences late results; restart pauses unfinished work without resetting counters.
Final artifact freeze is a separate actor=user command after hash-bound AI review.

Autonomous stages are run.phase projections over `requested/clarifying/queued/running`, not
another state machine. `waiting_for_user`, `paused`, `budget_exhausted`, `failed` and `cancelled`
retain results; `awaiting_final_confirmation` is not completed. See `agent_mode.md` and ADR 0033.
