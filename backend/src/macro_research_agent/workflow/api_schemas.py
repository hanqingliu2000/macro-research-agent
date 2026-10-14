from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from macro_research_agent.workflow.states import SessionState, WorkflowStage


class WorkflowSessionDocument(BaseModel):
    """Phase 1A envelope around the frontend-owned deterministic session payload."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    request: str = Field(min_length=1)
    status: SessionState
    active_stage: WorkflowStage = Field(alias="activeStage")
    reached_stages: list[WorkflowStage] = Field(alias="reachedStages", min_length=1)
    stage_health: dict[str, str] = Field(alias="stageHealth")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    archived: bool = False
    nodes: list[dict[str, Any]] = Field(min_length=1)

    @model_validator(mode="after")
    def active_stage_must_be_reached(self) -> WorkflowSessionDocument:
        if self.active_stage not in self.reached_stages:
            raise ValueError("active stage must be present in reached stages")
        return self


class WorkflowProjection(BaseModel):
    session_id: str
    status: SessionState
    active_stage: WorkflowStage
    reachable_stages: list[WorkflowStage]
    current_snapshot_hash: str
    current_snapshot_refs: dict[str, str | None] = Field(default_factory=dict)
    review_requirements: list[str] = Field(default_factory=list)
    updated_at: datetime


class StoredWorkflowSession(BaseModel):
    session: WorkflowSessionDocument
    projection: WorkflowProjection


class CreateWorkflowSessionRequest(BaseModel):
    request: str | None = Field(default=None, min_length=1)
    session: WorkflowSessionDocument | None = None

    @model_validator(mode="after")
    def require_one_creation_shape(self) -> CreateWorkflowSessionRequest:
        if (self.request is None) == (self.session is None):
            raise ValueError("provide exactly one of request or session")
        return self


class WorkflowCommandMeta(BaseModel):
    command_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    expected_stage: WorkflowStage
    expected_snapshot_hash: str = Field(min_length=1)
    actor: Literal["user", "agent"]
    requested_at: datetime


class WorkflowDocumentPatch(BaseModel):
    """Internal compatibility projection changes compiled by GraphService."""

    base_document_checksum: str = Field(min_length=1)
    set_fields: dict[str, Any] = Field(default_factory=dict)
    remove_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def protect_session_identity(self) -> WorkflowDocumentPatch:
        immutable = {"id", "createdAt"}
        touched = set(self.set_fields) | set(self.remove_fields)
        if touched & immutable:
            raise ValueError("document patch cannot change immutable session identity")
        overlap = set(self.set_fields) & set(self.remove_fields)
        if overlap:
            raise ValueError("document patch cannot set and remove the same field")
        return self


class GraphTransitionPlan(BaseModel):
    """Typed, internal transition plan; never accepted from an API client."""

    meta: WorkflowCommandMeta
    command: dict[str, Any]
    document_patch: WorkflowDocumentPatch

    @model_validator(mode="after")
    def require_typed_command(self) -> GraphTransitionPlan:
        if not str(self.command.get("type") or "").strip():
            raise ValueError("graph transition plan requires a command type")
        return self


class DispatchPlanCommandRequest(BaseModel):
    meta: WorkflowCommandMeta
    command: dict[str, Any]


class DispatchDataCommandRequest(BaseModel):
    meta: WorkflowCommandMeta
    command: dict[str, Any]


class DispatchPipelineCommandRequest(BaseModel):
    meta: WorkflowCommandMeta
    command: dict[str, Any]


class DispatchOutputCommandRequest(BaseModel):
    meta: WorkflowCommandMeta
    command: dict[str, Any]


class GeographyResolveRequest(BaseModel):
    intent: str = Field(min_length=1)


class GraphPointerChange(BaseModel):
    previous_ref: str | None = None
    current_ref: str | None = None


class GraphTransitionSummary(BaseModel):
    created_node_ids: list[str] = Field(default_factory=list)
    created_edge_ids: list[str] = Field(default_factory=list)
    created_checkpoint_ids: list[str] = Field(default_factory=list)
    pointer_changes: dict[str, GraphPointerChange] = Field(default_factory=dict)
    invalidated_node_ids: list[str] = Field(default_factory=list)


class WorkflowCommandResponse(BaseModel):
    session: WorkflowSessionDocument
    projection: WorkflowProjection
    created_snapshot_refs: list[str] = Field(default_factory=list)
    invalidated_node_ids: list[str] = Field(default_factory=list)
    outcome: str
    idempotent_replay: bool = False
    graph_transition: GraphTransitionSummary | None = None


class WorkflowConflictDetail(BaseModel):
    code: Literal["workflow_conflict"] = "workflow_conflict"
    message: str
    current_stage: WorkflowStage
    current_snapshot_hash: str
    projection: WorkflowProjection
