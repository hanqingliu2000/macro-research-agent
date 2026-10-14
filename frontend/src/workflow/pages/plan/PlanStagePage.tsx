import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useWorkflowSession } from "../../components/useWorkflowSession";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { PlanChat } from "./PlanChat";
import { PlanEditor } from "./PlanEditor";

export function PlanStagePage() {
  const session = useWorkflowSession();
  const { execute } = useWorkflow();
  const navigate = useNavigate();
  const [manualEditPending, setManualEditPending] = useState(false);
  return (
    <div className="workflow-stage-layout plan-stage-layout">
      <PlanEditor
        onNext={async () => {
          const updated = await execute(session.id, { type: "plan_next" });
          if (updated?.activeStage === "data") navigate(`/sessions/${session.id}/data`);
        }}
        onDirtyChange={setManualEditPending}
        session={session}
      />
      <PlanChat manualEditPending={manualEditPending} session={session} />
    </div>
  );
}
