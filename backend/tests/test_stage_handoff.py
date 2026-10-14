from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.workflow.handoff import build_stage_handoff
from macro_research_agent.workflow.stage_adapters import (
    DeepSeekStageAssistant,
    StageProviderError,
)
from macro_research_agent.workflow.stage_assistant import DataAssistantProposal
from macro_research_agent.workflow.states import WorkflowStage
from test_workflow_planning import meta, planning_session


def legacy_session() -> dict[str, object]:
    session = planning_session()
    session["currentPlan"] = {
        "objective": "Compare inflation and policy rates.",
        "geographyIntent": "USA",
        "period": {"start": "2019", "end": "2024", "frequency": "annual"},
        "geographyResolutions": [],
        "dataSources": [
            {
                "id": "source-1",
                "connectorId": "local_file",
                "provider": "Local",
                "dataset": "uploaded_file",
                "indicators": ["CPI", "RATE"],
                "queryIntent": "Use the approved upload.",
                "enabled": True,
            }
        ],
        "transformationIntents": [],
        "modelIntents": [
            {"id": "ols", "label": "Regression", "enabled": True, "targetIndicators": []}
        ],
        "capabilityInvocations": [],
        "deliverables": {
            "charts": True,
            "tables": True,
            "cleanData": True,
            "python": True,
            "stata": False,
            "researchReport": True,
        },
        "assumptions": [],
        "warnings": [],
        "unresolvedItems": [],
    }
    session["currentPlanSnapshotId"] = "plan-legacy"
    return session


def test_legacy_handoff_marks_unknown_model_roles_for_confirmation() -> None:
    session = legacy_session()

    handoff = build_stage_handoff(session, WorkflowStage.DATA, inferred=True)

    assert handoff.schema_version == "mra-stage-handoff-v1"
    assert any(item.status == "needs_confirmation" for item in handoff.decisions)
    assert all(
        item.status == "inferred"
        for item in handoff.decisions
        if item.category != "indicator_role"
    )


def test_materialized_legacy_roles_remain_unconfirmed_until_user_resolution() -> None:
    session = legacy_session()
    plan = session["currentPlan"]
    assert isinstance(plan, dict)
    model_intents = plan["modelIntents"]
    assert isinstance(model_intents, list)
    model_intents[0] = {
        "capabilityId": "ols",
        "id": "ols",
        "purpose": "Regression",
        "enabled": True,
        "variables": [
            {"indicatorCode": "CPI", "role": "dependent", "order": 1},
            {"indicatorCode": "RATE", "role": "independent", "order": 2},
        ],
        "targetIndicators": ["CPI", "RATE"],
        "roleInferenceStatus": "needs_confirmation",
    }

    handoff = build_stage_handoff(session, WorkflowStage.DATA)

    role_decision = next(item for item in handoff.decisions if item.category == "indicator_role")
    assert role_decision.status == "needs_confirmation"


@pytest.mark.asyncio
async def test_user_can_confirm_and_resolve_lazy_legacy_handoff(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": legacy_session()}
        )
        listed = await client.get("/api/v1/workflow/sessions/planning-1/handoffs")
        decisions = listed.json()[0]["decisions"]
        unresolved = next(item for item in decisions if item["status"] == "needs_confirmation")
        inferred_ids = [item["id"] for item in decisions if item["status"] == "inferred"]
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/handoff/commands",
            json={
                "meta": meta(
                    created.json()["projection"]["current_snapshot_hash"],
                    "confirm-legacy-handoff",
                ),
                "command": {"type": "confirm_decisions", "decisionIds": inferred_ids},
            },
        )
        response = await client.post(
            "/api/v1/workflow/sessions/planning-1/handoff/commands",
            json={
                "meta": meta(
                    confirmed.json()["projection"]["current_snapshot_hash"],
                    "resolve-legacy-role",
                ),
                "command": {
                    "type": "resolve_decision",
                    "decisionId": unresolved["id"],
                    "value": "OLS: dependent CPI; independent RATE",
                },
            },
        )

    assert response.status_code == 200, response.text
    handoffs = response.json()["session"]["handoffs"]
    assert len(handoffs) == 3
    assert handoffs[-1]["supersedesHandoffId"] == handoffs[-2]["handoffId"]
    assert all(item["status"] == "confirmed" for item in handoffs[-1]["decisions"])


def test_deepseek_stage_adapter_repairs_invalid_contract_once() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        content = "{}" if len(calls) == 1 else json.dumps(
            {"summary": "No change required.", "operations": [], "source_mappings": []}
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    adapter = DeepSeekStageAssistant(
        role="data",
        api_key="test-key",
        model_id="deepseek-test",
        endpoint="https://example.invalid/chat",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = adapter._call(
        {"evidence": []},
        DataAssistantProposal,
        lambda proposal: None,
    )

    assert result.summary == "No change required."
    assert len(calls) == 2
    assert "invalid_model_contract" in str(calls[-1]["messages"])


def test_deepseek_stage_adapter_fails_closed_on_rate_limit() -> None:
    adapter = DeepSeekStageAssistant(
        role="analysis",
        api_key="test-key",
        model_id="deepseek-test",
        endpoint="https://example.invalid/chat",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(429, request=request))
        ),
    )

    with pytest.raises(StageProviderError, match="manual typed controls") as captured:
        adapter._call({"evidence": []}, DataAssistantProposal, lambda proposal: None)

    assert captured.value.code == "provider_unavailable"
