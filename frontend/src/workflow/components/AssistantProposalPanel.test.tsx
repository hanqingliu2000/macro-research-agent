import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssistantProposalPanel } from "./AssistantProposalPanel";

describe("AssistantProposalPanel", () => {
  it("separates read-only diagnostics from selectable mutations", () => {
    render(
      <AssistantProposalPanel
        diagnostics={[{
          summary: "Found 1 row with a missing analytical value.",
          details: ["USA · CPI · 2024-Q1"],
        }]}
        disabled={false}
        items={[{
          id: "sort",
          label: "sort",
          rationale: "Create deterministic order.",
          detail: "{}",
        }]}
        onApply={vi.fn()}
        onReject={vi.fn()}
        summary="Read-only diagnosis complete. Proposed 1 operation."
        target="sha256:data"
        title="Data preparation proposal"
      />,
    );

    expect(screen.getByRole("region", { name: "Read-only diagnostics" })).toHaveTextContent(
      "USA · CPI · 2024-Q1",
    );
    expect(screen.getByRole("checkbox")).toBeChecked();
  });
});
