# Macroeconomic data-source catalog

Research date: 2026-08-24; implementation alignment updated 2026-10-14.
The checked-in catalog snapshot below was collected on 2026-09-12; this documentation update is
not a new live availability or provider-terms verification.

This catalog identifies candidates comparable to IMF Data that expose documented programmatic access without a paid data license. Registration requirements can change; every connector must re-check current provider terms before release.

## Machine-readable planning knowledge

Plan AI's current source is
`backend/src/macro_research_agent/knowledge/source_index_lite.sqlite3`
(`source-index-lite-v1`). It is generated from complete provider snapshots and contains only the
provider, dataset, title, executable state and indicator code/label needed to identify “what
exists?”. Local full-text retrieval supplies bounded matches rather than embedding a whole catalog
in a model prompt. Identical indicator codelists are content-addressed and reused within each
provider. This projection preserves the complete provider-derived dataset and indicator identities
from that collected snapshot: eight providers, 10,832 datasets/dataflows/series and 50,758 unique
indicator concepts. "Complete" refers to that reconciled snapshot, not every possible indicator
currently published or every combination of source dimensions. The projection deliberately omits
frequency, geography, units and detailed dimension values from Plan context. The full Source Index
and raw harvesting evidence are ignored runtime artifacts, not bundled with a clean checkout.

The public `facts-only-v1` projection omits long dataset descriptions, HTML and contact text from
both stored rows and full-text search. Source snapshots, all dataset/indicator identities and
provider-local codelist reuse remain unchanged. Its current size is 20,291,584 bytes. Attribution
and projection modifications are recorded in [third-party notices](../../THIRD_PARTY_NOTICES.md).

The reviewed `data_source_catalog.json` (`data-source-knowledge-v1`) remains the compatibility API
and clean-runtime seed. Its cadence, geography, coverage and reference notes are not copied into the
Plan AI prompt; current details are validated from the full index and live connector at acquisition.

Only the v1 JSON compatibility seed has a curated, non-exhaustive indicator list; this is not the
coverage rule for the generated lite snapshot described above. Provider-level examples in that
seed marked `catalog_examples_not_executable` help identify future connector
needs but cannot be emitted as executable Plan sources. Each acquisition still verifies current
provider metadata, structure, codes, update marker and response scope. Update this narrative and
the machine-readable file together; semantic changes require a catalog version bump and tests.

Catalog `1.2.0` expands the WEO entry with government-finance and debt coverage. IMF live metadata
identifies `GGXWDG` as general-government gross debt in domestic currency and `GGXWDG_NGDP` as the
same concept in percent of GDP; bounded China observations for both passed on 2026-09-11. These are
now searchable planning seeds while the current WEO codelist is still validated at acquisition.

The hand-reviewed v1 JSON file is a transitional seed. ADR 0026 defines the implemented Source
Index v2, which inventories the collected advertised databases/dataflows and their complete
provider-owned dimensions for IMF Data, World Bank, OECD, Eurostat, ADB KIDB, ECB, BIS and UN SDG.
Each provider is marked `seed`, `partial`, `complete` or `failed`; no provider is considered complete
until its dataset and dimension counts reconcile with official metadata manifests.

Priority in this catalog does not mean that an entire provider catalog is live. The backend registers
`local_file`, `imf_data`, `world_bank`, `oecd`, `eurostat`, `adb`, `ecb`, `bis` and `un_sdg`
capability metadata. The local
loader/normalizer and Data workspace are implemented. Bounded IMF CPI/WEO, World Bank WDI, OECD
CLI, Eurostat HICP, ADB national accounts, ECB EXR, BIS policy-rate and UN SDG 8.1.1 slices pass
their connector gates, including
independent session evidence and fresh cross-session response reuse. Other provider datasets are
not automatically enabled.

## Active implementation priorities

Only P0 and P1 are in the active connector roadmap.

| Priority | Providers | Delivery intent |
|---|---|---|
| P0 | Local XLSX/CSV/JSON; IMF Data | Complete for local files plus the registered IMF CPI and annual WEO contracts. Additional IMF dataflows require explicit admission. |
| P1 | World Bank Indicators; OECD Data Explorer; Eurostat; ECB Data Portal; BIS Data Portal; UN SDG API; ADB Key Indicators | The admitted WDI, CLI, HICP, EXR, WS_CBPOL, SDG 8.1.1 and DF_NA slices are active. Wider provider catalogs remain unavailable. |
| Backlog | Bank of Canada; BLS; FRED; BEA; EIA; UN Comtrade; IDB; other national APIs; Bloomberg; Haver Analytics | Keep researched but do not implement until P0/P1 acceptance is complete and the product owner reprioritizes them. |

Priority is separate from authentication tier: the sections below classify access requirements rather than build order.

## Tier A — open APIs, normally no key

