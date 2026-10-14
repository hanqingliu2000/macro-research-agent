import {
  DELIVERABLE_LABELS,
  type DeliverableKey,
  type PlanDraft,
} from "../../domain/types";

const deliverableKeys = Object.keys(DELIVERABLE_LABELS) as DeliverableKey[];

function friendlyCapabilityText(capabilityId: string) {
  if (capabilityId === "connector.world_bank") {
    return {
      name: "World Bank data connector",
      summary: "Fetches World Bank macroeconomic series in a reproducible format for planning and analysis.",
    };
  }
  if (capabilityId === "data.prepare") {
    return {
      name: "Data preparation",
      summary: "Cleans and prepares source tables for downstream transformation and model jobs.",
    };
  }
  if (capabilityId.startsWith("transformation")) {
    return {
      name: "Data transformation",
      summary: "Applies approved transformation steps so inputs match model requirements.",
    };
  }
  if (capabilityId.startsWith("model")) {
    return {
      name: "Modeling",
      summary: "Runs the configured model and returns analysis-ready output.",
    };
  }
  if (capabilityId.startsWith("code.generate")) {
    return {
      name: "Code generation",
      summary: "Creates reproducible scripts for the planned model and transformation steps.",
    };
  }
  if (capabilityId.startsWith("artifact")) {
    return {
      name: "Artifact building",
      summary: "Generates publish-ready output artifacts from completed outputs.",
    };
  }
  return {
    name: capabilityId
      .split(".")
      .map((value) => value.replaceAll("_", " "))
      .map((value) => `${value.charAt(0).toUpperCase()}${value.slice(1)}`)
      .join(" · "),
    summary: "Executes the configured plan capability for the selected workflow step.",
  };
}

export function CapabilityLists({
  plan,
  onChange,
}: {
  plan: PlanDraft;
  onChange(plan: PlanDraft): void;
}) {
  return (
    <>
      <section className="plan-editor-section">
        <p className="panel-kicker">DATA SOURCES</p>
        <div className="plan-option-list">
          {plan.dataSources.map((source) => (
            <label key={source.id}>
              <input
                checked={source.enabled}
                onChange={() => onChange({
                  ...plan,
                  dataSources: plan.dataSources.map((item) =>
                    item.id === source.id ? { ...item, enabled: !item.enabled } : item,
                  ),
                })}
                type="checkbox"
              />
              <span className="plan-option-label">{source.provider} · {source.dataset}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="plan-editor-section plan-two-column">
        <div>
          <p className="panel-kicker">TRANSFORMATIONS</p>
          <div className="plan-option-list">
            {plan.transformationIntents.map((intent) => (
              <label key={intent.id}>
                <input
                  checked={intent.enabled}
                  onChange={() => onChange({
                    ...plan,
                    transformationIntents: plan.transformationIntents.map((item) =>
                      item.id === intent.id ? { ...item, enabled: !item.enabled } : item,
                    ),
                  })}
                  type="checkbox"
                />
                <span className="plan-option-label">{intent.label}</span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <p className="panel-kicker">MODELS</p>
          <div className="plan-option-list">
            {plan.modelIntents.map((intent) => (
              <label key={intent.capabilityId ?? intent.id}>
                <input
                  checked={intent.enabled}
                  onChange={() => onChange({
                    ...plan,
                    modelIntents: plan.modelIntents.map((item) =>
                      (item.capabilityId ?? item.id) === (intent.capabilityId ?? intent.id)
                        ? { ...item, enabled: !item.enabled }
                        : item,
                    ),
                  })}
                  type="checkbox"
                />
                <span>
                  <span className="plan-option-label">{intent.purpose ?? intent.label}</span>
                  <small>
                    {(intent.variables ?? [])
                      .map((variable) => `${variable.order}. ${variable.indicatorCode} (${variable.role})`)
                      .join(" · ") || "Variables need confirmation"}
                    {intent.forecastHorizon
                      ? ` · ${intent.forecastHorizon.steps} periods at ${Math.round(intent.forecastHorizon.confidenceLevel * 100)}%`
                      : ""}
                  </small>
                </span>
              </label>
            ))}
          </div>
        </div>
      </section>

      <section className="plan-editor-section">
        <p className="panel-kicker">DELIVERABLES</p>
        <div className="deliverable-checks">
          {deliverableKeys.map((key) => (
            <label key={key}>
              <input
                checked={plan.deliverables[key]}
                onChange={() => onChange({
                  ...plan,
                  deliverables: { ...plan.deliverables, [key]: !plan.deliverables[key] },
                })}
                type="checkbox"
              />
              <span>{DELIVERABLE_LABELS[key]}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="plan-editor-section">
        <p className="panel-kicker">AI CAPABILITY PLAN</p>
        <div className="plan-option-list">
          {plan.capabilityInvocations.map((invocation) => (
            <div
              className="planned-capability"
              key={`${invocation.capabilityId}@${invocation.capabilityVersion}`}
            >
              <span className="plan-capability-title">
                {friendlyCapabilityText(invocation.capabilityId).name}
              </span>
              <span className="plan-capability-summary">
                {friendlyCapabilityText(invocation.capabilityId).summary}
              </span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
