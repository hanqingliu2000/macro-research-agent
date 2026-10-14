import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlanReadinessNotice } from "./PlanReadinessNotice";

describe("PlanReadinessNotice", () => {
  it("renders blockers as one assertive readiness notice", () => {
    render(<PlanReadinessNotice unresolvedItems={["Confirm the source."]} warnings={[]} />);

    const notice = screen.getByRole("alert", { name: "Plan readiness" });
    expect(notice).toHaveTextContent("Before acquiring data");
    expect(notice).toHaveTextContent("Resolve these blockers");
    expect(notice).not.toHaveTextContent("Review these cautions");
  });

  it("renders cautions as one polite readiness notice", () => {
    render(<PlanReadinessNotice unresolvedItems={[]} warnings={["Review the unit."]} />);

    const notice = screen.getByRole("status", { name: "Plan readiness" });
    expect(notice).toHaveTextContent("Review these cautions");
    expect(notice).not.toHaveTextContent("Resolve these blockers");
  });

  it("consolidates blockers and cautions without duplicate instruction banners", () => {
    render(
      <PlanReadinessNotice
        unresolvedItems={["Confirm the source."]}
        warnings={["Review the unit."]}
      />,
    );

    expect(screen.getAllByLabelText("Plan readiness")).toHaveLength(1);
    expect(screen.getByText("Resolve these blockers")).toBeInTheDocument();
    expect(screen.getByText("Review these cautions")).toBeInTheDocument();
    expect(screen.queryByText("Resolve before continuing")).not.toBeInTheDocument();
    expect(screen.queryByText("Review before Next")).not.toBeInTheDocument();
  });

  it("renders nothing when the Plan is ready without cautions", () => {
    const { container } = render(<PlanReadinessNotice unresolvedItems={[]} warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not treat an explicitly non-blocking discovery alternative as a blocker", () => {
    render(
      <PlanReadinessNotice
        unresolvedItems={[
          "Confirm whether a future connector admission should be pursued for a discovery-only IMF dataset; this does not block the executable WEO-based plan.",
        ]}
        warnings={[
          "The discovery index is a low-frequency bounded retrieval and cannot prove current availability.",
          "WEO vintages can revise historical debt figures.",
        ]}
      />,
    );

    const notice = screen.getByRole("status", { name: "Plan readiness" });
    expect(notice).not.toHaveTextContent("Resolve these blockers");
    expect(notice).not.toHaveTextContent("discovery index");
    expect(notice).toHaveTextContent("WEO vintages can revise historical debt figures");
  });

  it("defers observation availability claims until acquisition", () => {
    render(
      <PlanReadinessNotice
        unresolvedItems={[
          "IMF WEO has no reported values for 2018-2020.",
          "IMF Data is planned but unavailable; attach a local file or enable an executable connector.",
        ]}
        warnings={[
          "Exact codes must be validated at acquisition.",
          "WEO vintages can revise historical debt figures.",
        ]}
      />,
    );

    const notice = screen.getByRole("alert", { name: "Plan readiness" });
    expect(notice).not.toHaveTextContent("no reported values");
    expect(notice).not.toHaveTextContent("Exact codes");
    expect(notice).toHaveTextContent("enable an executable connector");
    expect(notice).toHaveTextContent("WEO vintages can revise historical debt figures");
  });
});
