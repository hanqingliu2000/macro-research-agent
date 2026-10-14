import { Link, useLocation } from "react-router-dom";

import { WorkbenchIcon } from "./WorkbenchIcon";
import type { WorkbenchMode } from "./workbenchTypes";

export function WorkbenchActivityBar({
  brandMark,
  homePath,
  mode,
  settingsPath,
}: {
  brandMark: string;
  homePath: string;
  mode: WorkbenchMode;
  settingsPath?: string;
}) {
  const settingsActive = useLocation().pathname === "/settings";
  return (
    <aside aria-label="Research activity bar" className="workbench-activity-bar">
      <Link aria-label={`${mode === "agent" ? "Agent" : "Workflow"} Mode home`} className="workbench-logo" to={homePath}>
        {brandMark}
      </Link>
      <nav aria-label="Primary research tools">
        <Link aria-current={mode === "workflow" && !settingsActive ? "page" : undefined} aria-label="Workflow Mode" className={`activity-action${mode === "workflow" && !settingsActive ? " active" : ""}`} title="Workflow Mode" to="/">
          <WorkbenchIcon name="research" />
        </Link>
        <Link aria-current={mode === "agent" ? "page" : undefined} aria-label="Agent Mode" className={`activity-action${mode === "agent" ? " active" : ""}`} title="Agent Mode" to="/agent">
          <WorkbenchIcon name="agent" />
        </Link>
      </nav>
      {settingsPath && (
        <Link aria-current={settingsActive ? "page" : undefined} aria-label="Workflow settings" className={`activity-action activity-settings${settingsActive ? " active" : ""}`} title="Workflow settings" to={settingsPath}>
          <WorkbenchIcon name="settings" />
        </Link>
      )}
    </aside>
  );
}
