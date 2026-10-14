# ADR 0021: Plan AI uses a reviewed data-source knowledge index

Status: accepted

Date: 2026-09-10

Amended on 2026-09-11: catalog version `1.2.0` adds WEO government-finance/debt concepts and the
live-verified `GGXWDG` and `GGXWDG_NGDP` indicator seeds after a real Plan falsely treated them as
absent from WEO.

Superseded for Plan retrieval by ADR 0026. This v1 catalog remains only a compatibility endpoint and
clean-runtime Source Index seed until migration/rollback acceptance permits its removal.

## Context

Connector schemas answer whether a specific request is safe to execute, but they do not give Plan
AI enough domain context to choose among providers. Capability labels alone omit provider catalog
scope, observation frequency, publication cadence, geographic coverage, common indicators and the
metadata fields available for research design.

Provider catalogs and series metadata also change at different rates. Copying a complete live
catalog into every planning prompt would be large, volatile and could accidentally imply that every
listed dataset is executable. Keeping all source knowledge as prose inside the model instruction
would duplicate connector facts and make review difficult.

## Decision

Maintain reviewed, low-frequency source knowledge in
`backend/src/macro_research_agent/knowledge/data_source_catalog.json`. Its schema-validated loader
records:

- provider catalog summary, topics and official catalog/terms links;
- examples of provider holdings that are explicitly **not executable**;
- each admitted dataset slice, provider dataset identity, themes, frequencies, geography and
  temporal coverage;
- publication/update cadence, normalized metadata fields, common indicator codes and measurement
  notes;
- constraints, official documentation, verification date and review interval.

The application validates the file at startup, computes a content SHA-256 and exposes a bounded
read-only inspection endpoint. `WorkflowPlanningService` ranks the available dataset records against
the research request and includes the compact matches in `WorkflowPlanningContext.source_knowledge`.
The model instruction distinguishes discovery knowledge from capability: only a dataset marked
available and present in the runtime connector registry may enter an executable `data_sources`
proposal. Broader catalog examples may only explain an unresolved requirement.

This knowledge base is not runtime provider metadata. It is reviewed periodically rather than
refreshed during every Plan request. Connector acquisition remains responsible for verifying live
dataset identity, code lists, dimensions, versions, coverage, update markers and returned scope.

Official cadence references used for version 1.0.0 include:

- IMF WEO: https://www.imf.org/en/Publications/WEO/frequently-asked-questions
- World Bank update/revision behavior: https://datahelpdesk.worldbank.org/knowledgebase/articles/114939-how-are-revisions-managed
- OECD CLI: https://www.oecd.org/en/data/insights/data-explainers/2024/04/composite-leading-indicators-frequently-asked-questions.html
- Eurostat API updates: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/catalogue-api
- ADB KIDB FAQ: https://kidb.adb.org/faq

## Acceptance

- The checked-in catalog parses under a strict, extra-forbidden schema and has unique provider,
  dataset and indicator identities.
- Every non-local executable connector has reviewed knowledge and a verification date.
- Topic retrieval ranks inflation and population examples correctly, excludes unavailable connector
  IDs and enforces a bounded result count.
- A general-government debt request ranks WEO first and exposes the reviewed domestic-currency and
  percent-of-GDP codes without implying that the indicator seed list is an exhaustive WEO catalog.
- Plan AI is explicitly forbidden from treating absence from the seed list as evidence that a
  provider series does not exist. It may select an indexed executable candidate, but it may not
  assert observation gaps, unavailable periods or incomplete coverage before acquisition. Exact
  contents are connector outcomes, not Plan blockers or clarification premises.
- Planning prompt `planning-v6` rejects clarification questions that embed unverified availability
  or coverage claims. A deterministic classifier also removes acquisition-dependent claims from
  model-generated blockers and cautions while preserving known connector/configuration blockers.
- Plan requests contain the ranked knowledge and its executable-boundary notice.
- `GET /api/v1/data-source-knowledge` exposes the version, content checksum and bounded matches
  without contacting a provider or returning observations.

## Consequences

- Updating source knowledge is a reviewable data change and requires a catalog version bump when
  meaning or schema changes.
- Indicator lists are curated planning seeds, not claims of exhaustive provider coverage.
- A matched executable source can proceed to acquisition without asking the user to resolve a
  hypothetical data gap. Empty responses, missing observations and coverage mismatches are reported
  from the persisted connector result in Data, where they can be reviewed against actual values.
- An overdue review does not silently rewrite historical Plans; it prompts maintenance while live
  connectors continue to fail closed on structural drift.
- The former conclusion that richer indexing was unnecessary no longer applies after the complete-
  catalog product decision. ADR 0026 introduces local full-text indexing while retaining bounded
  planning context.
