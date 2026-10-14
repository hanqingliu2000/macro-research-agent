# Chart delivery and Review AI acceptance — 2026-09-28

Scope: targeted Output integration, not a fresh public-source browser E2E. Base `4998093`
plus ADR 0032 working tree. Tests use isolated temporary sessions with explicitly synthetic
observations. Existing India/Brazil session data, artifacts and three-round counters are untouched.

## Acceptance cases

1. Generate a chart through real DeepSeek wording plus controlled SVG/PNG rendering.
2. Run two separate real author self-checks before Codex-local review.
3. Approve a unit-label-only revision through typed Output commands. Numeric marks and immutable
   unit selection must survive; run both author checks again before the next formal review.
4. Accept only the documented placeholder scope advisory, Finish the selected package, download
   the manifest, verify it includes both self-check receipts, and reload completed state.
5. Exercise normalized `unit=null` with an explicit indicator-name definition, not just populated
   source units. No observation may disappear during a display-unit revision.
6. Offline failure injection: 429/5xx, timeout, missing credential, malformed/contradictory JSON,
   failed self-check, explicit retry, idempotent replay, legacy spec migration and forbidden
   source-selection patches. No failed handoff may spend a formal round or permit Finish.

Reproduction: opt-in `MRA_LIVE_CHART_DELIVERY=1` with existing local credentials, then run
`backend/tests/test_chart_delivery.py -k live_chart`. Ordinary CI skips the two live cases.
Fixtures prepare approved data/analysis offline; the **chart author, two self-check calls and
Codex reviewer are real**. No report is selected or claimed reviewed in this Output-only test.

## Development attempts (preserved, not reclassified as passes)

- First explicit-unit attempt stopped before Codex: author check 2 misread inverted SVG y
  coordinates. Both checks ran, no reviewer round was spent. Added coordinate-system metadata
  and explicit baseline/rounding semantics, without changing the rubric.
- A subsequent initial-delivery slice passed real self-checks and Codex review, then froze.
  This was an initial-delivery test, not yet a revision-cycle test.
- An expanded attempt was blocked by speculative self-check claims about footer proximity,
  country-code keys and ticks not matching every observation. Clarified the existing rubric's
  applicability: demand actual evidence, not invented restrictions.
- Explicit-unit revision cycle then passed at `2026-09-28T17:09:03.865005Z`: formal review 2,
  `review-4f044ad569368ede`, ArtifactSet
  `sha256:60ccfe6518548b3fac9e6125242333ffd87a1f8b5a552442a6c47c9ede42b89d`;
  manifest `artifact-20a2b90cda80419582957f2bb93df775`, reload `completed`.
- First missing-unit attempt was correctly blocked by its own failed check, but the findings
  were model errors: it imagined curved segments in a polyline and ignored explicit unit
  metadata. Separated semantic-round input from rendered SVG and enabled the official thinking
  mode for both checks. This change does not suppress a failed result or reset an existing run.

## Final-version verification

After input separation and the thinking-mode change, the explicit-unit case passed both author
rounds before each of two formal Codex reviews. The only finding was the known placeholder scope
advisory, explicitly acknowledged at Finish.

- Initial formal review: `review-11a3aef1ec7c6225`, completed `2026-09-28T17:13:32.912022Z`.
- Revised formal review: `review-3ecfb9f38bf15216`, completed `2026-09-28T17:15:03.004785Z`.
- Final ArtifactSet: `sha256:1bad06fe48e805112e44624a62335be056c6603fe6e4e402ed0cf1aad5c9b5c4`.
- Manifest: `artifact-91af355e70914947a6d7ed5a2939f11a`; download includes both author receipts;
  reload confirms `completed`; formal review count **2/3**, not 6/3.

The missing-unit case also passed both checks before each of two formal Codex reviews. The
author used explicit indicator metadata for display wording; the normalized source units remained
null. A subsequent approved unit-label patch retained the curve and produced a newly reviewed
artifact. Only the placeholder scope advisory remained.

- Initial formal review: `review-8226b7ff55c1912b`, completed `2026-09-28T17:16:29.258362Z`.
- Revised formal review: `review-f6c37abce374a08a`, completed `2026-09-28T17:17:14.229886Z`.
- Final ArtifactSet: `sha256:2db3eb85ccd0c7b6cadd1f7fa5496e25b5413217072b161cb8ec3e3a8e2d1860`.
- Manifest: `artifact-78c86661266d4ab7820d0f80c0ca6d09`; both receipts verified in download;
  reload confirms `completed`; formal review count **2/3**.

Final live run: **2 passed**, 5 unrelated tests deselected, 324.24 seconds including generation,
four author checks and two Codex reviews per case. Both scoped delivery cycles pass. This small
sample does not establish an aggregate model reliability rate; the preserved development
false-positives are part of the evidence. Thinking-mode self-checks add material latency.

Automated suite: **330 backend passed, 4 opt-in live tests skipped; 111 frontend passed**.
Backend lint/types and frontend lint/build passed. Browser DOM smoke checks on the running app
verify the new self-check description; capabilities expose DeepSeek and two rounds. The historic
India test still has 3/3 formal rounds and disabled Finish after service restart.

The chart-only result cannot close the earlier full Workflow acceptance: phase-analysis coverage,
Stata delivery, upstream Plan revision and report accuracy remain separate open findings.
