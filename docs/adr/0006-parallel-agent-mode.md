# ADR 0006: Parallel experimental Agent Mode

Status: accepted

Date: 2026-08-24

Implementation amendment, 2026-10-14: both API namespaces and independent persistence are now
implemented. The original prototype wording below records the initial separation decision;
the current Agent authorization, diagnostics and Experimental acceptance are governed by ADR 0033
and `../development/agent_mode.md`.

## Decision

Add an experimental Agent Mode beside the existing review-gated Workflow Mode.

The modes have separate:

- session entities and identifiers;
- status machines and node kinds;
- frontend providers and route trees;
- mock services and localStorage keys;
- API namespaces and persistence repositories;
- session lists, history and recovery behavior.

There is no session conversion, shared session list, cross-mode resume or cross-mode mutation in
the initial implementation.

The modes may reuse stateless capabilities: connector implementations, upload inspection,
canonical data schemas, transformations, model runners, report builders, artifact formats, LLM
provider adapters and generic presentational components.

The shared Research Workbench shell, Slate tokens and SVG icon family are generic presentational
components. They accept display props and do not import either mode's domain, provider, commands,
session repository or storage. Sharing visual chrome does not create a shared session boundary.

## Workflow Mode

Workflow Mode remains plan-first and requires three explicit approvals. Agent Mode changes none of
its states, gates, routes or persistence behavior.

## Agent Mode

Agent Mode asks a bounded clarification batch and then autonomously selects only registered,
policy-approved capabilities. It does not show or require a plan approval before execution.

The router emits a typed route decision. A policy validator converts that decision into allowed
nodes. The model cannot issue arbitrary network requests, use web search for datasets, run free-form
code or bypass the Agent-owned, read-only data grant defined by ADR 0014.

Agent Mode is labelled Experimental in the interface and in exported metadata.

## Consequences

- Shared infrastructure must not import either mode's session model.
- The neutral frontend `ui` namespace must not import either mode's state or domain modules.
- A route under one mode cannot accept an ID from the other mode.
- Ordinary research chat shows high-level progress; the explicit Agent Inspect run surface may
  display owned diagnostic details through the separate administrative API.
- Adding future cross-mode duplication or conversion requires a new ADR and an explicit mapping.
