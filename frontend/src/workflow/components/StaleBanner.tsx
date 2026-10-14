import { Link } from "react-router-dom";

import type { WorkflowSession, WorkflowStage } from "../domain/types";

export function StaleBanner({ session, stage }: { session: WorkflowSession; stage: WorkflowStage }) {
  if (session.stageHealth[stage] !== "stale") return null;
  return (
    <div className="stale-banner" role="status">
      <div>
        <strong>This stage is stale.</strong>
        <span>An upstream snapshot changed. Existing results are read-only until rebuilt.</span>
      </div>
      <Link to={`/sessions/${session.id}/${session.activeStage}`}>Return to current work</Link>
    </div>
  );
}
