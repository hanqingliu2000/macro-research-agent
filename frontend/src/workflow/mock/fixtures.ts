import {
  createWorkflowSession,
  executeWorkflowCommand,
  makeCommandEnvelope,
} from "../domain/workflowEngine";
import type { WorkflowCommand, WorkflowSession } from "../domain/types";

function apply(session: WorkflowSession, command: WorkflowCommand) {
  return executeWorkflowCommand(session, makeCommandEnvelope(session, command));
}

function answered(session: WorkflowSession) {
  let next = apply(session, {
    type: "submit_clarification",
    answers: {
      geography: "United States, euro area and Japan",
      period: "2015–2025, monthly",
      emphasis: "Comparative trends",
    },
  });
  next = apply(next, { type: "confirm_geography", resolutionId: "geo-euro-area" });
  return next;
}

export function seedWorkflowSessions(): WorkflowSession[] {
  let inflation = answered(
    createWorkflowSession(
      "Compare post-pandemic inflation persistence and monetary-policy responses.",
    ),
  );
  inflation = {
    ...inflation,
    id: "demo-inflation",
    title: "Post-pandemic inflation dynamics",
  };

  let fiscal = answered(
    createWorkflowSession(
      "Estimate the relationship between fiscal consolidation and real GDP growth.",
    ),
  );
  fiscal = apply(fiscal, { type: "plan_next" });
  fiscal = apply(fiscal, { type: "data_next" });
  fiscal = apply(fiscal, { type: "run_pipeline" });
  fiscal = apply(fiscal, { type: "request_output_review" });
  fiscal = apply(fiscal, { type: "finalize_output" });
  fiscal = {
    ...fiscal,
    id: "demo-fiscal",
    title: "Fiscal consolidation and growth",
  };

  return [inflation, fiscal];
}
