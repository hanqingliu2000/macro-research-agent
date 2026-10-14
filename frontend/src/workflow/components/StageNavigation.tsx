import { NavLink } from "react-router-dom";

import { STAGE_LABELS, type WorkflowSession, type WorkflowStage } from "../domain/types";
import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";

const stages: WorkflowStage[] = ["plan", "data", "transformation", "output"];

export function StageNavigation({ session }: { session: WorkflowSession }) {
  return (
    <nav className="stage-navigation" aria-label="Workflow stages">
      {stages.map((stage) => {
        const reached = session.reachedStages.includes(stage);
        const health = session.stageHealth[stage];
        if (!reached) {
          return (
            <span aria-disabled="true" aria-label={`${STAGE_LABELS[stage]}, locked`} className="stage-link stage-locked" key={stage}>
              <WorkbenchIcon name="lock" />
              <span>{STAGE_LABELS[stage]}</span>
            </span>
          );
        }
        return (
          <NavLink
            aria-label={`${STAGE_LABELS[stage]}, ${health}`}
            className={({ isActive }) =>
              `stage-link stage-${health}${isActive ? " active" : ""}`
            }
            key={stage}
            to={`/sessions/${session.id}/${stage}`}
          >
            <WorkbenchIcon name={health === "stale" ? "alert" : health === "completed" ? "check" : "file"} />
            <span>{STAGE_LABELS[stage]}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
