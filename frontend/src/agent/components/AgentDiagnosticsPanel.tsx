import { useMemo, useState } from "react";

export interface AgentDiagnostics {
  events: Array<{ sequence: number; occurred_at: string; event_type: string; task_id: string | null;
    attempt_id: string | null; level: string; payload: Record<string, unknown> }>;
  attempts: Array<{ attempt_id: string; task: string; status: string; input_refs: string[];
    output_refs?: string[]; error?: unknown }>;
  payloads: Array<{ id: string; kind: string; hash: string }>;
  integrity_issues: unknown[];
  metrics: Record<string, unknown>;
}

export function AgentDiagnosticsPanel({ data, basePath }: { data: AgentDiagnostics; basePath: string }) {
  const [filter, setFilter] = useState("");
  const [attempt, setAttempt] = useState("");
  const [compare, setCompare] = useState("");
  const [evidence, setEvidence] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const filtered = useMemo(() => data.events.filter(event => (!attempt || event.attempt_id === attempt) &&
    `${event.event_type} ${event.task_id} ${JSON.stringify(event.payload)}`.toLowerCase().includes(filter.toLowerCase())), [data, filter, attempt]);
  const selectedAttempts = data.attempts.filter(item => item.attempt_id === attempt || item.attempt_id === compare);
  const inspect = async (id: string) => {
    setLoading(true); setError("");
    try {
      const response = await fetch(`${basePath}/payloads/${id}`);
      if (!response.ok) throw new Error("The diagnostic evidence could not be read.");
      setEvidence(await response.text());
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };
  return <details open className="agent-diagnostics"><summary>Diagnostic timeline and evidence</summary>
    {data.integrity_issues.length > 0 && <p role="alert">Evidence integrity problems: {JSON.stringify(data.integrity_issues)}</p>}
    <label>Filter by role, task, event or error<input value={filter} onChange={event => setFilter(event.target.value)} /></label>
    <label>Attempt<select value={attempt} onChange={event => setAttempt(event.target.value)}><option value="">All attempts</option>
      {data.attempts.map(item => <option key={item.attempt_id} value={item.attempt_id}>{item.task} · {item.status} · {item.attempt_id.slice(-6)}</option>)}
    </select></label>
    <label>Compare with<select value={compare} onChange={event => setCompare(event.target.value)}><option value="">No comparison</option>
      {data.attempts.map(item => <option key={item.attempt_id} value={item.attempt_id}>{item.task} · {item.attempt_id.slice(-6)}</option>)}
    </select></label>
    {selectedAttempts.length > 0 && <div aria-label="Attempt comparison" className="agent-attempt-comparison">
      {selectedAttempts.map(item => <section key={item.attempt_id}><h4>{item.task} · {item.status}</h4>
        <p>Inputs: {item.input_refs.join(", ")}</p><p>Outputs: {(item.output_refs ?? []).join(", ") || "No accepted output"}</p>
        {Boolean(item.error) && <pre>{JSON.stringify(item.error, null, 2)}</pre>}
      </section>)}
    </div>}
    <p>{filtered.length} matching events. UTC timestamps; complete evidence is available below.</p>
    <ol>{filtered.map(event => <li key={event.sequence}><details><summary>{event.occurred_at} · {event.event_type} · {event.task_id ?? "run"}</summary>
      <pre>{JSON.stringify(event.payload, null, 2)}</pre>
      {Object.values(event.payload).filter((value): value is string => typeof value === "string" && value.startsWith("agent-blob-")).map(id =>
        <button className="secondary-button" type="button" disabled={loading} key={id} onClick={() => void inspect(id)}>Read full evidence {id.slice(-6)}</button>)}
    </details></li>)}</ol>
    {error && <p role="alert">{error}</p>}
    {evidence && <details open><summary>Complete diagnostic payload</summary><pre>{evidence}</pre></details>}
    <details><summary>Metrics and payload index</summary><pre>{JSON.stringify({ metrics: data.metrics, payloads: data.payloads }, null, 2)}</pre></details>
    <a href={`${basePath}/replay?verify_numerics=true`} target="_blank" rel="noreferrer">Offline replay and numerical verification (no external calls)</a>
  </details>;
}
