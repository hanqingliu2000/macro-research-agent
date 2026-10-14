from __future__ import annotations

from typing import Any, Protocol

from macro_research_agent.trace.events import Actor, TraceEvent
from macro_research_agent.workflow.api_schemas import (
    StoredWorkflowSession,
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.graph.contracts import (
    ActivePointer,
    CheckpointRecord,
    GraphEdge,
    GraphSnapshot,
    NodeAttempt,
    ResearchNode,
)
from macro_research_agent.workflow.uploads import UploadedFileRecord


class WorkflowRepository(Protocol):
    def create(self, document: WorkflowSessionDocument) -> StoredWorkflowSession: ...

    def list_sessions(self) -> list[StoredWorkflowSession]: ...

    def get(self, session_id: str) -> StoredWorkflowSession: ...

    def set_deleted(self, session_id: str, deleted: bool) -> StoredWorkflowSession: ...

    def require_current(self, meta: WorkflowCommandMeta) -> StoredWorkflowSession: ...

    def list_nodes(self, session_id: str) -> list[dict[str, Any]]: ...

    def graph_snapshot(self, session_id: str) -> GraphSnapshot: ...

    def get_graph_node(self, session_id: str, node_id: str) -> ResearchNode: ...

    def list_graph_attempts(self, session_id: str) -> list[NodeAttempt]: ...

    def save_graph_node(self, node: ResearchNode) -> ResearchNode: ...

    def save_graph_edges(self, edges: list[GraphEdge]) -> None: ...

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord: ...

    def replace_active_pointers(
        self, session_id: str, pointers: list[ActivePointer]
    ) -> None: ...

    def save_attempt(self, attempt: NodeAttempt) -> NodeAttempt: ...

    def replay_command(
        self, session_id: str, idempotency_key: str
    ) -> WorkflowCommandResponse | None: ...

    def record_upload(self, record: UploadedFileRecord) -> UploadedFileRecord: ...

    def list_uploads(self, session_id: str) -> list[UploadedFileRecord]: ...

    def list_plan_snapshots(self, session_id: str) -> list[dict[str, Any]]: ...

    def trace(self, session_id: str) -> list[TraceEvent]: ...

    def record_trace_event(
        self,
        session_id: str,
        event_type: str,
        actor: Actor,
        payload: dict[str, Any],
    ) -> TraceEvent: ...
