# ADR 0023 — admit BIS monthly central bank policy rates

Status: accepted — 2026-09-10

## Decision

Admit only BIS dataflow `BIS:WS_CBPOL(1.0)` with key dimensions `FREQ.REF_AREA`, monthly frequency
and end-of-period collection. The Workflow contract is `POLICY_RATES / POLICY_RATE / M` with
explicit dates and a reviewed ISO3-to-BIS-area crosswalk.

Before observations, the connector issues an exact v2 availability request for the reviewed key,
rejects test/unmarked metadata, validates the attached flow and requires every requested area. It
then makes a bounded SDMX-CSV request using a TIME_PERIOD component filter. Returned flow, frequency,
areas, periods, values and logical keys are validated; unit, compilation, source and status fields
are preserved. A shared 20-request-per-minute application budget protects the provider.

Exports carry BIS attribution and the statement that BIS does not endorse conclusions derived from
its statistics. Use remains subject to BIS terms.

## Evidence and boundary

Fixture tests cover availability, returned-scope and typed-query refusal. A bounded live US policy-
rate January–February 2025 read passed on 2026-09-10. Other BIS flows and daily observations remain
unavailable. Official contracts: <https://stats.bis.org/api-doc/v2/> and
<https://data.bis.org/topics/CBPOL>.
