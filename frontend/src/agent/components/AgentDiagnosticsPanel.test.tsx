import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentDiagnosticsPanel, type AgentDiagnostics } from "./AgentDiagnosticsPanel";

describe("Agent diagnostics", () => {
  it("filters errors and compares complete immutable attempt references", () => {
    const data: AgentDiagnostics = { events: [
      { sequence: 1, occurred_at: "2026-10-06", event_type: "ai.contract_rejected", task_id: "report", attempt_id: "a", level: "error", payload: { role: "author", code: "invalid_model_contract" } },
      { sequence: 2, occurred_at: "2026-10-06", event_type: "task.completed", task_id: "report", attempt_id: "b", level: "info", payload: {} },
    ], attempts: [
      { attempt_id: "a", task: "report", status: "failed", input_refs: ["snapshot-v1"], output_refs: [] },
      { attempt_id: "b", task: "report", status: "completed", input_refs: ["snapshot-v1"], output_refs: ["report-v2"] },
    ], payloads: [], integrity_issues: [], metrics: {} };
    render(<AgentDiagnosticsPanel data={data} basePath="/diagnostics" />);
    fireEvent.change(screen.getByLabelText("Filter by role, task, event or error"), { target: { value: "invalid_model_contract" } });
    expect(screen.getByText(/1 matching events/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Attempt"), { target: { value: "a" } });
    fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "b" } });
    expect(screen.getByLabelText("Attempt comparison")).toHaveTextContent("report-v2");
    expect(screen.getByRole("link", { name: /Offline replay/ })).toHaveAttribute("href", "/diagnostics/replay?verify_numerics=true");
  });
});
