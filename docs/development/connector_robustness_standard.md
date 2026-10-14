# Public connector robustness standard

Status: normative Phase 3 acceptance contract

This standard is a release gate, not a design aspiration. A connector stays `planned` until its
registered dataset slice has fixture tests, a bounded live smoke test, a Plan-to-Data integration
test and an ADR recording provider-specific behavior. Passing one slice never activates a
provider's entire catalog.

## Current activation record

| Connector slice | Shared gates | Provider-specific gates | Evidence |
|---|---|---|---|
| IMF CPI and annual WEO | Passed | Separate DSD contracts and member-level fetch recovery | ADR 0016 |
| World Bank annual WDI/source 2 | Passed | Source identity and complete pagination/update checks | ADR 0017 |
| OECD CLI 4.1 monthly LI | Passed | Pinned DSD/dimensions and shared minute/hour budgets | ADR 0018 |
| Eurostat monthly TOTAL HICP index | Passed | JSON-stat order, ISO3 crosswalk and update-drift checks | ADR 0019 |
| ADB DF_NA 1.0 annual national accounts | Passed | Economy crosswalk and conservative shared minute budget | ADR 0020 |
| ECB EXR 1.0 monthly euro reference-rate averages | Passed | Quote/currency mapping, production values and 304-aware conditional reuse | ADR 0022 |
| BIS WS_CBPOL 1.0 monthly policy rates | Passed | Exact availability constraints, bounded key/rate budget and non-endorsement | ADR 0023 |
| UN SDG 8.1.1 / NY_GDP_PCAP annual | Passed | Current release evidence, M49 mapping, pagination and disaggregation preservation | ADR 0024 |

“Connector implemented” means more than receiving an HTTP 200 response. A connector is available
to Plan AI and Workflow sessions only after it satisfies the common requirements and its
provider-specific profile below. Planned connectors remain handler-less and fail closed.

## Common release gates

### 1. Query correctness and containment

- Hard-code the approved HTTPS host and endpoint family; never accept a URL from a user or model.
- Use a typed, versioned query contract with exact dataset, dimension, code, frequency and date
  bounds. Empty/wildcard dimensions require an explicit reviewed use case and stricter row limits.
- Validate returned dataset, series dimensions, entities, indicators, frequency and periods against
  the approved query. Reject out-of-scope and duplicate logical observation keys.
- Preserve missing observations as missing values when the provider represents them explicitly;
  never silently convert missing values to zero or drop them without a recorded rule.

### 2. Metadata, identity and revisions

- Resolve codes against provider metadata where practical and retain labels, units, scale, status,
  source/database identifiers and provider update or release information.
- Pin a source/dataflow/version when the provider supports it. When only “latest” exists, preserve
  retrieval time and raw checksum and use a bounded freshness policy for new sessions.
- Treat country groups and provider aggregates as distinct entities; never silently substitute one
  for a requested economy. Map provider codes to canonical IMF/ISO/M49 identifiers through a
  versioned crosswalk.

### 3. Transport and provider protection

- Enforce HTTPS, refuse redirects, verify the expected media type, cap compressed and decoded bytes,
  set connect/read timeouts and reject unsafe XML or malformed JSON/CSV.
- Implement bounded retry only for transport failures, 429 and selected 5xx responses. Respect a
  valid `Retry-After` within a configured ceiling; never retry validation or ordinary 4xx errors.
- Enforce the provider's published rate limit below that limit. Split large requests using the
  provider's recommended dimensions and stop on bounded page/row/request totals.

### 4. Pagination and completeness

- Check that page number, page count, total records and page size remain internally consistent.
- Detect repeated/skipped pages and metadata changes during a paged read. Partial page sets must
  fail rather than appear as complete data.
- Normalize only after all required pages/members complete. A retry may reuse already verified
  pieces but may not create duplicate observations.

### 5. Cache, isolation and reproducibility

- The request cache key binds provider, method, path, sorted parameters, requested representation
  and any request-body hash. The manifest and raw bytes are checksum-verified and atomically written.
- Shared public responses have a provider-specific freshness limit. Expired or corrupt entries are
  refetched for a new session; a current session's evidence remains immutable.
- Cross-session reuse is a performance optimization only. Every consuming session receives its own
  raw evidence copy, normalized snapshot, provenance and value-free trace so export/import and audit
  never depend on another session or shared-cache survival.

### 6. Security, licensing and observability

- Treat metadata and values as untrusted input. Never execute embedded text, formulas or code.
- Keep credentials out of URLs, cache keys exposed to clients, logs, traces and artifacts. Public
  and authenticated profiles are separate contracts.
- Record connector/version, bounded query hash, attempt result, cache scope, latency, provider
  release/update marker, raw hash, normalized hash and attribution without duplicating values in the
  trace.
- Complete provider terms, attribution, redistribution and retention review before activation.

### 7. Required evidence

- Recorded real-shape fixtures for metadata and every response representation used.
- Tests for valid normalization, missing values, out-of-query data, duplicates, malformed payloads,
  wrong media type, excessive bytes/pages/rows, pagination drift, retry exhaustion, cache corruption,
  cache expiry and cross-session isolation.
