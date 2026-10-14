import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { WORKFLOW_SESSION_STORAGE_KEY } from "../workflow/services/mockWorkflowService";
import { App } from "./App";

const AGENT_STORAGE_KEY = "macro-research-agent.agent.mock.sessions.v1";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("Macro Research Agent interfaces", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows the four-stage Workflow home", () => {
    renderAt("/");

    expect(
      screen.getByRole("heading", {
        name: "Macro Research Workbench",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary research tools" })).toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation", { name: "Primary research tools" })).queryByRole(
        "link",
        { name: "New research" },
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New research" })).toBeInTheDocument();
    expect(screen.queryByRole("contentinfo", { name: "Research status bar" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to research workspace" })).toHaveAttribute("href", "#research-workbench-main");
    expect(document.querySelector(".research-workbench-workflow")).toBeInTheDocument();
    expect(screen.getByText("Clarify and confirm the Plan")).toBeInTheDocument();
    expect(screen.getAllByText("Post-pandemic inflation dynamics")).not.toHaveLength(0);
    expect(screen.queryByText("Try Agent Mode")).not.toBeInTheDocument();
    expect(screen.queryByText("Four-stage mock")).not.toBeInTheDocument();
    expect(screen.queryByText("EXAMPLE QUESTIONS")).not.toBeInTheDocument();
    expect(screen.queryByText(/Plan, inspect, transform/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Clarification happens inside Plan/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Raw data is never sent/)).not.toBeInTheDocument();
    expect(screen.queryByText("Research Explorer")).not.toBeInTheDocument();
    expect(screen.queryByText("Local workflow store")).not.toBeInTheDocument();
    expect(screen.queryByText("Resume current work.")).not.toBeInTheDocument();
    expect(screen.queryByText("WORKBENCH / NEW SESSION")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What would you like to investigate?" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start planning" })).toBeInTheDocument();
    expect(screen.getByText("Import session")).toBeInTheDocument();
  });

  it("keeps Workflow and Agent storage and session lists isolated", () => {
    const workflow = renderAt("/");
    expect(window.localStorage.getItem(WORKFLOW_SESSION_STORAGE_KEY)).not.toBeNull();
    expect(window.localStorage.getItem(AGENT_STORAGE_KEY)).toBeNull();
    expect(screen.queryByText("Inflation normalization — agent run")).not.toBeInTheDocument();
    workflow.unmount();

    window.localStorage.clear();
    renderAt("/agent");
    expect(window.localStorage.getItem(AGENT_STORAGE_KEY)).not.toBeNull();
    expect(window.localStorage.getItem(WORKFLOW_SESSION_STORAGE_KEY)).toBeNull();
    expect(screen.getAllByText("Inflation normalization — agent run")).not.toHaveLength(0);
    expect(screen.queryByText("Post-pandemic inflation dynamics")).not.toBeInTheDocument();
    expect(screen.queryByText("Separate session store")).not.toBeInTheDocument();
    expect(screen.queryByText("WORKBENCH / NEW AGENT RUN")).not.toBeInTheDocument();
    expect(screen.queryByText(/Ask a research question, clarify the scope/)).not.toBeInTheDocument();
    expect(screen.queryByText("untitled-agent-run.md")).not.toBeInTheDocument();
    expect(screen.queryByText(/metadata stays within this Agent session/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No web search is used/)).not.toBeInTheDocument();
    expect(screen.queryByText("Agent Explorer")).not.toBeInTheDocument();
    expect(screen.queryByText("Isolated agent store")).not.toBeInTheDocument();
    expect(screen.queryByRole("contentinfo", { name: "Research status bar" })).not.toBeInTheDocument();
  });

  it("labels runtime capabilities without presenting planned adapters as live", () => {
    renderAt("/settings");

    expect(screen.getByText("Deterministic offline adapter")).toBeInTheDocument();
    expect(screen.getByText("Not configured", { selector: ".configuration-status" })).toBeInTheDocument();
    expect(screen.getByText("To be selected")).toBeInTheDocument();
    expect(screen.getByText(/Remote artifact and data disclosure remains disabled/)).toBeInTheDocument();
    expect(screen.getByText("Read-only, session- and stage-bound values")).toBeInTheDocument();
    expect(screen.getByText("PLANNED")).toBeInTheDocument();
    expect(screen.queryByText("DeepSeek profile")).not.toBeInTheDocument();
    expect(screen.queryByText("Schema and summaries only")).not.toBeInTheDocument();
  });

  it("creates a Workflow session directly in Plan clarification", async () => {
    renderAt("/");
    fireEvent.change(screen.getByLabelText("Research request"), {
      target: { value: "Compare inflation and policy rates across three economies." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start planning" }));

    expect(await screen.findByText("Confirm the research frame")).toBeInTheDocument();
    expect(
      screen.getByText("Which economies or regional group should define the sample?"),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Plan conversation" })).toBeInTheDocument();
    const emptyPlan = screen.getByRole("region", { name: "Current Plan" });
    expect(emptyPlan).toHaveClass("plan-editor", "plan-empty-state");
    expect(emptyPlan.nextElementSibling).toBe(
      screen.getByRole("region", { name: "Plan conversation" }),
    );
    expect(screen.queryByText("PLAN CHAT")).not.toBeInTheDocument();
    expect(screen.queryByText("Research design")).not.toBeInTheDocument();
    expect(screen.queryByText("Locked")).not.toBeInTheDocument();
  });

  it("guards an unreached future stage and returns to Plan", () => {
    renderAt("/sessions/demo-inflation/output");

    expect(screen.getByRole("region", { name: "Plan conversation" })).toBeInTheDocument();
    expect(screen.getByText("output is not ready. Complete plan first.")).toBeInTheDocument();
    expect(screen.queryByText("OUTPUT CHAT")).not.toBeInTheDocument();
  });

  it("creates and applies a typed Plan patch", async () => {
    renderAt("/sessions/demo-inflation/plan");
    expect(screen.queryByText("Current Plan saved")).not.toBeInTheDocument();
    expect(screen.queryByText("typed operation intent")).not.toBeInTheDocument();
    expect(screen.queryByText("independent model job")).not.toBeInTheDocument();
    expect(screen.queryByText(/Retrieve member-country CPI levels/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Request a Plan revision"), {
      target: { value: "Extend the start period for robustness." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propose change" }));

    expect(await screen.findByText("PROPOSED PLAN CHANGES")).toBeInTheDocument();
    expect(screen.getByText("Extend the sample start to 2010.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply selected changes" }));
    await waitFor(() => expect(screen.getByLabelText("Start")).toHaveValue("2010"));
    expect(screen.queryByText("VERSION HISTORY")).not.toBeInTheDocument();
  });

  it("opens a second clarification round from the reviewed Plan", async () => {
    renderAt("/sessions/demo-inflation/plan");

    fireEvent.click(screen.getByRole("button", { name: "Ask follow-up questions" }));

    expect(await screen.findByText("Confirm the research frame")).toBeInTheDocument();
    expect(screen.getByText("Which economies or regional group should define the sample?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit answers and draft Plan" })).toBeDisabled();
  });

  it("prevents Plan Chat from racing unsaved manual Plan edits", async () => {
    renderAt("/sessions/demo-inflation/plan");
    fireEvent.change(screen.getByLabelText("Research objective"), {
      target: { value: "A manually revised inflation objective." },
    });

    expect(screen.getByRole("button", { name: "Propose change" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save manual changes" }));
    await waitFor(() => expect(screen.getByLabelText("Request a Plan revision")).not.toBeDisabled());
  });

  it("runs the four-stage mock path including data preparation and Output", async () => {
    // LRS-OUTPUT-10/12: draft/final distinction and exact final package confirmation.
    renderAt("/sessions/demo-inflation/plan");
    fireEvent.click(screen.getByRole("button", { name: "Next: acquire data" }));

    expect(await screen.findByRole("heading", { name: "Sources and queries" })).toBeInTheDocument();
    expect(screen.queryByText("PLAN CHAT")).not.toBeInTheDocument();
    expect(screen.queryByText("Normalized connector data")).not.toBeInTheDocument();
    expect(screen.queryByText("Every action creates a snapshot.")).not.toBeInTheDocument();
    expect(screen.queryByText("Controlled XLSX round trip")).not.toBeInTheDocument();
    expect(screen.queryByText("Acquisition boundary")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export for external cleaning" })).toBeInTheDocument();
    expect(screen.getByLabelText("Reimport cleaned XLSX")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filter missing" }));
    expect(await screen.findAllByText("Filter missing observations")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Undo last data operation" }));
    expect(await screen.findByText("No preparation operation has changed the connector snapshot.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next: configure pipeline" }));
    expect(await screen.findByRole("heading", { name: "Applied operations" })).toBeInTheDocument();
    expect(screen.queryByText("PLAN CHAT")).not.toBeInTheDocument();
    expect(screen.queryByText(/No arbitrary Python/)).not.toBeInTheDocument();
    expect(screen.queryByText(/active_dataset.*step:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByRole("heading", { name: "Generated deliverables" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Transformation, completed" }));
    expect(await screen.findByRole("button", { name: "Revise analysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save target" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Revise analysis" }));
    expect(screen.getByRole("dialog", { name: "Revise the completed analysis?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Begin revision" }));
    expect(await screen.findByText(/Analysis revision in progress/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run updated analysis" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Run updated analysis" }));
    expect(await screen.findByRole("heading", { name: "Generated deliverables" })).toBeInTheDocument();
    expect(screen.getByText("OUTPUT CHAT")).toBeInTheDocument();
    expect(screen.queryByText(/Only artifact specs/)).not.toBeInTheDocument();
    expect(screen.getAllByText("research_report.md")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Finish and freeze selected" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Run output review" }));
    expect(
      await screen.findByText("No structural, visual or semantic findings."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Request an output revision"), {
      target: { value: "Short reviewed chart title" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propose revision" }));
    expect(await screen.findByText("Select corrections")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Apply selected corrections" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply selected corrections" }));
    await waitFor(() => expect(screen.queryByText("Select corrections")).not.toBeInTheDocument());
    expect(await screen.findByText("2/3 review rounds")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Finish and freeze selected" }));
    expect(screen.getByRole("dialog", { name: "Confirm the exact package to freeze" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm and freeze" }));
    expect(await screen.findByText(/Frozen at/)).toBeInTheDocument();
    expect(screen.queryByText(/^frozen$/i)).not.toBeInTheDocument();
  });

  it("shows a coherent reviewed state for the completed seed session", async () => {
    renderAt("/sessions/demo-fiscal/output");

    expect(
      await screen.findByText("No structural, visual or semantic findings."),
    ).toBeInTheDocument();
    expect(screen.getByText("1/3 review rounds")).toBeInTheDocument();
    expect(screen.queryByText("Run Output review before Finish.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish and freeze selected" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue in a new session" })).toBeInTheDocument();
  });

  it("reviews and selectively applies Data and Analysis AI proposals", async () => {
    const clickReadyCommand = async (name: string) => {
      const button = await screen.findByRole("button", { name });
      await waitFor(() => expect(button).toBeEnabled());
      // Commands commit session state and navigation after their service promise resolves.
      await act(async () => { fireEvent.click(button); });
    };

    renderAt("/sessions/demo-inflation/plan");
    await clickReadyCommand("Next: acquire data");
    expect(await screen.findByRole("heading", { name: "Sources and queries" })).toBeInTheDocument();

    fireEvent.change(await screen.findByLabelText("Ask Data AI"), {
      target: { value: "Review missing values and sort the data." },
    });
    await clickReadyCommand("Generate proposal");
    expect(await screen.findByRole("region", { name: "Data preparation proposal" })).toBeInTheDocument();
    expect(screen.getByText("filter missing")).toBeInTheDocument();
    await clickReadyCommand("Apply selected steps");
    expect(await screen.findByText("Filter missing observations")).toBeInTheDocument();

    await clickReadyCommand("Next: configure pipeline");
    expect(await screen.findByRole("heading", { name: "Applied operations" })).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("Ask Analysis AI"), {
      target: { value: "Add growth and descriptive analysis." },
    });
    await clickReadyCommand("Generate proposal");
    expect(await screen.findByRole("region", { name: "Analysis proposal" })).toBeInTheDocument();
    expect(screen.getByText("yoy growth")).toBeInTheDocument();
    expect(screen.getByText("descriptive model")).toBeInTheDocument();
    await clickReadyCommand("Apply selected steps");
    expect(await screen.findAllByText("Year-on-year growth")).not.toHaveLength(0);
    expect(screen.getByText("DESCRIPTIVE model")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeInTheDocument();
  });

  it("validates a cleaned XLSX mapping before replacing active data", async () => {
    renderAt("/sessions/demo-inflation/plan");
    fireEvent.click(screen.getByRole("button", { name: "Next: acquire data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Export for external cleaning" }));
    await waitFor(() => {
      const sessions = JSON.parse(
        window.localStorage.getItem(WORKFLOW_SESSION_STORAGE_KEY) ?? "[]",
      );
      expect(sessions.find((session: { id: string }) => session.id === "demo-inflation")?.data.lastExportedPackage).toBeDefined();
    });

    fireEvent.change(screen.getByLabelText("Reimport cleaned XLSX"), {
      target: {
        files: [
          new File(["mock workbook"], "cleaned_macro_data.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        ],
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Validate mapping" }));
    expect(await screen.findByText("validated")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use as active dataset" }));
    expect(
      await screen.findByText(
        "Validated external workbook is now the active dataset. Original snapshots remain preserved.",
      ),
    ).toBeInTheDocument();
  });

  it("confirms impact before an upstream Data edit and preserves stale Output", async () => {
    renderAt("/sessions/demo-fiscal/data");
    fireEvent.click(screen.getByRole("button", { name: "Filter missing" }));

    const impactDialog = screen.getByRole("dialog", { name: "Change the active dataset?" });
    expect(impactDialog).toBeInTheDocument();
    expect(within(impactDialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.keyDown(impactDialog, { key: "Tab", shiftKey: true });
    expect(within(impactDialog).getByRole("button", { name: "Confirm change" })).toHaveFocus();
    expect(within(impactDialog).getByText("Transformation")).toBeInTheDocument();
    expect(within(impactDialog).getByText("Output")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Change the active dataset?" })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("link", { name: /^Output/ }));
    expect(await screen.findByText("This stage is stale.")).toBeInTheDocument();
    expect(screen.getAllByText("inflation_comparison.png")).not.toHaveLength(0);
  });

  it("confirms impact before a Transformation edit invalidates reached Output", async () => {
    renderAt("/sessions/demo-inflation/plan");
    fireEvent.click(screen.getByRole("button", { name: "Next: acquire data" }));
    fireEvent.click(await screen.findByRole("button", { name: "Next: configure pipeline" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run analysis" }));
    fireEvent.click(await screen.findByRole("link", { name: "Transformation, completed" }));

    expect(screen.getByRole("button", { name: "Add to operation chain" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Revise analysis" }));

    const impactDialog = screen.getByRole("dialog", {
      name: "Revise the completed analysis?",
    });
    expect(within(impactDialog).getByText("Output")).toBeInTheDocument();
    fireEvent.click(within(impactDialog).getByRole("button", { name: "Begin revision" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Revise the completed analysis?" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Add to operation chain" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Add to operation chain" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: /^Output/ }));
    expect(await screen.findByText("This stage is stale.")).toBeInTheDocument();
  });

  it("keeps the existing isolated Agent flow working", () => {
    renderAt("/agent");
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Compare inflation normalization across three economies." },
    });
    fireEvent.change(screen.getByLabelText("Attach data"), {
      target: { files: [new File(["economy,value"], "supplement.csv", { type: "text/csv" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start agent run" }));
    expect(screen.getByText("Confirm the research frame")).toBeInTheDocument();
  });

  it("uses the shared Workbench chrome and accessible Agent result surfaces", () => {
    renderAt("/agent/agent-demo-inflation");

    expect(document.querySelector(".research-workbench-agent")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary research tools" })).toBeInTheDocument();
    expect(screen.queryByRole("contentinfo", { name: "Research status bar" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Agent Explorer" })).toBeInTheDocument();
    expect(screen.getByRole("log", { name: "Agent message log" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Agent research progress" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Underlying mock inflation and policy-rate data" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Inflation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Python" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("＋");
    expect(document.body.textContent).not.toContain("✓");
  });

  it("announces invalid Agent attachments and supports removing valid files", () => {
    renderAt("/agent");
    const input = screen.getByLabelText("Attach data");

    fireEvent.change(input, {
      target: { files: [new File(["notes"], "notes.txt", { type: "text/plain" })] },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Only .csv, .json and .xlsx");
    expect(input).toHaveAttribute("aria-invalid", "true");

    fireEvent.change(input, {
      target: { files: [new File(["economy,value"], "supplement.csv", { type: "text/csv" })] },
    });
    expect(screen.getByRole("button", { name: "Remove supplement.csv" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove supplement.csv" }));
    expect(screen.queryByText("supplement.csv")).not.toBeInTheDocument();
  });

  it("does not expose the removed five-step or Steps interfaces", () => {
    renderAt("/sessions/demo-inflation/plan");
    expect(screen.queryByRole("tab", { name: "Steps" })).not.toBeInTheDocument();
    expect(screen.queryByText("High-level progress")).not.toBeInTheDocument();
    expect(screen.queryByText("Model", { selector: "button" })).not.toBeInTheDocument();
    expect(screen.queryByText("event_id")).not.toBeInTheDocument();
  });
});
