# Source Index v2 catalog acceptance report

Date: 2026-09-12

Public projection amendment, 2026-10-14: the historical 24 MB projection described below was
rebuilt with `facts-only-v1`. It is now 20,291,584 bytes, omits descriptions/contact/HTML text from
rows and FTS, and preserves all dataset/indicator identities, mapping tables and source snapshot
hashes. This is projection minimization, not a new live harvest or a change to this historical
acceptance result. See ADR 0034 and [public release review](public_release_review.md).

Scope: Phase 3-3 steps 3–8 and 10 — complete advertised catalogs for the eight connected public
providers plus the lightweight Plan AI projection. This report accepts discovery metadata only and
does not admit newly discovered datasets for execution.

## Result

**Passed for catalog harvesting.** All eight providers produced atomic `complete` snapshots in the
development runtime. Together they contain 10,832 dataset/dataflow/series records and 2,786,753
searchable provider, inline-dimension and shared-codelist value relations. Every provider snapshot
records its source URL, retrieval time, upstream version/update marker, content hash, coverage state
and reconciliation counts.

| Provider | Dataset records | Principal completeness evidence | Snapshot SHA-256 prefix |
|---|---:|---|---|
| IMF Data | 222 | 214 DSDs; 624 unique codelists; 127,710 base codes; availability for all 222 flows | `643ad0c2ff8b` |
| World Bank | 71 | 29,544 source-indicator rows / 29,533 unique; 295 countries or aggregates; 21 topics; 223 advanced metadata resources | `833589c1a632` |
| OECD | 1,546 | 660 DSDs; 1,052 unique codelists; 444,889 base codes; availability for 1,541 flows and 5 explicit `not_advertised` states | `74305cc798ac` |
| Eurostat | 7,619 | 7,608 main datasets and 11 Comext/Prodcom datasets; 1,344,454 main and 78,158 Comext constraint/value relations | `c7e884004b35` |
| ADB KIDB | 66 | 2 DSDs; 19 base codelists; 2,648 base codes; 64 constrained dimensions | `aa58c95bbfd6` |
| ECB | 214 | 93 DSDs; 326 codelists; 186,574 base codes; availability for 210 flows and 4 explicit `not_advertised` states | `cd380adf0df1` |
| BIS | 32 | 27 DSDs; 143 codelists; 15,401 base codes; availability for 28 flows and 4 explicit `not_advertised` states | `00301aa3ecc5` |
| UN SDG | 1,062 | 713 current series; 251 indicators; 17 goals; 169 targets; 460 geographies; 73 releases; 3,189 disaggregation combinations | `0c927df123be` |

The generated SQLite database and raw provider responses are intentionally ignored runtime
artifacts. The full database is 2.0 GB and the raw response cache is 1.3 GB. The harvest code,
schemas, tests, this evidence and the generated 24 MB Plan projection are version controlled.
Rebuilding all providers and the projection uses:

```bash
PYTHONPATH=backend/src .venv/bin/python -m macro_research_agent.knowledge.sync \
  --provider all \
  --lite-output backend/src/macro_research_agent/knowledge/source_index_lite.sqlite3
```

Each provider is replaced in its own transaction. A failed or partial run cannot overwrite an
existing complete snapshot, so a later provider failure does not damage earlier last-known-good
catalogs. Version-scoped provider 404 responses for optional availability endpoints are retained in
a short-lived negative cache and included in the snapshot hash, so resumptions do not repeatedly
request known-unadvertised resources while new dataflow versions are still rechecked.

## Provider-specific reconciliation

- IMF generated DSDs sometimes omit their codelist reference. The harvester first applies official
  naming conventions, validates the referenced code set, and then uses a unique code-set plus
  flow/dimension semantic match. Ambiguous matches are not silently selected. Provider-published
  availability-only codes remain searchable with `catalog_status=availability_only` until a later
  codelist supplies their labels.
- OECD publishes availability across public, DCD, STI and archive services. They are merged with
  `Actual` constraints preferred over `Allowed`. One current availability dimension is newer than
  its DSD and is retained as an explicit availability-only dimension.
- ECB's aggregate content constraints cover 210 current flows. Four published flows do not expose a
  separate availability constraint and remain visible as `not_advertised`, not empty.
- BIS availability requests require the explicit comma-separated component list. Twenty-eight
  flows return constraints; four older flows return no advertised availability endpoint and are
  retained as `not_advertised`.
- Eurostat combines the twice-daily main catalogue/metabase/codelists with the separate
  Comext/Prodcom catalogue, structures, codelists and per-flow constraints.
- World Bank reconciles every page total and retains exact duplicate source-indicator memberships
  rather than silently collapsing them. Eighteen sources that do not advertise advanced metadata
  remain explicit.
- ADB enforces the provider's request budget and retains flow-specific allowed constraints,
  including counterpart and currency dimensions.
- UN SDG separates current series from the historical union and stores actual disaggregation
  combinations, releases and the official geography hierarchy; disaggregation values are not
  promoted to indicators.

Empty SDMX `KeyValue` elements are interpreted as provider-published wildcards, commonly for time,
not as proof that a dataset has no observations. Country/aggregate flags use provider metadata or a
conservative reviewed group-name rule; unknown values remain unknown.

## Acceptance evidence

- 22 focused harvester, index and API tests passed on 2026-09-12; the full backend suite passed
  225 tests, and the frontend suite passed 77 tests plus its production build.
- Provider status reconciliation returned `complete` for all eight snapshots.
- All IMF/OECD/ECB/BIS snapshots report zero unresolved data structures and zero unresolved
  codelists.
- Cross-dimension FTS can intersect terms from separate indicator and geography codelists. The
  codelist-reference index reduced a representative five-term query from an unbounded scan to about
  five seconds on the development snapshot; common two- or three-term queries completed in roughly
  0.5–2.6 seconds.
- Representative queries resolved IMF CPI, World Bank Quarterly Public Sector Debt, OECD and
  Eurostat government-debt data, BIS residential property prices, IMF/ECB interest-rate data, ADB
  poverty data and UN SDG public-debt/GDP-growth series. “China general government gross debt”
  includes executable IMF WEO in its bounded candidate set and exposes the relevant indicator and
  geography values.

## Lightweight Plan projection

`source-index-lite-v1` is generated from the accepted complete snapshots and contains all 8
providers and 10,832 dataset identities, 50,758 unique provider-local indicator concepts, 1,297
content-addressed indicator sets and 3,257 dataset/dimension-to-set references. Repeated upstream
codelists with identical code/label content inside one provider share one indicator set. The
3,257 references therefore require only 1,297 stored sets; provider boundaries are never merged.

The projection is 24 MB, about 98.8% smaller than the full 2.0 GB index. Plan AI performs local FTS
and receives no more than eight dataset candidates and five matching indicators per candidate. A
representative bounded result is below 10,000 JSON characters (roughly 2,000–2,500 model tokens),
instead of serializing the index. Each candidate includes provider snapshot identity and executable
state; acquisition must still fetch and validate frequency, geography, unit, current codes and
availability.

## Remaining Phase 3-3 gates

1. Add scheduled refresh policy, provider-specific conditional-update coverage where supported,
   stale alerts and repeat-run drift fixtures.
2. Run search-parity, migration and rollback acceptance before removing
   `data-source-knowledge-v1`.

Until those gates pass, the complete v2 catalog remains available through read-only discovery APIs
and the Plan assistant uses its checked-in lightweight projection; the reviewed v1 endpoint remains
available only for compatibility and clean-runtime seeding.
