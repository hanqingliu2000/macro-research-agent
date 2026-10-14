import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentDataPreview } from "./AgentDataPreview";
import type { BackendAgentRun } from "../domain/types";

afterEach(() => vi.unstubAllGlobals());

describe("Agent data preview", () => {
  it("shows period/value/unit and loads the actual remaining rows", async () => {
    const first = { columns: ["period", "value", "unit"], rows: Array.from({ length: 12 }, (_, index) => ({ period: String(2010 + index), value: index, unit: "Percent" })), total_rows: 13 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...first, rows: [{ period: "2022", value: 12, unit: "Percent" }] }))));
    render(<AgentDataPreview initial={first} run={{ session_id: "s", run_id: "r" } as BackendAgentRun} />);
    expect(screen.getAllByRole("columnheader").map(cell => cell.textContent)).toEqual(["period", "value", "unit"]);
    fireEvent.click(screen.getByRole("button", { name: "Next rows" }));
    await waitFor(() => expect(screen.getByText("Rows 13–13 of 13")).toBeInTheDocument());
    expect(screen.getByText("2022")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next rows" })).toBeDisabled();
  });
});
