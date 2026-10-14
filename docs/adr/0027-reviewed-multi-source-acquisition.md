# ADR 0027: Reviewed multi-source acquisition

Status: accepted

Date: 2026-09-12

## Context

An approved Plan may require indicators from more than one registered public connector. The Data
stage previously rejected every such Plan after approval, even though each source was executable in
isolation. Silently joining provider outputs would also violate the review-gated workflow because
frequency, units, missing values and series identity can differ across providers.

## Decision

The acquisition service executes each enabled public source as its own bounded connector request.
Every request retains its own source run, immutable normalized snapshot and provenance receipt.

Multiple normalized sources are combined only as a canonical long-form union. The union:

- keeps `entity_code · indicator_code · frequency · period` as its observation identity;
- rejects overlapping identities instead of choosing one provider silently;
- preserves frequency, unit attributes and missing observations without implicit conversion; and
- adds `source_connector_id`, `source_dataset` and `source_snapshot_id` to every merged row.

The resulting snapshot is represented by a `data_merge` graph node in
`waiting_for_review`. The Data screen shows the merge policy and lineage fields. A separate typed
`approve_data_merge` command records the reviewer and time and moves that node to `approved`.
`data_next` fails closed until this review is complete.

This acquisition union does not activate the analytical `merge` transformation. Horizontal joins,
frequency conversion, unit conversion and identity reconciliation remain separately reviewed
operations.

## Consequences

- A multi-provider Plan can enter Data without bypassing a human checkpoint.
- Original provider snapshots remain available for audit and portable-session export.
- Downstream transformations can consume one canonical long dataset while retaining row-level
  source lineage.
- Plans whose sources overlap on canonical identity keys stop in acquisition with a concrete
  reconciliation error.
