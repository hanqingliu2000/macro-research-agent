# Plan AI live integration acceptance

Date: 2026-09-09 (America/Los_Angeles; trace timestamps use UTC 2026-09-10).

## Verdict and scope

**Review-gated functional integration: PASS after corrections.** Two isolated sessions using
DeepSeek `deepseek-v4-flash` completed from live clarification and planning through explicit Plan,
Run and Finish commands, real local statistical execution, output review and portable export.

**Unsupervised research quality: NOT accepted.** Live drafts still require economist review. This
run found both application defects and plausible but inappropriate model suggestions; successful
human correction is evidence for the review loop, not proof that future first drafts are correct.
This is a bounded `T3` Plan integration slice, not the complete longitudinal `T4` acceptance.

No real user project was changed. Credentials were loaded locally; only synthetic uploaded values
were disclosed to the configured Plan provider. Data/Analysis and Output assistants remained local
and deterministic. No external analytical source was fetched and no browser screenshots were used.

## Scenario and evidence

The scenario adapts the user's China-inflation request: review 36 historical monthly observations
and project the following six months. The generated CSV has `country,period,indicator,value,note`,
36 CHN/CPI_YOY observations from 2023-09 through 2026-08, with every row marked synthetic.
Values are `round(1.2 + 0.25*sin(0.7*i) + 0.01*i, 5)`, for `i=0..35`.
It is software test data and conveys no information about actual Chinese inflation.

Both sessions used the actual FastAPI handlers and persistent SQLite/file stores in isolated
runtimes, with live HTTP calls from the Plan adapter. Each harness invocation reconstructed the
application from persistent state. Ordinary deterministic CI remained offline.

| Journey | Evidence |
|---|---|
| Request and selectable clarification | Live provider generated bounded questions; the test actor selected answers. |
| Data-aware draft | Receipts show 36 uploaded rows read per Plan grant, with matching checksum; final historical dates are 2023-09 / 2026-08. |
| Chinese correction and partial Apply | Only selected objective, assumptions, model and unresolved-item fields were applied; proposal creation did not move the Plan into Data. |
| Second clarification round | Accepted six-month horizon, Python-only output and synthetic scope survived application recreation and re-drafting. |
| Stale/rejected patch | A real objective-only proposal was superseded by a manual save; Apply returned 422, objective stayed unchanged, and Reject succeeded. |
| Human gates | Test actor explicitly confirmed geography and invoked Plan Next, Data Next, Run, Review and Finish. Graph contains all three checkpoint types. |
| Statistical execution | Descriptive, ADF and ARIMA completed with 36 observations each. Reviewed ARIMA(1,0,0), constant, six steps and 95% intervals produced six monthly rows from 2026-09 through 2027-02. |
| Output | Analytical CSV, forecast CSV, historical SVG chart, XLSX workbook, Python reproduction code, report and final manifest were generated. Stata was off. |
| Review and duplicate requests | Finish before Review returned 422. Local Review passed; Finish succeeded. Repeating each successful downstream command returned an idempotent replay. |
| Recovery and continuation | After recreation, the completed session document was identical; portable export succeeded and a fork preserved the frozen source. Trace sequences were contiguous. |
| Fresh-session retest | A second independently created session accepted a Chinese correction and also completed the local forecast/output journey. |

Primary session: `workflow-session-7d1fe72c50074db2945b72b4c2f61b2b`.
Fresh session: `workflow-session-c5c87edd8abc494c9b10563c284dafab`.
The two archives and local detailed evidence are retained under
`runtime/acceptance/plan-ai-2026-09-09/` (ignored by Git). Archives can be imported using the existing
portable-session importer. They include data, snapshots, generated files, graph and trace evidence.

There were 11 logical live planning calls and 15 total provider attempts, including diagnosis and
retests; the configured bound was two attempts per call. Ten calls completed; one intermediate
contract-checking implementation failed closed and was then corrected. Successful provider
latencies ranged from 2.32 to 22.56 seconds. These are observations, not an SLA. Dollar cost and
token usage were not measured and are not inferred from elapsed time.

