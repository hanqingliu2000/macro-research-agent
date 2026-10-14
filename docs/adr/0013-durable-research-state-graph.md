# ADR 0013: durable research state graph as Workflow source of truth

Status: accepted

Date: 2026-08-25

## Decision

Workflow Mode is governed by a durable typed state graph. The four routes and session statuses are
projections over graph nodes, edges, immutable snapshots, active pointers and checkpoint events.
Chat messages and AI responses are inputs or proposal nodes; they are never the workflow state.

AI cannot directly traverse the graph, change a pointer or mark a node complete. Stage-specific AI
ports return typed proposals/reviews. GraphService validates target hashes, dependencies,
capability availability, approval and invalidation before applying a user-confirmed command.

The graph is implemented behind repository/service ports and does not require a graph database or
third-party agent framework. SQLite remains acceptable for the local application.

## Consequences

- Phase 1E starts with graph normalization and invariant tests before live AI/tool orchestration.
- Upstream edits preserve old results and propagate stale state only to dependent descendants.
- Parallel country/model/artifact work uses typed fan-out/fan-in nodes rather than autonomous agent
  conversations.
- Retry creates a new attempt; idempotency and checkpoints prevent duplicate cost or gate bypass.
- Workflow and Agent Mode may share stateless capabilities but never graph/session repositories.
- Administrative trace can expose graph IDs and transitions; the normal UI remains a concise
  four-stage research surface.
