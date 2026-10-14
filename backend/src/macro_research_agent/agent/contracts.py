from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from macro_research_agent.research_core.planning import (
    ClarificationBatch,
    PlanDraft,
    ResearchPeriod,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier(kind: str) -> str:
    return f"agent-{kind}-{uuid4().hex}"


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


RunStatus = Literal[
    "requested",
    "clarifying",
    "queued",
    "running",
    "waiting_for_user",
    "paused",
    "budget_exhausted",
    "awaiting_final_confirmation",
    "completed",
    "failed",
    "cancelled",
]


class AgentBudgetLimitsV1(StrictAgentModel):
    model_calls: int = Field(default=40, ge=1, le=1000)
    tokens: int = Field(default=1_000_000, ge=1, le=100_000_000)
    nodes: int = Field(default=80, ge=1, le=2000)
    model_fits: int = Field(default=16, ge=1, le=1000)
    connector_requests: int = Field(default=300, ge=1, le=10000)
    active_seconds: float = Field(default=2700, gt=0, le=86400)
    clarification_batches: int = Field(default=2, ge=1, le=2)
    routes: int = Field(default=3, ge=1, le=3)
    analysis_candidates: int = Field(default=3, ge=1, le=3)
    output_candidates: int = Field(default=3, ge=1, le=3)
    formal_reviews: int = Field(default=3, ge=1, le=3)
    concurrency: int = Field(default=2, ge=1, le=2)


class AgentBudgetLedgerV1(StrictAgentModel):
    schema_version: Literal["agent-budget-ledger-v1"] = "agent-budget-ledger-v1"
    limits: AgentBudgetLimitsV1 = Field(default_factory=AgentBudgetLimitsV1)
    used: dict[str, float] = Field(default_factory=dict)
    reservations: dict[str, dict[str, float]] = Field(default_factory=dict)
    version: int = 1


class AgentRunEnvelopeV1(StrictAgentModel):
    schema_version: Literal["agent-run-envelope-v1"] = "agent-run-envelope-v1"
    envelope_id: str = Field(default_factory=lambda: identifier("authorization"))
    version: int = 1
    request: str
    answers: dict[str, str]
    allowed_connectors: list[str]
    allowed_models: list[str]
    allowed_transforms: list[str]
    cleaning_policy: Literal["statistical-cleaning-v1"] = "statistical-cleaning-v1"
    budget_limits: AgentBudgetLimitsV1 = Field(default_factory=AgentBudgetLimitsV1)
    provider_permissions: dict[str, Any] = Field(
        default_factory=lambda: {
            "research_roles": "deepseek-development",
            "reviewer": "codex-local",
            "remote_public": True,
            "remote_user_supplied": False,
            "remote_licensed": False,
        }
    )
    plan_hash: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    authorized_by: Literal["user"] = "user"
    created_at: str = Field(default_factory=utc_now)


class AgentAnalysisTaskV1(StrictAgentModel):
    task_id: str
    model: Literal["descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"]
    variables: list[str] = Field(min_length=1, max_length=12)
    dependent_variables: list[str] = Field(default_factory=list)
    independent_variables: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    sample_window: ResearchPeriod | None = None
    purpose: str = Field(min_length=1)


class AgentTransformTaskV1(StrictAgentModel):
    task_id: str
    operation: str
    indicators: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    purpose: str = Field(min_length=1)


class AgentTaskPlanV1(StrictAgentModel):
    schema_version: Literal["agent-task-plan-v1"] = "agent-task-plan-v1"
    plan: PlanDraft
    acquisition_checks: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Read-only coverage/metadata checks AFTER registered acquisition. "
        "Human choices/access prerequisites belong in plan.unresolved_items.",
    )
    source_periods: dict[str, ResearchPeriod] = Field(default_factory=dict)
    transformations: list[AgentTransformTaskV1] = Field(default_factory=list, max_length=20)
    analyses: list[AgentAnalysisTaskV1] = Field(min_length=1, max_length=16)
    cleaning: Literal["none", "complete_cases", "interpolate", "winsorize"] = "none"
    validation_start: str | None = None
    evaluation_policy: Literal["fixed-scope-and-coverage-v1"] = "fixed-scope-and-coverage-v1"
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_tasks(self) -> AgentTaskPlanV1:
        ids = [task.task_id for task in self.transformations] + [
            task.task_id for task in self.analyses
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be unique.")
        indicators = {code for source in self.plan.data_sources for code in source.indicators}
        if self.validation_start:
            ResearchPeriod(
                start=self.validation_start,
                end=self.validation_start,
                frequency=self.plan.period.frequency,
            )
            if self.validation_start <= self.plan.period.start or (
                self.plan.period.end != "latest" and self.validation_start > self.plan.period.end
            ):
                raise ValueError(
                    "Protected validation window must be inside the research period after training."
                )
        for task in self.analyses:
            if set(task.variables) - indicators:
                raise ValueError("Analytical variables must exist in selected source indicators.")
            if task.sample_window and (
                task.sample_window.frequency != self.plan.period.frequency
                or task.sample_window.start < self.plan.period.start
                or (
                    self.plan.period.end != "latest"
                    and task.sample_window.end > self.plan.period.end
                )
            ):
                raise ValueError("Sample window must be within the research period/frequency.")
        return self


class AgentInterventionV1(StrictAgentModel):
    intervention_id: str = Field(default_factory=lambda: identifier("intervention"))
    reason: str
    message: str
    options: list[str] = Field(default_factory=list)
    details_ref: str | None = None
    created_at: str = Field(default_factory=utc_now)


class AgentTraceEventV1(StrictAgentModel):
    schema_version: Literal["agent-trace-v1"] = "agent-trace-v1"
    event_id: str = Field(default_factory=lambda: identifier("event"))
    sequence: int
    session_id: str
    run_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    task_id: str | None = None
    node_id: str | None = None
    attempt_id: str | None = None
    command_id: str | None = None
    occurred_at: str = Field(default_factory=utc_now)
    event_type: str
    actor: str
    level: Literal["info", "warning", "error"] = "info"
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentNodeV1(StrictAgentModel):
    node_id: str = Field(default_factory=lambda: identifier("node"))
    kind: str
    status: Literal["pending", "running", "completed", "failed", "stale", "cancelled"] = "pending"
    depends_on: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    produced_refs: list[str] = Field(default_factory=list)
    attempt_ids: list[str] = Field(default_factory=list)
    physical_calls: dict[str, int] = Field(default_factory=dict)
    active_attempt_id: str | None = None
    lease_until: str | None = None
    epoch: int = 1
    created_at: str = Field(default_factory=utc_now)
    completed_at: str | None = None


class AgentRunV1(StrictAgentModel):
    schema_version: Literal["agent-run-v1"] = "agent-run-v1"
    run_id: str = Field(default_factory=lambda: identifier("run"))
    session_id: str
    parent_run_id: str | None = None
    request: str
    status: RunStatus = "requested"
    phase: str = "clarification"
    version: int = 1
    epoch: int = 1
    pause_requested: bool = False
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    clarification: ClarificationBatch | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    authorizations: list[AgentRunEnvelopeV1] = Field(default_factory=list)
    task_plan: AgentTaskPlanV1 | None = None
    route_history: list[dict[str, Any]] = Field(default_factory=list)
    ledger: AgentBudgetLedgerV1 = Field(default_factory=AgentBudgetLedgerV1)
    nodes: list[AgentNodeV1] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    intervention: AgentInterventionV1 | None = None
    error: dict[str, Any] | None = None
    no_progress: int = 0
    last_failure_signature: str | None = None


class AgentCommandV1(StrictAgentModel):
    command_id: str
    idempotency_key: str
    expected_version: int = Field(ge=1)
    type: Literal[
        "answer_clarification",
        "pause",
        "resume",
        "retry_review",
        "retry_failed_task",
        "cancel",
        "resolve_intervention",
        "extend_budget",
        "finalize",
        "new_run",
        "message",
        "start",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
    actor: Literal["user"] = "user"
