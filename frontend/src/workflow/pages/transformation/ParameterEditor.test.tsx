import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PipelineOperation } from "../../domain/types";
import { ParameterEditor } from "./ParameterEditor";

function operation(kind: PipelineOperation["kind"], parameters: PipelineOperation["parameters"]): PipelineOperation {
  return {
    id: `operation-${kind}`,
    kind,
    label: kind,
    enabled: true,
    target: { inputRef: "active_dataset", indicators: [], entities: [], fields: ["value"] },
    parameters,
    inputRef: "active_dataset",
    outputRef: `step:${kind}`,
    status: "not_run",
  };
}

describe("ParameterEditor harmonization controls", () => {
  it("uses visible typed controls for calendar and incomplete-period policy", () => {
    const onChange = vi.fn();
    render(<ParameterEditor disabled={false} operation={operation("frequency_conversion", {
      method: "mean",
      targetFrequency: "quarterly",
      calendar: "calendar",
      fiscalYearEndMonth: 12,
      incompletePeriod: "keep",
    })} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Calendar convention"), { target: { value: "fiscal" } });
    fireEvent.change(screen.getByLabelText("Fiscal year-end month"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Incomplete periods"), { target: { value: "error" } });
    fireEvent.click(screen.getByRole("button", { name: "Save parameters" }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      calendar: "fiscal",
      fiscalYearEndMonth: 6,
      incompletePeriod: "error",
    }));
  });

  it("explains and submits an affine unit conversion", () => {
    const onChange = vi.fn();
    render(<ParameterEditor disabled={false} operation={operation("unit_conversion", {
      sourceUnit: "percent",
      targetUnit: "basis points",
      factor: 100,
      offset: 0,
    })} onChange={onChange} />);

    expect(screen.getByText(/value multiplied by factor/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Multiply by"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save parameters" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ factor: 10 }));
  });
});
