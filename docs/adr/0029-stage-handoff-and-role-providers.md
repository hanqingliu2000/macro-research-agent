# ADR 0029 — Versioned stage handoff and role-scoped providers

Status: accepted and implemented for issue #23 on 2026-09-12.

## Decision

Workflow stages exchange an immutable `mra-stage-handoff-v1` envelope rather than relying on an
unfiltered chat transcript. Plan approval, Data approval and Transformation execution append new
handoff versions. A Transformation run records both its analytical handoff and the Output-facing
handoff after governed artifacts are generated.

Each envelope binds the research specification, data sources and snapshot/hash, preparation
decisions, typed analysis and model results, deliverables, provenance references and decision
status. New versions use `SUPERSEDES`; graph projection derives `CONSUMES` edges from the bound Plan,
Dataset, AnalyticalBundle and ArtifactSet references.

Plan, Data, Transformation and Output have separate persisted message lists. The compatibility
`planThread` and `outputThread` fields remain projections. Models receive the current handoff and a
bounded recent stage history, not every prior message.

The production roles are fixed: Planner, Data Steward and Analyst use DeepSeek through separate
typed adapters; Report Author and Report Reviewer are separate roles completed by issue #24. Role
adapters may diagnose/propose but cannot apply commands or satisfy Plan, Run or Finish checkpoints.
Data and Analysis retry schema or semantic repair at most twice and fail closed with a manual path.

## Legacy behavior

Old sessions are lazily projected into an inferred envelope. Determinable values are marked
`inferred`; missing variable roles are `needs_confirmation`. Only a user actor may confirm or
resolve decisions through the handoff command endpoint. AI operations reject incomplete handoffs.

## Consequences

Provider/model identity and limitations are visible in the stage UI and trace. Handoffs add durable
state and require graph invariant, reload, supersession and idempotency coverage. No AI provider
receives credentials, arbitrary file paths or mutation authority.
