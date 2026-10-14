import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createWorkflowSession, defaultPlan } from "../../domain/workflowEngine";
import { PlanChat } from "./PlanChat";

const mocks = vi.hoisted(() => ({
  execute: vi.fn(),
}));

vi.mock("../../state/WorkflowContextCore", () => ({
  useWorkflow: () => ({ execute: mocks.execute }),
}));

describe("PlanChat", () => {
  beforeEach(() => mocks.execute.mockReset());

  it("retains a failed revision for retry and prevents duplicate submissions while waiting", async () => {
    const session = createWorkflowSession("Forecast inflation.");
    session.currentPlan = defaultPlan(session.request);
    session.clarification.submitted = true;
    let finish: (() => void) | undefined;
    mocks.execute.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    render(<PlanChat manualEditPending={false} session={session} />);
    const input = screen.getByLabelText("Request a Plan revision");
    fireEvent.change(input, { target: { value: "Keep six forecast months and Python only." } });
    fireEvent.click(screen.getByRole("button", { name: "Propose change" }));
    expect(screen.getByRole("status")).toHaveTextContent("Preparing Plan changes…");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preparing changes…" })).toBeDisabled();
    await act(async () => finish?.());
    expect(input).toHaveValue("Keep six forecast months and Python only.");
    expect(screen.getByRole("button", { name: "Propose change" })).toBeEnabled();
    expect(mocks.execute).toHaveBeenCalledTimes(1);
  });

  it("shows and announces progress while drafting the Plan", async () => {
    const session = createWorkflowSession("Investigate inflation and prepare a forecast.");
    let finishDrafting: (() => void) | undefined;
    mocks.execute.mockReturnValue(new Promise<void>((resolve) => { finishDrafting = resolve; }));
    render(<PlanChat manualEditPending={false} session={session} />);

    session.clarification.questions.forEach((question) => {
      fireEvent.click(screen.getByLabelText(question.options[0]));
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit answers and draft Plan" }));

    expect(screen.getByRole("button", { name: "Drafting Plan…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Drafting Plan…" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Drafting Plan. Please wait.");
    session.clarification.questions.forEach((question) => {
      expect(screen.getByLabelText(question.options[0])).toBeDisabled();
    });
    expect(mocks.execute).toHaveBeenCalledTimes(1);

    await act(async () => finishDrafting?.());
    expect(screen.getByRole("button", { name: "Submit answers and draft Plan" })).toBeEnabled();
  });

  it("accepts a custom answer when the provided options do not fit", async () => {
    const session = createWorkflowSession("Investigate inflation and prepare a forecast.");
    mocks.execute.mockResolvedValue(undefined);
    render(<PlanChat manualEditPending={false} session={session} />);

    const [customQuestion, ...remainingQuestions] = session.clarification.questions;
    fireEvent.click(
      screen.getByRole("radio", {
        name: `Write another answer for: ${customQuestion.prompt}`,
      }),
    );
    const customInput = screen.getByRole("textbox", {
      name: `Custom answer for: ${customQuestion.prompt}`,
    });
    fireEvent.change(customInput, { target: { value: "China and ASEAN-5" } });
    remainingQuestions.forEach((question) => {
      fireEvent.click(screen.getByLabelText(question.options[0]));
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit answers and draft Plan" }));

    expect(mocks.execute).toHaveBeenCalledWith(session.id, {
      type: "submit_clarification",
      answers: expect.objectContaining({ [customQuestion.id]: "China and ASEAN-5" }),
    });
  });
});
