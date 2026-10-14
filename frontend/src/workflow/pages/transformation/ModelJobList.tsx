import { useState } from "react";

import type { CovarianceKind, ExecutableModelKind, ModelJob, WorkflowSession } from "../../domain/types";
import { WorkbenchIcon } from "../../../ui/components/WorkbenchIcon";
import { SectionHeading } from "../../components/SectionHeading";

const models: ExecutableModelKind[] = ["descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"];

function codes(value: FormDataEntryValue | null) {
  return String(value ?? "").split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
}

function SpecificationEditor({ disabled, model, onSave }: { disabled: boolean; model: ModelJob; onSave(specification: Pick<ModelJob, "variables" | "dependentVariables" | "independentVariables" | "parameters">): void }) {
  const isForecast = model.kind === "arima" || model.kind === "sarimax";
  const isVar = model.kind === "var";
  const [includeIrf, setIncludeIrf] = useState(model.parameters.includeIrf ?? false);
  return (
    <form className="model-specification" onSubmit={(event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      onSave({
        variables: codes(data.get("variables")),
        dependentVariables: codes(data.get("dependent")),
        independentVariables: codes(data.get("independent")),
        parameters: {
          missing: "drop",
          addConstant: data.get("constant") === "on",
          covariance: String(data.get("covariance") ?? "nonrobust") as CovarianceKind,
          maxLags: Number(data.get("maxLags") ?? 1),
          ...(model.kind === "adf" ? {
            regression: String(data.get("regression") ?? "c") as "c" | "ct" | "ctt" | "n",
            autolag: String(data.get("autolag") ?? "AIC") as "AIC" | "BIC" | "t-stat" | "none",
          } : {}),
          ...(isForecast ? {
            orderP: Number(data.get("orderP") ?? 1),
            orderD: Number(data.get("orderD") ?? 0),
            orderQ: Number(data.get("orderQ") ?? 0),
            seasonalP: Number(data.get("seasonalP") ?? 0),
            seasonalD: Number(data.get("seasonalD") ?? 0),
            seasonalQ: Number(data.get("seasonalQ") ?? 0),
            seasonalPeriod: Number(data.get("seasonalPeriod") ?? 0),
            trend: String(data.get("trend") ?? "c") as "n" | "c" | "t" | "ct",
            forecastSteps: Number(data.get("forecastSteps") ?? 4),
            confidenceLevel: Number(data.get("confidenceLevel") ?? 0.95),
            enforceStationarity: data.get("enforceStationarity") === "on",
            enforceInvertibility: data.get("enforceInvertibility") === "on",
          } : {}),
          ...(isVar ? {
            lagSelection: String(data.get("lagSelection") ?? "fixed") as "fixed" | "aic" | "bic" | "hqic" | "fpe",
            trend: String(data.get("trend") ?? "c") as "n" | "c" | "ct" | "ctt",
            includeIrf: data.get("includeIrf") === "on",
            irfPeriods: Number(data.get("irfPeriods") ?? 12),
            impulseVariables: codes(data.get("impulseVariables")),
            orthogonalized: data.get("orthogonalized") === "on",
            confidenceLevel: Number(data.get("confidenceLevel") ?? 0.95),
            forecastSteps: Number(data.get("forecastSteps") ?? 0),
          } : {}),
        },
      });
    }}>
      {!isForecast && model.kind !== "ols" && <label><span>{isVar ? "Ordered endogenous indicators" : "Indicators"}</span><input defaultValue={(model.variables ?? []).join(", ")} disabled={disabled} name="variables" placeholder={model.kind === "descriptive" ? "Blank = all indicators" : "CPI, POLICY_RATE"} /></label>}
      {model.kind === "ols" && <>
        <label><span>Dependent</span><input defaultValue={model.dependentVariables.join(", ")} disabled={disabled} name="dependent" placeholder="INFLATION" /></label>
        <label><span>Independent</span><input defaultValue={model.independentVariables.join(", ")} disabled={disabled} name="independent" placeholder="POLICY_RATE, OUTPUT_GAP" /></label>
        <div className="model-parameter-row">
          <label><span>Covariance</span><select defaultValue={model.parameters?.covariance ?? "nonrobust"} disabled={disabled} name="covariance"><option value="nonrobust">Nonrobust</option><option value="HC1">HC1</option><option value="HAC">HAC</option></select></label>
          <label><span>Max lags</span><input defaultValue={model.parameters?.maxLags ?? 1} disabled={disabled} min="1" name="maxLags" type="number" /></label>
          <label className="model-checkbox"><input defaultChecked={model.parameters?.addConstant ?? true} disabled={disabled} name="constant" type="checkbox" /><span>Constant</span></label>
        </div>
      </>}
      {model.kind === "adf" && <div className="model-parameter-row">
        <label><span>Deterministic terms</span><select defaultValue={model.parameters?.regression ?? "c"} disabled={disabled} name="regression"><option value="c">Constant</option><option value="ct">Constant + trend</option><option value="ctt">Constant + quadratic trend</option><option value="n">None</option></select></label>
        <label><span>Lag selection</span><select defaultValue={model.parameters?.autolag ?? "AIC"} disabled={disabled} name="autolag"><option value="AIC">AIC</option><option value="BIC">BIC</option><option value="t-stat">t-stat</option><option value="none">Fixed</option></select></label>
        <label><span>Max lags</span><input defaultValue={model.parameters?.maxLags ?? 1} disabled={disabled} min="0" name="maxLags" type="number" /></label>
      </div>}
      {isForecast && <>
        <label><span>Forecast target</span><input defaultValue={model.dependentVariables.join(", ")} disabled={disabled} name="dependent" placeholder="INFLATION" /></label>
        {model.kind === "sarimax" && <label><span>Future exogenous indicators</span><input defaultValue={model.independentVariables.join(", ")} disabled={disabled} name="independent" placeholder="POLICY_RATE, OUTPUT_GAP" /></label>}
        <div className="model-parameter-row" aria-label="ARIMA order">
          <label><span>AR order (p)</span><input defaultValue={model.parameters.orderP ?? 1} disabled={disabled} max="5" min="0" name="orderP" type="number" /></label>
          <label><span>Difference (d)</span><input defaultValue={model.parameters.orderD ?? 0} disabled={disabled} max="2" min="0" name="orderD" type="number" /></label>
          <label><span>MA order (q)</span><input defaultValue={model.parameters.orderQ ?? 0} disabled={disabled} max="5" min="0" name="orderQ" type="number" /></label>
        </div>
        {model.kind === "sarimax" && <div className="model-parameter-row" aria-label="Seasonal order">
          <label><span>Seasonal AR (P)</span><input defaultValue={model.parameters.seasonalP ?? 0} disabled={disabled} max="5" min="0" name="seasonalP" type="number" /></label>
          <label><span>Seasonal difference (D)</span><input defaultValue={model.parameters.seasonalD ?? 0} disabled={disabled} max="2" min="0" name="seasonalD" type="number" /></label>
          <label><span>Seasonal MA (Q)</span><input defaultValue={model.parameters.seasonalQ ?? 0} disabled={disabled} max="5" min="0" name="seasonalQ" type="number" /></label>
          <label><span>Season length (s)</span><input defaultValue={model.parameters.seasonalPeriod ?? 0} disabled={disabled} max="24" min="0" name="seasonalPeriod" type="number" /></label>
        </div>}
        <div className="model-parameter-row">
          <label><span>Trend</span><select defaultValue={model.parameters.trend ?? "c"} disabled={disabled} name="trend"><option value="n">None</option><option value="c">Constant</option><option value="t">Linear trend</option><option value="ct">Constant + trend</option></select></label>
          <label><span>Forecast periods</span><input defaultValue={model.parameters.forecastSteps ?? 4} disabled={disabled} max="60" min="1" name="forecastSteps" type="number" /></label>
          <label><span>Confidence level</span><input defaultValue={model.parameters.confidenceLevel ?? 0.95} disabled={disabled} max="0.99" min="0.5" name="confidenceLevel" step="0.01" type="number" /></label>
        </div>
        <div className="model-parameter-row">
          <label className="model-checkbox"><input defaultChecked={model.parameters.enforceStationarity ?? true} disabled={disabled} name="enforceStationarity" type="checkbox" /><span>Enforce stationarity</span></label>
          <label className="model-checkbox"><input defaultChecked={model.parameters.enforceInvertibility ?? true} disabled={disabled} name="enforceInvertibility" type="checkbox" /><span>Enforce invertibility</span></label>
        </div>
        {model.kind === "sarimax" && <p className="model-parameter-note">Future exogenous values must already exist in the approved snapshot for every forecast period.</p>}
      </>}
      {isVar && <>
        <div className="model-parameter-row">
          <label><span>Lag selection</span><select defaultValue={model.parameters.lagSelection ?? "fixed"} disabled={disabled} name="lagSelection"><option value="fixed">Fixed</option><option value="aic">AIC</option><option value="bic">BIC</option><option value="hqic">HQIC</option><option value="fpe">FPE</option></select></label>
          <label><span>Maximum lags</span><input defaultValue={model.parameters.maxLags ?? 1} disabled={disabled} max="12" min="1" name="maxLags" type="number" /></label>
          <label><span>Forecast periods</span><input defaultValue={model.parameters.forecastSteps ?? 0} disabled={disabled} max="60" min="0" name="forecastSteps" type="number" /></label>
          <label><span>Trend</span><select defaultValue={model.parameters.trend ?? "c"} disabled={disabled} name="trend"><option value="n">None</option><option value="c">Constant</option><option value="ct">Constant + trend</option><option value="ctt">Constant + linear + quadratic trend</option></select></label>
        </div>
        <label className="model-checkbox"><input checked={includeIrf} disabled={disabled} name="includeIrf" onChange={(event) => setIncludeIrf(event.target.checked)} type="checkbox" /><span>Generate impulse responses</span></label>
        {includeIrf && <div className="model-irf-options">
          <label><span>Impulse indicators</span><input defaultValue={(model.parameters.impulseVariables ?? []).join(", ")} disabled={disabled} name="impulseVariables" placeholder="Blank = all selected indicators" /></label>
          <div className="model-parameter-row">
            <label><span>IRF periods</span><input defaultValue={model.parameters.irfPeriods ?? 12} disabled={disabled} max="40" min="1" name="irfPeriods" type="number" /></label>
            <label><span>Confidence level</span><input defaultValue={model.parameters.confidenceLevel ?? 0.95} disabled={disabled} max="0.99" min="0.5" name="confidenceLevel" step="0.01" type="number" /></label>
            <label className="model-checkbox"><input defaultChecked={model.parameters.orthogonalized ?? true} disabled={disabled} name="orthogonalized" type="checkbox" /><span>Orthogonalized shocks</span></label>
          </div>
          <p className="model-parameter-note">Indicator order determines recursive orthogonalized shock ordering. Review it before Run.</p>
        </div>}
      </>}
      <button className="secondary-button" disabled={disabled} type="submit">Save specification</button>
    </form>
  );
}

