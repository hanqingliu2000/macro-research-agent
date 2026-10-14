# ADR 0015: portable Workflow sessions and immutable continuation

Status: Accepted
Date: 2026-09-06

## Context

A research project may span days or machines. Durable local storage alone cannot transfer the full
project, while copying only the visible session document omits uploads, immutable data snapshots,
generated code, artifacts, graph attempts and audit events. Completed sessions are publication
records and cannot be reopened in place without invalidating their frozen manifest.

## Decision

Workflow export uses the versioned `mra-portable-session-v1` ZIP contract. `manifest.json` binds the
database payload and each session-owned file by SHA-256. `database.json` contains only rows owned by
one Workflow session from an explicit table allowlist. Files retain paths relative to that session's
root. Trace JSONL is reconstructed from authoritative trace rows and is not a second archive source
of truth.

Import validates the archive before mutation: supported schema, bounded expansion/file count, safe
relative paths, exact manifest membership, checksums, exact database table shapes and session-row
ownership. It creates a server-selected session ID, rewrites only the session identity/path scope,
records source lineage and never overwrites an existing session.

Finish remains immutable. Continue is a fork operation valid only for a completed source. The child
inherits evidence and history but removes the old manifest from its current artifact set, marks the
prior review/manifest nodes stale and reopens at Output Review. A new review and final checkpoint are
required. The source database rows and bytes are never modified.

Workflow archives never contain Agent Mode state, and Agent imports cannot enter this API.

## Consequences

- Cross-day and cross-machine work has a complete, verifiable transport unit.
- Imported and forked sessions have explicit provenance without ID collisions.
- Publication history remains immutable while users can continue analysis deliberately.
- Future schema migrations must add a new archive version or an explicit validated migration.
