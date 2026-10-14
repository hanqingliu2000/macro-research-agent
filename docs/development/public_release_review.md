# Public source release review

Date: 2026-10-14. Scope: version 0.1.0 public development source and its documentation. This
review does not certify production deployment, research validity, unrestricted third-party rights
or absence of every possible sensitive string.

## Code and documentation alignment

The README, current status, API, architecture, mode-isolation, stage and AI-orchestration documents
now use the same implementation boundaries:

- DeepSeek research/author roles, two checks for chart-bearing Workflow handoffs/every Agent
  delivery review and independent Codex-local formal review.
- Durable and isolated Workflow/Agent stores; Workflow gates versus bounded Agent authorization.
- Actual snapshot-bound data reads and potential remote disclosure, not schema-only or offline AI.
- Existing report/visual revision, evidence handoff and the active publication placeholder.
- Registered connector slices versus broader discovery; no unrestricted provider access.
- Real Agent persistence but Experimental acceptance: latest fixed cohort five of six, not a pass.
- No HTTP authentication; loopback-only use. No open-source license grant.

Quick start explicitly loads the environment file and sets the HTTP Workflow adapter. The example
configuration no longer suggests that unimplemented connectors or unused settings are available.
Historical reports retain their test dates, revision labels and outcomes. Later amendments are
identified separately, not presented as reruns of old acceptance.

## Source minimization

The distribution is built only from reviewed source files, synthetic fixtures, guidelines and
minimal public discovery metadata. It does not inherit a private repository's Git history,
branches, issues/comments, CI logs, credentials or runtime material. Its initial commit uses a
GitHub no-reply author address.

The SQLite projection uses `facts-only-v1`. All 8 providers, 10,832 dataset identities, 50,758
indicator concepts, 1,297 deduplicated sets and their mappings remain. Description/contact/HTML
prose was removed and full-text indexes rebuilt into a fresh compacted file. File size is
20,291,584 bytes; SHA-256:

`a17e81f7d2758604b118dd5cfec23caf76821dd362069c995d358da4a095039b`

The six identity/mapping tables match the prior projection logically. Source snapshot hashes,
access timestamps and the full local source database were not changed. Tests cover omitted
description-only terms, preserved discovery and code-list reuse. See
[third-party notices](../../THIRD_PARTY_NOTICES.md) for source attribution and modifications.

## Verification and publication gate

Before publication, verify the exact staged distribution:

1. Run backend lint, type checking and the full offline test suite; run frontend lint, tests and
   TypeScript/production build. Live model flags must be disabled.
2. Check documentation links and compare configuration, registry, API and budget claims with code.
3. Run a pinned, locally executed secret scanner against the source tree and all reachable public
   Git history. Review findings without printing raw candidates or credentials.
4. Inspect filenames, binary contents, database fields/FTS, configuration and CI for private
   integrations, endpoints, personal paths, runtime evidence and unexpected Git references.
5. Confirm that the public staging repository contains only the reviewed initial branch/tree,
   not a fork or push of prior history. No private discussion, logs or artifacts are migrated.
6. Confirm the source-only publication decision and keep the development repositories private.

### Verification results

- Backend: 431 passed, four opt-in real-model tests skipped; Ruff and strict mypy passed for
  123 source files. The exported public source also passed all 431 offline tests independently.
- Frontend: 130 passed across 27 test files, ESLint passed, TypeScript and Vite build passed.
  Installation from the existing npm cache and the full checks passed in the exported copy.
- Packaging: an isolated wheel build from the exported source succeeded with the declared build
  dependencies. A first no-build-isolation check failed because the existing developer environment
  had no wheel command; the normal isolated build required no source workaround.
- Documentation: 84 Markdown files and 90 explicit local file links checked, zero broken links;
  staged whitespace checks passed. Capability/configuration/approval facts were cross-checked
  against runtime composition, registries, schemas and tests.
- Source scanner: Gitleaks 8.30.1, official archive checksum verified, 100% candidate redaction,
  no inline allow-comment bypass; source-tree scan also enables archive/encoded-content depth 2.
  The minimized source tree and fresh single-root public history returned zero candidates.
  Both are scanned again after final documentation edits before the visibility change; the
  original private history is not imported.
  CI repeats the pinned history scan with read-only repository permissions.
- Findings: scanner candidates were test idempotency labels, not provider credentials. Public
  fixtures now use short explicit identifiers rather than a scanner allowlist. An initially
  intermittent frontend test passed isolated reruns; synchronization now awaits ready buttons,
  service-driven React updates and destination headings without loosening its assertions or
  timeout. The first failure is not claimed to prove a product defect.

No live model test was enabled and no runtime research record was changed to obtain these results.
The public Git tree is compared with the reviewed source tree before upload. Local dependency
caches, build outputs and environment files are not tracked in that tree. Contextual review found
no deployment-specific integration, internal endpoint or credential in the distributed source;
official public data-provider names and source attribution remain intentionally present.

## Remaining acceptance

No new real-provider browser cohort is part of this documentation/release pass. Candidate-history
clarity, multi-session/SSE responsiveness, six-run A6 reliability, source refresh/drift, full
multi-day/manual UAT, final creative standards and hosted-service security remain open. No
experimental gate is closed by a clean secret scan or an offline test pass.
