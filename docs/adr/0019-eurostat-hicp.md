# ADR 0019: Eurostat begins with a bounded monthly all-items HICP index

Status: accepted

Date: 2026-09-10

## Context

Eurostat's Statistics API returns the latest data in JSON-stat 2.0. It may refresh twice daily and
does not provide the historical release archive needed to reconstruct old responses from the API
alone. Its native country dimension also uses Eurostat codes, including exceptions such as `EL`
and `UK`, while the workbench uses canonical ISO3 codes.

## Decision

Register only the current ECOICOP v2 provider dataset `prc_hicp_minr` as connector dataset
`HICP_INDEX`, monthly COICOP 2018 all-items `TOTAL`, unit `I25` (2025=100), and explicit bounded European
countries. Use a reviewed,
version-controlled ISO3-to-Eurostat crosswalk. Query one country per response so scope can be
proven without relying on undocumented multi-value filter behavior.

The connector validates the exact `freq · unit · coicop18 · geo · time` dimension order, category
sizes and returned codes; preserves missing cells and status; records the provider `updated`
timestamp; rejects update drift across a multi-country fetch; and keeps checksum-addressed raw
responses in the shared/session evidence boundary. Large asynchronous requests are not used until
the workflow has a separate resumable job contract.

Eurostat's reuse terms require source acknowledgement and identification of changes. Provenance
therefore records the dataset DOI and access date. The active country crosswalk is limited to EU
and EFTA economies covered by the general reuse rule; exceptions require a separate review.

## Verification

Fixtures cover JSON-stat sparse values/status, dimension drift, crosswalk scope, update drift,
media/size limits, cache reuse and query bounds. A bounded live query retrieved Germany's HICP
index for 2026-05 through 2026-07 and retained Eurostat's `2026-09-01T23:00:00+0200` update marker.

## Consequences

The retired-through-2025 `prc_hicp_midx` table is explicitly not used for current research. Other
Eurostat datasets, aggregates, units and COICOP groups are not enabled. Because only the
latest provider version is exposed, reproducibility depends on retained raw evidence and checksums,
not on the assumption that a later provider query will reproduce the same values.
