# Browser run: India unemployment and the fixed visual placeholder

- Date: 2026-09-28
- Application base: `4466b30` plus the academic visual placeholder working tree
- Result: `FAIL` — round 3 exhausted; a unit-label revision produces an empty chart
- Session: `workflow-session-ca9a51810e294a30b7425aa393e59758`
- Coverage: single provider, World Bank WDI
- Runtime: local Chromium controls, FastAPI and Vite; no backend evidence mutations
- Plan/Report Author: DeepSeek (configured model); reviewer: Codex-local
- Rubric: `academic-publication-placeholder-v1` (one Nature-inspired operational standard)

## Question and journey

The user is unsure whether women in India shared in the post-pandemic improvement in job
prospects. Compare annual female/male unemployment during 2010–2024, distinguishing pre-pandemic,
disruption and recovery, with charts, underlying data and a short descriptive report.

- Clarification selected WDI, annual frequency, 2010–2019 / 2020–2021 / 2022–2024 and rate levels.
  A custom answer excluded regression, causality, forecasts and a derived gap series, and requested
  discussion of the participation/job-quality limitations of unemployment rates.
- Plan produced `SL.UEM.TOTL.FE.ZS` and `SL.UEM.TOTL.MA.ZS`, but turned a discovery-only retrieval
  limitation into an acquisition blocker. A normal chat correction confirmed codes and requested
  treating actual availability as an acquisition check. The proposed caution/blocker patch was
  explicitly approved through its impact-confirmation dialog. No backend override was used.
- Geography was confirmed as IND and Plan Next was approved.
- WDI acquisition completed with 30 rows, 0% missing observations and no duplicate keys.
  Data AI inspected full acquired metadata, identified percent-of-sex-specific-labour-force
  definitions despite null `unit` fields, and proposed only a reproducible sort. That proposal
  was approved and the 30-row descriptive model was run through the UI.
- Generated all six selected artifacts (CSV, two SVGs, XLSX, Python and Research Report).
  CSV and workbook initially exceeded the 24-column technical limit because provider metadata
  appeared as display columns. Normal Output chat requested compact columns on each artifact.
- Applying the CSV correction automatically consumed round 1, which failed on the still-wide
  workbook before either real visual or semantic review ran. Applying the workbook correction
  started round 2, including real Codex review. No required artifact was deselected.
- Selected the female chart and requested `Unit: percent of female labour force` through Output
  chat. Inspected the unit-only proposal and explicitly applied it. Automatic round 3 reviewed
  the regenerated chart and unchanged companion artifacts. No data or model result was edited.

## Review and final state

| Round | Artifact-set hash | Result |
|---|---|---|
| 1 | `sha256:37e0eea89380e6e4e3fb59fd5fedcdbae87b85e5699900f6e00f960984b8a2c5` | Preflight fail: workbook still exceeds the column limit; no model review yet. |
| 2 | `sha256:1fb6028b6ab26a243127beab6c0a89780d730d277504476436c55f322c36ad29` | Preflight passes; real Codex visual fails on both chart units; report requires upstream stage. |
| 3 | `sha256:2f8bdd1cc38d112def175a6ee42a981669895f93ebbda9c87276a62f1585edb9` | Preflight passes, but the female chart becomes empty after its unit-label revision; visual and report review fail. |

- Review 2 completed at `2026-09-28T16:30:34.115958Z`, provider `codex-local`, model
  `codex-configured-default`; all six selected artifacts and 30 underlying rows were bound.
- Rubric hash: `sha256:88ef7a346e23da4d3b713e50201a7bc587fffbc795e3bf0707b7cebf667acbdd`.
- Active dataset: `dataset-83fe086d812c4cd39f6bf802bff0d697`, content hash
  `sha256:2c23aa4c48341f852e906631554f58a6b5d72d3e913baf2dc88891a8a5e29522`.
- Analytical bundle: `analytical-bundle-11d10554bbd2405ab743653dcd837b06`.
- Findings: two `CODEX-VISUAL-AXIS-UNIT` failures ("As reported" instead of each sex-specific
  percentage denominator); `REPORT-APPROVED-SCOPE` (phase statistics missing);
  `REPORT-DIRECTION-ACCURACY` (opposite-direction claim contradicted by observations);
  `REPORT-REPRODUCTION-COMPLETENESS` (promised Stata artifact absent); and
  `REPORT-ARTIFACT-TRACEABILITY` (report references superseded table/workbook candidates).
- Review 3 (`review-a8d4ac92939f39f8`) completed at `2026-09-28T16:47:04.335922Z` under the same
  rubric hash. It caught `CODEX-VISUAL-RENDER-SPEC-MISMATCH`: the revised female chart says no
  plottable series are available despite the bound dataset retaining 15 numeric observations.
  Its empty-state title also clips; the unchanged male chart still lacks an explicit unit.
  Regenerated female artifact: `artifact-c6104e56ec9b479f9be79d789a83e7dc`; render hash
  `sha256:e7d47861a2208955025690388f3f1d7976b41066aa30d9fee52b36fbaf95257f`.
- Report status remains `requires_upstream_stage`, with missing phase analysis/Stata code,
  incorrect direction claims and superseded artifact references. No report rewrite directive
  was issued for upstream requirements. No counter reset or backend fix forced progress.
- Finish remained disabled; no frozen manifest exists. Reload preserved `3/3 review rounds`,
  the disabled `Review limit reached` control, and disabled Finish.

The rubric successfully detected an actual chart defect, but this journey **did not achieve**
acceptable chart/report outputs within the allowed review loop. Detection is not an E2E pass.

## Findings

- Plan AI still occasionally conflates bounded discovery results with executable connector
  availability. This run recovered through normal human/AI Plan revision before acquisition.
- WDI leaves `unit` unresolved even when the acquired indicator name specifies the denominator.
- A presentation-only unit revision incorrectly changes the data selection: code inspection
  confirms regeneration passes the edited `ChartSpec.unit` to `_chart_frame`, which filters
  the source `unit` column. Those source units are null, so the revised chart becomes empty.
  Separate immutable series selection from display-unit wording; never hide an upstream unit
  conversion inside a presentation patch. The new rubric catches this defect but does not fix it.
- Generated technical-metadata-heavy tables fail their own default column limit. Independent
  presentation fixes consume the shared three-round budget, including preflight-only attempts.
- During a long Run/report-generation request, the Run control lacks the clear pending treatment
  used for Output review; no repeated Run was sent in this test.
- The browser automation tool reported successful radio clicks without dispatching the controls;
  direct DOM `click()` on the same visible controls worked. This is recorded as an operator/tool
  issue, not evidence that a human mouse interaction in the product is broken.
