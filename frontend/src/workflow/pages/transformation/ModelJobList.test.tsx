import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../../domain/workflowEngine";
import type { ModelJob } from "../../domain/types";
import { ModelJobList } from "./ModelJobList";

describe("ModelJobList", () => {
  it("exposes a stale model input instead of visually falling back to Active dataset", () => {
    const session = createWorkflowSession("Inspect a rebuilt transformation graph.");
    session.pipeline.models = [{
      id: "model-stale",
      kind: "descriptive",
      label: "DESCRIPTIVE model",
      inputRef: "step:deleted",
      variables: [],
      dependentVariables: [],
      independentVariables: [],
      parameters: {
        missing: "drop",
        addConstant: true,
        covariance: "nonrobust",
        maxLags: 1,
      },
      status: "not_run",
    }];
    const onInputChange = vi.fn();
    render(
      <ModelJobList
        disabled={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
        onInputChange={onInputChange}
        onSpecificationChange={vi.fn()}
        session={session}
      />,
    );

    const input = screen.getByLabelText("DESCRIPTIVE model input");
    expect(input).toHaveValue("step:deleted");
    expect(screen.getByRole("option", { name: "Unavailable output — choose input" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "active_dataset" } });
    expect(onInputChange).toHaveBeenCalledWith("model-stale", "active_dataset");
  });

  it("shows and submits only the reviewed ADF parameters", () => {
    const session = createWorkflowSession("Test a series for a unit root.");
    const model: ModelJob = {
      id: "model-adf",
      kind: "adf",
      label: "ADF model",
      inputRef: "active_dataset",
      variables: ["CPI"],
      dependentVariables: [],
      independentVariables: [],
      parameters: {
        missing: "drop",
        addConstant: false,
        covariance: "nonrobust",
        maxLags: 2,
        regression: "c",
        autolag: "AIC",
      },
      status: "not_run",
    };
    session.pipeline.models = [model];
    const onSpecificationChange = vi.fn();

    render(
      <ModelJobList
        disabled={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
        onInputChange={vi.fn()}
        onSpecificationChange={onSpecificationChange}
        session={session}
      />,
    );

    expect(screen.queryByText("Dependent")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Deterministic terms"), {
      target: { value: "ct" },
    });
    fireEvent.change(screen.getByLabelText("Lag selection"), { target: { value: "BIC" } });
    fireEvent.change(screen.getByLabelText("Max lags"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Save specification" }));

    expect(onSpecificationChange).toHaveBeenCalledWith(
      "model-adf",
      expect.objectContaining({
        variables: ["CPI"],
        parameters: expect.objectContaining({ regression: "ct", autolag: "BIC", maxLags: 4 }),
      }),
    );
  });

  it("shows SARIMAX forecast controls and submits typed orders", () => {
    const session = createWorkflowSession("Forecast inflation with policy-rate assumptions.");
    const model: ModelJob = {
      id: "model-sarimax",
      kind: "sarimax",
      label: "SARIMAX model",
      inputRef: "active_dataset",
      variables: [],
      dependentVariables: ["CPI"],
      independentVariables: ["POLICY_RATE"],
      parameters: {
        missing: "drop",
        addConstant: true,
        covariance: "nonrobust",
        maxLags: 1,
        orderP: 1,
        orderD: 0,
        orderQ: 0,
        seasonalP: 0,
        seasonalD: 0,
        seasonalQ: 0,
        seasonalPeriod: 0,
        trend: "c",
        forecastSteps: 4,
        confidenceLevel: 0.95,
        enforceStationarity: true,
        enforceInvertibility: true,
      },
      status: "not_run",
    };
    session.pipeline.models = [model];
    const onSpecificationChange = vi.fn();

    render(
      <ModelJobList
        disabled={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
        onInputChange={vi.fn()}
        onSpecificationChange={onSpecificationChange}
        session={session}
      />,
    );

    expect(screen.getByLabelText("Forecast target")).toHaveValue("CPI");
    expect(screen.getByLabelText("Future exogenous indicators")).toHaveValue("POLICY_RATE");
    fireEvent.change(screen.getByLabelText("Seasonal AR (P)"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Season length (s)"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Forecast periods"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Confidence level"), { target: { value: "0.9" } });
    fireEvent.click(screen.getByRole("button", { name: "Save specification" }));

    expect(onSpecificationChange).toHaveBeenCalledWith(
      "model-sarimax",
      expect.objectContaining({
        dependentVariables: ["CPI"],
        independentVariables: ["POLICY_RATE"],
        parameters: expect.objectContaining({
          seasonalP: 1,
          seasonalPeriod: 12,
          forecastSteps: 6,
          confidenceLevel: 0.9,
        }),
      }),
    );
  });

  it("reveals optional VAR impulse-response controls and preserves variable order", () => {
    const session = createWorkflowSession("Estimate policy transmission with a VAR.");
    const model: ModelJob = {
      id: "model-var",
      kind: "var",
      label: "VAR model",
      inputRef: "active_dataset",
      variables: ["CPI", "POLICY_RATE"],
      dependentVariables: [],
      independentVariables: [],
      parameters: {
        missing: "drop",
        addConstant: true,
        covariance: "nonrobust",
        maxLags: 2,
        lagSelection: "bic",
        trend: "c",
        includeIrf: false,
        irfPeriods: 12,
        impulseVariables: [],
        orthogonalized: true,
        confidenceLevel: 0.95,
      },
      status: "not_run",
    };
    session.pipeline.models = [model];
    const onSpecificationChange = vi.fn();

    render(
      <ModelJobList
        disabled={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
        onInputChange={vi.fn()}
        onSpecificationChange={onSpecificationChange}
        session={session}
      />,
    );

    expect(screen.getByLabelText("Ordered endogenous indicators")).toHaveValue(
      "CPI, POLICY_RATE",
    );
    expect(screen.queryByLabelText("Impulse indicators")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Generate impulse responses"));
    fireEvent.change(screen.getByLabelText("Impulse indicators"), {
      target: { value: "POLICY_RATE" },
    });
    fireEvent.change(screen.getByLabelText("IRF periods"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Forecast periods"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save specification" }));

    expect(onSpecificationChange).toHaveBeenCalledWith(
      "model-var",
      expect.objectContaining({
        variables: ["CPI", "POLICY_RATE"],
        dependentVariables: [],
        independentVariables: [],
        parameters: expect.objectContaining({
          lagSelection: "bic",
          includeIrf: true,
          impulseVariables: ["POLICY_RATE"],
          irfPeriods: 8,
          forecastSteps: 2,
          orthogonalized: true,
        }),
      }),
    );
  });
});
