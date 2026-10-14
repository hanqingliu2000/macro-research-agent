from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.capabilities.contracts import CapabilityInvocationIntent
from macro_research_agent.capabilities.executor import CapabilityExecutionError
from macro_research_agent.config import Settings
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from macro_research_agent.workflow.states import SessionState
from test_workflow_graph import session_document


@pytest.mark.asyncio
async def test_registry_discovery_separates_available_and_planned_by_stage(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        available = await client.get(
            "/api/v1/registry/capabilities?stage=plan&availability=available"
        )
        planned = await client.get(
            "/api/v1/registry/capabilities?stage=output&availability=planned"
        )
        output_available = await client.get(
            "/api/v1/registry/capabilities?stage=output&availability=available"
        )
        skills = await client.get("/api/v1/registry/skills?stage=output&availability=planned")
        inspection = await client.get("/api/v1/admin/registry")

    assert available.status_code == 200
    assert {item["capability_id"] for item in available.json()} == {
        "connector.adb",
        "connector.bis",
        "connector.ecb",
        "connector.eurostat",
        "connector.imf_data",
        "connector.local_file",
        "connector.oecd",
        "connector.un_sdg",
        "connector.world_bank",
        "geography.resolve",
    }
    planned_ids = {item["capability_id"] for item in planned.json()}
    assert planned_ids == set()
    output_available_ids = {item["capability_id"] for item in output_available.json()}
    assert output_available_ids >= {
        "artifact.regenerate",
        "artifact.report.generate",
        "artifact.report.revise",
        "output.review.structural",
        "output.review.semantic_report",
        "output.review.visual",
        "output.review.remote_visual",
    }
    assert skills.json() == []
    assert len(inspection.json()["capabilities"]) > len(available.json())
    assert inspection.json()["skills"]
    imf = next(
        item
        for item in inspection.json()["capabilities"]
        if item["capability_id"] == "connector.imf_data"
    )
    assert imf["availability"] == "available"
    assert imf["handler_ref"] == "workflow.data:imf_data"
    assert imf["approval_policy"] == "research_plan"


def test_capability_executor_validates_policy_and_writes_value_free_receipts(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path))
    repository = app.state.workflow_repository
    repository.create(WorkflowSessionDocument.model_validate(session_document()))
    executor = app.state.capability_executor
    success = executor.execute(
        CapabilityInvocationIntent(
            invocation_id="resolve-g7",
            session_id="graph-session",
            stage="plan",
            target_snapshot_hash="sha256:plan",
            capability_id="geography.resolve",
            capability_version="1.0.0",
            purpose="Resolve the reviewed group name.",
            arguments={"intent": "G7"},
            expected_output_role="geography_resolution",
            skill_id="workflow.plan.resolve_scope",
            skill_version="1.0.0",
        )
    )
    assert success.status == "completed"
    assert success.output is not None
    assert len(success.output["members"]) == 7
    assert success.result_refs == ["geography:group-g7@mra-geography-v1"]
    graph_node = repository.get_graph_node("graph-session", "capability-resolve-g7")
    assert graph_node.authority == "execution"
    assert graph_node.lifecycle == "completed"
    assert graph_node.capability_version == "1.0.0"
    assert graph_node.output_refs == success.result_refs

    with pytest.raises(CapabilityExecutionError) as planned:
        executor.execute(
            CapabilityInvocationIntent(
                invocation_id="try-imf",
                session_id="graph-session",
                stage="data",
                target_snapshot_hash="sha256:plan",
                capability_id="output.review.remote_visual",
                capability_version="1.0.0",
                purpose="Acquire data.",
                arguments={"request": {}},
                expected_output_role="source_snapshot",
            )
        )
    assert planned.value.code == "stage_not_allowed"

    for unsafe_id in (
        "browser.open",
        "network.fetch",
        "filesystem.read",
        "python.exec",
        "shell.exec",
        "stata.exec",
    ):
        with pytest.raises(CapabilityExecutionError) as arbitrary:
            executor.execute(
                CapabilityInvocationIntent(
                    invocation_id=f"try-{unsafe_id}",
                    session_id="graph-session",
                    stage="data",
                    target_snapshot_hash="sha256:plan",
                    capability_id=unsafe_id,
                    capability_version="1.0.0",
                    purpose="Bypass execution policy.",
                    arguments={"target": "unregistered"},
                    expected_output_role="source_snapshot",
                )
            )
        assert arbitrary.value.code == "capability_not_registered"

    with pytest.raises(CapabilityExecutionError) as typed_boundary:
        executor.execute(
            CapabilityInvocationIntent(
                invocation_id="bypass-data-command",
                session_id="graph-session",
                stage="data",
                target_snapshot_hash="sha256:data",
                capability_id="data.prepare",
                capability_version="1.0.0",
                purpose="Try to bypass the typed stage command.",
                arguments={"operation": "sort", "parameters": {}},
                expected_output_role="dataset_snapshot",
            )
        )
    assert typed_boundary.value.code == "typed_boundary_required"

    receipts = [
        event
        for event in repository.trace("graph-session")
        if event.event_type.startswith("capability.invocation_")
    ]
    assert receipts[0].payload["status"] == "completed"
    assert all(event.payload["status"] == "blocked" for event in receipts[1:])
    assert receipts[0].payload["capability_version"] == "1.0.0"
    assert receipts[0].payload["skill_id"] == "workflow.plan.resolve_scope"
    assert receipts[0].payload["skill_version"] == "1.0.0"
    assert receipts[0].payload["result_refs"] == success.result_refs
    assert receipts[0].payload["argument_checksum"].startswith("sha256:")
    assert "arguments" not in receipts[0].payload
    assert "G7" not in str(receipts[0].payload)
    assert repository.get("graph-session").projection.status == SessionState.PLAN_REVIEW
