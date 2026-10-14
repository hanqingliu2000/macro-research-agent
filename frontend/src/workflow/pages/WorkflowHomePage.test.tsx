import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../domain/workflowEngine";
import { MockWorkflowService } from "../services/mockWorkflowService";
import { WorkflowProvider } from "../state/WorkflowContext";
import { WorkflowHomePage } from "./WorkflowHomePage";

afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear(); });

describe("Session lifecycle", () => {
  it("keeps the full initial prompt as title", () => {
    const prompt = "Investigate China's inflation for the last 36 months and project the coming six months.";
    expect(createWorkflowSession(prompt).title).toBe(prompt);
  });

  it("confirms deletion, hides the session, and restores it from Trash", async () => {
    const service = new MockWorkflowService();
    const session = await service.createSession("Research to restore");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MemoryRouter><WorkflowProvider service={service}><WorkflowHomePage /></WorkflowProvider></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: `Delete ${session.title}` }));
    expect(screen.getByRole("link", { name: session.title })).toBeInTheDocument();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: `Delete ${session.title}` }));
    await waitFor(() => expect(screen.queryByRole("link", { name: session.title })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Trash" }));
    fireEvent.click(screen.getByRole("button", { name: `Restore ${session.title}` }));
    await waitFor(() => expect(screen.queryByRole("button", { name: `Restore ${session.title}` })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Show active" }));
    expect(screen.getByRole("link", { name: session.title })).toBeInTheDocument();
  });
});
