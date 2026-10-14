# ADR 0003: Replaceable LLM provider profiles

Status: accepted

Date: 2026-08-24

Amended by ADR 0025 on 2026-09-11: the deferred Phase 4 is limited to the additional remote provider profile;
licensed connectors and general deployment are no longer part of that phase.

Amended on 2026-09-12: the current product/development Plan runtime is locked to DeepSeek. The
provider-neutral port remains, but runtime provider selection and deterministic fallback are removed.

## Decision

All runtime LLM calls use a provider-neutral interface. The current product and development Plan
runtime admits only DeepSeek, does not read a provider selector from the environment, and reports
DeepSeek as the sole planning provider in the public capability contract. Missing DeepSeek
credentials fail startup; they never activate a deterministic or OpenAI fallback. Each invocation
records its provider/model in the session trace. A deterministic provider remains solely as an
explicitly injected offline test fake and is not a runtime capability. The 2026-09-09 DeepSeek
acceptance run covers a synthetic-data integration journey, not a general research-quality or cost
certification. See `../development/plan_ai_acceptance_report.md`.

Plan output must pass JSON-schema and domain capability-ID validation, with bounded corrective
retries. Capability versions, availability and approval policy are grounded in the server registry;
the model cannot redefine them or confirm geography for the user. Planning context includes the
reference date, current questions/answers, current Plan and recent persisted conversation.

Each profile declares supported task capabilities, including structured output, provider-native
function calling and vision. A task cannot select a profile that lacks its required capability.
Provider-native tools are mapped to application registry IDs and narrowed to the task allowlist;
they never expose a general browser, network, filesystem or code-execution tool.

Remote visual artifact review additionally requires the explicit session authorization defined in
ADR 0012. A text-only profile may still perform planning or narrative tasks but cannot be silently
used as the visual reviewer.

The public development composition now uses Codex-local as the formal visual and semantic review
runtime, in addition to its independent use as a development tool. The adapter is read-only and
fails closed; a local executable does not imply offline inference. Research/author roles remain
DeepSeek. This supersedes the initial decision that Codex was development-only.

The future `approved_remote` distribution must support source-level exclusion of disallowed provider code,
dependencies, secrets, settings and UI choices where its policy requires it. Its full governance,
activation and acceptance contract is `../development/provider_profiles.md`.

## Consequences

As of 2026-09-10, the opt-in DeepSeek Plan configuration uses `deepseek-flash`,
the official API alias for V4.1 Flash. This is a moving provider alias, not a pinned
model version; historical acceptance results remain attributed to their original model.
The existing text-only Plan contract and disclosure/approval rules remain unchanged;
native vision availability does not automatically enable visual review.
Source: https://www.deepseek.com/en/news/deepseek-v4-1-flash/

- Provider-specific request/response handling lives in adapters.
- Capability and vision support are discoverable profile metadata, not inferred from model names.
- Domain code relies on typed task outputs, not SDK response types.
- Packaging tests must prove a restricted distribution contains no policy-disallowed components.
