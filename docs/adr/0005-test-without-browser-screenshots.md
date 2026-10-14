# ADR 0005: Automated testing without model-driven browser screenshots

Status: accepted

Date: 2026-08-24

Amended: 2026-09-12 — distinguish logged browser-driven UAT from routine screenshot/model CI.

## Context

Having an AI model open pages and repeatedly inspect screenshots consumes substantial tokens, is slow and produces brittle acceptance criteria.

## Decision

Routine automated tests do not use model-driven browser screenshots or screenshot-diff visual regression.

Bounded browser-driven UAT may operate the real interface to simulate a user from question through
final freeze. It is not routine CI, does not use page screenshots as Review AI input and must leave
a concise structured record under `docs/testing/browser-runs/`. A claimed end-to-end pass requires
the direct-artifact Review AI loop to reach `pass` before the reviewed set is frozen.

Use:

- component, DOM, state, accessibility and API-contract tests for the web interface;
- numeric, schema and property assertions for data and model output;
- workbook-cell, formula, named-range and chart-XML/specification inspection;
- deterministic render metadata and artifact checksums.

Final appearance is reviewed by a person in the local web application or Excel at the publication approval gate.

Phase 1E may add a multimodal Review AI for generated charts and tables. It receives a direct,
checksum-addressed artifact render plus its specification and guideline rules. This is product
output review, not browser UI testing. Deterministic CI uses recorded review responses and
schema/rule assertions; live-model review evaluations are opt-in and separately bounded.

## Consequences

- CI remains fast and text/structure based.
- A human owns aesthetic acceptance.
- Review AI can identify compliance findings and propose typed specification patches, but cannot
  replace the final human publication gate.
- Browser screenshots may still be supplied manually for a specific defect but are not a routine agent test tool.
