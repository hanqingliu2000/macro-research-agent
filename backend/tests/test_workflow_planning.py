from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from macro_research_agent.workflow.planning_provider import (
    DeterministicPlanningProvider,
    openai_structured_request,
    validate_structured_output,
)
from macro_research_agent.workflow.schemas import ClarificationBatch
from test_workflow_persistence import session_document


def planning_session() -> dict[str, object]:
    document = session_document("planning-1")
    document.update(
        {
            "clarification": {"id": "initial", "questions": [], "answers": {}, "submitted": False},
            "planThread": [],
            "planSnapshots": [],
        }
    )
    return document


def meta(snapshot_hash: str, key: str) -> dict[str, str]:
    return {
        "command_id": f"command-{key}",
        "idempotency_key": key,
        "session_id": "planning-1",
        "expected_stage": "plan",
        "expected_snapshot_hash": snapshot_hash,
        "actor": "user",
        "requested_at": "2026-08-24T12:01:00Z",
    }


def test_follow_up_context_retains_answers_questions_history_and_real_inventory(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    document = planning_session()
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(document))
    document["clarification"] = {
        "questions": [{"id": "measure", "prompt": "Which measure?", "options": ["YoY", "Index"]}],
        "answers": {"measure": "YoY"},
    }
    document["planThread"] = [{"role": "user", "body": "保留六个月预测，关闭Stata"}]
    context = app.state.workflow_planning_service._context(document)
    assert context.clarification_answers == {"measure": "YoY"}
    assert context.clarification_questions[0]["prompt"] == "Which measure?"
    assert context.conversation_history[-1]["body"] == "保留六个月预测，关闭Stata"
    assert {"rolling_mean", "frequency_conversion", "log"} <= set(
        context.available_transformation_ids
    )
    assert "correlation" in context.available_model_ids
    assert context.source_knowledge
    assert {"world_bank", "imf_data"} <= {
        item["connector_id"] for item in context.source_knowledge
    }
    assert all("source_index_snapshot" in item for item in context.source_knowledge)
    assert all(len(item["matched_indicators"]) <= 5 for item in context.source_knowledge)
    assert (context.source_knowledge_catalog_version or "").startswith(
        "source-index-lite-v1:"
    )
    assert len(context.source_knowledge_catalog_sha256 or "") == 64
    assert context.reference_date
    china = app.state.geography_resolver.resolve("China")
    assert [member.code for member in china.members] == ["CHN"]


def test_planning_context_surfaces_executable_wdi_for_expenditure_side_intent(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    document = planning_session()
    document["request"] = (
        "I want to understand whether China's growth model is really shifting from investment "
        "toward household consumption, and whether the pandemic changed that trend."
    )
    document["clarification"] = {
        "questions": [],
        "answers": {
            "scope": "China only; expenditure-side GDP decomposition",
            "measures": "Both level shares and growth contributions",
            "comparison": "Pre/post-2020 descriptive split; annual data from 2000",
        },
    }
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(document))

    context = app.state.workflow_planning_service._context(document)
    wdi = next(
        item
        for item in context.source_knowledge
        if item["connector_id"] == "world_bank" and item["dataset"] == "2"
    )

    assert wdi["executable"] is True
    assert {
        "NY.GDP.MKTP.KD.ZG",
        "NE.GDI.TOTL.ZS",
        "NE.CON.PRVT.ZS",
    } <= {item["code"] for item in wdi["matched_indicators"]}


