# Browser run: issue #15 forecast-contract regression

- Date/time (UTC): 2026-09-12
- Application commit: issue-fix commit containing this log
- Result: `PARTIAL`
- Browser/runtime: local Chromium automation against the running FastAPI and Vite services
- Session ID: `workflow-session-41918c7be26a41b2894d6b2ae6c6c777`
- Coverage: existing IMF WEO + World Bank WDI Transformation slice
- Plan AI provider/model: DeepSeek / configured `deepseek-flash`
- Review AI provider/model: not exercised

## Research question and intent

The existing China session promised a two-year joint outlook for growth, public debt and household
consumption. The regression checked that VAR now exposes an explicit forecast-period control while
automated contract tests exercised Plan compilation, multi-series execution and Output delivery
gating.

## Journey

| Stage | User/AI interaction and decisions | Result/evidence |
|---|---|---|
| Plan | Existing approved two-provider Plan. | The saved historical session was not mutated. |
| Data | Existing IMF WEO + World Bank WDI snapshot. | Outside this regression slice. |
| Transformation | Opened the completed Transformation page through its normal route. | The VAR specification visibly exposes `Forecast periods`; legacy nonforecast VAR correctly shows 0. |
| Output | Not regenerated from the legacy session. | Automated tests verify missing target/period output produces `FORECAST-DELIVERABLE-001`. |
| Resume/final state | No workflow mutation was made. | Existing session remained at Output review. |

## Output review loop

Not exercised. This is not an end-to-end run.

## Findings

| Severity | Summary | Issue/commit | Status |
|---|---|---|---|
| Fixed | Approved two-year horizons previously became four periods. | GitHub #15 / same commit | Fixed by frequency-aware horizon compilation. |
| Fixed | Joint forecasting previously used a one-target SARIMAX or a nonforecast VAR. | GitHub #15 / same commit | Joint intent now compiles to forecast-enabled VAR; plural ARIMA expands per target. |
| Fixed | Output did not verify promised forecast targets and steps. | GitHub #15 / same commit | Finish is blocked by `FORECAST-DELIVERABLE-001` when incomplete. |

## Conclusion

The browser-visible VAR control and automated executable contract passed. The run remains `PARTIAL`
because it intentionally reused a legacy completed session and did not proceed through Review AI
and final freeze.
