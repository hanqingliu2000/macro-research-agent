import { useEffect, useMemo, useState } from "react";

import { CheckpointBar } from "../../components/CheckpointBar";
import { ImpactDialog } from "../../components/ImpactDialog";
import { impactForPlanChanges, isPlanReady } from "../../domain/workflowEngine";
import { type PlanDraft, type WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { CapabilityLists } from "./CapabilityLists";
import { GeographyResolutionEditor } from "./GeographyResolutionEditor";
import { PlanReadinessNotice } from "./PlanReadinessNotice";

const calendarYearConnectors = new Set(["world_bank", "adb", "un_sdg"]);

function fiscalYearEnd(value: string): string | undefined {
  const match = value.trim().match(/^(?:fy\s*)?([12]\d{3})\s*[-/]\s*(\d{2}|[12]\d{3})$/i);
  if (!match) return undefined;
  const start = Number(match[1]);
  let end = Number(match[2]);
  if (match[2].length === 2) {
    end = Math.floor(start / 100) * 100 + end;
    if (end < start) end += 100;
  }
  return end === start + 1 ? String(end) : undefined;
}

export function PlanEditor({
  session,
  onNext,
  onDirtyChange,
}: {
  session: WorkflowSession;
  onNext(): void;
  onDirtyChange(dirty: boolean): void;
}) {
  const { execute, pending } = useWorkflow();
  const [form, setForm] = useState<PlanDraft | undefined>(session.currentPlan);
  const [pendingChanges, setPendingChanges] = useState<Partial<PlanDraft>>();

  useEffect(() => setForm(session.currentPlan), [session.currentPlanSnapshotId, session.currentPlan]);

  const changes = useMemo<Partial<PlanDraft>>(() => {
    if (!form || !session.currentPlan) return {};
    const result: Partial<PlanDraft> = {};
    for (const key of Object.keys(form) as Array<keyof PlanDraft>) {
      if (JSON.stringify(form[key]) !== JSON.stringify(session.currentPlan[key])) {
        Object.assign(result, { [key]: form[key] });
      }
    }
    return result;
  }, [form, session.currentPlan]);
  const changed = Object.keys(changes).length > 0;
  const queryPeriodPreview = useMemo(() => {
    if (!form || form.period.frequency !== "annual") return undefined;
    const source = form.dataSources.find(
      (item) => item.enabled !== false && calendarYearConnectors.has(item.connectorId),
    );
    if (!source) return undefined;
    const start = fiscalYearEnd(form.period.start) ?? form.period.start;
    const end = fiscalYearEnd(form.period.end) ?? form.period.end;
    if (start === form.period.start && end === form.period.end) return undefined;
    return `${source.dataset} query period: ${start}–${end}. Fiscal years use their ending calendar year.`;
  }, [form]);
  useEffect(() => onDirtyChange(changed), [changed, onDirtyChange]);

  if (!form || !session.currentPlan) {
    return (
      <section aria-label="Current Plan" className="plan-editor plan-empty-state">
        <span>PLAN</span><h2>The current Plan will appear here.</h2><p>Answer the clarification questions in chat first.</p>
      </section>
    );
  }

  const save = () => {
    const impact = impactForPlanChanges(session, changes);
    if (impact.length) setPendingChanges(changes);
    else execute(session.id, { type: "save_plan", changes });
  };

  return (
    <section className="plan-editor" aria-label="Current Plan">
      <fieldset className="plan-edit-fields" disabled={pending}>
      <section className="plan-editor-section plan-fields">
        <label>Research objective<textarea rows={4} value={form.objective} onChange={(event) => setForm({ ...form, objective: event.target.value })} /></label>
        <label>Geography intent<input value={form.geographyIntent} onChange={(event) => setForm({ ...form, geographyIntent: event.target.value })} /></label>
        <div className="period-fields">
          <label>Start<input value={form.period.start} onChange={(event) => setForm({ ...form, period: { ...form.period, start: event.target.value } })} /></label>
          <label>End<input value={form.period.end} onChange={(event) => setForm({ ...form, period: { ...form.period, end: event.target.value } })} /></label>
          <label>Frequency<select value={form.period.frequency} onChange={(event) => setForm({ ...form, period: { ...form.period, frequency: event.target.value as PlanDraft["period"]["frequency"] } })}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="annual">Annual</option></select></label>
        </div>
        {queryPeriodPreview && <p className="plan-period-resolution" role="status">{queryPeriodPreview}</p>}
      </section>

      <GeographyResolutionEditor disabled={changed} session={session} />

      <CapabilityLists onChange={setForm} plan={form} />

      {form.assumptions.length > 0 && <section className="plan-editor-section"><h3>Plan assumptions</h3><ul>{form.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}

      <PlanReadinessNotice unresolvedItems={form.unresolvedItems} warnings={form.warnings} />
      </fieldset>

      <CheckpointBar actionLabel="Next: acquire data" disabled={pending || changed || !isPlanReady(session)} leading={<><button className="secondary-button" disabled={pending || !changed} onClick={save} type="button">Save manual changes</button>{changed && <span>Unsaved Plan edits</span>}</>} onAction={onNext} />

      {pendingChanges && (
        <ImpactDialog
          onCancel={() => setPendingChanges(undefined)}
          onConfirm={() => { execute(session.id, { type: "save_plan", changes: pendingChanges }); setPendingChanges(undefined); }}
          stages={impactForPlanChanges(session, pendingChanges)}
          title="Save these Plan changes?"
        />
      )}
    </section>
  );
}
