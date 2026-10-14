# ADR 0034 Public source distribution and documentation alignment

Status: accepted 2026-10-14.

## Decision

Publish a reviewed public source distribution with a fresh Git history. Do not publish private
development branches/history, deployment-specific integrations, discussions, CI logs, runtime
sessions, credentials, debug bundles or original research uploads. Keep development repositories
and their existing history private. Future public updates must use the same reviewed-tree boundary.

Public documentation describes only the general development runtime: DeepSeek research/author
roles and Codex-local formal review, with no alternative production fallback. It must distinguish
implemented functions, historical acceptance and outstanding experimental gates. It must not
describe the application as an authenticated hosted service or treat local client execution as
offline inference.

The public Plan discovery projection follows `facts-only-v1`: retain provider/source provenance,
dataset and indicator identifiers/labels, execution-admission flags and provider-local codelist
reuse; exclude long descriptions, HTML and contact text from both rows and full-text indexes.
Rebuild the SQLite file rather than leaving omitted content in old pages. Keep original source
snapshot versions/checksums and introduce a distinct projection-policy version. This is a local
projection change, not a new provider harvest or expansion of executable connector scope.

Provider metadata retains its original rights and attribution. Do not add an open-source code
license without a rights-holder decision. The initial public distribution intentionally has no
open-source license grant.

## Consequences

- Public releases are scanned as exact source trees and reachable Git objects, not just as a
  currently clean README. Binary metadata needs explicit field/integrity inspection.
- Credentials/configuration, internal identities/endpoints, personal paths and private runtime
  evidence are excluded. Automated secret detection supplements, not replaces, contextual review.
- The README becomes a product/setup entry point; current status is a concise capability/acceptance
  map. Historical test outcomes remain in their dated evidence records.
- Catalog counts, indicator mappings and executable admissions remain unchanged. Search no longer
  matches terms found only in long descriptions; identity/indicator retrieval is regression-tested.
- Offline regression does not close the Agent A6 fixed-cohort gate or certify live-model quality.
  Final visual/icon standards, authentication and hosted deployment remain separate work.

See [public release review](../development/public_release_review.md),
[provider profiles](../development/provider_profiles.md) and
[third-party notices](../../THIRD_PARTY_NOTICES.md).
