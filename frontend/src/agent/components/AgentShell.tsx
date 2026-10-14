import type { ReactNode } from "react";

import { WorkbenchShell } from "../../ui/components/WorkbenchShell";
import { AGENT_STATUS_LABELS } from "../domain/types";
import { useAgent } from "../state/AgentContextCore";

export function AgentShell({ children }: { children: ReactNode }) {
  const { sessions } = useAgent();

  return (
    <WorkbenchShell
      brandMark="AM"
      explorerLabel="Agent Explorer"
      homePath="/agent"
      mode="agent"
      newLabel="New agent run"
      recent={sessions.slice(0, 4).map((session) => ({
        id: session.id,
        status: AGENT_STATUS_LABELS[session.status],
        title: session.title,
        to: `/agent/${session.id}`,
      }))}
      recentLabel="Agent runs"
      showExplorerHeader={false}
      showRailFooter={false}
      showStatusBar={false}
    >
      {children}
    </WorkbenchShell>
  );
}
