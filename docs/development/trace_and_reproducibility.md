# Trace and reproducibility

Implementation status: Workflow trace persistence, monotonic sequence allocation, recursive secret
redaction, append-only JSONL materialization, restart recovery and the versioned `publication-v1`
reproduction manifest are implemented. Agent adds independent transactional audit, reconstructable
inputs, full redacted final responses/repair evidence, payload integrity and offline replay.

## Event model

Each session writes append-only JSON Lines events. Events have a session ID, monotonically increasing sequence, UTC timestamp, event type, actor, payload and optional parent event/artifact references.

Representative event types include:

- graph.node_created, graph.node_ready, graph.node_started, graph.node_completed,
  graph.node_stale, graph.nodes_stale and graph.edge_created
- graph.pointer_moved, graph.attempt_failed, graph.attempt_cancelled, graph.attempt_retried,
  graph.attempts_orphaned and graph.checkpoint_authorized
- message.received and message.sent
- clarification.answered
- plan.created, plan.patched, checkpoint.recorded and downstream.invalidated
- connector.called and connector.completed
- dataset.snapshotted, dataset.normalized, roundtrip.imported and transform.applied
- model.specified and model.completed
- artifact.created and artifact.reviewed
- capability.proposed, capability.authorized, capability.completed and capability.failed
- skill.proposed, skill.completed and skill.failed
- output.preflight_completed, output.visual_review_completed and output.patch_applied
- session.completed or session.failed

## Frontend boundary

The research UI does not render the complete event stream. Workflow exposes only the current
four-stage route state, stage-specific operation history and material warnings. Its former general
Steps panel is removed. Agent exposes only a concise autonomous-route outline beside its chat and
result package; it does not expose node payloads, prompts or tool parameters.

Full prompts, tool parameters, hashes, logs and node identifiers are available only to backend
administration and reproducibility export, subject to redaction. The normal Workflow frontend
does not call the administrative trace endpoint. Agent's explicit "Inspect run" action opens a
diagnostic surface for filtering, complete payloads, attempt comparison and metrics; ordinary
research chat still shows only material progress.

## Reproduction manifest

A completed Workflow session exports a `publication-v1` manifest containing:

- approved Plan and Dataset snapshot references;
- the analytical bundle and final dataset ref;
- ordered transformation and model specifications plus result hashes;
- selected output IDs, names and checksums;
- guideline version, warnings and limitations.

Phase 1E extends the manifest with:

- current graph root/node refs, checkpoint hashes and the graph/projection schema version;
- capability/function/runtime-skill IDs and versions used by each stage;
- AI task, provider/model/settings, validated tool arguments and result references;
- deterministic preflight and Review AI report IDs for frozen artifacts.
- Report Author request/draft, EvidenceClaim ledger, semantic-review status, approved directives
  and immutable report revision hashes.

Application commit/environment lock details, connector-version expansion and execution-log bundling
remain required before a distribution-grade manifest is declared complete.

## Redaction

Never record API tokens, passwords, authorization headers, hidden reasoning or duplicate licensed
observation values in trace. Prompt records use the exact user-visible/system-approved prompt text
after secret redaction; model data is referenced by access receipt and immutable hashes.

## LLM boundary

Trace provider/model/settings and a model-data access receipt for every value read: grant ID,
session/stage, source/checksum or snapshot hash, classification, columns, filters/page ranges, row
counts, page hashes and disclosure-policy version. ADR 0014 permits row-level model access; do not
copy those rows into JSONL, logs or ordinary API responses merely for auditing.

For visual review, trace the exact artifact, underlying dataset and specification hashes, render dimensions, guideline
subset/version, deterministic finding refs, provider profile, authorization ref and structured
review result. Do not duplicate image bytes in JSONL or store hidden reasoning. A remote visual
review is prohibited without the authorization ref required by ADR 0012.

Every function/tool/skill attempt records registry ID/version, stage, target snapshot hash,
validated argument checksum, approval checkpoint, start/end time, status and immutable output refs.
Unavailable placeholders record a rejected/blocked attempt and cannot create a result reference.

## Graph reconstruction

Durable node, edge, attempt, checkpoint and active-pointer records are authoritative application
state; append-only trace events explain how that state changed. The current status, reachable
stages and current refs must be reproducible from the graph and must agree with the cached API
projection. Recovery may rematerialize missing JSONL events from durable graph/repository records,
but never fabricates a completed node or rewrites historical attempts.

Each accepted stage command records the same typed graph-transition summary returned by the API:
created node/edge/checkpoint IDs, active-pointer before/after refs and invalidated node IDs. This is
a concise state-change receipt, not a substitute for the normalized graph records or private model
reasoning.
