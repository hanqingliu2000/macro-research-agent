# ADR 0001: Local-first single-user architecture

Status: accepted

Date: 2026-08-24

## Decision

The first release runs as a local FastAPI service with a local React client. Raw uploads, downloaded source responses, normalized datasets, model inputs and artifacts remain on the user's machine.

ADR 0014 supersedes the original model-disclosure restriction. Raw files remain in local,
session-owned storage, while an approved model may read their actual values through controlled,
read-only, checksum/snapshot-bound grants. Local-first describes storage and application ownership;
it no longer means schema-only model context.

A generated chart/table render is derived analytical content and can reveal plotted labels and
values. ADR 0012 permits sending that exact artifact to a remote Review AI only under an approved
provider profile and explicit per-session authorization. Without authorization, visual review is
deterministic, local-model or human-only.

## Consequences

- Local filesystem and SQLite implementations are sufficient for foundation work.
- Authentication for multiple application users is out of scope initially.
- Secrets use environment variables or the OS keychain.
- A future remote/multi-user design requires a privacy and storage ADR.
- The trace records disclosure receipts and hashes without duplicating observation values.
