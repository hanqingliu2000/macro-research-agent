# Visual artifact authoring and acceptance rubric

Status: **placeholder active** — 2026-09-28

Use the single [Nature-inspired academic placeholder](academic-publication-placeholder-v1.md)
(`academic-publication-placeholder-v1`) for new generation and Codex-local acceptance. Its typed
subset lives in `workflow/publication_rubric.py`; reviews and manifests retain its version/hash.
Substantive failures remain blocking within three rounds. `VISUAL-RUBRIC-PLACEHOLDER` records the
limited scope and may be acknowledged at Finish; it is not journal submission certification.
Final project creative direction, print packaging and the icon standard remain unprovided.

## Historical missing-rubric policy (before 2026-09-28)

The following describes the earlier implementation, not the current review rules. Historical
reviews remain unchanged.

The project owner has not yet supplied the project-specific chart/visual-artifact creation
standards or the corresponding visual acceptance rubric. A product-specific icon creation standard
and icon acceptance checklist are also missing; the existing UI rules cover only structural use,
accessibility names and the prohibition on emoji/Unicode substitutes.

`publication-v1.yaml` remains an interim deterministic technical contract for supported chart
types, dimensions, metadata, accessible encodings and workbook structure. It is not a substitute
for the missing product-specific creative direction or final visual acceptance rules.

Until the rubric is supplied:

- Codex-local review may report only directly observable mechanical defects such as clipping,
  overlap, illegible text, a missing multi-series legend or a render/specification mismatch.
- Every Codex-local visual report includes `VISUAL-RUBRIC-MISSING` and remains advisory.
- Codex must not invent brand, editorial or aesthetic preferences and must not author correction
  patches.
- Deterministic structural failures remain blocking. Final visual quality still requires a human.

The future rubric needs, at minimum: intended audience and publication context; chart-selection
rules; typography and hierarchy; layout and annotation rules; palette/brand constraints;
accessibility requirements; number/date/unit conventions; severity and pass/fail thresholds; and
approved/rejected reference examples.

The future icon standard additionally needs: an approved grid and bounding box; stroke/fill and
corner rules; optical sizing; state variants; accessibility/contrast thresholds; naming and export
rules; and approved/rejected reference examples.
