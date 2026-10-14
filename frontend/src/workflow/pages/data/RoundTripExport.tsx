import type { WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { WorkbenchIcon } from "../../../ui/components/WorkbenchIcon";

export function RoundTripExport({ session, disabled }: { session: WorkflowSession; disabled: boolean }) {
  const { execute } = useWorkflow();
  const exportWorkbook = async () => {
    const updated = await execute(session.id, { type: "prepare_round_trip_export" });
    const target = updated?.data.lastExportedPackage;
    if (target?.downloadUrl) {
      const link = document.createElement("a");
      link.href = target.downloadUrl;
      link.download = target.filename;
      link.click();
    }
  };
  return (
    <div className="data-inline-control">
      <button className="data-transfer-button data-transfer-export" disabled={disabled} onClick={exportWorkbook} type="button"><WorkbenchIcon name="export" />Export for external cleaning</button>
    </div>
  );
}
