# ADR 0017: World Bank starts with a bounded WDI annual connector

Status: accepted

Date: 2026-09-10

## Context

The World Bank Indicators API V2 is public and does not require an API key. Its JSON data response
is paginated and includes page/total information and a provider `lastupdated` marker. Indicators can
exist in more than one World Bank source, so a code alone is not sufficient source identity.

Official references:

- https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
- https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
- https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries

## Decision

Register `world_bank` for World Development Indicators (`dataset=WDI`, `source=2`) annual series
only. The first contract requires explicit IMF/ISO3 economy codes, official indicator codes and a
four-digit start/end year. It allows at most 20 economies, 20 indicators, 50 years and 20,000
normalized observations. Other World Bank sources, regions and income aggregates are not enabled by
this decision.

The connector:

- uses only `https://api.worldbank.org/v2` and refuses redirects or user/model-provided URLs;
- validates indicator metadata against source 2 before retrieving observations;
- retrieves JSON pages with a fixed page size and validates page number, page count, total and
  `lastupdated` consistency before normalization;
- preserves explicit null values, observation status, footnotes, indicator label/source notes and
  the provider update marker;
- normalizes units by evidence priority: observation unit, indicator-metadata unit, then a bounded
  parser over the official indicator label. The parser recognizes percent, percent-of-GDP and
  current/constant-US-dollar patterns; unknown units remain null. Raw observation/metadata units,
  normalized unit and derivation source remain in attributes and provenance;
- rejects malformed/wrong-type/oversized responses, out-of-query rows, duplicates and partial or
  drifting pagination;
- retries transport, 429 and selected 5xx failures at most three times with bounded delay;
- uses checksum-verified, atomic six-hour public caching while retaining a raw copy and immutable
  normalized/provenance records in every consuming session.

## Acceptance evidence

Recorded real-shape tests cover metadata/source validation, null values, WDI label-derived units
for GDP growth, gross-capital-formation share and household-consumption share, pagination drift/excess,
wrong media type, oversize, malformed JSON, out-of-query entities, duplicate keys, retry exhaustion,
cache expiry/corruption, cross-session isolation and Plan approval to Data snapshot creation.

A bounded live query retrieved China `SP.POP.TOTL` for 2022–2023 and retained World Bank
`lastupdated=2026-07-13`. A second session reused both verified metadata and observation pages
without another provider call and retained its own raw files.

## Consequences

- No World Bank credential or API key setting is added.
- Plan AI may propose only `connector_id=world_bank`, `dataset=WDI`, annual frequency and official
  indicator codes such as `SP.POP.TOTL` or `NY.GDP.MKTP.CD`.
- Other World Bank sources or aggregates remain unavailable until separately reviewed and tested.
- Provider failures remain visible; the connector never substitutes another source or fabricated
  rows.
