"""Read-only recovery advice derived from the actual ledger and failed task."""

from typing import Any

from macro_research_agent.agent.contracts import AgentRunV1

PROVIDER_ACTION_CODES = {
    "provider_payment_required",
    "provider_authentication_failed",
    "provider_credentials_missing",
    "provider_request_rejected",
}
EVIDENCE_STOP_CODES = {"requires_upstream_stage", "presentation_handoff_incomplete"}
RETRY_CODES = PROVIDER_ACTION_CODES | {
    "provider_unavailable",
    "provider_timeout",
    "provider_rate_limited",
    "provider_server_error",
    "provider_connection_failed",
    "invalid_model_contract",
    "invalid_report_contract",
}


def recovery_advice(run: AgentRunV1) -> dict[str, Any] | None:
    if not run.error or run.status in {"completed", "cancelled"}:
        return None
    code = str(run.error.get("code", "execution_error"))
    node = next(
        (
            n
            for n in reversed(run.nodes)
            if n.kind.split(":")[0] == run.phase and n.status != "stale"
        ),
        None,
    )
    used_calls = max(node.physical_calls.values(), default=0) if node else None
    used_attempts = len(node.attempt_ids) if node else None

    def remaining(key: str) -> float:
        return float(
            max(
                0,
                run.ledger.limits.model_dump()[key]
                - run.ledger.used.get(key, 0)
                - sum(r.get(key, 0) for r in run.ledger.reservations.values()),
            )
        )

    phase_key = {"clarification": "clarification_batches", "route": "routes"}.get(run.phase)
    limits = {
        "task_calls": max(0, 3 - used_calls) if used_calls is not None else None,
        "task_attempts": max(0, 3 - used_attempts) if used_attempts is not None else None,
        "model_calls": remaining("model_calls"),
        "tokens": remaining("tokens"),
        "active_seconds": remaining("active_seconds"),
        "phase_attempts": remaining(phase_key) if phase_key else None,
        "output_candidates": remaining("output_candidates"),
        "formal_reviews": remaining("formal_reviews"),
    }
    exhausted = (
        code in {"task_attempt_limit", "delivery_round_limit"}
        or (
            code in RETRY_CODES
            and any(limits[k] == 0 for k in ("task_calls", "task_attempts", "phase_attempts"))
        )
        or (
            code == "no_progress"
            and any(limits[k] == 0 for k in ("output_candidates", "formal_reviews"))
        )
        or (
            code == "budget_exhausted"
            and any(
                key in str(run.error.get("message", "")) and remaining(key) == 0
                for key in (
                    "clarification_batches",
                    "routes",
                    "analysis_candidates",
                    "output_candidates",
                    "formal_reviews",
                )
            )
        )
        or (
            code in RETRY_CODES
            and (
                (
                    run.phase in {"report", "report_revision", "chart", "output_revision"}
                    and limits["output_candidates"] == 0
                )
                or (run.phase == "review" and limits["formal_reviews"] == 0)
            )
        )
    )
    action = "provide_input"
    if code in EVIDENCE_STOP_CODES:
        action = "repair_evidence"
    elif exhausted:
        action = "start_linked_run"
    elif code in RETRY_CODES:
        action = (
            "extend_budget"
            if any(limits[k] == 0 for k in ("model_calls", "tokens", "active_seconds"))
            else "retry_failed_task"
        )
    elif run.status == "budget_exhausted":
        action = (
            "start_linked_run"
            if "Output candidate limit" in str(run.error.get("message", ""))
            else "extend_budget"
        )
    return {
        "code": code,
        "message": run.error.get("message", ""),
        "action": action,
        "can_retry": action == "retry_failed_task",
        "requires_provider_confirmation": code in PROVIDER_ACTION_CODES,
        "failed_step": node.kind if node else run.phase,
        "remaining": limits,
        "preserves_history": True,
    }
