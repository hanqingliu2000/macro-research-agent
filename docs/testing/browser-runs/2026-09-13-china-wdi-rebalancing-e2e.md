# Browser run: China WDI rebalancing and two-year share forecast

- Date/time (UTC): 2026-09-13 00:40–00:57 UTC
- Application commit: `de6c552`
- Result: `FAIL`
- Browser/runtime: local Chromium automation against the running FastAPI and Vite services
- Session ID: `workflow-session-a23147b5ef9c41eaa90e673edd4df596`
- Coverage: single provider, World Bank WDI
- Plan AI provider/model: DeepSeek / configured `deepseek-flash`
- Review AI provider/model: `deterministic-local` / `MRA_OUTPUT_REVIEW_PROVIDER` not configured

## Research question and intent

The simulated user asked whether China's growth has become less investment-driven and more
household-consumption-led since COVID-19. The request constrained acquisition to World Bank WDI
annual data from 2015 through the latest available year, asked for a pre/post-2020 comparison and
a two-year joint forecast of the investment and household-consumption shares, and requested charts,
a compact table and a research report.

The deliberately broad question exercised clarification, Plan revision, live single-provider
acquisition, AI-assisted and manual data preparation, Plan-to-analysis compilation, a manual
analysis correction, governed Output revisions and the three-round Review AI limit. No session data
or workflow state was altered outside the visible application controls.

## Journey

| Stage | User/AI interaction and decisions | Result/evidence |
|---|---|---|
| Clarification | Selected WDI `NE.GDI.FTOT.ZS` and `NE.CON.PRVT.ZS`, descriptive correlation with `NY.GDP.MKTP.KD.ZG`, a two-share joint VAR, three comparison periods and the last complete analytical year. | Six questions exposed explicit choices and an alternative free-text answer. Plan drafting displayed a disabled `Drafting Plan…` state. |
| Plan | The first draft put an explanatory sentence in `ResearchPeriod.end`. The user asked Plan AI to use the literal `latest available year` token and retain all three WDI indicators. The proposal was reviewed and applied, then China membership/aggregation was confirmed. | The revised period became executable and acquisition was enabled. The title was shortened to `中国增长是否从投资驱动转向消费驱动（WDI 2015–最新年）`. |
| Data | Executed one World Bank WDI run, paged through the preview, asked Data AI to remove null `value` rows and sort, approved its sort proposal, then used the visible `Filter missing` quick action. | 33 raw rows covered all three indicators. The two 2025 share observations were null; after two reversible operations the active snapshot contained 31 rows, 0% missing and 0 duplicate keys. `period`, `value` and `unit` were visible on the first preview page. |
| Transformation | Reviewed three compiled jobs. The VAR incorrectly contained GDP growth as a third endogenous variable, so the user asked Analysis AI to keep only the two share series. The request failed; the user corrected the visible VAR field manually and saved it. | Manual specification persisted as `NE.GDI.FTOT.ZS, NE.CON.PRVT.ZS`, fixed lag 1, constant and forecast horizon 2. The three registered jobs executed and produced eight artifacts. |
| Output | Ran Review AI, selected the two wide table artifacts in turn and approved governed eight-column revisions. | Both `TABLE-COLUMNS-001` blockers were removed. The revision history advanced and the artifacts were regenerated without row loss. |
| Resume/final state | Remained on Output after the review limit was reached. | Review status `FAIL`, iteration `3/3`, one unresolved `FORECAST-DELIVERABLE-001`; Finish remained disabled and no frozen manifest was created. |

## Output review loop

| Iteration | Artifact-set hash | Review status | Findings and user disposition | Resulting version |
|---|---|---|---|---|
| 1 | Current generated set | `fail` | Two `TABLE-COLUMNS-001` findings plus a false `FORECAST-DELIVERABLE-001` for GDP growth. User selected `analytical_data.csv` and requested exactly eight publication columns. | Versioned analytical CSV retained 31 rows and only `provider`, `dataset`, `entity_code`, `indicator_code`, `frequency`, `period`, `value`, `unit`. |
| 2 | Regenerated CSV set | `fail` | Workbook remained too wide; GDP forecast finding remained. User selected `research_workbook.xlsx` and applied the same bounded column correction to its analytical sheet. | Workbook regenerated; comparison showed no rows added or removed. |
| 3 | Workbook `sha256:9b1748ff7c9a01a6a666364e6a7bcf32fb77958ae8f1b38f839ee3d826cea811` | `fail` | Only the false GDP-growth forecast requirement remained. It cannot be corrected by a chart/table-only Output patch without contradicting the approved two-share VAR. | No further correction; review limit reached. |

- Deterministic preflight at Finish: one blocking `FORECAST-DELIVERABLE-001` requiring
  `NY.GDP.MKTP.KD.ZG` periods 1 and 2, although the approved Plan requests forecasts only for the
  two share indicators.
- Final Review AI status: `fail` from `deterministic-local`, iteration 3/3.
- Frozen manifest ID/hash: none.
- Post-reload verification: not applicable because Finish never became available.

## Findings

| Severity | Summary | Issue/commit | Status |
|---|---|---|---|
| Blocking | Forecast acceptance derives targets too broadly: a descriptive correlation indicator is treated as a required forecast target, contradicting the approved two-share VAR. | New finding; related to the forecast contract implemented for GitHub #15. | Open. |
| High | Analysis AI correction returned HTTP 500. Backend evidence shows an uncaught `ValueError`: `An Analysis transformation refusal cannot substitute an unrelated model job.` | New finding; related to the Analysis revision boundary covered by GitHub #17. | Open. |
| High | Plan-to-Pipeline compilation placed all three source indicators in the VAR despite the clarification and Plan text naming only the two share series. | Issue #18. | Fixed in code; browser rerun pending. |
| Medium | Data AI correctly diagnosed the two missing analytical values but ignored the explicit removal request and proposed only `sort`; the separate quick action completed the intended reversible filter. | Issue #21. | Fixed in code; browser rerun pending. |
| High | The generated research report contains execution counts and boilerplate but no model estimates, forecasts, sub-period comparison or substantive answer to the research question. | New finding. | Open. |
| Coverage gap | Output review used `deterministic-local` because `MRA_OUTPUT_REVIEW_PROVIDER` was not configured, so this run did not exercise Codex-local multimodal visual review. It also reported no structural or visual findings despite the non-substantive report. | Environment/configuration plus review-scope gap. | Open. |
| Observation | Several automation-level clicks on proposal/apply/review buttons did not dispatch, while invoking the same visible button's native click did. Normal clicks worked on other controls; manual-browser reproduction is needed before classifying this as a product hit-target defect. | Browser harness observation only. | Needs reproduction. |

## Conclusion

The workflow successfully covered clarification, an AI Plan revision, live single-source acquisition,
reversible cleaning, manual model correction, analysis execution and bounded Output revisions. It
does **not** satisfy the end-to-end completion rule because the approved two-share forecast contract
was widened incorrectly at Output, Review AI ended in `FAIL`, the three-round limit was exhausted
and no final package could be frozen. The next regression should first correct forecast-target
derivation and the Analysis AI 500, configure Codex-local review, then rerun this same scenario until
Review AI passes and the frozen package survives reload.