| Provider | Coverage | Access | Interface | Initial notes |
|---|---|---|---|---|
| IMF Data | Global macro, finance, fiscal, external and sector datasets | Public API; some account/sign-in capabilities | SDMX 2.1 and 3.0 | First live institutional connector. CPI and annual WEO are registered; the broader portal catalog is not yet supported. |
| World Bank Indicators | Development, macro, social and environmental indicators | No API key required | REST/JSON/XML | Annual WDI/source 2 slice active under ADR 0017; other sources and aggregates remain unavailable. |
| OECD Data Explorer | OECD and partner-country economic/social statistics | Free public access; rate limited | SDMX-JSON/CSV | CLI 4.1 monthly LI slice active under ADR 0018; every other dataflow remains unavailable. |
| Eurostat | EU and candidate-country official statistics | Public | SDMX 2.1/3.0 and JSON-stat | Monthly COICOP 2018 TOTAL HICP index active under ADR 0019; other datasets/units/aggregates remain unavailable. |
| ECB Data Portal | Monetary, financial, exchange-rate and euro-area statistics | Public | SDMX 2.1 | EXR 1.0 monthly euro reference-rate average slice active under ADR 0022; other flows remain unavailable. |
| BIS Data Portal | International banking, credit, property, exchange-rate and payment statistics | Public subject to terms | SDMX | WS_CBPOL 1.0 monthly policy-rate slice active under ADR 0023 with availability checks and non-endorsement text. |
| UN SDG API | Global Sustainable Development Goal indicators | Public | REST/Swagger | Current-release SDG 8.1.1 / NY_GDP_PCAP slice active under ADR 0024; all other indicators remain unavailable. |
| ADB Key Indicators Database | Asia-Pacific economic, financial, social and environmental indicators | Public; documented rate limit | SDMX 3.0/2.1 | Annual DF_NA 1.0 GDP/value-added slice active under ADR 0020 with a conservative 18/minute application budget; other flows remain unavailable. |
| Bank of Canada Valet | Canadian economic and financial series | No registration or key | REST/JSON/CSV/XML | Good example of a simple national central-bank connector. |
| BLS Public Data v1 | US labour statistics | No registration for v1 | REST/JSON | v1 has tighter limits; registered v2 offers expanded access. |

## Tier B — free registration or API key

| Provider | Coverage | Registration | Interface | Initial notes |
|---|---|---|---|---|
| FRED | US and international macro/financial time series | Free API key | REST/JSON/XML | Large catalog; source and release metadata are important. |
| BLS Public Data v2 | US employment, prices, productivity and compensation | Free registration key | REST/JSON | Prefer v2 when batch size/history exceeds v1 limits. |
| BEA | US national, industry, regional and international accounts | Free API key | REST/JSON/XML | Dataset-specific parameters require metadata discovery. |
| EIA Open Data | US/international energy production, prices, balances and forecasts | Free API key | REST/JSON | Energy-macro workflows; respect route/facet/query limits. |
| UN Comtrade | International merchandise and services trade | Free account/key for standard API; preview access is limited | REST/JSON/CSV | Product/country/flow classification mapping is a substantial workstream. |

## Tier C — public regional candidates needing connector due diligence

| Provider | Region/coverage | Status |
|---|---|---|
| Inter-American Development Bank SIMS | Latin America and Caribbean social indicators | Public data/API materials exist; confirm current endpoint stability and terms before scheduling. |
| African Development Bank | Africa-wide development and economic indicators | Keep on watchlist until current official API documentation, availability and terms are verified. |
| National central banks/statistical offices | Country-specific high-frequency and detailed official data | Add only when a stable documented API exists and demand justifies provider-specific mappings. |

## Licensed integrations

These remain unscheduled backlog. They are outside any deferred approved remote-provider profile
and require separate prioritization, entitlement design and acceptance. A provider credential or
catalog entry does not authorize licensed data disclosure. See
[`provider_profiles.md`](../development/provider_profiles.md).

| Provider | Access model | Product treatment |
|---|---|---|
| Bloomberg | Paid terminal/data license | Use an optional local adapter only when the user's licensed environment permits it. Never proxy or redistribute data outside terms. |
| Haver Analytics | Paid subscription/license | Use an optional local adapter and preserve database/series attribution and entitlements. |

## Official references

- IMF Data API: https://data.imf.org/en/Resource-Pages/IMF-API
- World Bank Indicators API: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
- OECD API: https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html
- OECD Data Explorer FAQ and request limits: https://www.oecd.org/en/data/insights/data-explainers/2024/09/OECD-DE-FAQ.html
- OECD terms and attribution: https://www.oecd.org/en/about/terms-conditions.html
- Eurostat API introduction: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction
- Eurostat copyright and reuse notice: https://ec.europa.eu/eurostat/help/copyright-notice
- ECB API overview: https://data.ecb.europa.eu/help/api/overview
- BIS statistics terms: https://www.bis.org/terms_statistics.htm
- UN SDG API: https://unstats.un.org/sdgapi/swagger/
- UN Comtrade API: https://uncomtrade.org/docs/un-comtrade-api/
- ADB Key Indicators API: https://kidb.adb.org/api
- ADB Key Indicators terms and attribution: https://kidb.adb.org/terms
- IDB SIMS: https://www.iadb.org/en/knowledge-resources/data/social-data/sims
- Bank of Canada Valet API: https://www.bankofcanada.ca/valet-api-how-to/
- FRED API key documentation: https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html
- BLS developer portal: https://www.bls.gov/developers/
- BEA API guide: https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
- EIA API documentation: https://www.eia.gov/opendata/documentation.php

## Connector rollout requirements

Before activation, each provider needs:

1. official documentation and terms captured in an ADR;
2. hostname and endpoint allowlist;
3. typed discovery and query schemas;
4. recorded response fixtures and opt-in live smoke test;
5. raw and normalized checksums;
6. rate-limit, timeout and retry policy;
7. code/label/frequency/unit mapping;
8. attribution and redistribution handling;
9. provenance display in the UI and export package.
