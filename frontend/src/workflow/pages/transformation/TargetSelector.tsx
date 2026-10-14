import { useEffect, useState } from "react";

import type { PipelineOperation, WorkflowSession } from "../../domain/types";

export function TargetSelector({
  operation,
  onChange,
  session,
  disabled,
}: {
  operation?: PipelineOperation;
  disabled: boolean;
  onChange(target: Partial<PipelineOperation["target"]>): void;
  session: WorkflowSession;
}) {
  const [draft, setDraft] = useState<PipelineOperation["target"] | undefined>(
    operation?.target,
  );
  useEffect(() => setDraft(operation?.target), [operation]);
  if (!operation) return <section className="pipeline-card"><p>Select an operation to edit its target.</p></section>;
  if (!draft) return null;
  const changed = JSON.stringify(draft) !== JSON.stringify(operation.target);
  const operationIndex = session.pipeline.operations.findIndex((item) => item.id === operation.id);
  const upstreamOperations = session.pipeline.operations.slice(0, operationIndex);
  return (
    <section className="pipeline-card target-selector">
      <p className="panel-kicker">TARGET SELECTOR</p>
      <h2>{operation.label}</h2>
      <label>Input dataset<select disabled={disabled} value={draft.inputRef} onChange={(event) => setDraft({ ...draft, inputRef: event.target.value })}><option value="active_dataset">Active dataset</option>{upstreamOperations.map((item) => <option key={item.outputRef} value={item.outputRef}>{item.label} output</option>)}</select></label>
      <div className="target-grid"><label>Indicators<input disabled={disabled} placeholder="Empty selects all" value={draft.indicators.join(", ")} onChange={(event) => setDraft({ ...draft, indicators: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></label><label>Entities / group members<input disabled={disabled} placeholder="Empty selects all" value={draft.entities.join(", ")} onChange={(event) => setDraft({ ...draft, entities: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></label><label>Start<input disabled={disabled} value={draft.periodStart ?? ""} onChange={(event) => setDraft({ ...draft, periodStart: event.target.value })} /></label><label>End<input disabled={disabled} value={draft.periodEnd ?? ""} onChange={(event) => setDraft({ ...draft, periodEnd: event.target.value })} /></label><label>Frequency<select disabled={disabled} value={draft.frequency ?? ""} onChange={(event) => setDraft({ ...draft, frequency: event.target.value || undefined })}><option value="">Any</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="annual">Annual</option></select></label></div>
      <dl className="target-parameters">{Object.entries(operation.parameters).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
      <button className="secondary-button" disabled={disabled || !changed} onClick={() => onChange(draft)} type="button">Save target</button>
    </section>
  );
}
