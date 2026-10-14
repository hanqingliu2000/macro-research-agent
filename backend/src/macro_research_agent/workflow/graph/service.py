from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from macro_research_agent.workflow.api_schemas import (
    GraphTransitionPlan,
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowDocumentPatch,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.graph.contracts import (
    GraphEdge,
    GraphEdgeKind,
    GraphSnapshot,
    NodeAttempt,
    NodeAuthority,
    NodeLifecycle,
    ResearchNode,
)
from macro_research_agent.workflow.graph.ports import ResearchGraphRepository


class GraphInvariantError(ValueError):
    pass


def _document_wire(document: WorkflowSessionDocument) -> dict[str, Any]:
    return document.model_dump(mode="json", by_alias=True)


def _document_checksum(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class GraphService:
    """Validates graph readiness and computes dependency impact without route/LLM authority."""

    def __init__(self, repository: ResearchGraphRepository) -> None:
        self.repository = repository

    def snapshot(self, session_id: str) -> GraphSnapshot:
        snapshot = self.repository.graph_snapshot(session_id)
        self.validate(snapshot)
        return snapshot

    def apply_transition(
        self,
        meta: WorkflowCommandMeta,
        command: dict[str, Any],
        target_session: WorkflowSessionDocument,
    ) -> WorkflowCommandResponse:
        """Compile and commit one graph-native transition from a typed stage command."""
        current = self.repository.get(meta.session_id).session
        if target_session.id != current.id:
            raise ValueError("target session does not match command session")
        current_wire = _document_wire(current)
        target_wire = _document_wire(target_session)
        immutable_fields = {"id", "createdAt"}
        if any(current_wire.get(field) != target_wire.get(field) for field in immutable_fields):
            raise ValueError("graph transitions cannot change immutable session identity")
        set_fields = {
            key: value
            for key, value in target_wire.items()
            if key not in immutable_fields and current_wire.get(key) != value
        }
        remove_fields = sorted(
            key
            for key in current_wire.keys() - target_wire.keys()
            if key not in immutable_fields
        )
        plan = GraphTransitionPlan(
            meta=meta,
            command=command,
            document_patch=WorkflowDocumentPatch(
                base_document_checksum=_document_checksum(current_wire),
                set_fields=set_fields,
                remove_fields=remove_fields,
            ),
        )
        return self.repository.commit_graph_transition(plan)

    def claim(
        self,
        session_id: str,
        node_id: str,
        idempotency_key: str,
        claimed_at: datetime,
    ) -> NodeAttempt:
        return self.repository.claim_graph_node(
            session_id, node_id, idempotency_key, claimed_at, False
        )

    def retry(
        self,
        session_id: str,
        node_id: str,
        idempotency_key: str,
        claimed_at: datetime,
    ) -> NodeAttempt:
        return self.repository.claim_graph_node(
            session_id, node_id, idempotency_key, claimed_at, True
        )

    def complete(
        self,
        session_id: str,
        attempt_id: str,
        output_refs: list[str],
        completed_at: datetime,
    ) -> NodeAttempt:
        return self.repository.complete_graph_attempt(
            session_id, attempt_id, output_refs, completed_at
        )

    def fail(
        self,
        session_id: str,
        attempt_id: str,
        error_code: str,
        completed_at: datetime,
    ) -> NodeAttempt:
        return self.repository.stop_graph_attempt(
            session_id, attempt_id, "failed", error_code, completed_at
        )

    def cancel(
        self,
        session_id: str,
        attempt_id: str,
        completed_at: datetime,
    ) -> NodeAttempt:
        return self.repository.stop_graph_attempt(
            session_id, attempt_id, "cancelled", "cancelled_by_user", completed_at
        )

    def invalidate_descendants(
        self,
        session_id: str,
        changed_node_ids: set[str],
        reason: str,
        changed_at: datetime,
    ) -> list[ResearchNode]:
        snapshot = self.snapshot(session_id)
        affected = self.descendants(snapshot, changed_node_ids)
        return self.repository.mark_graph_nodes_stale(
            session_id, affected, changed_node_ids, reason, changed_at
        )

    def recover_orphans(
        self, session_id: str, cutoff: datetime, recovered_at: datetime
    ) -> list[NodeAttempt]:
        return self.repository.recover_orphaned_graph_attempts(
            session_id, cutoff, recovered_at
        )

    def save_proposal(
        self,
        proposal: ResearchNode,
        *,
        target_snapshot_hash: str,
        current_snapshot_hash: str,
    ) -> ResearchNode:
        if proposal.authority != NodeAuthority.PROPOSAL:
            raise GraphInvariantError("Only proposal-authority nodes use save_proposal.")
        if target_snapshot_hash != current_snapshot_hash:
            raise GraphInvariantError("AI proposal target is stale.")
        if target_snapshot_hash not in proposal.input_refs:
            raise GraphInvariantError("AI proposal must consume its exact target snapshot hash.")
        return self.repository.save_graph_node(proposal)

    def record_capability_invocation(
        self,
        node: ResearchNode,
        edges: list[GraphEdge],
        attempt: NodeAttempt,
    ) -> ResearchNode:
        if node.kind.value != "capability_invocation":
            raise GraphInvariantError("Capability receipt requires a capability-invocation node.")
        if node.authority != NodeAuthority.EXECUTION:
            raise GraphInvariantError("Capability receipt requires execution authority.")
        saved = self.repository.save_graph_node(node)
        if edges:
            self.repository.save_graph_edges(edges)
        self.repository.save_attempt(attempt)
        self.snapshot(node.session_id)
        return saved

    @staticmethod
    def validate(snapshot: GraphSnapshot) -> None:
        nodes = {node.node_id: node for node in snapshot.nodes}
        if len(nodes) != len(snapshot.nodes):
            raise GraphInvariantError("graph contains duplicate node IDs")

        dependency_children: dict[str, list[str]] = defaultdict(list)
        for edge in snapshot.edges:
            if edge.source_node_id not in nodes:
                raise GraphInvariantError(f"edge source does not exist: {edge.edge_id}")
            if edge.target_node_id is not None and edge.target_node_id not in nodes:
                raise GraphInvariantError(f"edge target does not exist: {edge.edge_id}")
            if edge.kind == GraphEdgeKind.DEPENDS_ON:
                assert edge.target_node_id is not None
                dependency_children[edge.target_node_id].append(edge.source_node_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise GraphInvariantError("depends_on edges contain a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in dependency_children.get(node_id, []):
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in nodes:
            visit(node_id)

        checkpoints = {
            item.checkpoint_id: item
            for item in snapshot.checkpoints
            if item.revoked_at is None
        }
        attempt_keys: set[tuple[str, int]] = set()
        for attempt in snapshot.attempts:
            if attempt.node_id not in nodes:
                raise GraphInvariantError(f"attempt node does not exist: {attempt.attempt_id}")
            key = (attempt.node_id, attempt.attempt_number)
            if key in attempt_keys:
                raise GraphInvariantError("graph contains duplicate node attempt numbers")
            attempt_keys.add(key)
        for node in snapshot.nodes:
            if node.authority == NodeAuthority.PROPOSAL and any(
                edge.kind == GraphEdgeKind.AUTHORIZED_BY
                and edge.source_node_id == node.node_id
                for edge in snapshot.edges
            ):
                raise GraphInvariantError(
                    f"proposal node cannot have authorization edges: {node.node_id}"
                )
            if node.required_checkpoint is not None and node.lifecycle in {
                NodeLifecycle.IN_PROGRESS,
                NodeLifecycle.APPROVED,
                NodeLifecycle.COMPLETED,
            }:
                authorized = any(
                    edge.kind == GraphEdgeKind.AUTHORIZED_BY
                    and edge.source_node_id == node.node_id
                    and edge.target_ref in checkpoints
                    and checkpoints[edge.target_ref].gate == node.required_checkpoint
                    for edge in snapshot.edges
                )
                if not authorized:
                    raise GraphInvariantError(
                        f"executed node lacks active checkpoint authorization: {node.node_id}"
                    )

    @staticmethod
    def descendants(snapshot: GraphSnapshot, changed_node_ids: set[str]) -> set[str]:
        children: dict[str, set[str]] = defaultdict(set)
        for edge in snapshot.edges:
            if edge.kind == GraphEdgeKind.DEPENDS_ON and edge.target_node_id is not None:
                children[edge.target_node_id].add(edge.source_node_id)
        affected: set[str] = set()
        queue = deque(changed_node_ids)
        while queue:
            parent = queue.popleft()
            for child in children.get(parent, set()):
                if child not in affected and child not in changed_node_ids:
                    affected.add(child)
                    queue.append(child)
        return affected

    @staticmethod
    def is_ready(snapshot: GraphSnapshot, node: ResearchNode) -> bool:
        if node.lifecycle not in {NodeLifecycle.PENDING, NodeLifecycle.READY}:
            return False
        nodes = {item.node_id: item for item in snapshot.nodes}
        parent_ids = {
            edge.target_node_id
            for edge in snapshot.edges
            if edge.kind == GraphEdgeKind.DEPENDS_ON
            and edge.source_node_id == node.node_id
            and edge.target_node_id is not None
        }
        allowed_parent_states = {NodeLifecycle.APPROVED, NodeLifecycle.COMPLETED}
        if any(nodes[parent_id].lifecycle not in allowed_parent_states for parent_id in parent_ids):
            return False
        if node.required_checkpoint is None:
            return True
        active_checkpoints = {
            item.checkpoint_id: item
            for item in snapshot.checkpoints
            if item.revoked_at is None
        }
        return any(
            edge.kind == GraphEdgeKind.AUTHORIZED_BY
            and edge.source_node_id == node.node_id
            and edge.target_ref in active_checkpoints
            and active_checkpoints[edge.target_ref].gate == node.required_checkpoint
            for edge in snapshot.edges
        )
