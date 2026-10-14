# ADR 0026: Provider-derived complete Source Index

Status: accepted; eight-provider harvesting and lightweight Plan retrieval implemented

Date: 2026-09-11

## Context

`data-source-knowledge-v1` is a small reviewed list of admitted connector slices and representative
indicator seeds. It is useful for known examples but cannot answer the broader discovery question
“what does this provider contain?”. A real China general-government-debt Plan demonstrated the
failure mode: the provider and valid WEO codes were identified, while the sparse index still led the
model to question whether the series existed.

The eight connected public providers expose much richer metadata. Their structures differ:

- IMF, OECD, ECB, BIS and ADB expose SDMX dataflows, DSDs, concepts, codelists and constraints;
- Eurostat exposes a Catalogue API plus SDMX structures and constraints, with separate Comext and
  Prodcom endpoints;
- World Bank exposes sources/databases, indicators, topics, countries, regions, income groups and
  lending groups through its Indicators API;
- UN SDG exposes goals, targets, indicators, series, geographic areas, releases and provider-owned
  disaggregation dimensions.

Complete catalogs are too large and volatile for one checked-in JSON file or one model prompt.
They also must not imply that every discoverable dataset is already executable.

## Decision

Replace the seed-list architecture incrementally with `source-index-v2`, a normalized SQLite/FTS
index built from versioned provider metadata snapshots. The index stores:

1. provider identity, catalog URL, retrieval time, upstream version/update marker, checksum and
   explicit coverage status;
2. every public database/dataflow with agency, version, title, description, update marker and a
   separate executable flag;
3. the ordered dimensions of every dataset and their semantic role;
4. every published dimension value, including code, label, description, hierarchy/parents,
   provider attributes and an explicit `is_aggregate` value where the provider or a reviewed
   crosswalk establishes it;
5. indicator/series, frequency, geography, unit, measure, time, status and classification roles,
   while retaining source-specific dimensions rather than reducing them to a fixed macro schema.

The index does not materialize Cartesian products of dimension values. Provider content or
availability constraints are retained separately and are the authority for valid combinations.
Unknown country/aggregate classifications remain unknown; they are never guessed from code shape.
A conservative reviewed label rule may mark names that explicitly denote groups (for example
“World”, “euro area” or “income group”), but does not infer that every other value is a country.

Source synchronization is provider-owned and resumable. Each adapter must use official metadata
interfaces, bounded concurrency, documented rate limits, pagination, conditional requests where
available, raw-response checksums and atomic last-known-good replacement. A partial or failed run
cannot overwrite a complete snapshot.

Plan AI uses a generated `source-index-lite-v1` projection containing only provider, dataset and
indicator identity needed to answer “what exists?”. Dataset and indicator full-text search happens
locally and returns at most eight datasets and five matching indicators per dataset. The complete
catalog is never copied into the prompt. A discoverable result may be shown as future connector
scope, but only a dataset/key admitted by the capability registry may enter an executable Plan.

The projection stores indicator concepts once per provider and represents every dataset indicator
dimension as a reference to a content-addressed indicator set. Two codelists from the same provider
with identical code/label members therefore share one stored set even when their upstream IDs
differ. Provider boundaries are retained: equivalent sets from different institutions are not
silently merged. Frequency, geography, unit, hierarchy and availability combinations remain in the
full runtime index and are retrieved or revalidated only after a source candidate is selected.

The existing v1 catalog can still seed a clean runtime with `coverage_status=seed`, and its public
endpoint remains available during migration. It is no longer the knowledge source passed to Plan
AI once the committed lite projection is present.

## Provider synchronization matrix

| Provider | Dataset inventory | Required structural inventory |
|---|---|---|
| IMF Data | all public dataflows | referenced DSD/concepts/codelists and constraints; country and group classification |
| World Bank | all API sources/databases | all indicators per source; countries and aggregates; regions, income/lending groups and topics |
| OECD | all public dataflows | versioned DSDs, all codelists and content/availability constraints |
| Eurostat | main and Comext/Prodcom Catalogue APIs | SDMX structures, codelists, constraints, GEO/NUTS and EU/euro-area aggregates |
| ADB KIDB | all KIDB dataflows | KIDB and trade DSDs, all indicators/economies/counterparts/currencies and constraints |
| ECB | all ECB Data Portal dataflows | referenced DSDs, concepts, codelists, content constraints and maintained versions |
| BIS | all BIS public dataflows | DSDs/codelists, availability constraints, reference areas and collection-specific dimensions |
| UN SDG | all goals/targets/indicators/series | geographic areas/regions, releases, units, nature/status and all disaggregation dimensions |