export function ModelJobList({ session, onAdd, onDelete, onInputChange, onSpecificationChange, disabled }: { session: WorkflowSession; disabled: boolean; onAdd(model: ExecutableModelKind): void; onDelete(modelId: string): void; onInputChange(modelId: string, inputRef: string): void; onSpecificationChange(modelId: string, specification: Pick<ModelJob, "variables" | "dependentVariables" | "independentVariables" | "parameters">): void }) {
  const [selected, setSelected] = useState<ExecutableModelKind>("descriptive");
  return (
    <section className="pipeline-card model-job-card">
      <SectionHeading eyebrow="MODEL JOBS" meta={<span>{session.pipeline.models.length}</span>} title="Registered analysis" />
      {session.pipeline.lastBindingNotice && (
        <p className="pipeline-binding-notice" role="status">{session.pipeline.lastBindingNotice}</p>
      )}
      <div className="model-job-list">{session.pipeline.models.map((model) => <article key={model.id}>
        <div><strong>{model.label}</strong><label><small>Input</small><select aria-label={`${model.label} input`} disabled={disabled} onChange={(event) => onInputChange(model.id, event.target.value)} value={model.inputRef}>{model.inputRef !== "active_dataset" && !session.pipeline.operations.some((operation) => operation.outputRef === model.inputRef) && <option disabled value={model.inputRef}>Unavailable output — choose input</option>}<option value="active_dataset">Active dataset</option>{session.pipeline.operations.map((operation) => <option key={operation.outputRef} value={operation.outputRef}>{operation.label} output</option>)}</select></label></div>
        <div><span>{model.status.replace("_", " ")}</span><button aria-label={`Delete ${model.label}`} disabled={disabled} onClick={() => onDelete(model.id)} type="button"><WorkbenchIcon name="trash" /></button></div>
        <SpecificationEditor disabled={disabled} model={model} onSave={(specification) => onSpecificationChange(model.id, specification)} />
      </article>)}</div>
      <div className="add-model-row"><select aria-label="Model kind" disabled={disabled} onChange={(event) => setSelected(event.target.value as ExecutableModelKind)} value={selected}>{models.map((model) => <option key={model} value={model}>{model.toUpperCase()}</option>)}</select><button className="secondary-button" disabled={disabled} onClick={() => onAdd(selected)} type="button">Add model job</button></div>
    </section>
  );
}
