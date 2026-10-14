# Security and data handling

Macro Research Agent is an experimental local single-user application, not a hardened hosted
service. The backend currently has no HTTP user authentication or multi-user authorization layer.
Session identifiers and CORS restrictions are not access controls. Anyone able to reach the API
may be able to access sessions, data, artifacts and administrative diagnostics or submit commands.

## Run locally only

Bind both backend and frontend to `127.0.0.1`, use a trusted personal machine and do not expose
their ports through a public address, tunnel, shared proxy or port forwarding. Do not deploy the
application as a public or shared multi-user service. A production deployment would require a
separate authentication, authorization, isolation and operational-security design and acceptance.

The application does not provide encryption at rest, a tenant boundary or a managed secret vault.
Protect its files with operating-system permissions, encrypted storage and appropriate backups.
Do not use it with confidential, employer, client, personal or licensed information unless the
applicable owners, policies and model-provider terms explicitly permit the complete processing path.

## AI calls can disclose actual data

Local-first means that the application stores its research state and files locally; it does not
mean that inference is offline. The standard runtime uses DeepSeek for planning, stage assistance,
authoring and self-checks, and an installed, authenticated Codex CLI for formal review. The
`codex-local` name describes the local adapter process. Its model service may receive the review
context, actual data and chart images; it is not an offline reviewer.

AI roles can read actual values through bounded, read-only grants tied to immutable uploads,
snapshots or results. Depending on the role, their context includes prompts, approved decisions,
data pages, typed model results, report text and exact rendered charts or tables. Do not assume
that only schemas or a small preview leave the machine. These controls limit application access;
they do not change a provider's retention, training or account terms.

The following controls are read from the backend environment:

- `MRA_AI_DATA_ACCESS` enables the model-data access service and defaults to `true`.
- `MRA_AI_REMOTE_USER_DATA_ALLOWED` permits remote disclosure of user-supplied values and defaults
  to `true`. Set it to `false` before starting when that disclosure is not authorized.
- `MRA_AI_REMOTE_LICENSED_DATA_ALLOWED` defaults to `false`. Keep it disabled unless a separately
  reviewed integration, license and provider policy authorize that use; the flag alone grants none.
- `MRA_AI_DATA_PAGE_SIZE` bounds individual pages, not the total amount a role may read.

Disabling a data grant is not a substitute for keeping secrets out of prompts or for disconnecting
an external model provider. Some AI actions will stop when required data access is unavailable;
there is no production deterministic-provider fallback. Human approval gates, hash checks and
bounded retries reduce specific risks but do not guarantee factual accuracy or data confidentiality.

## Local records and diagnostic exports

The ignored `runtime` directory contains session databases, original uploads and provider
responses, normalized snapshots, generated files, audit events and diagnostic payloads. Agent
diagnostics can reconstruct model-visible inputs and retain redacted final responses, repairs,
failed attempts, usage and error details. This is useful for debugging and also makes the local
records sensitive. Hidden model reasoning is not an intended audit artifact.

Redaction is defense in depth, not a guarantee: arbitrary secrets or personal data embedded in
free text may evade detection. Review any trace, archive, screenshot, error report or diagnostic
bundle before sharing it. Do not upload them to public issues or attach real runtime directories
to a contribution. `.gitignore` does not remove a file already committed to Git or protect data
included elsewhere.

Durable research evidence and diagnostics have no automatic expiry policy. Removing a session
from a list is not proof of secure erasure, and retained archives or backups can contain older
copies. Manage retention and deletion deliberately, with the application stopped and backups
accounted for; the application does not promise forensic erasure. A scanner finding no secrets
does not certify that a repository or export contains no sensitive information.

## Report a vulnerability privately

Use GitHub's private vulnerability reporting or a private Security Advisory for this repository
if the feature is enabled. Include only the minimum redacted reproduction, affected version,
impact and relevant file locations. Do not include credentials, real datasets, internal addresses,
private project material or a complete diagnostic archive in the initial report.

If private reporting is unavailable, first establish a verified private channel with the
maintainer. Do not publish exploit steps, vulnerable data, credentials or private evidence in a
public issue while trying to find a reporting channel. There is currently no published guaranteed
response time or long-term security-support commitment.

If credentials or private material have been exposed, stop sharing the affected artifact, revoke
or rotate the credentials, assess access and notify the relevant owner through a private channel.
Deleting a file or adding it to `.gitignore` does not remove existing Git history, remote copies,
logs or caches. Coordinate any history cleanup and publication decision rather than assuming that
a later clean scan resolves the incident.
