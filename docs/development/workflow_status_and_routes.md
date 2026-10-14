# Workflow status, nodes and routes

This document defines the user-facing status and route projection. The durable typed state graph in
`state_graph.md` is the source of truth; stage payloads and UI communication rules are in
`workflow_stage_protocols.md`.

## Session projection

`active_stage` is one of `plan`, `data`, `transformation` or `output`. Session status answers what
the application can do next:

| Status | Meaning |
|---|---|
| clarifying | Plan chat is waiting for clarification answers. |
| plan_review | A current Plan exists and may be edited or confirmed. |
| acquiring | Approved source queries are running. |
| data_review | An active dataset is available for review/preparation. |
| pipeline_editing | Transformations and model jobs may be configured. |
| pipeline_running | The confirmed pipeline is executing. |
| output_generating | Selected artifacts are being built. |
| output_review | Current artifacts may be previewed, revised or exported. |
| completed | The selected artifact set and manifest are frozen. |
| failed | A classified operation failed. |
| cancelled | Work was explicitly stopped. |

Status and reachable stages are derived from current, non-stale nodes and checkpoint events. A
frontend route never sets either field.

The implementation may cache this projection with a canonical hash for efficient reads and 409
conflict responses. Cached projection fields are not independent authority: after graph migration,
they must be reproducible from nodes, typed edges, attempts, checkpoints and active pointers.

## Node kinds

- research_request
- clarification_batch
- research_plan
- geography_resolution
- data_acquisition
- data_preparation
- external_round_trip
- transformation_pipeline
- model_execution
- capability_invocation
- output_generation
- output_revision
- output_compliance_review
- visual_artifact_review
- reproduction_manifest

Nodes retain the existing lifecycle: pending, ready, in_progress, waiting_for_review, approved,
completed, stale, failed and cancelled. Every node records identifiers, attempt, timestamps,
parents, input/output snapshot references, required checkpoint, stale/superseded relationships and
classified errors.

Durable edge kinds are `depends_on`, `consumes`, `produces`, `authorized_by`, `reviews`,
`supersedes` and `invalidates`. Retry creates a new `NodeAttempt`; it never rewrites a failed or
cancelled attempt. AI proposal/review nodes are non-authoritative and cannot satisfy checkpoints.

Capability invocation nodes additionally record capability/skill ID and version, provider profile,
validated argument checksum, authorization checkpoint and result reference. Review nodes record
artifact/specification hashes, guideline version, deterministic preflight reference, provider/model
and structured finding IDs. They never store private reasoning tokens.

## Hidden snapshots and current pointers

Plans, datasets, pipelines, model results and artifact sets are immutable snapshots. The standard
UI shows only the current snapshot for each stage, not a version history. Append-only events retain
who changed what and which snapshot/hash was active.

Viewing upstream work does nothing. Confirmed upstream edits follow the invalidation matrix in
workflow_stage_protocols.md: dependent current nodes become stale, old artifacts remain readable
and downstream current pointers are cleared. Stale nodes cannot satisfy a checkpoint.

## Frontend routes

| Route | Responsibility |
|---|---|
| `/` | Create/list Workflow sessions. |
| `/sessions/{id}` | Redirect to the session's latest reachable stage. |
| `/sessions/{id}/plan` | Clarification, Plan chat and current Plan editing. |
| `/sessions/{id}/data` | Sources, provenance, preparation and round trip. |
| `/sessions/{id}/transformation` | Ordered operations, model jobs and execution. |
| `/sessions/{id}/output` | Deliverable controls, Output chat, previews and export. |
| `/settings` | Local runtime and connector readiness. |

Reached stages are viewable. A guarded future route redirects to the latest reachable stage with a
plain-language notice. The old Model/Steps panels and five-step progress control do not exist.

## API ownership

Workflow endpoints are rooted at `/api/v1/workflow`; Agent Mode has a separate namespace and
repository. Full Workflow trace is available only from
`GET /api/v1/admin/workflow/sessions/{id}/trace`.

All mutation routes use the shared command envelope, idempotency and expected snapshot/stage
checks described in workflow_stage_protocols.md. Stage services call `GraphService`; no route
accepts arbitrary graph mutations or a client-selected status/current pointer.
