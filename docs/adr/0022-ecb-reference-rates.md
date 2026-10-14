# ADR 0022 — admit ECB monthly euro reference rates

Status: accepted — 2026-09-10

## Decision

Admit only ECB `EXR` 1.0 monthly-average spot reference rates with the fixed SDMX key shape
`M.CURRENCY.EUR.SP00.A`. The Workflow contract is `EXCHANGE_RATES / EUR_REFERENCE_RATE / M` with
explicit dates and a reviewed ISO3-to-currency crosswalk. Values are foreign-currency units per
euro; the connector never silently inverts the quote. Euro-area countries are not represented as
an EUR/EUR series.

The connector requests `detail=full`, CSV data and `includeHistory=false`, validates returned
dimensions, scope, period, status, units and duplicate keys, and retains raw and normalized hashes.
Revision vintages require a future separate typed contract.

Shared public responses have a six-hour freshness limit. When the provider supplied ETag or
Last-Modified, an expired shared entry is conditionally revalidated. HTTP 304 refreshes only a
checksum-verified prior response and is recorded as `not_modified`; HTTP 404 is no data and cannot
be mistaken for an empty successful result.

## Evidence and boundary

Fixture tests cover normalization, scope/version/duplicate drift and conditional reuse. A bounded
live USD/EUR January–February 2025 read passed on 2026-09-10. The wider ECB catalog remains
unavailable. Official contracts: <https://data.ecb.europa.eu/help/api/data> and
<https://data.ecb.europa.eu/help/api/status-codes>.
