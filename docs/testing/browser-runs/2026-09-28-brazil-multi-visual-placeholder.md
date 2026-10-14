# Browser run: Brazil debt/growth across IMF and World Bank

- Date: 2026-09-28
- Application base: `4466b30` plus the academic visual placeholder working tree
- Result: `FAIL` for complete E2E; both charts have no substantive visual findings at round 1
- Session: `workflow-session-f061079d80a64c699297bf7efd03d965`
- Coverage: IMF WEO + World Bank WDI (two providers)
- Runtime: local Chromium controls, FastAPI and Vite; no backend evidence mutations
- Plan/Report Author: DeepSeek (configured model); reviewer: Codex-local
- Rubric: `academic-publication-placeholder-v1`

## Question and journey

The user is concerned that Brazil accumulated public debt without sustained growth and asks whether
the post-pandemic picture is an improvement or merely a rebound. Use general-government gross debt
as a GDP share from IMF WEO and real GDP annual growth from WDI, 2010–2024, with separate labelled
charts, underlying data and a short report; exclude causal claims and forecasts.

- Clarification selected general-government gross debt, pre-pandemic 2010–2019 versus recovery
  2021–2024, WDI `NY.GDP.MKTP.KD.ZG`, and as-published ratios with no rebasing.
- Geography was confirmed as BRA. Plan acquisition was approved with vintage/comparability cautions.
- The initial Plan has no model job although its narrative asks for descriptive period comparisons;
  Transformation must explicitly configure a descriptive analysis through normal controls.
- Both connectors completed (15 annual observations each), with 30 merged rows, no missing values
  and no duplicate keys. The cross-source review explicitly preserved frequency and separate
  units, and the user approved the merge.
- A Data AI diagnostic/keep/sort request failed with `invalid_model_contract` after repair. Manual
  operations stayed available; no fallback model was selected.
- Returned to Plan to explicitly add a descriptive model, make the period discussion qualitative,
  and choose Python-only reproduction. DeepSeek proposed the requested patch, but confirming it
  returned HTTP 422: `completed graph node references are immutable:
  node-research_plan-95d7006b2d1543a29be716b9ddd7cc1f`. The patch did not apply. Cancelled the
  dialog and rejected the proposal; continued the **original** Plan rather than editing storage.
- Tried the manual Keep columns shortcut. It removed unit and source identifiers along with
  non-required columns; Undo restored the source snapshot. A narrower Data AI request then
  successfully proposed an explicit 13-column keep operation including units/source identity.
  Approved it; no observation, unit or numeric value was altered. Source snapshots retain full
  provider metadata independently of the presentation-oriented active table.
- In Transformation, manually added DESCRIPTIVE and explicitly entered `GGXWDG_NGDP` and
  `NY.GDP.MKTP.KD.ZG`, saved the specification and approved Run.

## Review and final state

All six artifacts remained selected. The compact active table has 13 fields, so preflight passed
without table-width revisions or lost review rounds. The original Plan (including its Stata
deliverable) remained authoritative after the rejected/failed upstream patch.

- Codex-local round 1 completed `2026-09-28T16:41:14.661352Z`, model
  `codex-configured-default`, inspecting both direct chart renders and 30 underlying rows.
- **Chart-only result:** no `CODEX-VISUAL-*` substantive finding; the only visual-related warning
  is the known placeholder scope advisory. Both requested charts meet the current interim review
  standard on their first review. This is not a full Workflow pass.
- **Report result:** `requires_upstream_stage`. Codex found incorrect period medians/means,
  incorrect 2024-versus-2019 debt ordering and an incorrect joint-direction claim. It also found
  the promised Stata artifact absent because of reshape-unsafe indicator codes. No report rewrite
  can supply that missing code; no rewrite directive was returned.
- Review ID: `review-9763866c422a64cb`.
- Artifact-set hash: `sha256:978f375acebd5cd72adef808d137578e77de7fac0ba8dd1ecaaeb0b0c965ce6c`.
- Rubric hash: `sha256:88ef7a346e23da4d3b713e50201a7bc587fffbc795e3bf0707b7cebf667acbdd`.
- Source snapshot hashes: IMF
  `sha256:f8ea002d3306bc324033ea03ef061b3674a5dffc5fc622b4edb74ba5264ad2d7`; WDI
  `sha256:d9ea9eaf5b07e806eccf9c18f98da573404eeff47b1b20d2832e13737f326101`.
- Merged snapshot hash: `sha256:822a390f9413a3dca63cba41581126728bcf2dc231994da864ce4c5e14c4b654`.
- Active prepared snapshot: `dataset-3ab190326328439982fcd973d8b9126f`, hash
  `sha256:dcfaa68be8c46a23ec2c4c1f2ada772abe255cf81ad9ac7c518f2f82276d90e1`.
- Analytical bundle: `analytical-bundle-4f6dd351bb9c4847a2104bffd611322f`.
- Finish stayed disabled, no frozen manifest was produced, and reload retained the round-1 failure.

## Findings and conclusion

The fixed visual rubric is usable for these two-provider charts, but **the complete end-to-end
acceptance did not pass**. The failed upstream Plan revision, unit/provenance-dropping shortcut,
Data AI schema failure, missing approved code and unreliable report arithmetic remain separate
product/model findings. No backend storage was altered and no review counter was reset. Additional
unchanged reviews would not resolve an upstream missing deliverable, so no redundant rounds were
spent merely to exhaust the budget.
