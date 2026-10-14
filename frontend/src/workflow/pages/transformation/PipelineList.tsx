import type { WorkflowSession } from "../../domain/types";
import { WorkbenchIcon } from "../../../ui/components/WorkbenchIcon";
import { SectionHeading } from "../../components/SectionHeading";

export function PipelineList({
  session,
  onMove,
  onSelect,
  onToggle,
  onDelete,
  onUndo,
  disabled,
}: {
  session: WorkflowSession;
  disabled: boolean;
  onMove(id: string, direction: "up" | "down"): void;
  onSelect(id: string): void;
  onToggle(id: string): void;
  onDelete(id: string): void;
  onUndo(): void;
}) {
  return (
    <section className="pipeline-card pipeline-list-card">
      <SectionHeading eyebrow="OPERATION CHAIN" meta={<button className="secondary-button" disabled={disabled || session.pipeline.editHistory.length === 0} onClick={onUndo} type="button"><WorkbenchIcon name="undo" />Undo pipeline edit</button>} title="Applied operations" />
      {session.pipeline.lastValidationError && <p className="pipeline-error" role="alert">{session.pipeline.lastValidationError}</p>}
      {session.pipeline.operations.length === 0 ? (
        <div className="pipeline-empty-state" role="status">
          <strong>No data transformation required</strong>
        </div>
      ) : <ol className="pipeline-list">
        {session.pipeline.operations.map((operation, index) => (
          <li className={session.pipeline.selectedOperationId === operation.id ? "selected" : ""} key={operation.id}>
            <button aria-label={`${operation.label}: ${operation.inputRef} to ${operation.outputRef}`} aria-pressed={session.pipeline.selectedOperationId === operation.id} className="pipeline-select" onClick={() => onSelect(operation.id)} type="button"><span>{index + 1}</span><div><strong>{operation.label}</strong></div></button>
            <div className="pipeline-item-actions">
              <button aria-label={`Move ${operation.label} up`} disabled={disabled || index === 0} onClick={() => onMove(operation.id, "up")} type="button"><WorkbenchIcon name="chevron-up" /></button>
              <button aria-label={`Move ${operation.label} down`} disabled={disabled || index === session.pipeline.operations.length - 1} onClick={() => onMove(operation.id, "down")} type="button"><WorkbenchIcon name="chevron-down" /></button>
              <label><input checked={operation.enabled} disabled={disabled} onChange={() => onToggle(operation.id)} type="checkbox" /><span>On</span></label>
              <button aria-label={`Delete ${operation.label}`} disabled={disabled} onClick={() => onDelete(operation.id)} type="button"><WorkbenchIcon name="trash" /></button>
            </div>
          </li>
        ))}
      </ol>}
    </section>
  );
}
