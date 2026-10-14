from __future__ import annotations

from datetime import datetime
from typing import Protocol

from macro_research_agent.workflow.api_schemas import (
    GraphTransitionPlan,
    StoredWorkflowSession,
    WorkflowCommandResponse,
)
from macro_research_agent.workflow.graph.contracts import (
    ActivePointer,
    CheckpointRecord,
    GraphEdge,
    GraphSnapshot,
    NodeAttempt,
    ResearchNode,
)


class ResearchGraphRepository(Protocol):
    def commit_graph_transition(
        self, plan: GraphTransitionPlan
    ) -> WorkflowCommandResponse: ...

    def get(self, session_id: str) -> StoredWorkflowSession: ...

    def graph_snapshot(self, session_id: str) -> GraphSnapshot: ...

    def get_graph_node(self, session_id: str, node_id: str) -> ResearchNode: ...

    def list_graph_attempts(self, session_id: str) -> list[NodeAttempt]: ...

    def save_graph_node(self, node: ResearchNode) -> ResearchNode: ...

    def save_graph_edges(self, edges: list[GraphEdge]) -> None: ...

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord: ...

    def replace_active_pointers(self, session_id: str, pointers: list[ActivePointer]) -> None: ...

    def save_attempt(self, attempt: NodeAttempt) -> NodeAttempt: ...

    def claim_graph_node(
        self,
        session_id: str,
        node_id: str,
        idempotency_key: str,
        claimed_at: datetime,
        allow_retry: bool = False,
    ) -> NodeAttempt: ...

    def complete_graph_attempt(
        self,
        session_id: str,
        attempt_id: str,
        output_refs: list[str],
        completed_at: datetime,
    ) -> NodeAttempt: ...

    def stop_graph_attempt(
        self,
        session_id: str,
        attempt_id: str,
        status: str,
        error_code: str,
        completed_at: datetime,
    ) -> NodeAttempt: ...

    def mark_graph_nodes_stale(
        self,
        session_id: str,
        node_ids: set[str],
        invalidated_by: set[str],
        reason: str,
        changed_at: datetime,
    ) -> list[ResearchNode]: ...

    def recover_orphaned_graph_attempts(
        self, session_id: str, cutoff: datetime, recovered_at: datetime
    ) -> list[NodeAttempt]: ...
