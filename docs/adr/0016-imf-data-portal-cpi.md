# ADR 0016: IMF Data Portal uses registered, bounded public dataflow contracts

Status: accepted

Date: 2026-09-10

Amended on 2026-09-11: live WEO metadata and observations confirmed China general-government gross
debt codes `GGXWDG` (domestic currency) and `GGXWDG_NGDP` (percent of GDP). Their reviewed labels
and units are normalized even when the observation payload omits a unit attribute.

## Context

The IMF Data Portal documents both public-user and authenticated-user SDMX access. Its public
Python example uses `sdmx.Client("IMF_DATA")` without a personal API key. The portal exposes SDMX
2.1 and 3.0. CPI was the initial acquisition path. Reuse across research sessions and support for
structurally different datasets require a provider-level contract without opening arbitrary IMF
dataflows.

Official references:

- https://data.imf.org/en/Resource-Pages/IMF-API
- https://datasupport.imf.org/knowledge?id=knowledge_category&sys_kb_id=5ca208d697bc4390d4f0b437f053af9e&category_id=9959b2bc1b6391903dba646fbd4bcb6a

## Decision

Register `imf_data` as a public, no-credential connector for explicitly reviewed IMF Data Portal
SDMX 2.1 dataflows. Requests are generated from typed fields and target the hard-coded
`https://api.imf.org/external/sdmx/2.1` host. The current registry supports:

- CPI index levels (`INDEX_TYPE=CPI`, `TYPE_OF_TRANSFORMATION=IX`);
- explicit IMF country codes and COICOP 1999 codes (`_T` for all items);
- monthly, quarterly or annual frequency and an explicit period of at most 20 years;
- annual World Economic Outlook series with explicit country and WEO indicator codes and a period
  of at most 50 years;
- reviewed planning knowledge for common WEO concepts, including general-government gross debt in
  domestic currency and as a percentage of GDP; the live WEO codelist remains authoritative;
- no arbitrary URL, query option, unregistered dataset, measure or authentication header.

The connector fetches members separately. A successful public response is content-addressed by
request and response hashes and may be reused by later sessions for six hours. The freshness bound
prevents a new research session from silently relying forever on data that IMF may have revised.
Cache manifests and bytes are verified before every reuse and written atomically. Reuse never shares
session state: every session retains its own raw-response copy, immutable normalized snapshot,
provenance and value-free trace.
Only after every member succeeds are observations normalized into one immutable dataset snapshot.

The connector requests structure-specific SDMX XML because the live IMF endpoint returned that
format successfully while rejecting the generic XML media type during acceptance. XML DTD/entity
content, redirects, oversized responses, unbounded time ranges, excessive members and out-of-query
observations fail closed.

## Consequences

- Public CPI and WEO work does not require an `IMF_API_KEY` setting.
- Authentication may be added later for restricted workspaces as a separate provider profile.
- Other IMF datasets and broader discovery remain outside this connector version until they receive
  their own registry contract and acceptance coverage.
- The Plan AI must emit `dataset=CPI` with COICOP codes or `dataset=WEO` with WEO indicator codes;
  WEO is annual only.
