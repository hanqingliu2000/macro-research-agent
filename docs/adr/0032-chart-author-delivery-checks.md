# ADR 0032 — Chart author and two pre-handoff self-checks

Date: 2026-09-28
Status: implemented

## Decision

Production chart wording is authored by DeepSeek using the existing endpoint/key and
`DEEPSEEK_MODEL`. Typed templates still generate SVG/PNG and tables; the model cannot draw or
edit data, execute SVG/code, add indicators, change the sample or cross approval gates. The model
may resolve absent display units only from explicit indicator metadata. Explicit source units
remain authoritative. Report Author and Codex-local review retain their separate roles.

Before **every** chart-bearing Output handoff (including user-approved revisions and retries),
the chart author makes two separate model calls against the exact selected SVGs, specifications,
fixed rubric and complete snapshot rows accessed through a disclosure-approved, paginated grant:

1. Check indicator/entity/period, values, units, missingness and provenance. This round receives
   semantic specifications and full rows, not SVG, to avoid inventing visual defects.
2. Independently check final SVG structure, text, coordinates and layout. SVG coordinate metadata
   disambiguates inverted y coordinates and tick-text baseline offsets; it does not waive defects.

Both calls must pass. A fail, malformed response, timeout, denied grant or over-budget complete
dataset stops handoff. No deterministic production fallback is available. Each logical call has
at most one schema repair; self-check rounds and schema repairs are distinct. A provider error
may prevent completion of both rounds and is recorded as incomplete/error, never as success.
Retries are explicit user actions, not an automatic unbounded loop. Suggested corrections are
diagnostic text; actual changes still require a separately approved typed presentation patch.

Self-check requests enable DeepSeek thinking mode with an 8,000-token completion ceiling;
wording generation remains bounded to 2,500 tokens without thinking. Only the final structured
result is read/persisted; provider reasoning content is never logged or exposed. This uses the
[official thinking-mode control](https://api-docs.deepseek.com/guides/thinking_mode/).

These are **structural author checks, not visual-model approval**. Codex-local still reviews the
direct checksum-bound PNGs. Author checks do not spend the existing maximum three formal review
rounds. A blocked check cannot produce a completed review graph node or permit Finish.

## Data/wording separation

`ChartSpec.source_unit` binds the original unit selection independently of editable `unit` text.
It is not patchable. Legacy specs infer it from the original pre-patch unit (`As reported` maps
to no unit filter). Regeneration preserves selected y fields and refuses an empty numeric result.
It never treats new unit text as a filter or performs a numerical unit conversion. Conversions
must go upstream. Empty-state titles use the same wrapping as populated charts.

## Persistence and scope

`output.chartSelfChecks` is append-only per Output generation and includes attempt identity,
provider/model, selected chart IDs, ArtifactSet/evidence hashes, each round's result and time.
Ordinary trace events contain hashes/status, not copied values. The final reproduction manifest
retains these receipts. Prior review records/counters remain unchanged, and old chart specs are
read-compatible. Each requested handoff rechecks the current selection; old receipts are not a
cache that can authorize a changed artifact set.

Offline tests explicitly inject fakes. Live delivery tests use isolated synthetic data and real
DeepSeek/Codex, and must be distinguished from a full public-source browser E2E. The earlier
India/Brazil failures remain historical and their counters must not be reset.
