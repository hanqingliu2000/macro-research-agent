# ADR 0025 Defer additional provider profiles

Status: accepted 2026-09-11; public scope clarification 2026-10-14.

## Context

Additional AI providers, distribution policies, licensed connectors and general deployment are
independent deliverables. Combining them under one milestone would imply approval or
implementation that has not occurred.

## Decision

Phase 4 remains deferred until explicitly resumed. Its public scope is a separately approved
remote provider profile behind the existing typed AI ports. Detailed requirements and acceptance
gates are in [provider profiles](../development/provider_profiles.md).

Every added task needs its own adapter, disclosure policy, typed contract, usage/retry limits,
revocation and quality acceptance. A credential or successful prompt does not authorize a model,
data class or additional task. There is no deterministic production fallback; test doubles remain
restricted to offline tests.

Current public development continues to use DeepSeek for research/authoring and Codex-local for
formal review. Provider selection cannot change Workflow gates, Agent authorization or user-only
final freeze. Any policy-restricted distribution must omit disallowed components physically,
not merely hide a UI choice.

## Consequences

- No additional provider is enabled by this decision or by the presence of generic adapter source.
- Licensed connectors, new public dataset admissions, authentication and hosted deployment are
  separate roadmap decisions.
- Agent persistence is tracked in its independent milestone and is now implemented; its strict
  A6 acceptance remains open. The earlier Phase 4 deferral did not accept or forbid that work.
- Public documentation describes reusable policy boundaries without deployment-specific details.