- A bounded opt-in live smoke test and a second-session reuse run. Live evidence records provider
  update/release identifiers but does not make CI depend on the provider.
- Plan/capability schema tests and an end-to-end Plan approval → Data snapshot test.

### 8. Plan knowledge and catalog maintenance

- Synchronize complete provider metadata into Source Index v2 and rebuild the lightweight Plan
  projection before making a dataset discoverable to Plan AI. Update
  `knowledge/data_source_catalog.json` while it remains the compatibility seed/API.
- For every executable slice, record stable provider/dataset identity, topics, frequency,
  publication cadence, geography and time coverage, important metadata fields, reviewed indicator
  seeds, constraints, official references, verification date and review interval.
- Treat the lightweight index as “what exists” discovery guidance, not runtime metadata. Connector
  validation of current codes, dimensions, versions, coverage and update markers remains mandatory.
- Keep provider catalog examples that have no admitted connector explicitly non-executable. A model
  may report the resulting gap but cannot use those examples as a data source.
- Validate unique identities, runtime-registry alignment, bounded retrieval, provider-local
  codelist content reuse and representative topic ranking in tests. Version and checksum the
  projection so a Plan can identify its knowledge basis.

## Provider-specific profiles

### World Bank Indicators

- Start with source 2, World Development Indicators (WDI), and require explicit ISO3 economies,
  indicator codes and annual ranges. Do not mix same-named indicators from different sources.
- Follow the V2 JSON envelope and validate every page's `page`, `pages`, `per_page`, `total` and
  `lastupdated`. Pin `source=2`, include footnotes/status and retain indicator source metadata.
- Keep requests below the documented 60-indicator and URL-length maxima; the product contract uses
  a stricter 20-economy/20-indicator/50-year/20,000-observation bound.
- Reject World Bank regions/income groups unless the approved geography explicitly represents that
  aggregate. Preserve null observations and forecast/status flags.

### OECD Data Explorer

- Register exact dissemination space, agency, dataflow, DSD version and dimension order. Never
  accept a Data Explorer-generated URL directly.
- Enforce both the published per-minute throttle and the current download-per-hour allowance; use
  cached metadata and coalesce reviewed keys before issuing requests.
- Handle dedicated-space restrictions separately from the main public space. Do not use blocked
  first/last-observation parameters for TiVA/CRS spaces.
- Bind parsing to an explicit SDMX-CSV/JSON media type and fail on DSD/dimension drift.

### Eurostat

- Use the current dissemination or SDMX 3.0 API, not retired legacy JSON/Unicode endpoints.
- Because Eurostat exposes only the latest dataset and may refresh twice daily, use a shorter shared
  freshness window and preserve retrieval/update metadata plus raw hashes for reproducibility.
- Track classification/base-period migrations explicitly; current HICP work must use the ECOICOP v2
  table and may not silently continue through the archived-through-2025 table.
- Bound every dimension explicitly; use asynchronous large-result behavior only after a separate
  job/recovery contract exists. Detect JSON-stat dimension/category ordering changes.

### ECB Data Portal

- Register exact flow and dimension order; use bounded periods and explicit `detail`/format.
- Use `ETag`/`If-None-Match` or `If-Modified-Since` when supplied and distinguish HTTP 304 from an
  empty dataset. Preserve update timestamps.
- Default to current production values (`includeHistory=false`). Historical revisions require a
  separate typed query and normalized revision dimension so multiple vintages cannot collide.

### BIS Data Portal

- Use the BIS-documented SDMX REST subset and register exact flow/DSD keys.
- Query availability/content constraints before enabling broad selections; require bounded series
  keys and reject an accidental whole-flow request.
- Preserve BIS attribution/non-endorsement requirements and review redistribution terms for every
  exported artifact profile.

### UN SDG

- Pin an official release code and series code; use M49 geography identifiers and a versioned M49 ↔
  canonical-country crosswalk.
- Preserve all disaggregation dimensions, nature/reporting type, units and status. Never collapse
  multiple disaggregated observations into one key.
- Validate `pageNumber`, `totalPages`, `totalElements` and release consistency across pages. Treat
  API/catalog “test” or legacy surfaces as unavailable for production data.

### ADB Key Indicators

- Enforce the published 20-query-per-minute limit below the provider ceiling and honor its guidance
  to split large requests into 15–20 indicator chunks.
- Register `KIDB_DSD` and `KIDB_TRADE_DSD` separately; trade counterpart/currency dimensions may not
  be omitted unless a reviewed bounded aggregate query explicitly allows them.
- Annual requests currently require the provider-supported period bounds and economy codes. Pin
  SDMX version/format and fail on structure-version drift.

## Availability rule

A connector can be marked available only for the exact dataset slices whose provider profile and
evidence pass. Completing one slice does not make the provider's whole catalog available. The
implementation plan and current status must list completed slices and remaining exclusions.