@pytest.mark.asyncio
async def test_model_cannot_confirm_geography_on_behalf_of_user(tmp_path: Path) -> None:
    class OverconfidentProvider(DeterministicPlanningProvider):
        async def draft_plan(self, context, data_access=None):
            plan = await super().draft_plan(context, data_access)
            for geography in plan.geography_resolutions:
                geography.confirmed = True
            return plan

    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    app.state.workflow_planning_service.provider = OverconfidentProvider()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(
                    created.json()["projection"]["current_snapshot_hash"], "unapproved-geo"
                ),
                "command": {"type": "submit_clarification", "answers": {"geography_scope": "G7"}},
            },
        )
        assert drafted.status_code == 200, drafted.text
        assert not drafted.json()["session"]["currentPlan"]["geographyResolutions"][0]["confirmed"]
        invalid = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(drafted.json()["projection"]["current_snapshot_hash"], "unknown-geo"),
                "command": {"type": "confirm_geography", "resolutionId": "unknown"},
            },
        )
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_backend_owns_clarification_plan_snapshots_and_approval(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        current_hash = created.json()["projection"]["current_snapshot_hash"]
        started = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={"meta": meta(current_hash, "start"), "command": {"type": "start_clarification"}},
        )
        assert started.status_code == 200
        assert len(started.json()["session"]["clarification"]["questions"]) == 2
        replay = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={"meta": meta(current_hash, "start"), "command": {"type": "start_clarification"}},
        )
        assert replay.json()["idempotent_replay"] is True

        current_hash = started.json()["projection"]["current_snapshot_hash"]
        uploaded = await client.post(
            "/api/v1/workflow/sessions/planning-1/sources/uploads",
            files={
                "file": (
                    "private.csv",
                    b"country,period,value\nUSA,2024-Q1,987654.321\n",
                )
            },
        )
        assert uploaded.status_code == 201
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(current_hash, "answers"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "G7",
                        "period_frequency": "2019-2024 quarterly",
                    },
                },
            },
        )
        assert drafted.status_code == 200
        body = drafted.json()
        assert body["session"]["currentPlan"]["dataSources"][0]["connectorId"] == "local_file"
        invocations = body["session"]["currentPlan"]["capabilityInvocations"]
        assert {item["capabilityId"] for item in invocations} >= {
            "connector.local_file",
            "transformation.apply",
            "output.review.visual",
        }
        assert (
            next(item for item in invocations if item["capabilityId"] == "output.review.visual")[
                "availability"
            ]
            == "available"
        )
        assert "987654.321" not in drafted.text

        current_hash = body["projection"]["current_snapshot_hash"]
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(current_hash, "confirm"),
                "command": {"type": "confirm_geography", "resolutionId": "geo-primary"},
            },
        )
        assert confirmed.status_code == 200
        current_hash = confirmed.json()["projection"]["current_snapshot_hash"]
        approved = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={"meta": meta(current_hash, "approve"), "command": {"type": "plan_next"}},
        )
        snapshots = await client.get("/api/v1/workflow/sessions/planning-1/plan/snapshots")
        trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")

    assert approved.status_code == 200
    assert approved.json()["session"]["activeStage"] == "data"
    assert len(snapshots.json()) == 2
    assert snapshots.json()[-1]["approved"] is True
    assert "987654.321" not in trace.text
    event_types = [event["event_type"] for event in trace.json()]
    assert event_types.count("ai.planning_completed") == 2
    planning_event = next(
        event for event in trace.json() if event["event_type"] == "ai.planning_completed"
    )
    assert planning_event["payload"]["source_knowledge_catalog_version"].startswith(
        "source-index-lite-v1:"
    )
    assert len(planning_event["payload"]["source_knowledge_catalog_sha256"]) == 64
    assert "plan.drafted" in event_types
    assert "plan.approved" in event_types
    drafted_event = next(event for event in trace.json() if event["event_type"] == "plan.drafted")
    assert drafted_event["payload"]["added_plan_messages"][1]["body"] == (
        "A structured Plan is ready for review."
    )
    approved_event = next(event for event in trace.json() if event["event_type"] == "plan.approved")
    assert approved_event["payload"]["approved_plan_snapshot_id"]


@pytest.mark.asyncio
async def test_plan_ai_proposals_are_graph_nodes_and_support_partial_or_rejected_apply(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        started = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "p-start"),
                "command": {"type": "start_clarification"},
            },
        )
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(started.json()["projection"]["current_snapshot_hash"], "p-draft"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "G7",
                        "period_frequency": "2019-2024 quarterly",
                    },
                },
            },
        )
        original_objective = drafted.json()["session"]["currentPlan"]["objective"]
        proposed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(drafted.json()["projection"]["current_snapshot_hash"], "p-propose"),
                "command": {"type": "propose_plan_patch", "request": "Add robustness."},
            },
        )
        proposal_id = proposed.json()["session"]["pendingPlanPatch"]["id"]
        graph = await client.get("/api/v1/admin/workflow/sessions/planning-1/graph")
        proposal_node = next(
            node for node in graph.json()["nodes"] if node["node_id"] == f"node-{proposal_id}"
        )
        applied = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(proposed.json()["projection"]["current_snapshot_hash"], "p-apply"),
                "command": {
                    "type": "apply_plan_patch",
                    "acceptedFields": ["assumptions"],
                },
            },
        )
        proposed_again = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(applied.json()["projection"]["current_snapshot_hash"], "p-again"),
                "command": {"type": "propose_plan_patch", "request": "Add report."},
            },
        )
        rejected = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(
                    proposed_again.json()["projection"]["current_snapshot_hash"],
                    "p-reject",
                ),
                "command": {"type": "reject_plan_patch"},
            },
        )
        rejected_graph = await client.get("/api/v1/admin/workflow/sessions/planning-1/graph")

    assert proposed.status_code == 200
    assert proposal_node["authority"] == "proposal"
    assert proposal_node["lifecycle"] == "waiting_for_review"
    assert proposal_node["input_refs"] == [
        proposed.json()["session"]["pendingPlanPatch"]["targetSnapshotHash"]
    ]
    assert applied.status_code == 200
    assert applied.json()["session"]["currentPlan"]["objective"] == original_objective
    assert applied.json()["session"]["currentPlan"]["assumptions"][-1] == "Add robustness."
    assert applied.json()["session"].get("pendingPlanPatch") is None
    assert rejected.status_code == 200
    assert rejected.json()["session"].get("pendingPlanPatch") is None
    rejected_id = proposed_again.json()["session"]["pendingPlanPatch"]["id"]
    rejected_node = next(
        node for node in rejected_graph.json()["nodes"] if node["node_id"] == f"node-{rejected_id}"
    )
    assert rejected_node["lifecycle"] == "stale"
    assert rejected.json()["projection"]["status"] == "plan_review"


