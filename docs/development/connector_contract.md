# Connector contract

A connector is an allowlisted local class that translates a typed query into a provider request and a normalized dataset.

The normative definition of “robust enough to activate,” including common and provider-specific
release gates, is [`connector_robustness_standard.md`](connector_robustness_standard.md). This file
defines the interface; that standard defines the evidence required before availability changes.

Implementation status: `local_file` is active for user uploads. `imf_data` is active for the
bounded public CPI and annual WEO SDMX 2.1 contracts in ADR 0016, including scoped metadata
discovery, typed validation, member fetch/retry, cross-session public-response reuse, session-owned
raw evidence, normalization and provenance. `world_bank` is active for annual WDI/source 2 under
ADR 0017 with provider-specific metadata/source checks and complete JSON pagination. `oecd` is
active only for pinned CLI 4.1 monthly `LI` under ADR 0018. `eurostat` is active only for monthly
COICOP 2018 all-items `TOTAL` HICP index under ADR 0019. `adb` is active only for annual `DF_NA`
1.0 GDP/value-added series within 2000–2024 under ADR 0020. Other datasets and remaining public
providers stay outside the active contract.

The generated `source-index-lite-v1` projection supplies Plan AI with bounded provider/dataset/
indicator discovery facts and explicit executable state. It does not expand connector capability.
The transitional `data-source-knowledge-v1` endpoint remains available for compatibility. Runtime
metadata and returned data remain authoritative and must pass this contract even when the indexed
snapshot is current.

For WEO government debt, normalization assigns the live-verified meanings `GGXWDG` = domestic-
currency general-government gross debt and `GGXWDG_NGDP` = percent of GDP when the structure-
specific observation response omits unit text. Provider scale and raw attributes remain preserved.

World Bank WDI resolves units by evidence priority: observation field, indicator-metadata field,
then bounded patterns in the official indicator label. The last step covers percent,
percent-of-GDP and current/constant-US-dollar labels; it is recorded as label-derived and never
applied to an unrecognized label. Raw unit fields remain namespaced provider attributes and the
indicator-level unit receipt is included in normalized metadata and provenance.

## Required operations

- capabilities: supported datasets, dimensions, frequencies and authentication mode.
- discover: search provider metadata and codes without retrieving observations.
- validate_query: reject unsupported or unsafe parameters before network access.
- fetch: retrieve observations through the provider's documented API or licensed local interface.
- normalize: produce the canonical observation schema.
- provenance: return provider, dataset, endpoint identifier, query, retrieval time, license/attribution and checksums.

## Canonical observation fields

- provider
- dataset
- series_id
- entity_code
- entity_name
- indicator_code
- indicator_name
- frequency
- period
- value
- unit
- scale
- status
- observation_attributes

Provider-specific metadata is preserved in a namespaced field.

## Network rule

Only connector implementations may contact data-provider hosts. Hostnames and endpoint patterns are configured in code. Redirects, pagination and compressed responses must be bounded. The agent cannot pass an arbitrary URL.

Web search and browser tooling are outside this contract and cannot supply rows to the analytical data layers.

Every connector is also exposed as a versioned `CapabilityDescriptor`. AI may propose
only a registered connector ID and schema-valid query. The capability executor delegates to this
connector contract after the acquisition gate; provider-native tool calling cannot create an ad hoc
URL or bypass connector provenance. `connector.imf_data` is available only for the registered CPI
and WEO schemas in ADR 0016; unsupported IMF requests fail before network access.

## Reliability

Each fetch records request metadata, response checksum and normalized checksum. Connectors implement
timeouts, bounded retries, provider rate limits, explicit missing-value handling and error
classification. Unit tests use recorded fixtures; live tests are opt-in. IMF member retrievals are
content-addressed so a retry reuses completed members and fresh public responses can be reused by
other sessions. Shared entries expire after six hours and are checksum-verified; every session also
keeps its own raw copy and immutable normalized/provenance records. The reusable admission and
acceptance procedure is defined in `imf_dataflow_onboarding.md`.

Provider mechanisms are deliberately not flattened into one generic parser. World Bank owns page
envelope validation; OECD owns pinned SDMX DSD validation and persistent dual-window rate budgets;
Eurostat owns JSON-stat sparse-cube parsing, ISO3 code translation and update-drift detection; ADB
owns its distinct economy crosswalk, dataflow version check and conservative minute budget; ECB
owns quote direction, production-history semantics and conditional 304 handling; BIS owns exact
availability constraints and non-endorsement; UN SDG owns release evidence, M49 mapping, complete
pagination and disaggregation identity. The
Workflow acquisition service only builds the reviewed common query and dispatches to the registered
adapter, so adding a provider cannot weaken another provider's checks.
