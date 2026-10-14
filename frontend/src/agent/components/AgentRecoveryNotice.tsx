import { useState } from "react";
import type { BackendAgentRun } from "../domain/types";
import { useAgent } from "../state/AgentContextCore";

export function AgentRecoveryNotice({ sessionId, recovery, busy }: {
  sessionId: string; recovery: NonNullable<BackendAgentRun["recovery"]>; busy: boolean;
}) {
  const { execute } = useAgent();
  const [ready, setReady] = useState(false);
  const remaining = recovery.remaining;
  const title = ({ provider_payment_required: "API credit/payment needs attention",
    provider_authentication_failed: "API credentials or access rejected",
    provider_credentials_missing: "API key is not configured",
    provider_rate_limited: "Provider rate limit reached", provider_timeout: "AI call timed out",
    provider_server_error: "Provider service unavailable", invalid_model_contract: "AI output contract failed",
    invalid_report_contract: "Report output contract failed",
    presentation_handoff_incomplete: "Chart/table evidence handoff is incomplete",
    requires_upstream_stage: "Upstream evidence is required" } as Record<string, string>)[recovery.code] ?? "Run recovery";
  return <section aria-label="Failure recovery" role="alert">
    <h3>{title}</h3><p>{recovery.message}</p>
    <p>Failed step: {recovery.failed_step}. History, data and consumed budgets are preserved.</p>
    <p>Remaining: {remaining.task_calls ?? "unknown"} AI call(s) for this task,
      {" "}{remaining.task_attempts ?? "unknown"} task attempt(s), {remaining.model_calls} run AI call(s).
      {remaining.phase_attempts !== null && ` ${remaining.phase_attempts} phase attempt(s).`}</p>
    <p>Remaining delivery limits: {remaining.output_candidates} Output version(s),
      {" "}{remaining.formal_reviews} formal review round(s). Run budget: {remaining.tokens} tokens,
      {" "}{Math.floor(remaining.active_seconds / 60)} active minute(s), after reserved usage.</p>
    {recovery.action === "start_linked_run" && <p>This run has reached a hard limit. Cancel it if still waiting, then start a linked research run below. Adding execution budget cannot reset that limit.</p>}
    {recovery.action === "extend_budget" && <p>Run budget is exhausted. Increase permitted execution budget explicitly; this cannot increase hard task or review limits.</p>}
    {recovery.action === "provide_input" && <p>Provide the requested research decision below; retrying alone cannot resolve it.</p>}
    {recovery.action === "repair_evidence" && <p>Required upstream or chart/table evidence is missing. Inspect run for the exact finding. Repair the inputs or evidence handoff before starting a linked run; rewriting the report or retrying the same step cannot supply that evidence. Existing results and budgets are preserved.</p>}
    {recovery.can_retry && <div>
      {recovery.requires_provider_confirmation && <label><input type="checkbox" checked={ready}
        onChange={event => setReady(event.target.checked)} />I have restored API credit, credentials or configuration</label>}
      {recovery.code === "provider_rate_limited" && <p>Wait for the provider's rate-limit window before retrying.</p>}
      <button type="button" className="primary-button" disabled={busy || (recovery.requires_provider_confirmation && !ready)}
        onClick={() => void execute(sessionId, "retry_failed_task", { confirm_provider_ready: ready })}>
        {busy ? "Retrying…" : "Retry failed step"}</button>
    </div>}
  </section>;
}
