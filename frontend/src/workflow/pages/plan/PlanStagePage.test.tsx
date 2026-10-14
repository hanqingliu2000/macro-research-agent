import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { PlanStagePage } from "./PlanStagePage";

vi.mock("../../components/useWorkflowSession", () => ({ useWorkflowSession: () => ({ id: "session" }) }));
vi.mock("../../state/WorkflowContextCore", () => ({ useWorkflow: () => ({ execute: vi.fn() }) }));
vi.mock("./PlanEditor", () => ({ PlanEditor: () => <section aria-label="Plan information" /> }));
vi.mock("./PlanChat", () => ({ PlanChat: () => <aside aria-label="Plan conversation" /> }));

it("places Plan information before the right-hand conversation in DOM and focus order", () => {
  render(<MemoryRouter><PlanStagePage /></MemoryRouter>);
  const editor = screen.getByRole("region", { name: "Plan information" });
  const chat = screen.getByRole("complementary", { name: "Plan conversation" });
  expect(editor.nextElementSibling).toBe(chat);
});
