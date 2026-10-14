import type { AgentSession } from "../domain/types";
import { completeAgentRun, createAgentSession } from "../domain/agentWorkflow";

export function seedAgentSessions(): AgentSession[] {
  const session = createAgentSession(
    "Compare inflation normalization across major advanced economies.",
    [],
  );
  return [
    {
      ...completeAgentRun(session, {
        geography: "United States, euro area and Japan",
        period: "2019–latest, quarterly",
        deliverable: "Research note with charts",
      }),
      id: "agent-demo-inflation",
      title: "Inflation normalization — agent run",
    },
  ];
}
