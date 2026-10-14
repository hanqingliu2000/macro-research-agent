from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from macro_research_agent.workflow.states import ApprovalGate, WorkflowStage


class ResearchNodeKind(str, Enum):
    RESEARCH_REQUEST = "research_request"
    CLARIFICATION_BATCH = "clarification_batch"
    RESEARCH_PLAN = "research_plan"
    GEOGRAPHY_RESOLUTION = "geography_resolution"
    DATA_ACQUISITION = "data_acquisition"
    DATA_MERGE = "data_merge"
    DATA_PREPARATION = "data_preparation"
    EXTERNAL_ROUND_TRIP = "external_round_trip"
    TRANSFORMATION_PIPELINE = "transformation_pipeline"
    MODEL_EXECUTION = "model_execution"
    STAGE_HANDOFF = "stage_handoff"
    CAPABILITY_INVOCATION = "capability_invocation"
    OUTPUT_GENERATION = "output_generation"
    OUTPUT_REVISION = "output_revision"
    OUTPUT_COMPLIANCE_REVIEW = "output_compliance_review"
    VISUAL_ARTIFACT_REVIEW = "visual_artifact_review"
    SEMANTIC_REPORT_REVIEW = "semantic_report_review"
    REPRODUCTION_MANIFEST = "reproduction_manifest"


class NodeLifecycle(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_REVIEW = "waiting_for_review"
    APPROVED = "approved"
    COMPLETED = "completed"
    STALE = "stale"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GraphEdgeKind(str, Enum):
    DEPENDS_ON = "depends_on"
    CONSUMES = "consumes"
    PRODUCES = "produces"
    AUTHORIZED_BY = "authorized_by"
    REVIEWS = "reviews"
    SUPERSEDES = "supersedes"
    INVALIDATES = "invalidates"


class NodeAttemptStatus(str, Enum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


class NodeAuthority(str, Enum):
    RECORD = "record"
    PROPOSAL = "proposal"
    EXECUTION = "execution"
    REVIEW = "review"


class ResearchNode(BaseModel):
    session_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    kind: ResearchNodeKind
    lifecycle: NodeLifecycle
    authority: NodeAuthority = NodeAuthority.RECORD
    stage: WorkflowStage | None = None
    schema_version: str = "1"
    attempt: int = Field(default=1, ge=1)
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    capability_id: str | None = None
    capability_version: str | None = None
    required_checkpoint: ApprovalGate | None = None
    rationale: str | None = None
    stale_reason: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle_details(self) -> ResearchNode:
        if self.lifecycle == NodeLifecycle.STALE and not self.stale_reason:
            raise ValueError("stale nodes require a stale reason")
        if self.lifecycle == NodeLifecycle.FAILED and not self.error_code:
            raise ValueError("failed nodes require an error code")
        if self.capability_version and not self.capability_id:
            raise ValueError("capability_version requires capability_id")
        if self.authority == NodeAuthority.PROPOSAL and self.required_checkpoint is not None:
            raise ValueError("proposal nodes cannot carry execution checkpoint authority")
        return self


class GraphEdge(BaseModel):
    session_id: str = Field(min_length=1)
    edge_id: str = Field(min_length=1)
    kind: GraphEdgeKind
    source_node_id: str = Field(min_length=1)
    target_node_id: str | None = None
    target_ref: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def require_one_target(self) -> GraphEdge:
        if (self.target_node_id is None) == (self.target_ref is None):
            raise ValueError("an edge requires exactly one node or immutable-ref target")
        if (
            self.kind
            in {
                GraphEdgeKind.DEPENDS_ON,
                GraphEdgeKind.SUPERSEDES,
                GraphEdgeKind.INVALIDATES,
            }
            and self.target_node_id is None
        ):
            raise ValueError(f"{self.kind.value} requires a node target")
        return self


class NodeAttempt(BaseModel):
    session_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    status: NodeAttemptStatus
    idempotency_key: str = Field(min_length=1)
    claimed_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_terminal_attempt(self) -> NodeAttempt:
        terminal = self.status in {
            NodeAttemptStatus.COMPLETED,
            NodeAttemptStatus.FAILED,
            NodeAttemptStatus.CANCELLED,
            NodeAttemptStatus.ORPHANED,
        }
        if terminal and self.completed_at is None:
            raise ValueError("terminal attempts require completed_at")
        failed_states = {NodeAttemptStatus.FAILED, NodeAttemptStatus.ORPHANED}
        if self.status in failed_states and not self.error_code:
            raise ValueError("failed or orphaned attempts require error_code")
        return self


class CheckpointRecord(BaseModel):
    session_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    gate: ApprovalGate
    target_hash: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=list)
    authorized_by: str = Field(min_length=1)
    authorized_at: datetime
    revoked_at: datetime | None = None


class ActivePointer(BaseModel):
    session_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    ref_id: str = Field(min_length=1)
    node_id: str | None = None
    updated_at: datetime


class GraphSnapshot(BaseModel):
    session_id: str
    schema_version: str = "1"
    nodes: list[ResearchNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    attempts: list[NodeAttempt] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    active_pointers: list[ActivePointer] = Field(default_factory=list)
