# ADR 0018: OECD begins with a pinned Composite Leading Indicators slice

Status: accepted

Date: 2026-09-10

## Context

OECD Data Explorer is a public SDMX service with a very large catalog. Dataflow versions can make
non-backward-compatible dimension changes, and OECD currently applies both short-window and hourly
download limits. Accepting a generated Data Explorer URL or silently following `latest` would make
the normalized meaning unstable and let separate sessions accidentally exceed provider budgets.

## Decision

Register only `OECD.SDD.STES:DSD_STES@DF_CLI(4.1)` as connector dataset `CLI`. The initial query is
monthly `LI` (Composite leading indicator), amplitude adjusted (`AA`) and OECD harmonised
methodology (`H`), for explicit ISO3 reference areas and bounded `YYYY-MM` ranges.

The connector:

- pins agency, dataflow and version in code and verifies all ten DSD dimensions before data fetch;
- builds the nine-component series key itself and never accepts a URL from a user or model;
- validates returned SDMX-CSV dimension order, scope, methodology and observation keys;
- preserves OECD labels, status, unit and all remaining namespaced attributes;
- enforces shared, process-safe rolling budgets of 20 requests/minute and 60/hour before every
  cache-miss attempt, failing immediately with a retry time rather than blocking an interactive run;
- uses bounded retry, media/size checks, checksum-verified six-hour shared cache reuse and a raw
  evidence copy owned by every consuming Session.
- emits OECD's required dataset/URL/access-date citation. Dataset-specific third-party restrictions
  still fail the admission review rather than inheriting the general OECD reuse permission.

## Verification

Fixture tests cover version/dimension drift, returned-row scope, missing values, cache reuse,
query bounds and shared rate budgets. A bounded live query retrieved United Kingdom CLI values for
2024-01 through 2024-03 from version 4.1 and retained status, unit, labels and both raw hashes.

## Consequences

The connector is not a generic OECD catalog client. Other measures, transformations,
methodologies, dataflows and dedicated dissemination spaces remain unavailable until separately
admitted and tested.
