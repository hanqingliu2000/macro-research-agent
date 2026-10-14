from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from macro_research_agent.workflow.planning_provider import DeterministicPlanningProvider
from macro_research_agent.workflow.schemas import TitledPlanDraft
from test_workflow_planning import meta, planning_session


@pytest.mark.asyncio
async def test_delete_restore_is_durable_recoverable_and_does_not_change_graph(tmp_path: Path):
    settings = Settings(environment="test", runtime_dir=tmp_path, llm_provider="test")
    app = create_app(settings)
    repository = app.state.workflow_repository
    repository.create(WorkflowSessionDocument.model_validate(planning_session()))
    before = repository.graph_snapshot("planning-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        deleted = await client.delete("/api/v1/workflow/sessions/planning-1")
        assert deleted.status_code == 200
        assert deleted.json()["session"]["archived"]
        repeated = await client.delete("/api/v1/workflow/sessions/planning-1")
        assert repeated.json() == deleted.json()
        blocked = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(deleted.json()["projection"]["current_snapshot_hash"], "deleted"),
                "command": {"type": "submit_clarification", "answers": {}},
            },
        )
        assert blocked.status_code == 409
        assert (await client.delete("/api/v1/workflow/sessions/missing")).status_code == 404
    restarted = create_app(settings)
    assert restarted.state.workflow_repository.get("planning-1").session.archived
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        restored = await client.post("/api/v1/workflow/sessions/planning-1/restore")
        assert restored.status_code == 200
        assert not restored.json()["session"]["archived"]
    assert restarted.state.workflow_repository.graph_snapshot("planning-1") == before
    events = restarted.state.workflow_repository.trace("planning-1")
    assert [
        e.event_type for e in events if e.event_type in {"session.deleted", "session.restored"}
    ] == ["session.deleted", "session.restored"]


@pytest.mark.asyncio
async def test_first_draft_sets_title_and_follow_up_keeps_it(tmp_path: Path):
    class Provider(DeterministicPlanningProvider):
        async def draft_plan(self, context, data_access=None):
            plan = await super().draft_plan(context, data_access)
            return TitledPlanDraft(**plan.model_dump(), session_title="China inflation outlook")

    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    app.state.workflow_planning_service.provider = Provider()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        prompt = (
            "Investigate China's inflation over the last 36 months and project the next six months."
        )
        created = await client.post("/api/v1/workflow/sessions", json={"request": prompt})
        assert created.status_code == 201, created.text
        record = created.json()
        assert record["session"]["title"] == prompt
        session_id = record["session"]["id"]
        for index in range(2):
            metadata = meta(record["projection"]["current_snapshot_hash"], f"title-{index}")
            metadata["session_id"] = session_id
            response = await client.post(
                f"/api/v1/workflow/sessions/{session_id}/plan/commands",
                json={"meta": metadata, "command": {"type": "submit_clarification", "answers": {}}},
            )
            assert response.status_code == 200, response.text
            record = response.json()
            assert record["session"]["title"] == "China inflation outlook"


def test_imf_public_access_does_not_require_credentials():
    from macro_research_agent.connectors.registry import capability_for

    assert capability_for("imf_data").authentication == "none"
    assert capability_for("imf_data").availability == "available"
    assert capability_for("world_bank").authentication == "none"
    assert capability_for("world_bank").availability == "available"
    assert capability_for("oecd").authentication == "none"
    assert capability_for("oecd").availability == "available"
    assert capability_for("eurostat").authentication == "none"
    assert capability_for("eurostat").availability == "available"
    assert capability_for("adb").authentication == "none"
    assert capability_for("adb").availability == "available"
    assert capability_for("ecb").availability == "available"
    assert capability_for("bis").availability == "available"
    assert capability_for("un_sdg").availability == "available"
