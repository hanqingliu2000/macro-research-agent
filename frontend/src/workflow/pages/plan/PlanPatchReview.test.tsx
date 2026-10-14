import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultPlan } from "../../domain/workflowEngine";
import { PlanPatchReview } from "./PlanPatchReview";

describe("PlanPatchReview", () => {
  it("formats nested Plan fields as readable sections instead of raw JSON", () => {
    const plan = defaultPlan("Research China's government debt.");
    const onApply = vi.fn();
    render(
      <PlanPatchReview
        disabled={false}
        onApply={onApply}
        onReject={vi.fn()}
        proposal={{
          id: "patch-1",
          summary: "Use the executable IMF WEO debt series",
          request: "Re-plan using the current source index.",
          affectedStages: [],
          targetSnapshotHash: "sha256:current-plan-version",
          changes: {
            period: { start: "2015", end: "2024", frequency: "annual" },
            dataSources: [
              {
                ...plan.dataSources[0],
                connectorId: "imf_data",
                provider: "IMF Data",
                dataset: "WEO",
                indicators: ["GGXWDG", "GGXWDG_NGDP"],
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Use the executable IMF WEO debt series" })).toBeInTheDocument();
    expect(screen.getByText("Research period")).toBeInTheDocument();
    expect(screen.getByText("Data sources")).toBeInTheDocument();
    expect(screen.getByText("GGXWDG_NGDP")).toBeInTheDocument();
    expect(screen.queryByText(/\{"start"/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply selected changes" }));
    expect(onApply).toHaveBeenCalledWith(["period", "dataSources"]);
  });
});
