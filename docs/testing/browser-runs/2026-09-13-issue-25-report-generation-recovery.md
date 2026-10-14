# Browser run: Issue #25 Report Author recovery and governed finish

- Date/time (UTC): 2026-09-13 17:45–19:11 UTC
- Application base commit: `855349f` plus the Issue #25 working tree
- Result: `PASS`
- Browser/runtime: local Chromium automation against running FastAPI and Vite services
- Session ID: `workflow-session-a713cd0ffacc40a88a64750796ef0e40`
- Coverage: single provider, World Bank WDI
- Plan/Data/Analysis/Report Author: DeepSeek / configured `deepseek-flash`
- Report/Visual Reviewer: `codex-local` / local Codex authentication

## Scenario and method

The simulated user investigated whether China had become less investment-driven and more
household-consumption-led since COVID-19, using annual WDI investment and consumption shares from
2015 through the latest observation and a two-step VAR forecast. The run resumed the failed journey
recorded in `2026-09-13-china-wdi-report-author-rerun.md`. All recovery, review, revision, selection,
Finish and reload actions used normal browser controls; no database or artifact was changed to force
progress.

## Recovery and review journey

| Check | Browser-observed result |
|---|---|
| Report Author failure | DeepSeek returned truncated/invalid `ReportDraftV1` JSON. The UI moved to Output recovery, stated that analysis was safe, exposed only bounded `$`/EOF diagnostics and offered `Retry report generation`. |
| Output-only retry | Retry regenerated Output from the preserved analytical bundle without rerunning the model. No partial ArtifactSet appeared. The base output budget was raised to 12,000 tokens and length termination used the bounded expanded repair attempt. |
| Revision authority | Codex-local identified numerical, model-specification, uncertainty and provenance errors. User-approved directives triggered DeepSeek section rewrites; attempted changes to evidence/citation/section bindings were projected back to their immutable values before validation. |
| Hash semantics | A reviewer initially conflated the hash of a complete typed result record with its nested numerical-result hash. The request now labels both scopes explicitly and states that they are expected to differ; the false upstream blocker disappeared on re-review. |
| Selective package | The wide analytical CSV and workbook were deselected; forecast CSV, two charts and the Research Report remained selected. Artifact-bound preflight findings for deselected files did not block review or Finish. |
| Bounded review | Iteration 2 produced three report directives. After one approved revision, iteration 3 returned Research Report semantic `pass`; no fourth revision was possible. |
| Final warning | The only remaining finding was `VISUAL-RUBRIC-MISSING`, the known project-level visual-rule advisory. The user acknowledgment gate remained explicit. |

## Final evidence

- Final selected ArtifactSet: `artifact-set-125ec8c145ce4c11b55c099f7b6c6847`
- ArtifactSet hash: `sha256:6ed0a878fd1edfdde4f4f3c005c773c4ab2d8612b14f6666f44568de61eb1ada`
- Frozen manifest artifact: `artifact-4e5291a0b8ab49baa27626b7678617b5`
- Frozen selected outputs: forecast CSV, two SVG charts and Research Report.
- Final Review AI status: `warning`; Research Report semantic status: `pass`; iteration `3/3`.
- Post-reload: session displayed `COMPLETED`, all four selected outputs and the manifest remained
  frozen, and the reviewed warning/history remained visible.

## Conclusion

Issue #25's failure mode is recoverable without losing completed analysis or silently substituting a
provider. Output-only retry, safe diagnostics, bounded contract repair, section-only report revision,
selective preflight, Codex-local semantic approval, human Finish, manifest creation and reload all
completed through the product UI. Project-specific chart authoring/acceptance rules remain separately
tracked as missing and were not invented for this run.
