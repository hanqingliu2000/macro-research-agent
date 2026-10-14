import { useMemo, useState } from "react";

import type {
  AgentRuntimeDescriptor,
  HandoffDecision,
  WorkflowSession,
} from "../domain/types";
import { useWorkflow } from "../state/WorkflowContextCore";

const ROLE_LABELS: Record<AgentRuntimeDescriptor["role"], string> = {
  planner: "Planner",
  data_steward: "Data Steward",
  analyst: "Analyst",
  report_author: "Report Author",
  report_reviewer: "Report Reviewer",
};

export function DecisionSummary({
  session,
  activeAgent,
}: {
  session: WorkflowSession;
  activeAgent?: AgentRuntimeDescriptor;
}) {
  const { execute, pending } = useWorkflow();
  const handoff = session.currentHandoff;
  const [selected, setSelected] = useState<string[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const inferred = useMemo(
    () => handoff?.decisions.filter((item) => item.status === "inferred") ?? [],
    [handoff],
  );
  const unresolved = handoff?.decisions.filter(
    (item) => item.status === "needs_confirmation",
  ) ?? [];
  const agents = activeAgent
    ? [activeAgent, ...(handoff?.agents ?? []).filter((item) => item.role !== activeAgent.role)]
    : handoff?.agents ?? [];

  if (!handoff) {
    return (
      <section className="decision-summary" aria-label="Confirmed research decisions">
        <p className="panel-kicker">CONFIRMED RESEARCH DECISIONS</p>
        <p>The first approved stage will create a versioned decision handoff.</p>
      </section>
    );
  }

  const toggle = (decision: HandoffDecision) => {
    setSelected((current) =>
      current.includes(decision.id)
        ? current.filter((id) => id !== decision.id)
        : [...current, decision.id],
    );
  };

  return (
    <section className="decision-summary" aria-label="Confirmed research decisions">
      <div className="decision-summary-heading">
        <div>
          <p className="panel-kicker">CONFIRMED RESEARCH DECISIONS</p>
          <small>Handoff from {handoff.sourceStage} · v{(session.handoffs?.length ?? 0) || 1}</small>
        </div>
        <span className="decision-status" data-status={unresolved.length ? "attention" : "ready"}>
          {unresolved.length ? `${unresolved.length} to resolve` : "Ready"}
        </span>
      </div>

      {agents.length > 0 && (
        <div className="decision-agent-list" aria-label="AI roles">
          {agents.map((agent) => (
            <div className="decision-agent" key={`${agent.role}-${agent.providerProfile}-${agent.modelId}`}>
              <strong>{ROLE_LABELS[agent.role]}</strong>
              <span>{agent.providerProfile} · {agent.modelId || "configured default"}</span>
              <small>{agent.authority} only · cannot approve or execute</small>
            </div>
          ))}
        </div>
      )}

      <details>
        <summary>Review {handoff.decisions.length} recorded decisions</summary>
        <ul className="decision-list">
          {handoff.decisions.map((decision) => (
            <li key={decision.id}>
              <span className="decision-status" data-status={decision.status}>
                {decision.status.replaceAll("_", " ")}
              </span>
              <p>{decision.summary}</p>
              {decision.status === "inferred" && (
                <label className="decision-confirm-choice">
                  <input
                    checked={selected.includes(decision.id)}
                    disabled={pending}
                    onChange={() => toggle(decision)}
                    type="checkbox"
                  />
                  Confirm this inferred decision
                </label>
              )}
              {decision.status === "needs_confirmation" && (
                <form
                  className="decision-resolution"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = resolutions[decision.id]?.trim();
                    if (value) {
                      void execute(session.id, {
                        type: "resolve_decision",
                        decisionId: decision.id,
                        value,
                      });
                    }
                  }}
                >
                  <label>
                    <span>Confirmed value</span>
                    <input
                      disabled={pending}
                      onChange={(event) => setResolutions((current) => ({
                        ...current,
                        [decision.id]: event.target.value,
                      }))}
                      value={resolutions[decision.id] ?? ""}
                    />
                  </label>
                  <button
                    className="secondary-button"
                    disabled={pending || !resolutions[decision.id]?.trim()}
                    type="submit"
                  >
                    Resolve
                  </button>
                </form>
              )}
            </li>
          ))}
        </ul>
        {inferred.length > 0 && (
          <button
            className="secondary-button decision-confirm-button"
            disabled={pending || selected.length === 0}
            onClick={() => void execute(session.id, { type: "confirm_decisions", decisionIds: selected })}
            type="button"
          >
            Confirm selected decisions
          </button>
        )}
      </details>
    </section>
  );
}
