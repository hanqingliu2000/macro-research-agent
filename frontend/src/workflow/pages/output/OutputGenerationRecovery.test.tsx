import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../../domain/workflowEngine";
import { OutputGenerationRecovery } from "./OutputGenerationRecovery";

describe("OutputGenerationRecovery", () => {
  it("explains preserved analysis and exposes a bounded retry with field details", () => {
    const session = createWorkflowSession("Compare inflation outcomes.");
    session.pipeline.outputGeneration = {
      status: "failed",
      attempt: 1,
      bundleId: "bundle-1",
      retryable: true,
      error: {
        code: "invalid_report_contract",
        message: "DeepSeek returned an invalid report contract after repair.",
        issues: [
          {
            attempt: 2,
            path: "$.sections[].heading",
            code: "missing_required_sections",
            message: "Report draft is missing the Results section.",
          },
        ],
      },
    };
    const onRetry = vi.fn();

    render(
      <OutputGenerationRecovery onRetry={onRetry} pending={false} session={session} />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Analysis is safe");
    expect(screen.getByText(/does not rerun the analysis/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Contract details (1)"));
    expect(screen.getByText("$.sections[].heading")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Output generation" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("announces progress and disables duplicate retries", () => {
    const session = createWorkflowSession("Compare inflation outcomes.");
    session.pipeline.outputGeneration = {
      status: "failed",
      attempt: 2,
      bundleId: "bundle-1",
      retryable: true,
    };

    render(
      <OutputGenerationRecovery onRetry={vi.fn()} pending session={session} />,
    );

    expect(screen.getByRole("button", { name: "Retrying Output generation…" })).toBeDisabled();
  });
});
