from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from macro_research_agent.workflow.graph.contracts import (
    CheckpointRecord,
    GraphEdge,
    GraphEdgeKind,
    GraphSnapshot,
    NodeAttempt,
    NodeAttemptStatus,
    NodeAuthority,
    NodeLifecycle,
    ResearchNode,
    ResearchNodeKind,
)
from macro_research_agent.workflow.graph.executor import NodeExecutor
from macro_research_agent.workflow.graph.projection import (
    WorkflowProjectionError,
    WorkflowProjectionService,
)
from macro_research_agent.workflow.graph.service import GraphInvariantError, GraphService
from macro_research_agent.workflow.repository import WorkflowSessionNotFound
from macro_research_agent.workflow.states import (
    ApprovalGate,
    SessionState,
    WorkflowStage,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def node(
    node_id: str,
    lifecycle: NodeLifecycle = NodeLifecycle.COMPLETED,
    *,
    required_checkpoint: ApprovalGate | None = None,
) -> ResearchNode:
    return ResearchNode(
        session_id="graph-session",
        node_id=node_id,
        kind=ResearchNodeKind.RESEARCH_REQUEST,
        lifecycle=lifecycle,
        required_checkpoint=required_checkpoint,
        created_at=NOW,
        updated_at=NOW,
    )


def edge(source: str, target: str) -> GraphEdge:
    return GraphEdge(
        session_id="graph-session",
        edge_id=f"edge-{source}-{target}",
        kind=GraphEdgeKind.DEPENDS_ON,
        source_node_id=source,
        target_node_id=target,
        created_at=NOW,
    )


def session_document() -> dict[str, object]:
    timestamp = "2026-08-25T12:00:00Z"
    return {
        "id": "graph-session",
        "title": "Graph migration",
        "request": "Validate the durable research graph.",
        "status": "clarifying",
        "activeStage": "plan",
        "reachedStages": ["plan"],
        "stageHealth": {
            "plan": "current",
            "data": "not_reached",
            "transformation": "not_reached",
            "output": "not_reached",
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "archived": False,
        "nodes": [
            {
                "id": "request-node",
                "kind": "research_request",
                "status": "completed",
                "inputSnapshotIds": [],
                "outputSnapshotId": "request-ref",
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            {
                "id": "plan-node",
                "kind": "research_plan",
                "status": "waiting_for_review",
                "inputSnapshotIds": ["request-ref"],
                "outputSnapshotId": "plan-ref",
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
        ],
        "data": {"activeSnapshotId": "dataset-ref"},
        "pipeline": {},
        "output": {},
    }


def test_dependency_impact_preserves_unaffected_siblings() -> None:
    snapshot = GraphSnapshot(
        session_id="graph-session",
        nodes=[node("plan"), node("data"), node("model"), node("artifact"), node("sibling")],
        edges=[edge("data", "plan"), edge("model", "data"), edge("artifact", "model")],
    )

    GraphService.validate(snapshot)

    assert GraphService.descendants(snapshot, {"data"}) == {"model", "artifact"}
    assert "sibling" not in GraphService.descendants(snapshot, {"data"})


def test_fan_in_waits_for_every_required_parent() -> None:
    first = node("first")
    second = node("second", NodeLifecycle.WAITING_FOR_REVIEW)
    fan_in = node("fan-in", NodeLifecycle.PENDING)
    snapshot = GraphSnapshot(
        session_id="graph-session",
        nodes=[first, second, fan_in],
        edges=[edge("fan-in", "first"), edge("fan-in", "second")],
    )
    assert GraphService.is_ready(snapshot, fan_in) is False

    completed_second = second.model_copy(update={"lifecycle": NodeLifecycle.COMPLETED})
    ready_snapshot = snapshot.model_copy(
        update={"nodes": [first, completed_second, fan_in]}
    )
    assert GraphService.is_ready(ready_snapshot, fan_in) is True


def test_graph_rejects_dependency_cycles_and_unauthorized_execution() -> None:
    cyclic = GraphSnapshot(
        session_id="graph-session",
        nodes=[node("one"), node("two")],
        edges=[edge("one", "two"), edge("two", "one")],
    )
    with pytest.raises(GraphInvariantError, match="cycle"):
        GraphService.validate(cyclic)

    unauthorized = GraphSnapshot(
        session_id="graph-session",
        nodes=[
            node(
                "acquisition",
                required_checkpoint=ApprovalGate.RESEARCH_PLAN,
            )
        ],
    )
    with pytest.raises(GraphInvariantError, match="lacks active checkpoint"):
        GraphService.validate(unauthorized)


def test_checkpoint_controls_node_readiness() -> None:
    pending = node(
        "acquisition",
        NodeLifecycle.PENDING,
        required_checkpoint=ApprovalGate.RESEARCH_PLAN,
    )
    checkpoint = CheckpointRecord(
        session_id="graph-session",
        checkpoint_id="checkpoint-plan",
        gate=ApprovalGate.RESEARCH_PLAN,
        target_hash="sha256:plan",
        authorized_by="user",
        authorized_at=NOW,
    )
    authorization = GraphEdge(
        session_id="graph-session",
        edge_id="edge-authorization",
        kind=GraphEdgeKind.AUTHORIZED_BY,
        source_node_id=pending.node_id,
        target_ref=checkpoint.checkpoint_id,
        created_at=NOW,
    )

    no_checkpoint = GraphSnapshot(session_id="graph-session", nodes=[pending])
    assert GraphService.is_ready(no_checkpoint, pending) is False
    authorized = GraphSnapshot(
        session_id="graph-session",
        nodes=[pending],
        edges=[authorization],
        checkpoints=[checkpoint],
    )
    assert GraphService.is_ready(authorized, pending) is True

    wrong_gate = checkpoint.model_copy(update={"gate": ApprovalGate.PIPELINE_EXECUTION})
    mismatched = authorized.model_copy(update={"checkpoints": [wrong_gate]})
    assert GraphService.is_ready(mismatched, pending) is False


@pytest.mark.parametrize(
    ("kind", "lifecycle", "expected_status", "expected_stage"),
    [
        (
            ResearchNodeKind.RESEARCH_PLAN,
            NodeLifecycle.WAITING_FOR_REVIEW,
            SessionState.PLAN_REVIEW,
            WorkflowStage.PLAN,
        ),
        (
            ResearchNodeKind.DATA_PREPARATION,
            NodeLifecycle.APPROVED,
            SessionState.PIPELINE_EDITING,
            WorkflowStage.TRANSFORMATION,
        ),
        (
            ResearchNodeKind.OUTPUT_GENERATION,
            NodeLifecycle.COMPLETED,
            SessionState.OUTPUT_REVIEW,
            WorkflowStage.OUTPUT,
        ),
        (
            ResearchNodeKind.REPRODUCTION_MANIFEST,
            NodeLifecycle.COMPLETED,
            SessionState.COMPLETED,
            WorkflowStage.OUTPUT,
        ),
    ],
)
def test_projection_is_derived_from_current_graph_nodes(
    kind: ResearchNodeKind,
    lifecycle: NodeLifecycle,
    expected_status: SessionState,
    expected_stage: WorkflowStage,
) -> None:
    current = node("current", lifecycle).model_copy(update={"kind": kind})
    facts = WorkflowProjectionService.derive(
        GraphSnapshot(session_id="graph-session", nodes=[current]),
        fallback_status=SessionState.FAILED,
        fallback_stage=WorkflowStage.OUTPUT,
        fallback_reachable=list(WorkflowStage),
    )
    assert facts.status == expected_status
    assert facts.active_stage == expected_stage
    assert expected_stage in facts.reachable_stages
    assert facts.used_legacy_fallback is False


def test_projection_rejects_an_empty_graph_after_migration_window() -> None:
    with pytest.raises(WorkflowProjectionError, match="fallback is retired"):
        WorkflowProjectionService.derive(
            GraphSnapshot(session_id="legacy-session"),
            fallback_status=SessionState.DATA_REVIEW,
            fallback_stage=WorkflowStage.DATA,
            fallback_reachable=[WorkflowStage.PLAN, WorkflowStage.DATA],
        )


def test_failed_projection_uses_the_terminal_nodes_stage() -> None:
    failed = node("failed-acquisition").model_copy(
        update={
            "kind": ResearchNodeKind.DATA_ACQUISITION,
            "lifecycle": NodeLifecycle.FAILED,
            "stage": WorkflowStage.DATA,
            "error_code": "connector_failed",
        }
    )
    facts = WorkflowProjectionService.derive(
        GraphSnapshot(session_id="graph-session", nodes=[failed]),
        fallback_status=SessionState.FAILED,
        fallback_stage=WorkflowStage.OUTPUT,
        fallback_reachable=list(WorkflowStage),
    )

    assert facts.status == SessionState.FAILED
    assert facts.active_stage == WorkflowStage.DATA
    assert facts.used_legacy_fallback is False


@pytest.mark.asyncio
async def test_legacy_nodes_are_migrated_to_durable_graph_and_survive_restart(
    tmp_path: Path,
) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": session_document()}
        )
        graph = await client.get("/api/v1/admin/workflow/sessions/graph-session/graph")

    assert created.status_code == 201
    assert graph.status_code == 200
    graph_body = graph.json()
    assert [item["node_id"] for item in graph_body["nodes"]] == [
        "request-node",
        "plan-node",
    ]
    assert any(
        item["kind"] == "depends_on"
        and item["source_node_id"] == "plan-node"
        and item["target_node_id"] == "request-node"
        for item in graph_body["edges"]
    )
    assert {item["role"] for item in graph_body["active_pointers"]} == {"data"}

    restarted = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        graph_after_restart = await client.get(
            "/api/v1/admin/workflow/sessions/graph-session/graph"
        )
        one_node = await client.get(
            "/api/v1/admin/workflow/sessions/graph-session/graph/nodes/plan-node"
        )

    assert graph_after_restart.status_code == 200
    assert len(graph_after_restart.json()["nodes"]) == 2
    assert one_node.json()["output_refs"] == ["plan-ref"]


def test_attempts_are_append_only_and_completed_node_refs_are_immutable(tmp_path: Path) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    attempt = NodeAttempt(
        session_id="graph-session",
        attempt_id="attempt-request-1",
        node_id="request-node",
        attempt_number=1,
        status=NodeAttemptStatus.COMPLETED,
        idempotency_key="request-run-1",
        claimed_at=NOW,
        completed_at=NOW,
    )
    repository.save_attempt(attempt)
    assert repository.list_graph_attempts("graph-session") == [attempt]
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_attempt(attempt)

    completed = repository.get_graph_node("graph-session", "request-node")
    changed = completed.model_copy(update={"output_refs": ["different-ref"]})
    with pytest.raises(ValueError, match="immutable"):
        repository.save_graph_node(changed)

    checkpoint = CheckpointRecord(
        session_id="graph-session",
        checkpoint_id="immutable-checkpoint",
        gate=ApprovalGate.RESEARCH_PLAN,
        target_hash="sha256:original",
        authorized_by="user",
        authorized_at=NOW,
    )
    repository.save_checkpoint(checkpoint)
    with pytest.raises(ValueError, match="immutable"):
        repository.save_checkpoint(
            checkpoint.model_copy(update={"target_hash": "sha256:changed"})
        )


def test_graph_executor_is_idempotent_and_retry_recovery_is_attempt_scoped(
    tmp_path: Path,
) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))

    runnable = ResearchNode(
        session_id="graph-session",
        node_id="capability-node",
        kind=ResearchNodeKind.CAPABILITY_INVOCATION,
        lifecycle=NodeLifecycle.READY,
        authority=NodeAuthority.EXECUTION,
        capability_id="test.capability",
        capability_version="1",
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save_graph_node(runnable)
    first = graph_service.claim("graph-session", runnable.node_id, "run-once", NOW)
    replay = graph_service.claim("graph-session", runnable.node_id, "run-once", NOW)
    assert replay == first
    completed = graph_service.complete(
        "graph-session", first.attempt_id, ["result-ref"], NOW + timedelta(seconds=1)
    )
    assert completed.status == NodeAttemptStatus.COMPLETED
    assert repository.get_graph_node("graph-session", runnable.node_id).output_refs == [
        "result-ref"
    ]

    retryable = runnable.model_copy(
        update={"node_id": "retry-node", "output_refs": [], "updated_at": NOW}
    )
    repository.save_graph_node(retryable)
    failed_attempt = graph_service.claim(
        "graph-session", retryable.node_id, "first-failure", NOW
    )
    graph_service.fail(
        "graph-session",
        failed_attempt.attempt_id,
        "provider_timeout",
        NOW + timedelta(seconds=1),
    )
    retried = graph_service.retry(
        "graph-session",
        retryable.node_id,
        "retry-after-failure",
        NOW + timedelta(seconds=2),
    )
    assert retried.attempt_number == 2
    recovered = graph_service.recover_orphans(
        "graph-session",
        cutoff=NOW + timedelta(seconds=3),
        recovered_at=NOW + timedelta(seconds=4),
    )
    assert [item.attempt_id for item in recovered] == [retried.attempt_id]
    assert recovered[0].status == NodeAttemptStatus.ORPHANED
    recovered_node = repository.get_graph_node("graph-session", retryable.node_id)
    assert recovered_node.lifecycle == NodeLifecycle.FAILED
    assert recovered_node.error_code == "execution_interrupted"


def test_startup_recovers_attempts_older_than_configured_cutoff(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_dir=tmp_path,
        graph_orphan_timeout_seconds=1,
    )
    app = create_app(settings)
    repository = app.state.workflow_repository
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    runnable = ResearchNode(
        session_id="graph-session",
        node_id="startup-orphan",
        kind=ResearchNodeKind.CAPABILITY_INVOCATION,
        lifecycle=NodeLifecycle.READY,
        authority=NodeAuthority.EXECUTION,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save_graph_node(runnable)
    claimed = app.state.workflow_graph_service.claim(
        "graph-session", runnable.node_id, "startup-run", NOW
    )

    restarted = create_app(settings)
    assert [
        attempt.attempt_id for attempt in restarted.state.recovered_orphan_attempts
    ] == [claimed.attempt_id]
    recovered = restarted.state.workflow_repository.get_graph_node(
        "graph-session", runnable.node_id
    )
    assert recovered.lifecycle == NodeLifecycle.FAILED
    assert recovered.error_code == "execution_interrupted"


def test_concurrent_duplicate_claim_creates_one_attempt(tmp_path: Path) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    runnable = ResearchNode(
        session_id="graph-session",
        node_id="concurrent-node",
        kind=ResearchNodeKind.CAPABILITY_INVOCATION,
        lifecycle=NodeLifecycle.READY,
        authority=NodeAuthority.EXECUTION,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save_graph_node(runnable)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: graph_service.claim(
                    "graph-session", runnable.node_id, "same-cost-key", NOW
                ),
                range(2),
            )
        )

    assert results[0] == results[1]
    attempts = [
        item
        for item in repository.list_graph_attempts("graph-session")
        if item.node_id == runnable.node_id
    ]
    assert len(attempts) == 1


def test_proposal_node_cannot_be_claimed_or_authorized(tmp_path: Path) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    proposal = ResearchNode(
        session_id="graph-session",
        node_id="plan-patch-proposal",
        kind=ResearchNodeKind.RESEARCH_PLAN,
        lifecycle=NodeLifecycle.READY,
        authority=NodeAuthority.PROPOSAL,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save_graph_node(proposal)
    with pytest.raises(ValueError, match="no execution authority"):
        graph_service.claim("graph-session", proposal.node_id, "proposal-run", NOW)

    unauthorized_edge = GraphEdge(
        session_id="graph-session",
        edge_id="proposal-authorization",
        kind=GraphEdgeKind.AUTHORIZED_BY,
        source_node_id=proposal.node_id,
        target_ref="checkpoint-any",
        created_at=NOW,
    )
    current = repository.graph_snapshot("graph-session")
    snapshot = current.model_copy(update={"edges": [*current.edges, unauthorized_edge]})
    with pytest.raises(GraphInvariantError, match="proposal node"):
        GraphService.validate(snapshot)


def test_stale_ai_proposal_is_rejected_before_persistence(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path))
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    proposal = ResearchNode(
        session_id="graph-session",
        node_id="stale-proposal",
        kind=ResearchNodeKind.RESEARCH_PLAN,
        lifecycle=NodeLifecycle.WAITING_FOR_REVIEW,
        authority=NodeAuthority.PROPOSAL,
        input_refs=["sha256:old-plan"],
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(GraphInvariantError, match="target is stale"):
        graph_service.save_proposal(
            proposal,
            target_snapshot_hash="sha256:old-plan",
            current_snapshot_hash="sha256:new-plan",
        )
    with pytest.raises(WorkflowSessionNotFound):
        repository.get_graph_node("graph-session", "stale-proposal")


def test_bounded_node_executor_releases_fan_in_after_parallel_parents(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path))
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    for node_id, capability_id in (
        ("member-usa", "test.member"),
        ("member-jpn", "test.member"),
        ("aggregate", "test.aggregate"),
    ):
        repository.save_graph_node(
            ResearchNode(
                session_id="graph-session",
                node_id=node_id,
                kind=ResearchNodeKind.CAPABILITY_INVOCATION,
                lifecycle=(
                    NodeLifecycle.PENDING if node_id == "aggregate" else NodeLifecycle.READY
                ),
                authority=NodeAuthority.EXECUTION,
                capability_id=capability_id,
                capability_version="1.0.0",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    repository.save_graph_edges(
        [edge("aggregate", "member-usa"), edge("aggregate", "member-jpn")]
    )
    executor = NodeExecutor(graph_service, max_concurrency=2, max_nodes_per_run=3)
    executor.register(
        "test.member", lambda research_node, _: [f"snapshot:{research_node.node_id}"]
    )

    def aggregate_handler(_: ResearchNode, __: NodeAttempt) -> list[str]:
        snapshot = graph_service.snapshot("graph-session")
        parents = {
            item.node_id: item.lifecycle
            for item in snapshot.nodes
            if item.node_id.startswith("member-")
        }
        assert set(parents.values()) == {NodeLifecycle.COMPLETED}
        return ["snapshot:aggregate"]

    executor.register("test.aggregate", aggregate_handler)
    report = executor.run_ready("graph-session")
    assert report.claimed == 3
    assert report.completed == 3
    assert report.failed == 0
    assert repository.get_graph_node("graph-session", "aggregate").output_refs == [
        "snapshot:aggregate"
    ]


def test_graph_invalidation_is_transitive_and_records_edges(tmp_path: Path) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    nodes = [
        node("upstream"),
        node("downstream"),
        node("artifact"),
        node("unaffected"),
    ]
    for item in nodes:
        repository.save_graph_node(item)
    repository.save_graph_edges(
        [edge("downstream", "upstream"), edge("artifact", "downstream")]
    )

    stale = graph_service.invalidate_descendants(
        "graph-session",
        {"upstream"},
        "Upstream specification changed.",
        NOW + timedelta(seconds=1),
    )
    assert {item.node_id for item in stale} == {"downstream", "artifact"}
    snapshot = graph_service.snapshot("graph-session")
    unaffected = next(item for item in snapshot.nodes if item.node_id == "unaffected")
    assert unaffected.lifecycle == NodeLifecycle.COMPLETED
    assert any(item.kind == GraphEdgeKind.INVALIDATES for item in snapshot.edges)