## Defects corrected

1. **Valid JSON with invalid capability identifiers.** A draft used `connector.local_file` as the
   data-source ID and `data.prepare` as a transformation. Live outputs now validate against the
   distinct connector/transformation/model namespaces and catalog stages, with bounded corrective
   retries. Unknown models are rejected before a Plan is persisted.
2. **Model-authored registry metadata.** The model invented versions and approval policies. The
   server registry now owns version, availability and gate fields in typed proposals.
3. **Missing conversational context and incomplete capability lists.** Revision/follow-up context
   omitted previous answers and only exposed three transformations. It now includes current
   questions/answers, reference date, current Plan, the last 40 persisted messages and the actual
   supported model/transformation inventories. New answer messages retain question-to-answer
   correspondence for subsequent rounds.
4. **Inappropriate planning suggestions.** Drafts mixed forecast dates into historical bounds,
   proposed enabled conditional transformations on an already-YoY series, and repeated answered
   questions as blockers. `planning-v2` explicitly separates these concepts and constrains later
   stage promises. Live Chinese corrections successfully removed the inappropriate steps/blockers.
   These prompt improvements are not a deterministic guarantee of statistical judgment.
5. **Human geography confirmation.** Model-provided `confirmed=true` cannot confirm a new or changed
   geography. Unknown confirmation IDs fail. China/CHN is now present in the controlled resolver
   and recognized by the offline planner.
6. **Invisible blockers and fragile revision UX.** Plan assumptions and unresolved items are now
   visible. Revision/follow-up operations show waiting feedback and prevent duplicate actions;
   failed revisions retain their text. A replacement patch resets field selections by proposal ID.
7. **Free-text clarification and advisory classification.** Every clarification question now has a
   separate labeled custom-answer field. Plan Patch cards render nested values by field instead of
   exposing JSON. Explicitly non-blocking discovery-only alternatives, generic index limitations
   and patch changelog prose are deterministically removed from blockers/cautions; material risks
   such as WEO vintage revisions remain visible.

## Regression evidence

- Backend: **119 passed**, including new namespace/retry/registry-policy, context and geography
  authority tests. The existing longitudinal suite also covers Data cleaning, XLSX round trips,
  selective Output revision, numeric/model checks and archive import.
- Frontend: **69 passed**, including failed-revision input preservation and disabled pending state.
- Ruff, mypy (71 source files), frontend lint and production build passed.
- The development frontend/backend were restarted with the corrected code; health through the
  frontend HTTP proxy returned `ok`.

Re-run deterministic checks from the repository root with `.venv/bin/pytest -q`,
`.venv/bin/ruff check backend` and `.venv/bin/mypy`; run `npm test`, `npm run lint` and
`npm run build` from `frontend`. Live calls remain opt-in and are not added to ordinary CI.

## Remaining acceptance work

- Broader reviewed corpus, independent research-quality scoring, repeated-run variability,
  large-data behavior, latency distribution and provider token/cost accounting.
- This DeepSeek development run is not acceptance of the deferred additional remote provider profile. Its
  governance, distribution, recorded-contract, live-Plan and longitudinal gates `W0`–`W4` and `W6`
  remain open; a generic OpenAI key or adapter selection cannot satisfy them.
- Plan transformation/model intent IDs now become a reviewable Transformation draft at Data Next;
  selectors and variable roles are limited to indicators observed in the approved snapshot. Plan
  intents now use structured ModelIntentV2 variable roles and forecast horizons; narrative text is
  not an executable parameter source. Bounded registered defaults remain editable and require
  the explicit Transformation Run gate. This later contract does not change the historical run.
- Forecast values and intervals are exported in CSV and the workbook Forecasts sheet. Historical
  charts work; forecast overlays/fan charts are not yet governed renderer features.
- Data/Analysis assistants and admitted Phase 3 connectors are now implemented under their local
  and provider-specific contracts. Enabling any of them through `approved_remote` still requires a
  separate task gate `W5`; remote multimodal review, human Excel/visual UAT and full cross-day `T4`
  retain their documented acceptance boundaries.
