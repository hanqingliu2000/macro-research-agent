from __future__ import annotations

from enum import Enum
from typing import TypeAlias

from macro_research_agent.research_core.data_access import ResearchStage

WorkflowStage: TypeAlias = ResearchStage


class SessionState(str, Enum):
    CLARIFYING = "clarifying"
    PLAN_REVIEW = "plan_review"
    ACQUIRING = "acquiring"
    DATA_REVIEW = "data_review"
    PIPELINE_EDITING = "pipeline_editing"
    PIPELINE_RUNNING = "pipeline_running"
    OUTPUT_GENERATING = "output_generating"
    OUTPUT_REVIEW = "output_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalGate(str, Enum):
    RESEARCH_PLAN = "research_plan"
    PIPELINE_EXECUTION = "pipeline_execution"
    FINAL_OUTPUTS = "final_outputs"


ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CLARIFYING: {SessionState.PLAN_REVIEW, SessionState.CANCELLED},
    SessionState.PLAN_REVIEW: {
        SessionState.CLARIFYING,
        SessionState.ACQUIRING,
        SessionState.CANCELLED,
    },
    SessionState.ACQUIRING: {
        SessionState.PLAN_REVIEW,
        SessionState.DATA_REVIEW,
        SessionState.FAILED,
        SessionState.CANCELLED,
    },
    SessionState.DATA_REVIEW: {
        SessionState.PLAN_REVIEW,
        SessionState.ACQUIRING,
        SessionState.PIPELINE_EDITING,
        SessionState.CANCELLED,
    },
    SessionState.PIPELINE_EDITING: {
        SessionState.PLAN_REVIEW,
        SessionState.DATA_REVIEW,
        SessionState.PIPELINE_RUNNING,
        SessionState.CANCELLED,
    },
    SessionState.PIPELINE_RUNNING: {
        SessionState.PIPELINE_EDITING,
        SessionState.OUTPUT_GENERATING,
        SessionState.FAILED,
        SessionState.CANCELLED,
    },
    SessionState.OUTPUT_GENERATING: {
        SessionState.PIPELINE_EDITING,
        SessionState.OUTPUT_REVIEW,
        SessionState.FAILED,
        SessionState.CANCELLED,
    },
    SessionState.OUTPUT_REVIEW: {
        SessionState.PLAN_REVIEW,
        SessionState.DATA_REVIEW,
        SessionState.PIPELINE_EDITING,
        SessionState.OUTPUT_GENERATING,
        SessionState.COMPLETED,
        SessionState.CANCELLED,
    },
    # Completed sessions are immutable audit records. A future explicit
    # continue/fork command may create a new working session from one.
    SessionState.COMPLETED: set(),
    SessionState.FAILED: {
        SessionState.PLAN_REVIEW,
        SessionState.DATA_REVIEW,
        SessionState.PIPELINE_EDITING,
        SessionState.OUTPUT_GENERATING,
        SessionState.OUTPUT_REVIEW,
        SessionState.CANCELLED,
    },
    SessionState.CANCELLED: set(),
}


def ensure_transition(current: SessionState, target: SessionState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid workflow transition: {current.value} -> {target.value}")
