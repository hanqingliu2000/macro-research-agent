import { useEffect, useState } from "react";

import type { PipelineOperation } from "../../domain/types";

const labels: Record<string, string> = {
  sourceUnit: "Source unit",
  targetUnit: "Target unit",
  outputUnit: "Output unit",
  factor: "Multiply by",
  offset: "Then add",
  method: "Aggregation",
  targetFrequency: "Target frequency",
  calendar: "Calendar convention",
  fiscalYearEndMonth: "Fiscal year-end month",
  incompletePeriod: "Incomplete periods",
};

const choices: Record<string, Array<[string, string]>> = {
  method: [["mean", "Mean"], ["sum", "Sum"], ["end", "End of period"]],
  targetFrequency: [["quarterly", "Quarterly"], ["annual", "Annual"]],
  calendar: [["calendar", "Calendar year"], ["fiscal", "Fiscal year"]],
  incompletePeriod: [["keep", "Keep and disclose"], ["drop", "Drop incomplete periods"], ["error", "Stop the run"]],
};

export function ParameterEditor({
  disabled,
  operation,
  onChange,
}: {
  disabled: boolean;
  operation?: PipelineOperation;
  onChange(parameters: PipelineOperation["parameters"]): void;
}) {
  const [draft, setDraft] = useState<PipelineOperation["parameters"]>(
    operation?.parameters ?? {},
  );
  useEffect(() => setDraft(operation?.parameters ?? {}), [operation]);
  if (!operation) return null;
  const entries = Object.entries(draft);
  const changed = JSON.stringify(draft) !== JSON.stringify(operation.parameters);
  return (
    <section className="pipeline-card parameter-editor">
      <p className="panel-kicker">PARAMETERS</p>
      <h2>Typed operation settings</h2>
      {entries.length === 0 ? (
        <p>This operation has no editable parameters in the current registry.</p>
      ) : (
        <div className="target-grid">
          {entries.map(([key, value]) => (
            <label key={key}>
              {labels[key] ?? key}
              {choices[key] ? (
                <select disabled={disabled} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} value={String(value)}>
                  {choices[key].map(([option, label]) => <option key={option} value={option}>{label}</option>)}
                </select>
              ) : (
                <input
                  disabled={disabled}
                  max={key === "fiscalYearEndMonth" ? 12 : undefined}
                  min={key === "fiscalYearEndMonth" ? 1 : undefined}
                  onChange={(event) => {
                    const nextValue = typeof value === "number"
                      ? Number(event.target.value)
                      : typeof value === "boolean"
                        ? event.target.value === "true"
                        : event.target.value;
                    setDraft({ ...draft, [key]: nextValue });
                  }}
                  type={typeof value === "number" ? "number" : "text"}
                  value={String(value)}
                />
              )}
            </label>
          ))}
        </div>
      )}
      {operation.kind === "unit_conversion" && <p className="model-parameter-note">Values become (value multiplied by factor) plus offset. The selected source unit must match exactly.</p>}
      {operation.kind === "frequency_conversion" && <p className="model-parameter-note">Fiscal alignment relabels monthly observations using the reviewed fiscal year-end month.</p>}
      <button className="secondary-button" disabled={disabled || !changed} onClick={() => onChange(draft)} type="button">Save parameters</button>
    </section>
  );
}
