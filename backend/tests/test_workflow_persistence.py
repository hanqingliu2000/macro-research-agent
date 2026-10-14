from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.trace.events import Actor, TraceEvent
from macro_research_agent.trace.writer import JsonlTraceWriter
from macro_research_agent.workflow.api_schemas import WorkflowCommandMeta
from macro_research_agent.workflow.repository import WorkflowConflict
from macro_research_agent.workflow.states import SessionState, WorkflowStage


def session_document(session_id: str = "workflow-test-1") -> dict[str, object]:
    timestamp = "2026-08-24T12:00:00Z"
    return {
        "id": session_id,
        "title": "Inflation persistence",
        "request": "Compare inflation persistence.",
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
                "id": "node-request-1",
                "kind": "research_request",
                "status": "completed",
                "inputSnapshotIds": [],
                "outputSnapshotId": "request",
                "createdAt": timestamp,
                "updatedAt": timestamp,
            }
        ],
        "data": {"activeSnapshotId": "dataset-mock-1"},
        "pipeline": {},
        "output": {},
    }


@pytest.mark.asyncio
async def test_request_only_creation_is_backend_owned_and_preserves_planning_intent(
    tmp_path: Path,
) -> None:
    # LRS-PLAN-01/02: product creation starts clean and returned question IDs drive the draft.
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions",
            json={
                "request": (
                    "Compare the United States and Japan, 2010-2025 quarterly, "
                    "and produce a research report."
                )
            },
        )
        assert created.status_code == 201
        body = created.json()
        session = body["session"]
        assert session["data"]["sourceRuns"] == []
        assert session["data"]["snapshots"] == []
        question_ids = {item["id"] for item in session["clarification"]["questions"]}
        assert question_ids == {"geography_scope", "period_frequency"}
        period_question = next(
            item
            for item in session["clarification"]["questions"]
            if item["id"] == "period_frequency"
        )
        assert period_question["options"][0] == "2010-2025 quarterly"

        session_id = session["id"]
        drafted = await client.post(
            f"/api/v1/workflow/sessions/{session_id}/plan/commands",
            json={
                "meta": {
                    "command_id": "command-request-plan",
                    "idempotency_key": "request-plan",
                    "session_id": session_id,
                    "expected_stage": "plan",
                    "expected_snapshot_hash": body["projection"]["current_snapshot_hash"],
                    "actor": "user",
                    "requested_at": "2026-09-04T12:01:00Z",
                },
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "Use the economies in my request",
                        "period_frequency": "2019-2024 quarterly",
                    },
                },
            },
        )
        assert drafted.status_code == 200
        plan = drafted.json()["session"]["currentPlan"]
        assert plan["period"]["frequency"] == "quarterly"
        assert [item["memberCodes"] for item in plan["geographyResolutions"]] == [
            ["USA"],
            ["JPN"],
        ]
        assert plan["deliverables"]["researchReport"] is True


@pytest.mark.asyncio
async def test_product_runtime_rejects_client_seeded_session_state(tmp_path: Path) -> None:
    app = create_app(Settings(environment="development", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/workflow/sessions", json={"session": session_document()}
        )
    assert response.status_code == 422
    assert "test fixtures" in response.text


@pytest.mark.asyncio
async def test_session_survives_restart_and_exposes_projection_and_nodes(tmp_path: Path) -> None:
    # LRS-RECOVERY-01: durable state survives a process boundary.
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    document = session_document()
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions",
            json={"session": document},
        )
        assert created.status_code == 201
        initial_hash = created.json()["projection"]["current_snapshot_hash"]

    restarted = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        listed = await client.get("/api/v1/workflow/sessions")
        projection = await client.get("/api/v1/workflow/sessions/workflow-test-1/projection")
        nodes = await client.get("/api/v1/workflow/sessions/workflow-test-1/nodes")

    assert listed.json()[0]["session"]["title"] == "Inflation persistence"
    assert projection.json()["current_snapshot_hash"] == initial_hash
    assert projection.json()["current_snapshot_refs"]["data"] == "dataset-mock-1"
    assert nodes.json()[0]["kind"] == "research_request"


