import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AgentContext, type AgentContextValue } from "../state/AgentContextCore";
import type { AgentSession } from "../domain/types";
import { AgentChatPage } from "./AgentChatPage";

it("allows a linked research request when a failed run has no outputs", () => {
  const execute = vi.fn();
  const session = { id: "s", title: "Failed research", request: "Question", status: "failed",
    messages: [], steps: [], attachments: [], clarification: { questions: [], answers: {}, submitted: true },
    remote: { session_id: "s", run_id: "r", status: "failed", output: {}, nodes: [],
      ledger: { used: {}, limits: { active_seconds: 2700, formal_reviews: 3 } },
      error: { code: "task_attempt_limit", message: "Stopped" } },
  } as unknown as AgentSession;
  render(<AgentContext.Provider value={{ sessions: [session], execute, pending: {}, error: "" } as unknown as AgentContextValue}>
    <MemoryRouter initialEntries={["/agent/sessions/s"]}><Routes>
      <Route path="/agent/sessions/:agentSessionId" element={<AgentChatPage />} />
    </Routes></MemoryRouter>
  </AgentContext.Provider>);
  const input = screen.getByRole("textbox", { name: "Follow-up request" });
  expect(input).toBeEnabled();
  expect(screen.queryByText("Preparing clarification…")).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "A linked new research question" } });
  fireEvent.click(screen.getByRole("button", { name: "Start linked research run" }));
  expect(execute).toHaveBeenCalledWith("s", "new_run", { request: "A linked new research question" });
});