## Implemented snapshot — 2026-09-12

All eight provider harvesters produced `complete` local snapshots. “Complete” means complete against
the provider's advertised catalog and availability interfaces at collection time; it does not mean
that every discovered dataset is executable.

| Provider | Advertised datasets/dataflows/series | Provider inventory evidence |
|---|---:|---|
| IMF Data | 222 | 214 DSDs, 624 unique codelists, 222 availability constraints |
| World Bank | 71 sources | 29,544 source-indicator rows, 295 countries/aggregates, 21 topics |
| OECD | 1,546 | 660 DSDs, 1,052 unique codelists, availability for 1,541 flows; 5 explicitly not advertised |
| Eurostat | 7,619 | 7,608 main datasets plus 11 Comext/Prodcom datasets; 1,422,612 indexed value/constraint rows |
| ADB KIDB | 66 | 2 DSDs, 19 base codelists, 64 constrained dimensions |
| ECB | 214 | 93 DSDs, 326 codelists, availability for 210 flows; 4 explicitly not advertised |
| BIS | 32 | 27 DSDs, 143 codelists, availability for 28 flows; 4 explicitly not advertised |
| UN SDG | 1,062 historical series | 713 current series, 251 indicators, 460 geographies and 73 releases |

The runtime index contains 10,832 dataset records and approximately 2.79 million searchable
dimension-value relations. Raw responses and the generated SQLite file remain ignored runtime
artifacts; the harvesters, validation rules and acceptance evidence are version controlled.

Provider quirks are retained explicitly. An availability-only code is preserved with its code as a
temporary label and `catalog_status=availability_only` when the provider's availability response is
newer than its codelist. An availability-only dimension is retained on the dataset when a current
constraint is newer than its referenced DSD. Empty SDMX `KeyValue` elements are treated as
unbounded wildcards, not empty data. These states remain visible for later refresh reconciliation.

## Acceptance

- Every provider reports `seed`, `partial`, `complete` or `failed`; “complete” is allowed only when
  all advertised public datasets and their required dimensions passed the provider manifest checks.
- Counts reconcile with the provider response manifests, including pagination totals where exposed.
- Dataset, dimension and dimension-value identities are unique within their provider scope.
- Full-index discovery can jointly resolve terms located in different dimensions, such as a country
  plus an indicator, without loading the full catalog into a model prompt; Plan retrieval searches
  only provider/dataset/indicator identity by design.
- Dataset and dimension-value endpoints are paginated and expose coverage/provenance state.
- Countries and aggregates are distinguishable when the provider supplies that classification;
  hierarchies preserve parent membership rather than flattening all areas into “countries”.
- Important provider-specific dimensions remain available and searchable.
- Atomic refresh, resume, retry/rate-limit, upstream drift, stale-snapshot and rollback tests pass
  for every provider adapter.
- Plan AI retrieves bounded lite projections of v2 matches and cannot turn a discoverable but
  unregistered key into an executable acquisition request.
- Planning retrieval removes conversational/geography noise before its bounded token budget,
  expands reviewed macroeconomic aliases, and reserves indicator slots across distinct requested
  concepts. A multi-concept request must not let several variants of one concept crowd all other
  required concepts out of the five-indicator prompt projection.
- A cross-provider acceptance set covers fiscal, price, national accounts, external, monetary,
  financial, demographic, development and SDG questions, including China general-government debt.

## Consequences

- Source discovery becomes a maintained data product, separate from connector execution and
  Session analytical data.
- Complete provider metadata can be refreshed on its own cadence without rewriting historical
  Plans; each Plan records the index snapshot identifiers used.
- The repository contains the generated lightweight projection, not the 2.0 GB full database or
  1.3 GB raw harvest. Development can rebuild it from complete official snapshots. Content-addressed
  provider-local indicator sets avoid storing repeated upstream codelists multiple times.
- `data-source-knowledge-v1` is transitional and will be removed only after v2 parity and migration
  tests pass.
