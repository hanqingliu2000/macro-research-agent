# Academic publication chart standard — placeholder v1

- Version: `academic-publication-placeholder-v1`
- Status: active **placeholder**, not a claim of journal acceptance
- Selected and researched: 2026-09-28
- Owner: project maintainer; replacement requires a new version

## 1. Decision and reference

Use **one fixed Nature-inspired standard** for the current generation/review experiment. The
purpose is to test whether the application can produce acceptable charts within **at most three
Output review rounds**, not to build a journal-profile selector. Earlier missing-rubric evidence
remains historical; new reviews receive the versioned rules below.

The single external reference is Nature's official
[Building and exporting figure panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/),
accessed 2026-09-28. Its relevant guidance favors editable vector artwork and readable standard
fonts; coherent panel layouts; accessible colors, contrasting text and visible keys; and avoiding
decorative elements that obscure scientific meaning. Its print profile uses 89/183 mm widths,
170 mm maximum height and 5–7 pt lettering. These **print settings are reference information,
not claims about our current native-size review PNG**. The current workbench supplies SVG masters
and direct PNG review renders; journal-specific print export and submission certification remain
outside this test.

Everything below is this project's explicit operational adaptation. Data semantics, severity,
hash binding, supported chart types and test thresholds are **project rules**, not attributed to
Nature. Do not import other publishers' incompatible requirements during review.

## 2. Scope, priority and exclusions

- Applies to selected analytical **line charts** and their bound specifications/captions.
- Underlying data, analytical results and the approved research question are authoritative.
- A standard cannot authorize changing observations, units, model results or the approved sample.
- Continue using `publication-v1` for typed chart/table/report structure; this visual rubric is an
  additional independently versioned component, not a rename of historical artifacts.
- CSV/XLSX are analytical companions, not typeset journal tables. Their existing 24-column
  technical limit is unchanged; this experiment does not silently impose another table limit.
- Maps, photographs, diagrams, icons, branding, animations, arbitrary chart types and full-page
  journal composition are out of scope. Final project creative direction is still unprovided.
- Apply only relevant rules: a historical line chart does not need a forecast band merely because
  a separate forecast table/report is part of the approved deliverable.

## 3. Fixed authoring requirements

### 3.1 Purpose and artifact identity

Each chart must have a specific analytical purpose and a non-empty title, indicator identity,
unit, source note, descriptive alternative text, ordered series and snapshot hash. Identify the
period and entities either directly or through an unambiguous bound caption/specification.
Avoid unsupported causal words such as “effect of” for descriptive comparisons. A shortened title
may be used for fit, but must not remove the indicator identity or change the meaning.

### 3.2 Canvas and layout

- Native vector/review canvas: at least 900 × 500; specification limits still apply.
- Plain white background; dark text; no gradients, decorative shadows, pictograms or 3-D effects.
- Reserve distinct title, plot, time-label, legend and source-note areas.
- Required text and marks must remain inside the canvas. Wrap a long source note rather than
  silently dropping it. Do not cover values with labels or keys.
- At most six series per supported chart. More series require approved grouping/splitting, never
  silent omission. Separate indicators and incompatible units into separate charts.
- Enlarging the canvas is a presentation change; changing the sample is not.

### 3.3 Typography and labels

- Use consistent, editable sans-serif SVG text with a font available to the renderer.
- Current native-size defaults: 20 px title, 12 px axes, 13 px legend, 11 px source note.
  These are screen/vector-coordinate defaults, **not final printed point sizes**.
- No missing-character boxes, clipped minus signs, unreadable superscripts or overlapping labels.
- Titles may occupy two lines. Notes may wrap across multiple lines; enlarge reserved space.
- Precision must communicate the scale without excess digits. A formatting-only change cannot
  round the stored observations or alter the model result.
- Keep opaque codes traceable. Define them in the title, accessible description or companion
  specification/report; country codes are acceptable if the research scope identifies them.

### 3.4 Encodings and accessibility

- Keep the registered palette and alternate solid/dashed/dotted line patterns; hue must not be
  the only way to identify overlapping series. The legend must match both color and pattern.
- Prefer dark labels on white. Light gridlines provide context without competing with marks.
- Use a legend or unambiguous direct labels. A one-series chart may omit a redundant legend only
  if the entity/series is otherwise explicit.
- Every SVG has title/description metadata. The companion table supplies exact values; the
  description must not contradict those values. Do not infer a WCAG certification from this test.
- Flag unreadable essential marks/labels; an exact contrast ratio is a deterministic measurement,
  not something a reviewer should guess from a PNG.

### 3.5 Axes, units and comparisons

- Sort periods chronologically, preserve meaningful gaps and expose the displayed time range.
- Line-chart y axes may be non-zero. Visible labels must make the actual range clear; a non-zero
  baseline alone is not a failure. No unmarked broken or logarithmic axes.
- Keep unit, price basis, scale and frequency consistent with approved rows and transformations.
- Distinguish percent from percentage points, fraction from percent, nominal from real amounts,
  index level from change, and level from growth. A stored percentage is not multiplied by 100
  unless the registered formatter explicitly expects a fraction.
- Do not put incompatible units on a shared scale. This renderer does not support dual axes.
- Comparisons across providers must retain indicator definitions and any comparability caveat in
  companion metadata/report. Similar names do not establish equivalent measurement concepts.

### 3.6 Missingness and integrity

