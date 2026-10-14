# ADR 0024 — admit UN SDG 8.1.1 real GDP per capita growth

Status: accepted — 2026-09-10

## Decision

Admit only Global SDG Indicator 8.1.1, current official series `NY_GDP_PCAP`, at annual frequency.
The Workflow contract is `SDG_INDICATORS / NY_GDP_PCAP / A`, with explicit dates and a reviewed
ISO3-to-M49 country crosswalk. Regions and other indicators are unavailable.

At acquisition the connector resolves the series through the official latest-release endpoint,
records its release identifier and metadata checksum, then retrieves every bounded observation
page. Page number, page count and total elements must remain consistent and complete within 25 pages
and 20,000 observations. The composite raw manifest binds release metadata and every page hash.

All reporting/disaggregation dimensions, Nature, Units, Observation Status, original values,
bounds, base period, source and footnotes are preserved as untrusted data. Distinct attribute/
dimension combinations receive distinct deterministic series keys and are never silently collapsed.
Test or unmarked surfaces fail closed.

## Evidence and boundary

Fixture tests cover release identity, multi-page completeness, pagination drift, metadata
preservation and typed-query refusal. A bounded live China 2022–2023 request resolved release
`2026.Q2.G.02` and returned the available 2022 observation on 2026-09-10. Official contract:
<https://unstats.un.org/SDGAPI/swagger/index.html>.
