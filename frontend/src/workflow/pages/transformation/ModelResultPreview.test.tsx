import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ModelResult } from "../../domain/types";
import { ModelResultPreview } from "./ModelResultPreview";

describe("ModelResultPreview", () => {
  it("shows grouped ADF evidence, its hypothesis, and warnings", () => {
    const result: ModelResult = {
      id: "result-adf",
      jobId: "model-adf",
      kind: "adf",
      inputSnapshotId: "snapshot-1",
      inputSnapshotHash: "snapshot-hash-123456789",
      specificationHash: "specification-hash",
      resultHash: "result-hash-123456789",
      sample: { observations: 80, dropped: 0 },
      result: {
        nullHypothesis: "The series has a unit root.",
        groups: [
          {
            entityCode: "USA",
            frequency: "A",
            statistic: -2.125,
            pValue: 0.24,
            criticalValues: { "5%": -2.89 },
          },
        ],
      },
      diagnostics: [],
      warnings: ["USA (A) does not reject the unit-root null at 5%."],
      createdAt: "2026-09-05T00:00:00Z",
    };

    render(<ModelResultPreview results={[result]} />);

    expect(screen.getByText(/The series has a unit root/)).toBeInTheDocument();
    expect(screen.getByText("USA")).toBeInTheDocument();
    expect(screen.getByText('{"5%":-2.89}')).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Model warnings" })).toHaveTextContent(
      "does not reject the unit-root null at 5%",
    );
  });

  it("shows forecast means and intervals separately from model fit", () => {
    const result: ModelResult = {
      id: "result-arima",
      jobId: "model-arima",
      kind: "arima",
      inputSnapshotId: "snapshot-1",
      inputSnapshotHash: "snapshot-hash-123456789",
      specificationHash: "specification-hash",
      resultHash: "result-hash-123456789",
      sample: { observations: 36, dropped: 0 },
      result: {
        groups: [{ entityCode: "USA", frequency: "monthly", aic: 12.5, converged: true }],
        forecasts: [
          {
            entityCode: "USA",
            frequency: "monthly",
            period: "2022-01",
            step: 1,
            mean: 110.25,
            lower: 108.1,
            upper: 112.4,
          },
        ],
      },
      diagnostics: [],
      warnings: [],
      createdAt: "2026-09-05T00:00:00Z",
    };

    render(<ModelResultPreview results={[result]} />);

    expect(screen.getByRole("heading", { name: "Forecast" })).toBeInTheDocument();
    expect(screen.getByText("2022-01")).toBeInTheDocument();
    expect(screen.getByText("110.25")).toBeInTheDocument();
    expect(screen.getByText("108.1")).toBeInTheDocument();
    expect(screen.getByText("112.4")).toBeInTheDocument();
  });

  it("shows VAR impulse responses as a separate review table", () => {
    const result: ModelResult = {
      id: "result-var",
      jobId: "model-var",
      kind: "var",
      inputSnapshotId: "snapshot-1",
      inputSnapshotHash: "snapshot-hash-123456789",
      specificationHash: "specification-hash",
      resultHash: "result-hash-123456789",
      sample: { observations: 60, dropped: 0 },
      result: {
        coefficients: [{ equation: "CPI", term: "L1.POLICY_RATE", estimate: 0.25 }],
        impulseResponses: [
          {
            entityCode: "USA",
            frequency: "quarterly",
            impulse: "POLICY_RATE",
            response: "CPI",
            period: 1,
            estimate: -0.2,
            lower: -0.35,
            upper: -0.05,
          },
        ],
      },
      diagnostics: [],
      warnings: [],
      createdAt: "2026-09-06T00:00:00Z",
    };

    render(<ModelResultPreview results={[result]} />);

    expect(screen.getByRole("heading", { name: "Impulse responses" })).toBeInTheDocument();
    expect(screen.getByText("POLICY_RATE")).toBeInTheDocument();
    expect(screen.getByText("-0.35")).toBeInTheDocument();
  });
});
