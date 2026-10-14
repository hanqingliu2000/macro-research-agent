# Macro Research Agent

AI-assisted macroeconomic research, from a question to a reviewed, reproducible research package.

Macro Research Agent combines conversational planning, controlled data acquisition, statistical
analysis and evidence-based output review in a local research workbench. AI proposes research
designs, helps prepare data, authors reports and checks charts and conclusions. Typed contracts,
immutable snapshots and explicit authorization determine what actually runs.

**Status: experimental research software, version 0.1.0.** The four-stage Workflow and bounded
Agent runtime are implemented. Agent reliability acceptance is still open. This is a local,
single-user application, not a production-hosted or multi-tenant service. Public source access
does not grant an open-source license; see [Licensing](#licensing).

## What the AI does

- Clarifies an incomplete research question and produces a structured, editable Plan, including
  historical periods, forecast horizons, ordered variables and their model roles.
- Searches a lightweight source catalog to identify candidate providers, datasets and indicators
  without sending the entire catalog to a model.
- Inspects actual approved data through bounded, read-only access grants—not just schemas or
  samples—and proposes data preparation and analytical changes.
- Writes structured reports whose claims reference dataset snapshots, model results, citations
  and artifacts. Deterministic code validates those references and renders the report.
- Authors chart wording and performs two model self-checks before chart-bearing Workflow handoffs
  and every Agent delivery review. Controlled
  renderers, rather than model-generated drawing code, produce the numerical chart geometry.
- Reviews direct chart renders and report evidence through a separate reviewer. Corrections create
  new versions; missing analytical evidence must be addressed upstream, not hidden by rewriting.

The public implementation uses **DeepSeek** for planning, data and analysis assistance, authoring
and author self-checks. **Codex-local** performs formal visual and semantic review through an
installed, authenticated Codex runtime. Provider failures remain visible; there is no automatic
production fallback to a deterministic or alternative AI provider.

## Two research modes

| Mode | Execution and control |
| --- | --- |
| Workflow | Plan → Data → Transformation → Output. Review changes interactively, approve the Plan, review the active data, explicitly Run the analysis and Finish the reviewed package. |
| Agent Experimental | Submit clarification answers to authorize bounded autonomous work. The controller may acquire, clean, analyze and revise only within that authorization. Scope or budget expansion requires intervention; final delivery still requires your confirmation. |

Modes have separate sessions, databases, files, state machines and data grants. Neither silently
reads or converts the other's research. Both preserve prior versions and record why downstream
results become stale after an upstream change.

For example, start with: “Has Brazil's debt position changed alongside growth since 2010, and
what should I compare?” Clarify the debt definition, sources, time window, methods and requested
outputs before execution. Available data and registered methods constrain the resulting Plan;
the application does not promise that every research question can be answered.

## Data and analysis

Upload **CSV, JSON or XLSX**, or use the admitted public connector slices below. Data preparation
includes paginated previews, schema mapping, filtering, reshaping, reversible operations and an
XLSX export/clean/reimport round trip. Multi-source acquisition preserves each source's snapshots
and provenance before a reviewed canonical union.

| Provider | Currently executable scope |
| --- | --- |
| IMF Data Portal | CPI index levels and annual World Economic Outlook series |
| World Bank | Annual World Development Indicators, source 2 |
| OECD | CLI 4.1 monthly leading indicator |
| Eurostat | Monthly all-items HICP index, COICOP 2018 TOTAL |
| Asian Development Bank | Annual DF_NA 1.0 national accounts GDP/value added |
| European Central Bank | EXR 1.0 monthly euro reference-rate averages |
| Bank for International Settlements | WS_CBPOL 1.0 monthly policy rates |
| United Nations SDG | Annual indicator 8.1.1, NY_GDP_PCAP |

These are **dataset-specific admissions**, not unrestricted access to each provider. The bundled
discovery snapshot covers 10,832 dataset identities and 50,758 indicator concepts from eight
providers, collected in September 2026. Discovery does not prove present availability or authorize
acquisition. Live connectors revalidate codes, structure and returned coverage. The complete
dimension database and raw catalog harvests are not bundled. See the
[data-source catalog](docs/data_sources/source_catalog.md) and
[third-party notices](THIRD_PARTY_NOTICES.md).

Registered analysis includes descriptive statistics, correlation, OLS with optional HAC errors,
ADF, ARIMA, SARIMAX and VAR, with supported forecasts and VAR impulse responses. Frequency/unit
alignment and transformation parameters are typed and reviewable. Models execute from structured
variable roles and forecast horizons, not guesses extracted from narrative text.

Outputs include line charts, SVG figures, CSV tables, XLSX workbooks, Markdown research reports,
Python reproduction files and supported Stata do-files. **Stata does not cover every registered
model or transformation.** A frozen manifest binds selected artifacts to their evidence and hashes.
PNG renders are generated internally for review; they are not a separate selectable export format.
Workflow sessions also support checksum-verified portable export/import and linked continuation
without rewriting a completed session.

## Guardrails and review

- Data comes only from user files or registered connectors. Scraping, arbitrary URLs and
  model-generated download or execution code are not analytical acquisition paths.
- Workflow Plan, Run and Finish remain human gates. Agent actions require a versioned authorization
  envelope; the model cannot expand permissions or freeze its own output.
- Agent budgets persist across retries and recovery. Defaults include 40 application model calls,
  one million tokens, 80 task nodes, 16 model fits, 300 connector requests, 45 minutes of active
  execution and at most two concurrent tasks. Exhaustion preserves partial results, not a false
  completion. See the [Agent contract](docs/development/agent_mode.md).
- Agent statistical cleaning preserves the raw baseline, protects validation windows and applies
  fixed limits for complete cases, internal single-period interpolation and winsorization.
- Charts, tables and reports share at most three formal Output review rounds. A selected report
  needs semantic approval. Chart-bearing Workflow handoffs and Agent delivery reviews require
  two successful author checks. The current
  [academic publication placeholder](guidelines/academic-publication-placeholder-v1.md) is a
  testable quality rubric, **not journal-submission certification**.
- Traces retain approvals, attempts, errors, provider/model metadata and hashes. Agent diagnostics
  additionally preserve redacted final responses, repair evidence and reconstructable inputs.
  Hidden model reasoning is not recorded.

AI approval is not a guarantee of scientific validity. Check the research design, source vintage,
units, sample, model diagnostics and uncertainty before using or publishing results.

## Run locally

Requirements: Python 3.10+, Node.js 22.12+ with npm, a DeepSeek API credential, and an installed,
signed-in `codex` executable on your PATH for formal Output review. Provider model access and
network connectivity are required. No personal IMF Data API key is needed for the admitted public
IMF connector.

Clone the public source and create a Python environment:

```sh
git clone https://github.com/hanqingliu2000/macro-research-agent.git
cd macro-research-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env.local
```

On Windows, create the environment with `python -m venv .venv`, activate it with
`.venv\Scripts\Activate.ps1`, and copy the example with `Copy-Item .env.example .env.local`.

Edit the ignored `.env.local` and set `DEEPSEEK_API_KEY`. The default model identifier is
`deepseek-flash`; use an accessible model identifier if your account requires a different one.
Optional Data, Analysis and Report Author overrides inherit `DEEPSEEK_MODEL` when blank. No
project OpenAI API key is used for Codex-local review.

Start the backend from the repository root:

```sh
python -m uvicorn macro_research_agent.app:create_app --factory --app-dir backend/src \
  --host 127.0.0.1 --port 8000 --env-file .env.local
```

Configuration is read from the process environment; **`.env.local` is not loaded automatically**.
The explicit `--env-file` above loads it. Keep the real runtime in `development`; `test` is reserved
for offline fixtures.

In a second terminal:

```sh
cd frontend
npm ci
VITE_WORKFLOW_ADAPTER=http npm run dev
```

For PowerShell, use `$env:VITE_WORKFLOW_ADAPTER = "http"` followed by `npm run dev`.
**Do not omit the adapter setting:** Workflow otherwise opens its mock demonstration, not the
backend's research sessions. Agent uses HTTP outside tests.

Open [the workbench](http://127.0.0.1:5173). Workflow is at `/`; Agent is at `/agent`. The API is at
`http://127.0.0.1:8000/api/v1`, with interactive documentation at `/docs`. Local SQLite state,
uploads, Parquet snapshots, traces and artifacts are stored under the ignored `runtime/` directory.

## Privacy and deployment limits

**Keep both services bound to loopback. There is no HTTP user authentication, including for
administrative diagnostics. CORS and `actor=user` fields are not identity or access controls.**
Do not expose the ports publicly or use this version as a shared multi-user service. This is an
independent project, not an official service of or endorsement by any data provider.

Local-first does **not** mean offline AI. Approved real data values and rendered artifacts may be
sent to the configured AI services; Codex-local describes the local adapter, not guaranteed local
model inference. Public and user-supplied data disclosure is enabled by default. Review the
`MRA_AI_*` controls in [.env.example](.env.example) before using private data. Licensed data is
denied by default; a configuration flag alone is not permission to disclose it.

Diagnostics and portable packages can contain research context and sensitive inputs despite
credential redaction. Do not publish runtime folders, uploads, model-response dumps or debug bundles.
Read [the security policy](SECURITY.md) before running real research.

## Status and next steps

The local Workflow baseline and the listed connector slices have historical acceptance evidence.
Agent has completed real single- and multi-source deliveries, but its latest fixed-version cohort
completed **five of six** required journeys. Subsequent presentation-evidence fixes have regression
coverage, not a new successful six-run live acceptance cohort. Agent remains Experimental.

Outstanding work includes repeat-cohort reliability acceptance, candidate-versus-attempt history,
multi-session responsiveness, catalog refresh/drift hardening, full longitudinal/manual acceptance
and production authentication/deployment hardening. No hosted service or unrestricted connector
coverage is claimed.

- [Documentation guide](docs/README.md)
- [Current implementation and limitations](docs/development/current_status.md)
- [Architecture](docs/development/architecture.md) and [state graph](docs/development/state_graph.md)
- [Development plan](docs/development/implementation_plan.md) and [Agent milestones](docs/development/agent_implementation_plan.md)
- [Acceptance scenarios](docs/development/longitudinal_acceptance_scenario.md) and [executed test records](docs/testing/browser-runs/README.md)
- [Contributing and verification](CONTRIBUTING.md)

## Licensing

No open-source license has been granted for the project code. Public availability is not a license
to reuse, modify or redistribute it; obtain the rights holder's permission where required.
Third-party dependencies, provider metadata and acquired data retain their respective terms.
See [third-party notices](THIRD_PARTY_NOTICES.md).
