import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentContext, type AgentContextValue } from "../state/AgentContextCore";
import type { BackendAgentRun, AgentSession } from "../domain/types";
import { AgentRecoveryNotice } from "./AgentRecoveryNotice";
import { AgentRunControls } from "./AgentRunControls";

const base: NonNullable<BackendAgentRun["recovery"]> = { code: "provider_payment_required",
  message: "Restore credit before retrying.", action: "retry_failed_task", can_retry: true,
  requires_provider_confirmation: true, failed_step: "analysis_assessment",
  remaining: { task_calls: 1, task_attempts: 2, phase_attempts: null, model_calls: 32,
    tokens: 900000, active_seconds: 2700, output_candidates: 3, formal_reviews: 3 } };
const provider = (execute = vi.fn()) => ({ execute, pending: {}, error: "" } as unknown as AgentContextValue);

describe("Explicit Agent failure recovery", () => {
  it.each(["presentation_handoff_incomplete", "requires_upstream_stage"])("does not offer retries or scope rewriting for %s", code => {
    const session = { id: "s", remote: { session_id: "s", run_id: "r", status: "waiting_for_user",
      output: { candidate: { self_checks: [], artifacts: [], review: { provider_profile: "codex-local",
        status: "fail", semantic_report_status: "requires_upstream_stage", findings: [] } } },
      recovery: { ...base, code, action: "repair_evidence", can_retry: false },
      error: { code, message: "Evidence missing" }, intervention: { message: "Evidence missing" },
      ledger: { used: {}, limits: { formal_reviews: 3, active_seconds: 2700 } },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={provider()}><AgentRunControls session={session} /></AgentContext.Provider>);
    expect(screen.getByText(/Repair the inputs or evidence handoff/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry failed step" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry current review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue with this response" })).not.toBeInTheDocument();
  });
  it("requires confirmation for payment/access errors and shows actual remaining calls", () => {
    const execute = vi.fn();
    render(<AgentContext.Provider value={provider(execute)}><AgentRecoveryNotice sessionId="s" recovery={base} busy={false} /></AgentContext.Provider>);
    expect(screen.getByText("API credit/payment needs attention")).toBeInTheDocument();
    expect(screen.getByText(/1 AI call\(s\) for this task/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry failed step" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Retry failed step" }));
    expect(execute).toHaveBeenCalledWith("s", "retry_failed_task", { confirm_provider_ready: true });
  });
  it.each(["provider_timeout", "provider_rate_limited", "invalid_model_contract"])("offers bounded retry for %s, not a scope-change form", code => {
    const recovery = { ...base, code, requires_provider_confirmation: false };
    const session = { id: "s", remote: { session_id: "s", run_id: "r", status: "waiting_for_user",
      output: {}, recovery, error: { code, message: "Safe" },
      intervention: { message: "Safe", reason: code, options: [] },
      ledger: { used: {}, limits: { formal_reviews: 3, active_seconds: 2700 } },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={provider()}><AgentRunControls session={session} /></AgentContext.Provider>);
    expect(screen.getByRole("button", { name: "Retry failed step" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Continue with this response" })).not.toBeInTheDocument();
    expect(screen.queryByText("Authorize a research scope change")).not.toBeInTheDocument();
  });
  it("does not show retry for exhausted clarification/task limits", () => {
    render(<AgentContext.Provider value={provider()}><AgentRecoveryNotice sessionId="s"
      recovery={{ ...base, action: "start_linked_run", can_retry: false,
        remaining: { ...base.remaining, phase_attempts: 0 } }} busy={false} /></AgentContext.Provider>);
    expect(screen.queryByRole("button", { name: "Retry failed step" })).not.toBeInTheDocument();
    expect(screen.getByText(/reached a hard limit/)).toBeInTheDocument();
  });
  it("offers explicit execution-budget enlargement while a failed task is waiting", () => {
    const execute = vi.fn();
    const session = { id: "s", remote: { session_id: "s", run_id: "r", status: "waiting_for_user",
      output: {}, recovery: { ...base, action: "extend_budget", can_retry: false },
      ledger: { used: {}, limits: { formal_reviews: 3, active_seconds: 2700, model_calls: 40,
        tokens: 1000000, model_fits: 16, nodes: 80, connector_requests: 300 } },
    } } as unknown as AgentSession;
    render(<AgentContext.Provider value={provider(execute)}><AgentRunControls session={session} /></AgentContext.Provider>);
    fireEvent.click(screen.getByRole("button", { name: "Add execution budget" }));
    expect(execute).toHaveBeenCalledWith("s", "extend_budget", { limits: {
      model_calls: 60, tokens: 1500000, model_fits: 24, active_seconds: 3600,
      nodes: 100, connector_requests: 400,
    } });
    expect(screen.queryByRole("button", { name: "Retry failed step" })).not.toBeInTheDocument();
  });
});
