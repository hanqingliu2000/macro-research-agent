import type { DataOperationKind, WorkflowSession } from "../../domain/types";
import { WorkbenchIcon } from "../../../ui/components/WorkbenchIcon";

const actions: Array<[DataOperationKind, string]> = [
  ["filter_missing", "Filter missing"],
  ["keep_columns", "Keep columns"],
  ["drop_columns", "Drop attributes"],
  ["rename_columns", "Rename mapped"],
  ["map_codes", "Map codes"],
  ["cast_types", "Cast types"],
  ["missing_value_rule", "Missing rule"],
  ["deduplicate", "Deduplicate"],
  ["sort", "Sort"],
];

export function QuickCleanToolbar({
  disabled,
  onApply,
  onUndo,
  session,
}: {
  disabled: boolean;
  onApply(operation: DataOperationKind): void;
  onUndo(): void;
  session: WorkflowSession;
}) {
  return (
    <section className="quick-clean-toolbar">
      <div><p className="panel-kicker">QUICK PREPARATION</p></div>
      <div className="quick-clean-actions">
        {actions.map(([operation, label]) => <button disabled={disabled} key={operation} onClick={() => onApply(operation)} type="button">{label}</button>)}
        <button aria-label="Undo last data operation" className="undo-button" disabled={disabled || session.data.operations.length === 0} onClick={onUndo} type="button"><WorkbenchIcon name="undo" />Undo</button>
      </div>
    </section>
  );
}
