# ADR 0011: governed basic output artifacts

Status: accepted; superseded in part by `publication-v1` on 2026-09-06; amended 2026-09-12 for unit-homogeneous chart sets

## Decision

Phase 1D-4 advances a successful reviewed Pipeline run into Output Review and generates artifacts
from the persisted `AnalyticalBundle`. The backend owns generation, selection and final approval;
the HTTP client never submits a client-computed Output session.

The initial fixed guideline is `basic-v1`. It is intentionally narrower than the future product
publication guide. It produces:

- canonical analytical CSV;
- an SVG line chart when Chart is selected;
- an XLSX workbook containing Analytical Data, Model Results, Provenance, Diagnostics and Chart
  Data, with a native Excel chart when plottable data exist;
- immutable copies of the generated Python and supported Stata artifacts;
- a JSON reproduction manifest at final approval.

Every artifact is stored outside the session document beneath the Workflow runtime. The session
contains IDs, media types, SHA-256 checksums and review state. Reads verify session ownership and
the on-disk checksum. Final approval freezes only selected ready artifacts and creates a manifest
that pins the approved Plan and Dataset references, analytical bundle, operation/model results,
limitations and selected artifact hashes.

Research Report generation and model-driven Output revisions were not part of the original
`basic-v1` decision. Phase 1E-4 now layers versioned report authoring, deterministic review and
typed selective regeneration on top of the unchanged basic renderer contract.

Phase 2 promotes the active guideline to `publication-v1`. Its typed registry and mirrored YAML
contract approve line charts with no more than six series, color plus line-pattern encoding, a
color-vision-safe palette, bottom legends, subtle grid lines, bounded titles and 900 by 500 minimum
review renders. Tables freeze and filter headers, right-align numeric formats, use an explicit
ellipsis for displayed missing values and retain source/unit metadata. Deterministic preflight
rejects unknown guideline versions, excessive chart/table density and undersized chart renders.
Historical `basic-v1` artifacts remain immutable but new runs use `publication-v1`.

The registered `research-workbook-v1` structural contract verifies the generated XLSX before
review. The publication reviewer binds chart series and table columns to the approved rows and
validates the checksum-bound Research Report against its typed specification, required sections,
observation count, source note, causal-inference boundary, reproducibility statement and citations.
Same-session artifact comparison separately classifies file/specification/value changes without
returning analytical cell values.

One chart represents one indicator and one homogeneous reported unit. Multiple requested
indicators therefore produce separate SVG artifacts and separate workbook chart-data sheets rather
than a dual-axis or mixed-scale chart. Each `ChartSpec` identifies its indicator and unit; review
fails when generated charts omit approved indicators or a declared unit disagrees with the bound
rows. Different legitimate units across separate charts are expected and are not normalized by a
package-wide cosmetic patch.

## Consequences

- Pipeline Run is now the transition from Transformation to Output Review.
- Returning to Transformation and saving an edit invalidates Output while preserving old artifacts
  as history; it never triggers an automatic rerun.
- Workbook/chart tests inspect cells and chart XML. Routine tests do not open a browser or use
  screenshot comparison.
- Typed selective regeneration, narrative generation and local visual Review AI began in Phase 1E.
  Phase 2 now includes the registered workbook template/linter, artifact comparison and expanded
  publication-specific review. Remote multimodal review remains separately authorized. See ADR 0012.
