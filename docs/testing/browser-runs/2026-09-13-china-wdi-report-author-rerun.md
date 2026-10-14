# Browser run: China WDI rebalancing Report Author regression

- Date/time (UTC): 2026-09-13 16:49–17:04 UTC
- Application commit: `40a1996`
- Result: `FAIL`
- Browser/runtime: local Chromium automation against the running FastAPI and Vite services
- Session ID: `workflow-session-a713cd0ffacc40a88a64750796ef0e40`
- Coverage: single provider, World Bank WDI
- Plan/Data/Report Author provider/model: DeepSeek / configured `deepseek-flash`
- Review AI provider/model: `codex-local` / local Codex authentication

## Research question and intent

The simulated user asked whether China's growth has become less investment-driven and more
household-consumption-led since COVID-19. The request constrained acquisition to World Bank WDI
annual data from 2015 through the latest available year, compared 2015–2019 with 2020 onward,
requested a two-year joint forecast of the investment and household-consumption shares, and asked
for charts, a compact table, cleaned data and a research report.

This reran the same single-provider scenario that failed on commit `de6c552`, after the Plan model
contract, handoff, Data AI and Report Author/Reviewer work. It exercised only normal browser controls;
no database, artifact or backend state was changed to force progress.

## Journey

| Stage | User/AI interaction and decisions | Result/evidence |
|---|---|---|
| Clarification | Answered five DeepSeek questions: use WDI `NE.GDI.TOTL.ZS` and `NE.CON.PRVT.ZS`, split at 2020, estimate one joint two-variable VAR, forecast two annual steps and produce all requested outputs. | The questions supported explicit options and Plan drafting showed a visible disabled `Drafting Plan…` state. The first rationale incorrectly said the bounded index lacked the share series even though its selected option named both executable codes. |
| Plan | Reviewed the generated typed Plan, confirmed China membership and aggregation, then approved it. | Period was `2015` to `latest` at annual frequency. `ModelIntentV2` contained exactly two ordered `system` variables and an explicit two-period horizon at 95% confidence. The generated short title was `中国投资与消费占比变化及两年预测`. |
| Data | Acquired one World Bank WDI run, then asked Data AI to remove missing values and sort by indicator and period. Approved its two proposed operations. | Acquisition returned 22 rows. `period`, `value` and `unit` appeared on the first preview page. Removing the two incomplete 2025 rows and sorting produced a 20-row snapshot with 0% missing and 0 duplicate keys. This confirms the former Data AI missing-value regression is fixed. |
| Transformation | Reviewed the compiled pipeline and ran it without manually changing its specification. | The compiler produced exactly one VAR with the two approved share indicators, fixed lag 1, constant and a two-period horizon. This confirms the former extra-forecast-target regression is fixed. The command then returned HTTP 422 because DeepSeek failed `ReportDraftV1` validation after the configured repair attempts. |
| Output | Not reached. | No ArtifactSet existed, so Codex-local semantic/visual review could not run. |
| Resume/final state | Reloaded/read the public session after three visible retry attempts. | Session remained `pipeline_editing` at Transformation, with zero persisted model results, no analytical bundle, no Output handoff or artifacts, and no manifest. Plan and Data handoffs remained intact. |

## Output review loop

No Output review iteration was possible. The configured reviewer was correctly reported as
`codex-local`, but Report Author failed before an ArtifactSet could be created.

- Deterministic preflight at Finish: not reached.
- Final Review AI status: not reached.
- Frozen manifest ID/hash: none.
- Post-reload verification: the failed session and its Plan/Data snapshots remained available at
  Transformation; there was no completed output state to verify.

## Findings

| Severity | Summary | Issue/commit | Status |
|---|---|---|---|
| Blocking | DeepSeek returned an invalid report contract after repair. The combined pipeline request returned HTTP 422 and left no durable model results or analytical bundle, so the author cannot be retried independently and Codex-local review cannot begin. | GitHub #25 | Open. |
| High | Data and Transformation displayed the empty handoff placeholder even though the session API exposed two persisted `mra-stage-handoff-v1` envelopes and a populated `currentHandoff`. | GitHub #23, browser evidence added | Open. |
| Medium | Clarification claimed the bounded WDI index lacked the requested share series, then proposed and successfully acquired those same two series. The provisional limitation remained in later handoffs after acquisition had proved availability. | GitHub #22, browser evidence added | Open. |
| Observation | Some automation-level pointer clicks did not dispatch while keyboard activation or DOM-equivalent pointer events did. Because normal controls worked elsewhere, this remains a browser-harness observation until manually reproduced. | No issue | Needs reproduction. |

## Conclusion

The run materially improved on the earlier scenario: clarification, typed Plan creation, live WDI
acquisition, AI-proposed reversible cleaning, preview usability and exact Plan-to-VAR compilation all
worked through the browser. It does **not** satisfy the end-to-end completion rule because Report
Author contract validation blocked Output creation. Codex-local could therefore neither approve the
report nor drive a governed revision; Finish, manifest creation and completed-state reload were not
available. The next rerun should start after GitHub #25 is fixed and must continue through a real
Codex-local `pass`, Finish and manifest reload.
