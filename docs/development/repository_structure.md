# Repository structure and mode isolation

## Frontend

    frontend/
      public/              local application mark and future static UI assets
      src/
        app/               route composition and reset/base styles only
        ui/                mode-neutral Workbench shell, SVG icons and Slate tokens
          components/      composed shell, Activity Bar, Explorer, optional Status Bar, icons and
                           presentation-only contracts
          styles/          shared tokens and Workbench chrome
        agent/             Agent-only domain, HTTP service, mock fixtures, state, pages,
                           components and styles
        workflow/          Workflow domain, graph projections, services, routes and stage components
          components/      Workflow stage controls and reusable SectionHeading/StageChatComposer
          services/        async service contract plus deterministic mock and typed HTTP adapters
          styles/          Workflow-only routed-stage styles

Within `workflow/state`, session projection, Plan, Data, Pipeline and Output use five composed
feature reducers. Route components issue typed service commands and never mutate a feature store
directly.

Agent code may import generic browser/React utilities but must not import Workflow modules.
Workflow code must not import Agent modules. The app route
composition may import both providers only to mount disjoint route branches. ESLint enforces these
import boundaries for the business directories.

Both modes may import the neutral `ui` namespace. That namespace receives display props only and
cannot import either mode's domain, context, reducer, storage or service modules. Visual reuse does
not permit session reuse.

Mock storage keys:

- Workflow: macro-research-agent.workflow.mock.sessions.v2
- Agent: macro-research-agent.agent.mock.sessions.v1

## Backend

    macro_research_agent/
      workflow/            approval-gated state graph, projection and orchestration
        graph/             graph contracts/repository port/service and bounded local executor
        model_data_access  Workflow-owned grants for actual upload/snapshot values
      agent/               authorized autonomous runtime, task graph, SQLite repository,
                           budgets, leases, diagnostics and recovery
      research_core/       mode-neutral computation, planning, authoring and evidence ports
      connectors/          shared stateless controlled data access
      data/                shared canonical schemas and transformations
      models/              shared typed model runners
      reporting/           shared governed export builders
      capabilities/        shared versioned descriptors, policy and direct-execution boundary
      skills/              shared declarative runtime-skill manifests; no arbitrary executable code
      llm/                 provider interfaces; no direct filesystem/session-store access
      trace/               shared event infrastructure with mode-specific repositories

Each mode owns persistence, session lookup, status derivation and retry behavior. A backend
architecture test rejects direct imports between the workflow and agent packages. The neutral
`research_core` facades currently reuse reviewed stateless helpers and typed ports located under
`workflow`; callers inject mode-owned data reads and storage. This code reuse does not permit
reading or mutating the other mode's sessions, grants or artifacts. It is not a claim that every
shared implementation has already moved to a separate physical package.

The `capabilities` and `skills` directories are implemented in Phase 1E-1. Workflow and Agent
orchestration may resolve their stateless descriptors/handlers but keep invocation state,
approvals and trace references in their separate repositories.

Workflow persistence is implemented beneath `runtime/workflow` with its own SQLite tables and
per-session JSONL trace. Phase 1E-0 now includes typed node/edge/attempt/checkpoint records behind
domain ports; SQLite remains an implementation detail and a graph database is not required. No Agent
table, endpoint or storage key reads this data. Agent uses its own SQLite repository and graph
beneath `runtime/agent`, including authorization envelopes, task attempts/leases, budget ledger,
trace events and checksum-bound diagnostic payloads. Agent's HTTP/SSE service and administrative
inspection routes are implemented; the strict fixed-version A6 acceptance gate remains open.

## Test evidence

    docs/testing/browser-runs/
      README.md             browser-driven completion rule and run index
      TEMPLATE.md           concise per-journey evidence template
      YYYY-MM-DD-*.md       immutable summaries of executed browser runs

These records contain identifiers, hashes, counts, decisions and issue links, not credentials,
licensed values, full prompts/responses or large runtime dumps.