@pytest.mark.asyncio
async def test_graph_transition_plan_replays_and_rejects_stale_write(tmp_path: Path) -> None:
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    document = session_document()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions",
            json={"session": document},
        )
    initial_hash = created.json()["projection"]["current_snapshot_hash"]
    repository = app.state.workflow_repository
    graph_service = app.state.workflow_graph_service
    target = repository.get("workflow-test-1").session.model_copy(
        update={
            "updated_at": datetime.fromisoformat("2026-08-24T12:01:00+00:00"),
            # Compatibility cursor values are deliberately wrong; graph projection must win.
            "status": SessionState.COMPLETED,
            "active_stage": WorkflowStage.OUTPUT,
            "reached_stages": list(WorkflowStage),
        }
    )
    meta = WorkflowCommandMeta(
        command_id="command-1",
        idempotency_key="fixture-1",
        session_id="workflow-test-1",
        expected_stage="plan",
        expected_snapshot_hash=initial_hash,
        actor="user",
        requested_at=datetime.fromisoformat("2026-08-24T12:01:00+00:00"),
    )
    first = graph_service.apply_transition(meta, {"type": "phase1a_test_update"}, target)
    duplicate = graph_service.apply_transition(meta, {"type": "phase1a_test_update"}, target)
    stale_meta = meta.model_copy(
        update={"command_id": "command-stale", "idempotency_key": "idempotency-stale"}
    )
    with pytest.raises(WorkflowConflict):
        graph_service.apply_transition(stale_meta, {"type": "phase1a_test_update"}, target)

    assert first.graph_transition is not None
    assert first.graph_transition.created_node_ids == []
    assert first.session.status == first.projection.status
    assert first.session.active_stage == first.projection.active_stage
    assert first.session.reached_stages == first.projection.reachable_stages
    assert first.session.status == SessionState.CLARIFYING
    assert first.session.active_stage == WorkflowStage.PLAN
    assert duplicate.idempotent_replay is True
    assert duplicate.graph_transition == first.graph_transition
    trace = repository.trace("workflow-test-1")
    assert [event.sequence for event in trace] == [1, 2]
    assert trace[-1].payload["transition_plan_checksum"].startswith("sha256:")
    assert trace[-1].payload["document_patch_fields"] == [
        "activeStage",
        "reachedStages",
        "status",
        "updatedAt",
    ]
    assert "document_patch" not in trace[-1].payload


def test_jsonl_trace_redacts_secrets_and_recovers_missing_events(tmp_path: Path) -> None:
    writer = JsonlTraceWriter(lambda session_id: tmp_path / session_id / "trace.jsonl")
    events = [
        TraceEvent(
            session_id="trace-session",
            sequence=1,
            event_type="session.created",
            actor=Actor.USER,
            payload={"token": "do-not-store", "checksum": "sha256:safe"},
        ),
        TraceEvent(
            session_id="trace-session",
            sequence=2,
            event_type="command.dispatched",
            actor=Actor.USER,
            payload={"nested": {"authorization": "Bearer secret"}},
        ),
    ]
    writer.append(events[0])
    writer.recover("trace-session", events)
    writer.recover("trace-session", events)

    lines = [
        json.loads(line)
        for line in (tmp_path / "trace-session" / "trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [line["sequence"] for line in lines] == [1, 2]
    assert lines[0]["payload"]["token"] == "[REDACTED]"
    assert lines[0]["payload"]["checksum"] == "sha256:safe"
    assert lines[1]["payload"]["nested"]["authorization"] == "[REDACTED]"


def test_shared_serialization_fixture_matches_backend_vocabularies() -> None:
    fixture_path = Path(__file__).parents[2] / "contracts" / "workflow_phase1a.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["stages"] == [stage.value for stage in WorkflowStage]
    assert fixture["statuses"] == [state.value for state in SessionState]
