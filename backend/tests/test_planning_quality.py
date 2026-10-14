from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from macro_research_agent.workflow.planning_provider import (
    DeterministicPlanningProvider,
    WorkflowPlanningContext,
)


@pytest.mark.asyncio
async def test_reviewed_planning_quality_cases_match_typed_expectations() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "planning_quality_cases.json"
    cases: list[dict[str, Any]] = json.loads(fixture_path.read_text())
    provider = DeterministicPlanningProvider()

    for case in cases:
        context = WorkflowPlanningContext(
            research_request=case["research_request"],
            clarification_answers=case["answers"],
            available_connector_ids=["local_file"],
            available_transformation_ids=["yoy_growth"],
            available_model_ids=["descriptive"],
            available_deliverable_ids=["charts", "tables", "clean_data"],
            uploaded_schema_summaries=(
                [{"upload_id": "reviewed-upload", "columns": ["period", "value"]}]
                if case["uploaded"]
                else []
            ),
        )

        plan = await provider.draft_plan(context)
        expected = case["expected"]

        assert case["reviewed"] is True
        assert plan.data_sources[0].connector_id == expected["connector_id"], case["case_id"]
        assert plan.period.frequency == expected["frequency"], case["case_id"]
        actual_capabilities = {
            invocation.capability_id for invocation in plan.capability_invocations
        }
        assert set(expected["capability_ids"]) <= actual_capabilities, case["case_id"]
        assert any(expected["unresolved_contains"] in item for item in plan.unresolved_items), case[
            "case_id"
        ]
