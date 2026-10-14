# ADR 0020: ADB begins with bounded annual national accounts

Status: accepted

Date: 2026-09-10

## Context

ADB Key Indicators v5 exposes SDMX 3.0 and 2.1 data with a published limit of 20 requests per
minute. The main `KIDB_DSD` and trade `KIDB_TRADE_DSD` have different dimensions. ADB also uses
economy codes such as `PHI`, `SIN` and `PRC`, which cannot be assumed to equal canonical ISO3.

## Decision

Register only annual `ADB,DF_NA` dataflow version 1.0 as connector dataset `NATIONAL_ACCOUNTS`, for
`NGDP_XDC` and `NGDPVA_XDC`, explicit reviewed economies, and the provider-documented 2000–2024
range. Use SDMX-CSV over API v5/SDMX 3.0 and a version-controlled ISO3-to-ADB crosswalk.

The connector constructs `A.INDICATORS.ECONOMIES`, caps indicator groups below ADB's suggested
15–20 chunk size, and applies a shared process-safe budget of 18 requests/minute. It validates the
CSV dimension order and `ADB:DF_NA(1.0)` on every row, rejects returned scope drift, preserves unit,
unit multiplier, status, footnote/source/methodology attributes, and keeps shared/session raw
evidence with bounded retry and transport checks.

KIDB terms require ADB and content-provider attribution. Provenance therefore uses the prescribed
KIDB/access-date citation and appends distinct `DATA_SOURCE` values returned by the selected rows;
those source fields are also retained per observation. No ADB logo or endorsement is implied.

## Verification

Fixtures cover query bounds, ISO3 mapping, missing values, version/scope/schema drift, duplicates,
media/size limits, retry exhaustion, cache reuse and Plan-to-Data dispatch. A bounded live query
retrieved Philippines `NGDP_XDC` for 2023–2024, including `PHP`, multiplier `10^9`, status `A` and
the provider dataflow version.

## Consequences

ADB trade, other thematic dataflows, subnational localities, years outside 2000–2024 and
unreviewed economy mappings remain unavailable. The trade flow cannot be activated by dropping its
counterpart-area and currency dimensions; it requires a separate typed contract.
