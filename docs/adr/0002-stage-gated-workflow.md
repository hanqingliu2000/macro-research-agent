# ADR 0002: Stage-gated research workflow

Status: accepted

Date: 2026-08-24

## Decision

Use clarification questions followed by an explicit execution plan and three human checkpoints.
Do not use an open-ended ReAct loop as the primary product interaction.

Approval is required before:

1. data acquisition begins;
2. the configured transformation pipeline and model jobs execute;
3. final outputs are frozen and exported.

## Consequences

- State transitions and approval target checksums are first-class domain objects.
- Each checkpoint is a durable state-graph node/record connected to the exact authorized inputs by
  `authorized_by` edges; neither AI nor a scheduler may manufacture or cross it.
- The UI shows one current Plan while internal immutable snapshots preserve audit and invalidation.
- Expensive and sensitive operations remain understandable and interruptible.
