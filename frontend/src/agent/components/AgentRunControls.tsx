import { useState } from "react";
import type { AgentSession } from "../domain/types";
import { useAgent } from "../state/AgentContextCore";
import { agentAdminPath, agentRunPath } from "../services/httpAgentService";
import { AgentDiagnosticsPanel, type AgentDiagnostics } from "./AgentDiagnosticsPanel";
import { AgentRecoveryNotice } from "./AgentRecoveryNotice";

export function AgentRunControls({ session }: { session: AgentSession }) {
  const { execute, pending, error } = useAgent();
  const [answer, setAnswer] = useState("");
  const [allowScopeChange, setAllowScopeChange] = useState(false);
  const [acceptWarnings, setAcceptWarnings] = useState(false);
  const [diagnostics, setDiagnostics] = useState<AgentDiagnostics | null>(null);
  const [diagnosticError, setDiagnosticError] = useState("");
  const [diagnosticPending, setDiagnosticPending] = useState(false);
  const run = session.remote;
  if (!run) return null;
  const busy = Boolean(pending[session.id]);
  const candidate = run.output.candidate;
  const recovery = run.recovery;
  const attemptsExhausted = run.error?.code === "task_attempt_limit";
  const deliveryStop = ["no_progress", "delivery_round_limit"].includes(run.error?.code ?? "") ||
    (run.error?.code === "budget_exhausted" && run.error.message.includes("Output candidate limit"));
  const deliveryRoundsExhausted = deliveryStop &&
    ((run.ledger.used.output_candidates ?? 0) >= run.ledger.limits.output_candidates ||
      (run.ledger.used.formal_reviews ?? 0) >= run.ledger.limits.formal_reviews);
  const inspect = async () => {
    setDiagnosticPending(true); setDiagnosticError("");
    try {
      const response = await fetch(`${agentAdminPath(run)}/diagnostics`);
      if (!response.ok) throw new Error("Diagnostics could not be loaded.");
      setDiagnostics(await response.json());
    } catch (reason) { setDiagnosticError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setDiagnosticPending(false); }
  };
  return <section aria-label="Agent run controls" className="agent-run-controls">
    {run.active_role && <p>Stage role: {run.active_role.label} · {run.active_role.provider} · {run.active_role.model}</p>}
    <div className="agent-control-buttons">
      {["queued", "running"].includes(run.status) && <button className="secondary-button" disabled={busy}
        onClick={() => void execute(session.id, "pause")} type="button">Pause</button>}
      {!recovery && !attemptsExhausted && !deliveryRoundsExhausted && ["paused", "failed"].includes(run.status) && <button className="primary-button" disabled={busy}
        onClick={() => void execute(session.id, "resume")} type="button">Resume</button>}
      {!["completed", "cancelled"].includes(run.status) && <button className="secondary-button" disabled={busy}
        onClick={() => void execute(session.id, "cancel")} type="button">Cancel run</button>}
      <button className="secondary-button" disabled={diagnosticPending} onClick={() => void inspect()} type="button">
        {diagnosticPending ? "Loading diagnostics…" : "Inspect run"}</button>
      <a className="secondary-button" href={`${agentAdminPath(run)}/debug-bundle`}>Download diagnostic bundle</a>
      {recovery?.action !== "repair_evidence" && candidate?.review && ["waiting_for_user", "budget_exhausted", "paused", "awaiting_final_confirmation"].includes(run.status) && (run.ledger.used.formal_reviews ?? 0) < run.ledger.limits.formal_reviews &&
        <button className="secondary-button" disabled={busy} onClick={() => void execute(session.id, "retry_review", { artifact_set_hash: candidate.artifact_set_hash })} type="button">Retry current review</button>}
    </div>
    <div aria-label="Run budget" className="agent-budget-grid">
      {[["model_calls", "AI calls"], ["model_fits", "Model fits"], ["routes", "Research routes"],
        ["analysis_candidates", "Analysis variants"], ["output_candidates", "Output versions"], ["formal_reviews", "Review rounds"]].map(([key, label]) =>
        <span key={key}><strong>{label}</strong> {run.ledger.used[key] ?? 0}/{run.ledger.limits[key]}</span>)}
      <span><strong>Active time</strong> {Math.round((run.ledger.used.active_seconds ?? 0) / 60)}/{Math.round(run.ledger.limits.active_seconds / 60)} min</span>
    </div>
    {error && <p role="alert">{error}</p>}
    {recovery && <AgentRecoveryNotice key={`${run.run_id}:${recovery.code}`} sessionId={session.id} recovery={recovery} busy={busy} />}
    {attemptsExhausted && <p role="status">This task has exhausted its three calls. Results and diagnostics are preserved; retrying cannot reset the limit.
      {run.status === "waiting_for_user" ? " Cancel this run, then start a linked new run below." : " Start a linked new run below."}</p>}
    {deliveryRoundsExhausted && run.status !== "budget_exhausted" && <p role="status">Delivery rounds are exhausted. Cancel this run, then start a linked new run below. Results and diagnostics are preserved.</p>}
    {(run.status === "budget_exhausted" || recovery?.action === "extend_budget") && <div role="status">
      <p>The budget limit was reached. Existing results and logs are preserved.</p>
      {deliveryRoundsExhausted || recovery?.action === "start_linked_run" ? <p>Delivery rounds are exhausted. Adding execution budget cannot add an output version or review round. Start a linked new run below.</p> :
      <button className="secondary-button" disabled={busy} onClick={() => void execute(session.id, "extend_budget", {
        limits: { model_calls: run.ledger.limits.model_calls + 20, tokens: run.ledger.limits.tokens + 500000,
          model_fits: run.ledger.limits.model_fits + 8, active_seconds: run.ledger.limits.active_seconds + 900,
          nodes: run.ledger.limits.nodes + 20, connector_requests: run.ledger.limits.connector_requests + 100 },
      })} type="button">Add execution budget</button>}
    </div>}
    {(!recovery || recovery.action === "provide_input") && !attemptsExhausted && !deliveryRoundsExhausted && run.intervention && run.status === "waiting_for_user" && <form onSubmit={event => {
      event.preventDefault(); void execute(session.id, "resolve_intervention", { answer, allow_scope_change: allowScopeChange });
    }}>
      <h3>Your input is needed</h3><p>{run.intervention.message}</p>
      <label>Response<textarea value={answer} onChange={event => setAnswer(event.target.value)} rows={3} /></label>
      <label><input type="checkbox" checked={allowScopeChange} onChange={event => setAllowScopeChange(event.target.checked)} />Authorize a research scope change</label>
      <button className="primary-button" disabled={busy || !answer.trim()} type="submit">{busy ? "Submitting…" : "Continue with this response"}</button>
    </form>}
    {candidate && <details open><summary>Delivery and review · version {candidate.candidate}</summary>
      {candidate.self_checks.map(check => <p key={check.round}>Author self-check {check.round}/2: {check.status}
        {check.issues.length > 0 && ` · ${check.issues.join("; ")}`}</p>)}
      {candidate.review && <><p>Review AI: {candidate.review.provider_profile} · {candidate.review.status}</p>
        <p>Report review: {candidate.review.semantic_report_status}</p>
        {candidate.review.findings.map((finding, index) => <p key={index}>{finding.rule_id}: {finding.message}</p>)}</>}
      <p>{run.output.history?.length ?? 0} previous output version(s) retained in diagnostics.</p>
      {(run.output.history ?? []).map((previous, index) => {
        const version = previous as NonNullable<typeof candidate>;
        return <details key={index}><summary>Previous delivery · version {version.candidate}</summary>
          <p>Review: {version.review?.status ?? "Not formally reviewed"}</p>
          {version.artifacts.map(artifact => <p key={artifact.id}><a href={`${agentRunPath(run)}/artifacts/${artifact.id}`}>{artifact.name}</a> · {artifact.hash}</p>)}
          {version.review?.findings.map((finding, offset) => <p key={offset}>{finding.rule_id}: {finding.message}</p>)}
        </details>;
      })}
    </details>}
    {run.status === "awaiting_final_confirmation" && <div>
      <label><input type="checkbox" checked={acceptWarnings} onChange={event => setAcceptWarnings(event.target.checked)} />Acknowledge the interim publication standard, if applicable</label>
      <button className="primary-button" disabled={busy} onClick={() => void execute(session.id, "finalize", { accept_warnings: acceptWarnings })} type="button">Confirm final delivery</button>
    </div>}
    {run.output.manifest && <a href={`${agentRunPath(run)}/artifacts/${run.output.manifest.id}`} download="reproduction-manifest.json">Download frozen reproduction manifest</a>}
    {diagnosticError && <p role="alert">{diagnosticError}</p>}
    {diagnostics !== null && <AgentDiagnosticsPanel data={diagnostics} basePath={agentAdminPath(run)} />}
  </section>;
}
