import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentContext, type AgentContextValue } from "../state/AgentContextCore";
import type { AgentSession } from "../domain/types";
import { AgentRunControls } from "./AgentRunControls";

describe("Agent hard-stop recovery", () => {
  it("does not offer execution budget as a way to add delivery rounds", () => {
    const session = { id: "s", remote: {
      session_id: "s", run_id: "r", status: "budget_exhausted", output: {},
      error: { code: "budget_exhausted", message: "Output candidate limit reached." },
      ledger: { used: { output_candidates: 3 }, limits: { output_candidates: 3, formal_reviews: 3, active_seconds: 2700 } },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={{ pending: {}, error: "" } as unknown as AgentContextValue}>
      <AgentRunControls session={session} />
    </AgentContext.Provider>);
    expect(screen.queryByRole("button", { name: "Add execution budget" })).not.toBeInTheDocument();
    expect(screen.getByText(/Adding execution budget cannot add/)).toBeInTheDocument();
  });
  it("hides an impossible intervention when no-progress exhausted delivery rounds", () => {
    const session = { id: "s", remote: { session_id: "s", run_id: "r", status: "waiting_for_user", output: {},
      error: { code: "no_progress", message: "Stopped" },
      intervention: { reason: "no_progress", message: "Try again", options: [] },
      ledger: { used: { output_candidates: 3 }, limits: { output_candidates: 3, formal_reviews: 3, active_seconds: 2700 } },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={{ pending: {}, error: "" } as unknown as AgentContextValue}>
      <AgentRunControls session={session} />
    </AgentContext.Provider>);
    expect(screen.queryByRole("button", { name: "Continue with this response" })).not.toBeInTheDocument();
    expect(screen.getByText(/Delivery rounds are exhausted/)).toBeInTheDocument();
  });
  it.each(["failed", "waiting_for_user"])("does not advertise impossible retries for %s", status => {
    const execute = vi.fn();
    const session = { id: "s", remote: {
      session_id: "s", run_id: "r", status,
      ledger: { used: { model_calls: 3 }, limits: { model_calls: 40, formal_reviews: 3, active_seconds: 2700 } },
      output: {}, error: { code: "task_attempt_limit", message: "Stopped" },
      intervention: { message: "Try again", reason: "task_attempt_limit", options: [] },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={{ execute, pending: {}, error: "" } as unknown as AgentContextValue}>
      <AgentRunControls session={session} />
    </AgentContext.Provider>);
    expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue with this response" })).not.toBeInTheDocument();
    expect(screen.getByText(/exhausted its three calls/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect run" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    expect(execute).toHaveBeenCalledWith("s", "cancel");
  });
});
