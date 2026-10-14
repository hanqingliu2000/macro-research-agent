# Issue #17 analysis-revision regression

- Date: 2026-09-12
- Application commit: issue-fix commit containing this log
- Status: `PARTIAL`
- Scope: Output → Transformation revision boundary, not a complete Review-AI-approved journey
- Session: `workflow-session-00b5c2cb3ed542d2ba5b302611ddaf8e`
- Research: India post-pandemic investment-led growth and consumption dependence
- Providers: existing World Bank dataset; no new acquisition or model call

## Browser path and evidence

1. Opened the existing current Output and navigated back to completed Transformation.
2. Before the fix, changing an operation target displayed the generic downstream-impact dialog;
   a separate completed China session confirmed that a model edit could persist and reopen the
   pipeline, so the original silent failure was not reproducible on the latest baseline.
3. After the UI change, reloaded the India Transformation route. All operation, target, parameter,
   model and Analysis-AI mutation controls were disabled while inspection remained available.
4. Selected `Revise analysis` and verified the focused confirmation dialog names the stale Output
   impact and states that nothing reruns automatically.
5. Confirmed the revision, changed the first operation target from four indicators to
   `NE.CON.PRVT.ZS` and `NE.GDI.FPRV.ZS`, saved it, then reloaded the route. The two-indicator target
   remained saved, the session remained at current Transformation, and the checkpoint read
   `Run updated analysis`.

## Acceptance disposition

Browser evidence confirms the explicit read-only/revision affordance and reload persistence.
Automated HTTP tests verify
that a direct mutation fails closed, accepting the revision moves the active stage to
Transformation and stales Output, a subsequent edit persists after reload, and prior artifacts,
model results and generated code remain in history. Frontend tests verify the confirmed transition
enables editing and exposes `Run updated analysis`. This bounded slice does not run Output Review AI
and is therefore not an end-to-end pass.
