from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.graph.contracts import (
    GraphEdge,
    GraphEdgeKind,
    NodeAttempt,
    NodeAttemptStatus,
    NodeAuthority,
    NodeLifecycle,
    ResearchNode,
    ResearchNodeKind,
)
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.states import ApprovalGate, WorkflowStage


class WorkflowCapabilityAuditWriter:
    """Materialize direct capability calls as graph attempts plus append-only trace."""

    def __init__(
        self, repository: WorkflowRepository, graph_service: GraphService
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service

    def __call__(
        self, session_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        now = datetime.now(timezone.utc)
        invocation_id = str(payload["invocation_id"])
        node_id = f"capability-{invocation_id}"
        completed = payload.get("status") == "completed"
        error_code = None if completed else str(payload.get("error_code") or "blocked")
        approval_value = str(payload.get("approval_policy") or "none")
        required_checkpoint = (
            ApprovalGate(approval_value)
            if completed and approval_value != "none"
            else None
        )
        node = ResearchNode(
            session_id=session_id,
            node_id=node_id,
            kind=ResearchNodeKind.CAPABILITY_INVOCATION,
            # A rejected standalone invocation is a completed audit record whose
            # attempt failed; it is not a terminal failure of the Workflow cursor.
            lifecycle=NodeLifecycle.COMPLETED,
            authority=NodeAuthority.EXECUTION,
            stage=WorkflowStage(str(payload["stage"])),
            input_refs=[str(item) for item in payload.get("input_refs") or []],
            output_refs=[str(item) for item in payload.get("result_refs") or []],
            capability_id=str(payload["capability_id"]),
            capability_version=str(payload["capability_version"]),
            required_checkpoint=required_checkpoint,
            error_code=error_code,
            rationale=None if completed else f"Invocation rejected: {error_code}",
            created_at=now,
            updated_at=now,
        )
        edges = [
            GraphEdge(
                session_id=session_id,
                edge_id=f"edge-{node_id}-consumes-{index}",
                kind=GraphEdgeKind.CONSUMES,
                source_node_id=node_id,
                target_ref=input_ref,
                created_at=now,
            )
            for index, input_ref in enumerate(node.input_refs)
        ]
        edges.extend(
            GraphEdge(
                session_id=session_id,
                edge_id=f"edge-{node_id}-produces-{index}",
                kind=GraphEdgeKind.PRODUCES,
                source_node_id=node_id,
                target_ref=output_ref,
                created_at=now,
            )
            for index, output_ref in enumerate(node.output_refs)
        )
        if checkpoint_ref := payload.get("checkpoint_ref"):
            edges.append(
                GraphEdge(
                    session_id=session_id,
                    edge_id=f"edge-{node_id}-authorized",
                    kind=GraphEdgeKind.AUTHORIZED_BY,
                    source_node_id=node_id,
                    target_ref=str(checkpoint_ref),
                    created_at=now,
                )
            )
        attempt = NodeAttempt(
                session_id=session_id,
                attempt_id=f"attempt-{invocation_id}-1",
                node_id=node_id,
                attempt_number=1,
                status=(
                    NodeAttemptStatus.COMPLETED if completed else NodeAttemptStatus.FAILED
                ),
                idempotency_key=invocation_id,
                claimed_at=now,
                completed_at=now,
                error_code=error_code,
        )
        self.graph_service.record_capability_invocation(node, edges, attempt)
        self.repository.record_trace_event(
            session_id,
            event_type,
            Actor(str(payload.get("actor") or "agent")),
            payload,
        )
