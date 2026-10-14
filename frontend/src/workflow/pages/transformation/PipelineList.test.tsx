import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../../domain/workflowEngine";
import { PipelineList } from "./PipelineList";

describe("PipelineList", () => {
  it("labels an intentionally empty Plan transformation chain", () => {
    const session = createWorkflowSession("Review reported macroeconomic levels.");
    session.pipeline.operations = [];

    render(
      <PipelineList
        disabled={false}
        onDelete={vi.fn()}
        onMove={vi.fn()}
        onSelect={vi.fn()}
        onToggle={vi.fn()}
        onUndo={vi.fn()}
        session={session}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("No data transformation required");
  });
});
