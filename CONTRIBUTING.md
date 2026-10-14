# Contributing

Macro Research Agent is an experimental, local single-user research application. Contributions
should improve a reproducible research workflow without weakening its approval, evidence,
data-access or execution boundaries. Read [AGENTS.md](AGENTS.md) before making changes and
[SECURITY.md](SECURITY.md) before running it with data or reporting a vulnerability.

No open-source license has been granted for this repository. Public source availability is not
a license to reuse or redistribute it. Contribute only material that you have the right to
provide; do not import third-party code or assets without checking their terms.

## Keep contributions safe to publish

- Never commit credentials, authentication files, environment files other than the empty example,
  personal information, employer or client material, internal endpoints, private project names,
  licensed data or real research-session exports.
- Use synthetic fixtures or clearly attributable public examples. Do not attach runtime databases,
  diagnostic archives, uploads, raw responses, private prompts, model responses or generated
  deliverables to public issues or pull requests.
- Treat source metadata, observation values, file content and model output as untrusted inputs.
  A string inside data must never gain instruction or execution authority.
- Review the entire staged change, including binary files and generated metadata. A passing secret
  scan does not prove that a contribution is safe to publish. If a secret was committed, follow
  the incident guidance in [SECURITY.md](SECURITY.md); deleting the current line is not enough.

## Development setup

Use Python 3.10 or newer and a Node.js version supported by the checked-in frontend dependencies;
Node 22.12 or newer is suitable for the current lockfile. From the repository root, create a
virtual environment and install the development dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` instead. Install frontend
dependencies with `npm ci` in `frontend`. Follow the [README](README.md) for running the real
services; tests do not require a production API key or Codex login. Do not put private
configuration in test fixtures.

## Required checks

Run the backend checks from the repository root, with live-model test flags unset or set to `0`:

```sh
python -m ruff check backend
python -m mypy backend/src
python -m pytest
```

Run the frontend checks from `frontend`:

```sh
npm ci
npm run lint
npm test
npm run build
```

CI also scans reachable Git history with checksum-pinned Gitleaks 8.30.1 and
redacts candidates in scanner output. To repeat it locally with that tool installed, use
`gitleaks git . --log-opts="--all" --redact=100 --ignore-gitleaks-allow --no-banner`.
Review binary metadata and contextual privacy separately; a secret scan is not a clearance.

The default test suite uses injected or recorded provider responses. Check your environment before
running it: `MRA_LIVE_CODEX_OUTPUT_REVIEW=1` opts into real Codex review tests, and
`MRA_LIVE_CHART_DELIVERY=1` opts into real chart-authoring/self-check/review tests. Live tests may
send their synthetic evidence to model providers, consume account limits and incur charges. Run
them only with explicit authorization, suitable accounts and a bounded test scope. Offline test
success is not evidence that a provider is available or that a live research journey passed.

## Preserve product boundaries

- Workflow Plan approval, Run and Finish remain explicit user actions. Agent execution must stay
  within its immutable user authorization and persistent budgets; final freezing remains user-only.
- Keep Workflow and Agent sessions, stores, grants and APIs isolated. Share typed computation
  interfaces, not session access.
- Add executable capabilities only through reviewed, typed registries. Dataset discovery does not
  authorize a connector, arbitrary URL, browser scraping or generated download code.
- Keep AI reads snapshot-bound and read-only. Never execute runtime-model-generated shell,
  Python, SQL or Stata as an unrestricted application operation.
- Preserve old results, attempts, consumed budgets and failures. A retry, revision or restart must
  not silently manufacture a successful state or reset an exhausted loop.
- Use component, DOM/state, API-contract and numerical/artifact tests. Review AI consumes direct
  generated artifact renders, not screenshots of the browser interface.

## Changes and review

Keep changes focused and add regression coverage for behavioral changes. Describe the problem,
the resulting behavior, checks performed and any remaining limitation in the pull request. Do
not claim a live acceptance result from mocks or mark experimental work as production-ready.

Update the implementation plan and relevant contracts, status documents and ADR when changing a
provider, connector, approval gate, state transition, data-disclosure policy, output contract,
trace schema or testing boundary. Historical test records must retain their original versions
and outcomes; add a new result instead of rewriting a failed run as successful.

Report security-sensitive findings privately as described in [SECURITY.md](SECURITY.md), not in
a normal public issue.