- A missing value is not zero. Never create an observation merely to make a line continuous.
- Break paths at missing values; a solitary observed point should remain visible.
- Do not average duplicate entity-period observations silently as an aesthetic fix. Resolve
  ambiguous analytical keys upstream through approved operations.
- A data filter, rebase, interpolation, seasonal adjustment or unit conversion must be an
  approved, reproducible data/transformation step, not a hidden chart patch.
- Check counts, ordering and displayed magnitudes against the full snapshot-bound rows and typed
  model results. Screenshot appearance cannot prove numeric accuracy.

### 3.7 Estimates, uncertainty and forecasts (conditional)

- If a chart displays forecasts, distinguish them from observations using a label plus an
  encoding change. State the forecast start and horizon in its caption/specification.
- If an interval is drawn, label its level and meaning (for example, prediction interval versus
  standard error). Use only returned interval bounds; do not fabricate a band.
- Forecast-only tables and reports remain legitimate deliverables when that is the approved
  scope. Do not demand that every historical chart show forecasts.
- Unsupported transformations or missing model results require returning upstream. Neither
  styling nor report rewriting may conceal an absent analysis.

### 3.8 Sources and reproducibility

The artifact/specification or companion report must identify the provider, dataset, indicator,
retrieval/vintage context and approved transformations. The render must show a concise source
note. Keep detailed source URLs, result/snapshot hashes and code versions in reproducibility
metadata; do not cram the entire manifest into the image. Credentials never belong in a caption.
Maintain SVG as the editable master and bind each direct PNG to its artifact checksum.

## 4. Review rules and severity

| Rule ID | Check | Failure threshold |
|---|---|---|
| `VISUAL-CLIPPING` | Canvas containment | Required text/data are cut off |
| `VISUAL-OVERLAP` | Layout separation | Overlap prevents identifying values or labels |
| `VISUAL-LEGIBILITY` | Readable text/glyphs | Essential content cannot be read |
| `VISUAL-LEGEND` | Series identification | Required series cannot be distinguished |
| `VISUAL-RENDER-SPEC-MISMATCH` | Render vs bound spec/rows | Wrong series, order, value or concealed gaps |
| `VISUAL-AXIS-UNIT` | Range, period, units | Scale or unit makes the figure misleading |
| `VISUAL-UNCERTAINTY` | Conditional estimates/intervals | Displayed uncertainty or forecast is misrepresented |
| `VISUAL-CAPTION-SOURCE` | Identity and source | Meaning/source cannot be resolved from supplied evidence |

Report concrete evidence and the affected artifact for each finding. Minor readability issues
that do not obscure meaning may be warnings. Personal taste, speculative defects, unsupported
print-DPI guesses and unrelated publisher rules are not valid findings. Missing data/analysis is
an upstream issue. The fixed placeholder must not be weakened after seeing a failing test.

`VISUAL-RUBRIC-PLACEHOLDER` is an explicit scope advisory: the standard is temporary and does not
certify journal submission. It does **not** excuse substantive visual failures. The final human
Finish acknowledgment remains required. `VISUAL-RUBRIC-MISSING` is historical, not emitted for
new reviews using this standard.

## 5. Three-round acceptance protocol

1. Generate from approved data and specifications; run deterministic structural/numeric checks.
   Before each formal handoff, the DeepSeek chart author performs two independent checks of
   full-data/specification consistency and final SVG structure. Both must pass; failures/errors
   are recorded and stop handoff without spending a formal review round. These checks are not
   pixel-based visual approval. See ADR 0032 for bounds and the correction/approval boundary.
2. Round 1: Codex-local reviews direct checksum-bound renders and evidence under this exact rubric.
3. On findings, the user approves only supported chart/table presentation patches or report
   section directives. Regenerate affected artifacts, preserve data/model hashes, then review
   the new exact package. That next review consumes round 2 (and, if necessary, round 3).
4. Success requires **no unresolved substantive visual finding**, semantic report `pass`, no
   blocking preflight findings, and at most three Output rounds. The placeholder scope advisory
   alone may be explicitly acknowledged. A pending review, unavailable reviewer or exhausted
   limit is not a pass. First-round success is acceptable; do not manufacture a defect to force
   a revision. Exercise a legitimate user-requested presentation revision where practical.
5. Finish/freeze the exact reviewed selection, obtain the manifest, reload and verify persistence.
   Do not reset counters, deselect a requested chart to hide a failure, edit database rows, or
   create a replacement session and report it as the same successful run.

Record separate single-provider and multi-provider journeys under `docs/testing/browser-runs`:
session ID, research scope, major interactions, provider/model, dataset hashes, artifact-set hashes,
each round's rules and disposition, rubric version/hash, final manifest and reload result.
If a defect requires a code fix, record the failed attempt; resume through normal UI if possible
or explicitly label a fresh rerun. No model-driven browser screenshots are used for acceptance.

## 6. Implementation and future replacement

The typed runtime subset lives in `workflow/publication_rubric.py`. Generation/Report Author
receives it through the publication guideline; Codex-local receives the same rule IDs and severity
policy. Review records and the final manifest retain its version/hash. The three-round limit and
Plan/Run/Finish human gates are unchanged. Historical review records remain immutable.

The subset is deliberately short enough for the model context; this document explains operational
details. Future journal-specific print profiles, additional chart types and final creative
standards need separate versioned development and acceptance, not implicit reviewer preferences.
