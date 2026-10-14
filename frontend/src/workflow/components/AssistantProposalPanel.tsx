import { useEffect, useState } from "react";

import type { AgentRuntimeDescriptor } from "../domain/types";

export interface AssistantProposalItem {
  id: string;
  label: string;
  rationale: string;
  detail: string;
}

export function AssistantProposalPanel({
  title,
  summary,
  target,
  items,
  diagnostics = [],
  agent,
  disabled,
  onApply,
  onReject,
}: {
  title: string;
  summary: string;
  target: string;
  items: AssistantProposalItem[];
  diagnostics?: Array<{ summary: string; details: string[] }>;
  agent?: AgentRuntimeDescriptor;
  disabled: boolean;
  onApply(ids: string[]): void;
  onReject(): void;
}) {
  const [selected, setSelected] = useState(items.map((item) => item.id));

  useEffect(() => {
    setSelected(items.map((item) => item.id));
  }, [items]);

  return (
    <section className="assistant-proposal-card" aria-label={title}>
      <div className="patch-heading"><span>AI PROPOSAL</span><strong>{title}</strong></div>
      {agent && (
        <p className="assistant-runtime">
          <strong>{agent.role.replaceAll("_", " ")}</strong>
          <span>{agent.providerProfile} · {agent.modelId || "configured default"}</span>
          <small>{agent.authority} only · cannot execute or approve</small>
        </p>
      )}
      <p>{summary}</p>
      {diagnostics.length > 0 && (
        <section className="assistant-diagnostic-list" aria-label="Read-only diagnostics">
          <strong>Read-only diagnostics</strong>
          {diagnostics.map((diagnostic, index) => (
            <div key={`${diagnostic.summary}-${index}`}>
              <p>{diagnostic.summary}</p>
              {diagnostic.details.length > 0 && (
                <ul>{diagnostic.details.map((detail) => <li key={detail}>{detail}</li>)}</ul>
              )}
            </div>
          ))}
        </section>
      )}
      <fieldset className="assistant-proposal-items">
        <legend>Select the proposed steps to apply</legend>
        {items.map((item) => (
          <label key={item.id}>
            <input
              checked={selected.includes(item.id)}
              onChange={() => setSelected(
                selected.includes(item.id)
                  ? selected.filter((id) => id !== item.id)
                  : [...selected, item.id],
              )}
              type="checkbox"
            />
            <span><strong>{item.label}</strong><small>{item.rationale}</small><code>{item.detail}</code></span>
          </label>
        ))}
      </fieldset>
      <small>Bound to {target}</small>
      <div className="button-row">
        <button className="primary-button" disabled={disabled || selected.length === 0} onClick={() => onApply(selected)} type="button">Apply selected steps</button>
        <button className="secondary-button" disabled={disabled} onClick={onReject} type="button">Reject proposal</button>
      </div>
    </section>
  );
}

export function AssistantRequestBox({
  label,
  placeholder,
  disabled,
  onSubmit,
}: {
  label: string;
  placeholder: string;
  disabled: boolean;
  onSubmit(request: string): void;
}) {
  const [request, setRequest] = useState("");
  return (
    <form
      className="assistant-request-box"
      onSubmit={(event) => {
        event.preventDefault();
        const value = request.trim();
        if (!value) return;
        onSubmit(value);
        setRequest("");
      }}
    >
      <label><span>{label}</span><textarea disabled={disabled} onChange={(event) => setRequest(event.target.value)} placeholder={placeholder} rows={3} value={request} /></label>
      <button className="secondary-button" disabled={disabled || !request.trim()} type="submit">Generate proposal</button>
    </form>
  );
}