@pytest.mark.asyncio
async def test_plan_supports_two_clarification_rounds_and_preserves_graph_history(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        first = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "round-1"),
                "command": {"type": "start_clarification"},
            },
        )
        first_draft = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(first.json()["projection"]["current_snapshot_hash"], "draft-1"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "G7",
                        "period_frequency": "2019-2024 quarterly",
                    },
                },
            },
        )
        second = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(first_draft.json()["projection"]["current_snapshot_hash"], "round-2"),
                "command": {"type": "request_plan_clarification"},
            },
        )
        second_draft = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(second.json()["projection"]["current_snapshot_hash"], "draft-2"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "Euro area",
                        "period_frequency": "2019-2024 monthly",
                    },
                },
            },
        )
        graph = await client.get("/api/v1/admin/workflow/sessions/planning-1/graph")
        trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")

    assert first.status_code == 200
    assert first.json()["session"]["clarification"]["round"] == 1
    assert second.status_code == 200
    assert second.json()["session"]["clarification"]["round"] == 2
    assert second.json()["session"]["status"] == "plan_review"
    assert second_draft.status_code == 200
    assert second_draft.json()["session"]["currentPlan"]["period"]["frequency"] == "monthly"
    proposal_nodes = [
        node
        for node in graph.json()["nodes"]
        if node["kind"] == "clarification_batch" and node["authority"] == "proposal"
    ]
    assert len(proposal_nodes) == 2
    assert all(node["lifecycle"] == "completed" for node in proposal_nodes)
    event_types = [event["event_type"] for event in trace.json()]
    assert "plan.clarification_requested" in event_types
    assert event_types.count("ai.planning_completed") == 4


@pytest.mark.asyncio
async def test_manual_plan_save_makes_an_older_ai_patch_stale(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        started = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "s-start"),
                "command": {"type": "start_clarification"},
            },
        )
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(started.json()["projection"]["current_snapshot_hash"], "s-draft"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "G7",
                        "period_frequency": "2019-2024 quarterly",
                    },
                },
            },
        )
        proposed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(drafted.json()["projection"]["current_snapshot_hash"], "s-propose"),
                "command": {"type": "propose_plan_patch", "request": "Add robustness."},
            },
        )
        saved = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(proposed.json()["projection"]["current_snapshot_hash"], "s-save"),
                "command": {
                    "type": "save_plan",
                    "changes": {"objective": "A human-authored objective."},
                    "actor": "user",
                },
            },
        )
        stale_apply = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(saved.json()["projection"]["current_snapshot_hash"], "s-apply"),
                "command": {"type": "apply_plan_patch"},
            },
        )
        current = await client.get("/api/v1/workflow/sessions/planning-1")

    assert saved.status_code == 200
    assert stale_apply.status_code == 422
    assert "Plan changed" in stale_apply.json()["detail"]
    assert current.json()["session"]["currentPlan"]["objective"] == "A human-authored objective."
    assert (
        current.json()["session"]["pendingPlanPatch"]["id"]
        == proposed.json()["session"]["pendingPlanPatch"]["id"]
    )


@pytest.mark.asyncio
async def test_planned_connector_cannot_cross_plan_approval_gate(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        started = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "start"),
                "command": {"type": "start_clarification"},
            },
        )
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(started.json()["projection"]["current_snapshot_hash"], "answers"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "Use the economies in my request",
                        "period_frequency": "2015-2024 annual",
                    },
                },
            },
        )
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(drafted.json()["projection"]["current_snapshot_hash"], "confirm"),
                "command": {"type": "confirm_geography", "resolutionId": "geo-primary"},
            },
        )
        rejected = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(confirmed.json()["projection"]["current_snapshot_hash"], "approve"),
                "command": {"type": "plan_next"},
            },
        )

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "connector_unavailable"
    assert "IMF Data is planned but unavailable" in rejected.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_plan_command_rejects_stale_hash_and_generic_endpoint_is_retired(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        generic = await client.post(
            "/api/v1/workflow/sessions/planning-1/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "generic"),
                "command": {"type": "submit_clarification", "answers": {}},
            },
        )
        stale = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta("sha256:stale", "stale"),
                "command": {"type": "start_clarification"},
            },
        )
    assert generic.status_code == 404
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_controlled_geography_resolver_is_versioned(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/workflow/geographies/resolve", json={"intent": "eurozone"}
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "country_group"
    assert response.json()["registry_version"] == "mra-geography-v1"
    assert len(response.json()["members"]) == 20


def test_structured_output_validation_and_request_builder() -> None:
    payload = {
        "questions": [
            {"question_id": "q1", "prompt": "Scope?", "options": ["Requested", "Broader"]}
        ],
        "answered": {},
    }
    validated = validate_structured_output(ClarificationBatch, payload)
    request = openai_structured_request(
        model="configured-later",
        instructions="Return one clarification batch.",
        input_text="Snapshot-bound data-aware planning context",
        output_model=ClarificationBatch,
    )
    assert validated.questions[0].question_id == "q1"
    assert request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
