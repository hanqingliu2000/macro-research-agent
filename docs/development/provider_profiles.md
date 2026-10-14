# AI provider profiles

Updated: 2026-10-14. This public contract describes application behavior and requirements for
future adapters. It contains no deployment-specific tenant, credential or integration information.

## Current public implementation

| Task | Runtime provider |
| --- | --- |
| Workflow Plan, Data Steward and Analyst | DeepSeek, with typed role-specific outputs |
| Chart/report authoring and two pre-review author checks | DeepSeek |
| Agent planning, preparation, analysis, authoring and recovery proposals | DeepSeek |
| Formal visual and semantic review | Codex-local through the installed, authenticated runtime |

Missing credentials, unavailable review runtime or invalid model output fail explicitly. There is
no selectable deterministic production fallback. Offline tests inject fakes; `test` environment
is not a real-research deployment. Generic adapter source is not a selectable production profile.

Provider-specific transports sit behind typed proposal/author/review ports. Models cannot set graph
pointers, execute arbitrary code, add tools or cross Workflow Plan/Run/Finish gates. Agent
controllers may apply only envelope-authorized actions; final freeze remains user-only.

## Data boundary

Providers may inspect actual values only through owned, read-only, checksum/snapshot-bound grants.
Access is bounded and audited. Remote disclosure depends on data classification and configuration;
public/user-supplied values are enabled by default, while licensed values are denied by default.
A configuration switch does not grant legal permission. Visual review binds direct renders and
underlying evidence to exact artifact/data hashes. Local adapter execution does not imply local
model inference or zero remote disclosure.

## Deferred additional remote profile

Phase 4 remains deferred. No new production provider is enabled by this document. A future
`approved_remote` profile must be accepted separately for each task, model and data classification;
successful text access cannot enable visual review by implication.

Required decisions include permitted endpoint/model/task combinations, data handling and retention,
secret injection, rate/token/cost limits, revocation, audit responsibility and distribution scope.
Missing or contradictory decisions disable the affected task. The profile is server-owned, never
a client-supplied endpoint, credential or policy.

| Gate | Required acceptance |
| --- | --- |
| W0 policy | Explicit allowed tasks, models, endpoints and classifications, retention and responsible owner. |
| W1 offline | Configuration, disclosure, grant ownership, schema, approval, secret-redaction and budget tests. |
| W2 distribution | Reproducible file/dependency inventory; secrets and any disallowed provider components absent. Test doubles are test-only, not a runtime fallback. |
| W3 contract | Recorded malformed/success/error responses, bounded retries, stale targets and revocation. |
| W4 live planning | Authorized synthetic/public corpus with contract/research-quality, latency and cost thresholds. |
| W5 additional task | Independent Data/Analysis/author/visual evaluation and disclosure permission for every added task. |
| W6 longitudinal | Restart, revisions, paging, scope/approval boundaries, export/reload and credential revocation. |

Record profile/schema/prompt versions, actual model identifiers, request/response hashes,
latency/usage when supplied and all failures. Unknown usage keeps its reservation. Never store
credentials, hidden reasoning or redundant observation values in ordinary audit events.

Negative tests must cover unapproved endpoints/models, cross-session or stale reads, restricted
disclosure, prompt-like data, secret leakage, retry amplification, duplicate commands and attempts
to use a provider answer as execution or finalization authority.
