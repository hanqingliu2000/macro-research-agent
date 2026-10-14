import { describe, expect, it } from "vitest";

import { completeAgentRun, createAgentSession } from "./agentWorkflow";

describe("Agent Mode workflow", () => {
  it("creates an independent clarification session", () => {
    const session = createAgentSession("Study inflation persistence.", []);

    expect(session.status).toBe("clarifying");
    expect(session.clarification.questions).toHaveLength(3);
    expect(session.steps.map((step) => step.nodeKind)).toEqual([
      "clarification_batch",
      "data_acquisition",
      "transformation",
      "model_execution",
      "final_response",
    ]);
  });

  it("produces a deterministic research package after clarification", () => {
    const session = createAgentSession("Study inflation persistence.", []);
    const completed = completeAgentRun(session, {
      geography: "Advanced economies",
      period: "2019–latest, quarterly",
      deliverable: "Research note with charts",
    });

    expect(completed.status).toBe("completed");
    expect(completed.steps.every((step) => step.status === "completed")).toBe(true);
    expect(completed.result?.artifacts.map((artifact) => artifact.format)).toContain("stata_do");
    expect(completed.result?.pythonCode).toContain("pandas");
  });
});
