import type { ReactNode } from "react";

import { WorkbenchShell } from "../../ui/components/WorkbenchShell";
import { SESSION_STATUS_LABELS } from "../domain/types";
import { useWorkflow } from "../state/WorkflowContextCore";

export function WorkflowShell({ children }: { children: ReactNode }) {
  const { sessions } = useWorkflow();
  const recent = sessions.filter((session) => !session.archived).slice(0, 4);

  return (
    <WorkbenchShell
      brandMark="MR"
      explorerLabel="Research Explorer"
      homePath="/"
      mode="workflow"
      newLabel="New research"
      recent={recent.map((session) => ({
        id: session.id,
        status: SESSION_STATUS_LABELS[session.status],
        title: session.title,
        to: `/sessions/${session.id}/${session.activeStage}`,
      }))}
      recentLabel="Open sessions"
      settingsPath="/settings"
      showExplorerHeader={false}
      showRailFooter={false}
      showStatusBar={false}
    >
      {children}
    </WorkbenchShell>
  );
}
