from __future__ import annotations

from enum import Enum


class AgentSessionState(str, Enum):
    REQUESTED = "requested"
    CLARIFYING = "clarifying"
    ROUTING = "routing"
    ACQUIRING = "acquiring"
    TRANSFORMING = "transforming"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentNodeKind(str, Enum):
    AGENT_REQUEST = "agent_request"
    ATTACHMENT_INSPECTION = "attachment_inspection"
    CLARIFICATION_BATCH = "clarification_batch"
    ROUTE_DECISION = "route_decision"
    DATA_ACQUISITION = "data_acquisition"
    TRANSFORMATION = "transformation"
    MODEL_EXECUTION = "model_execution"
    REPORT_GENERATION = "report_generation"
    FINAL_RESPONSE = "final_response"


class AgentNodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_AGENT_STATES = {
    AgentSessionState.COMPLETED,
    AgentSessionState.FAILED,
    AgentSessionState.CANCELLED,
}
