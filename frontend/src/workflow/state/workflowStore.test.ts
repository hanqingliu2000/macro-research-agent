import { describe, expect, it } from "vitest";

import { createWorkflowSession } from "../domain/workflowEngine";
import {
  createWorkflowStore,
  selectWorkflowSessions,
  workflowStoreReducer,
} from "./workflowStore";

describe("Workflow feature stores", () => {
  it("round-trips a session through five isolated feature projections", () => {
    const session = createWorkflowSession("Compare inflation outcomes.");
    const store = createWorkflowStore([session]);

    expect(Object.keys(store)).toEqual([
      "sessionProjection",
      "plan",
      "data",
      "pipeline",
      "output",
    ]);
    expect(selectWorkflowSessions(store)).toEqual([session]);
  });

  it("upserts every feature with one typed store action", () => {
    const session = createWorkflowSession("Compare inflation outcomes.");
    const store = createWorkflowStore([session]);
    const updated = {
      ...session,
      title: "Updated projection",
      output: { ...session.output, guidelineVersion: "excel-publication-v2" },
    };
    const next = workflowStoreReducer(store, { type: "upsert", session: updated });

    expect(next.sessionProjection.byId[session.id].title).toBe("Updated projection");
    expect(next.output[session.id].output.guidelineVersion).toBe("excel-publication-v2");
  });
});
