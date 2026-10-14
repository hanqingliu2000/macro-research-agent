# IMF dataflow onboarding and cross-session reuse

Status: active engineering contract

The `imf_data` connector is a provider boundary, not an unrestricted SDMX proxy. CPI and annual
WEO are the first registered dataflows. Every additional IMF dataset must pass the same steps below
before Plan AI may propose it or Plan approval may execute it.

## Runtime boundaries

- The only provider host is `https://api.imf.org/external/sdmx/2.1`; callers never provide a URL.
- Dataset, dimension order, fixed dimensions, allowed frequencies, code shapes and maximum period
  are declared in `IMF_DATASETS`.
- Queries require explicit countries, indicators and start/end periods. Empty SDMX dimensions and
  arbitrary query options are rejected.
- Responses are size-bounded, redirects are rejected, transient requests retry once, unsafe XML is
  rejected and every returned series is checked against the reviewed query.
- Normalized observations use the common `Observation` schema and produce an immutable,
  checksum-addressed session snapshot with source provenance.

## Cross-session cache contract

Public response bytes may be reused across Workflow sessions for six hours. The cache key binds the
SDMX path, parameters and representation media type. The manifest points to content-addressed bytes;
both are checked before reuse and written atomically. Expired or corrupted entries cause a provider
refetch.

The shared cache is only a performance layer. A consuming session receives its own raw-response
copy, normalized snapshot, provenance and value-free connector trace. Session export therefore does
not depend on another session or on the continued existence of the shared cache. Existing session
evidence remains immutable even after IMF revises a series; a new session refetches after the
freshness window.

## Adding a dataflow

1. Confirm the official IMF dataflow agency, ID and latest data-structure definition through the
   connector's metadata route. Record the official dataset page in the relevant ADR.
2. Add an `ImfDatasetContract` entry with exact key order, user-supplied dimensions, fixed
   dimensions, code patterns, supported frequencies, maximum period, indicator dimension and
   attribution.
3. Limit metadata discovery to codelists referenced by that dataflow. Do not expose every codelist
   returned by `references=all`.
4. Add a real-shape structure-specific XML fixture and tests for key construction, normalization,
   out-of-query rejection, frequency/period mismatch, duplicate observations and size bounds.
5. Add the dataset to the capability input contract and to both the Plan AI instructions and
   semantic validator. Until then the model must report the source as unresolved.
6. Run a bounded live smoke query against the official endpoint, then repeat it from a different
   session and confirm `reused_shared` plus a session-owned raw copy.
7. Update `current_status.md`, `implementation_plan.md`, the connector ADR and the longitudinal
   acceptance matrix before marking the dataflow available.

## Current registered contracts

| Dataset | Agency | Query dimensions | Frequency | Period bound |
| --- | --- | --- | --- | --- |
| CPI | IMF.STA | country, COICOP 1999 | Monthly, quarterly, annual | 20 years |
| WEO | IMF.RES | country, WEO indicator | Annual | 50 years |

Metadata is available from `GET /api/v1/workflow/connectors/imf/{dataset}`. The local registry is
available from `GET /api/v1/workflow/connectors/imf` without a provider request.
