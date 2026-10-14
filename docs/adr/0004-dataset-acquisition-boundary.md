# ADR 0004: Dataset acquisition uses controlled connectors

Status: accepted

Date: 2026-08-24

## Context

Research reliability requires authoritative data, repeatable queries, stable provenance and compliance with provider terms. General web search is not a reliable dataset transport.

## Decision

Analytical datasets may enter the application only through local file loaders or registered connector functions that call documented APIs or licensed local integrations.

During dataset acquisition, prohibit:

- web search results as observation data;
- browser downloads and browser scraping;
- arbitrary user- or model-supplied URLs;
- model-generated network or extraction code.

Web search is allowed for non-acquisition work such as methodology research, documentation lookup and contextual evidence when included in the approved plan. Such sources are cited and stored separately from analytical datasets.

## Consequences

- Network egress for data can be allowlisted by connector.
- Every source query can be replayed and checksummed.
- Adding a provider requires code, tests, attribution review and registry activation.
