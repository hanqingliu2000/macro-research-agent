from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from macro_research_agent.workflow.stage_assistant import (
    AnalysisAssistantProposal,
    AnalysisModelProposal,
    AnalysisOperationProposal,
    DataAssistantProposal,
    DataOperationProposal,
    parse_analysis_request_intent,
    parse_data_request_intent,
    validate_analysis_proposal_constraints,
    validate_data_proposal_constraints,
)
from test_workflow_data_workspace import approved_data_client, command_meta
from test_workflow_pipeline import pipeline_command


async def data_command(
    client: Any, current: dict[str, Any], key: str, command: dict[str, Any]
) -> Any:
    return await client.post(
        "/api/v1/workflow/sessions/planning-1/data/commands",
        json={
            "meta": command_meta(current["projection"]["current_snapshot_hash"], key),
            "command": command,
        },
    )


def test_analysis_proposal_guard_rejects_provider_that_ignores_explicit_subset() -> None:
    rows = [
        {"indicator_code": "NY.GDP.MKTP.KD.ZG"},
        {"indicator_code": "NE.GDI.TOTL.ZS"},
        {"indicator_code": "NE.CON.PRVT.ZS"},
    ]
    request = (
        "Keep NY.GDP.MKTP.KD.ZG unchanged. Apply a first difference only to "
        "NE.GDI.TOTL.ZS and NE.CON.PRVT.ZS."
    )
    invalid = AnalysisAssistantProposal(
        summary="Incorrect provider output.",
        operations=[
            AnalysisOperationProposal(
                proposal_item_id="bad-growth",
                operation="yoy_growth",
                indicators=[row["indicator_code"] for row in rows],
                rationale="Incorrectly transformed every series.",
            )
        ],
    )

    with pytest.raises(ValueError, match="requested difference"):
        validate_analysis_proposal_constraints(request, rows, invalid)


def test_analysis_proposal_guard_rejects_transformation_when_forbidden() -> None:
    rows = [{"indicator_code": "GDP"}, {"indicator_code": "DEBT"}]
    invalid = AnalysisAssistantProposal(
        summary="Incorrect provider output.",
        operations=[
            AnalysisOperationProposal(
                proposal_item_id="bad-growth",
                operation="yoy_growth",
                indicators=["GDP", "DEBT"],
                rationale="Incorrectly adds a transformation.",
            )
        ],
        models=[
            AnalysisModelProposal(
                proposal_item_id="analysis-var",
                model="var",
                variables=["GDP", "DEBT"],
                parameters={"forecastSteps": 2},
                rationale="Requested model.",
            )
        ],
    )

    with pytest.raises(ValueError, match="forbidden transformation"):
        validate_analysis_proposal_constraints(
            "Use one VAR over GDP and DEBT, forecasting exactly 2 annual periods. "
            "Do not add transformations.",
            rows,
            invalid,
        )


def test_analysis_intent_scopes_var_variables_and_lag_as_model_parameter() -> None:
    rows = [
        {"indicator_code": "NE.GDI.FTOT.ZS"},
        {"indicator_code": "NE.CON.PRVT.ZS"},
        {"indicator_code": "NY.GDP.MKTP.KD.ZG"},
    ]
    request = (
        "Revise only the joint VAR specification so ordered endogenous indicators are exactly "
        "NE.GDI.FTOT.ZS and NE.CON.PRVT.ZS, with one fixed lag, constant trend, and two forecast "
        "periods. Keep NY.GDP.MKTP.KD.ZG only in the descriptive correlation job. Preserve the "
        "other two analysis jobs unchanged."
    )

    intent = parse_analysis_request_intent(request, rows)

    assert intent.model_kind == "var"
    assert intent.model_variables == ("NE.CON.PRVT.ZS", "NE.GDI.FTOT.ZS")
    assert intent.forecast_steps == 2
    assert intent.replace_models is True
    assert intent.operation is None
    assert intent.has_explicit_operation is False


@pytest.mark.asyncio
async def test_analysis_assistant_value_error_is_governed_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data_current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2023,CPI,100\nUSA,2024,CPI,103\n",
        include_plan_analysis=False,
    )
    entered = await data_command(
        client, data_current, "analysis-error-enter", {"type": "data_next"}
    )
    service = client._transport.app.state.workflow_pipeline_service  # type: ignore[attr-defined]

    def invalid_proposal(*_args: Any, **_kwargs: Any) -> AnalysisAssistantProposal:
        raise ValueError("Rejected invalid assistant proposal.")

    monkeypatch.setattr(service.assistant, "propose_analysis", invalid_proposal)
    response = await pipeline_command(
        client,
        entered.json(),
        "analysis-error-propose",
        {"type": "propose_analysis_assistance", "request": "Revise the VAR."},
    )
    await client.aclose()

    assert response.status_code == 422
    assert response.json()["detail"] == "Rejected invalid assistant proposal."


def test_data_proposal_guard_rejects_missing_filter_when_rows_must_be_preserved() -> None:
    invalid = DataAssistantProposal(
        summary="Incorrect provider output.",
        operations=[
            DataOperationProposal(
                proposal_item_id="drop-missing",
                operation="filter_missing",
                rationale="Incorrectly removes missing rows.",
            )
        ],
    )

    with pytest.raises(ValueError, match="preserve missing"):
        validate_data_proposal_constraints(
            "Keep all missing rows; do not filter or delete them.", invalid
        )


def test_data_intent_does_not_confuse_non_missing_preservation_with_missing_rows() -> None:
    intent = parse_data_request_intent(
        "Remove only rows where value is null. Preserve all six columns and all non-missing "
        "observations, and sort by indicator_code then period ascending."
    )

    assert intent.preserve_missing is False
    assert intent.sort_only is False


@pytest.mark.asyncio
async def test_data_assistant_honors_explicit_null_removal_with_valid_row_preservation(
    tmp_path: Path,
) -> None:
    client, current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2023,CPI,100\nUSA,2024,CPI,\n",
    )
    proposed = await data_command(
        client,
        current,
        "data-ai-explicit-null-removal",
        {
            "type": "propose_data_assistance",
            "request": (
                "Remove only rows where value is null. Preserve all six columns and all "
                "non-missing observations, and sort by indicator_code then period ascending."
            ),
        },
    )
    await client.aclose()

    assert proposed.status_code == 200, proposed.text
    operations = proposed.json()["session"]["data"]["pendingAssistantProposal"]["operations"]
    assert [item["operation"] for item in operations] == ["filter_missing", "sort"]
    assert operations[0]["parameters"] == {"column": "value"}


@pytest.mark.asyncio
async def test_data_assistant_reads_values_and_applies_selected_typed_steps(
    tmp_path: Path,
) -> None:
    client, current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value\n"
        b"USA,2024-Q2,CPI,3.0\n"
        b"USA,2024-Q1,CPI,\n",
    )
    proposed = await data_command(
        client,
        current,
        "data-ai-propose",
        {"type": "propose_data_assistance", "request": "Review missing values."},
    )
    proposal = proposed.json()["session"]["data"]["pendingAssistantProposal"]
    graph = await client.get("/api/v1/admin/workflow/sessions/planning-1/graph")
    applied = await data_command(
        client,
        proposed.json(),
        "data-ai-apply",
        {"type": "apply_data_assistance", "acceptedItemIds": ["data-filter-missing"]},
    )
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")
    await client.aclose()

    assert proposed.status_code == 200, proposed.text
    assert {item["id"] for item in proposal["operations"]} == {
        "data-filter-missing",
        "data-sort",
    }
    node = next(
        item for item in graph.json()["nodes"] if item["node_id"] == f"node-{proposal['id']}"
    )
    assert node["authority"] == "proposal"
    assert node["input_refs"] == [proposal["targetSnapshotHash"]]
    assert applied.status_code == 200, applied.text
    assert applied.json()["session"]["data"]["quality"]["observations"] == 1
    assert applied.json()["session"]["data"].get("pendingAssistantProposal") is None
    event_types = [event["event_type"] for event in trace.json()]
    assert "ai.data_assistance_completed" in event_types
    assert "ai.data_accessed" in event_types


@pytest.mark.asyncio
async def test_data_assistant_reports_missing_locations_and_honors_sort_only(
    tmp_path: Path,
) -> None:
    client, current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value\n"
        b"USA,2024-Q2,CPI,3.0\n"
        b"USA,2024-Q1,CPI,\n",
    )
    proposed = await data_command(
        client,
        current,
        "data-ai-preserve-missing",
        {
            "type": "propose_data_assistance",
            "request": (
                "Review the missing observations and tell me where they occur. Keep all missing "
                "rows for now; do not filter or delete them. Propose only a deterministic sort "
                "if useful."
            ),
        },
    )
    await client.aclose()

    assert proposed.status_code == 200, proposed.text
    proposal = proposed.json()["session"]["data"]["pendingAssistantProposal"]
    assert [item["operation"] for item in proposal["operations"]] == ["sort"]
    assert "Read-only diagnostic" in proposal["summary"]
    assert "Proposed 1 mutating operation" in proposal["summary"]
    assert proposal["diagnostics"] == [
        {
            "kind": "missing_observations",
            "summary": "Found 1 row(s) with a missing analytical value.",
            "details": ["USA · CPI · 2024-Q1"],
        }
    ]


@pytest.mark.asyncio
async def test_data_assistant_proposes_editable_source_schema_mapping(tmp_path: Path) -> None:
    client, current = await approved_data_client(
        tmp_path,
        b"economy_label,time_label,measure_label,observation_value\nUSA,2024,CPI,3.0\n",
    )
    assert current["session"]["data"]["activeSnapshotId"] == ""
    proposed = await data_command(
        client,
        current,
        "mapping-ai-propose",
        {"type": "propose_data_assistance", "request": "Map this local file."},
    )
    proposal = proposed.json()["session"]["data"]["pendingAssistantProposal"]
    first = proposal["sourceMappings"][0]
    applied = await data_command(
        client,
        proposed.json(),
        "mapping-ai-apply",
        {"type": "apply_data_assistance", "acceptedItemIds": [first["id"]]},
    )
    await client.aclose()

    assert proposed.status_code == 200, proposed.text
    assert proposal["operations"] == []
    assert len(proposal["sourceMappings"]) == 4
    assert applied.status_code == 200, applied.text
    mapping = applied.json()["session"]["data"]["sourceMappingDraft"]["mappings"]
    assert mapping[first["sourceColumn"]] == first["role"]


@pytest.mark.asyncio
async def test_analysis_assistant_is_selective_and_stale_safe(tmp_path: Path) -> None:
    client, data_current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value\n"
        b"USA,2023,CPI,100\n"
        b"USA,2024,CPI,103\n",
        include_plan_analysis=False,
    )
    entered = await data_command(
        client, data_current, "analysis-enter", {"type": "data_next"}
    )
    proposed = await pipeline_command(
        client,
        entered.json(),
        "analysis-ai-propose",
        {"type": "propose_analysis_assistance", "request": "Compare inflation."},
    )
    proposal = proposed.json()["session"]["pipeline"]["pendingAssistantProposal"]
    applied = await pipeline_command(
        client,
        proposed.json(),
        "analysis-ai-apply",
        {
            "type": "apply_analysis_assistance",
            "acceptedItemIds": ["analysis-descriptive"],
        },
    )
    proposed_again = await pipeline_command(
        client,
        applied.json(),
        "analysis-ai-again",
        {"type": "propose_analysis_assistance", "request": "Add growth."},
    )
    manually_changed = await pipeline_command(
        client,
        proposed_again.json(),
        "analysis-manual-edit",
        {"type": "add_pipeline_operation", "operation": "difference"},
    )
    stale = await pipeline_command(
        client,
        manually_changed.json(),
        "analysis-stale-apply",
        {
            "type": "apply_analysis_assistance",
            "acceptedItemIds": ["analysis-yoy-growth"],
        },
    )
    await client.aclose()

    assert proposed.status_code == 200, proposed.text
    assert {item["id"] for item in [*proposal["operations"], *proposal["models"]]} == {
        "analysis-yoy-growth",
        "analysis-descriptive",
    }
    assert applied.status_code == 200, applied.text
    assert applied.json()["session"]["pipeline"]["operations"] == []
    assert applied.json()["session"]["pipeline"]["models"][0]["kind"] == "descriptive"
    assert applied.json()["session"]["activeStage"] == "transformation"
    assert applied.json()["session"]["pipeline"]["runStatus"] == "editing"
    assert stale.status_code == 422
    assert "Pipeline changed" in stale.json()["detail"]


@pytest.mark.asyncio
async def test_analysis_assistant_honors_difference_subset_and_unchanged_indicator(
    tmp_path: Path,
) -> None:
    client, data_current = await approved_data_client(
        tmp_path,
        b"country,period,indicator,value,unit,indicator_name\n"
        b"CHN,2023,NY.GDP.MKTP.KD.ZG,5.2,Percent,GDP growth (annual %)\n"
        b"CHN,2024,NY.GDP.MKTP.KD.ZG,5.0,Percent,GDP growth (annual %)\n"
        b"CHN,2023,NE.GDI.TOTL.ZS,42.1,Percent of GDP,Gross capital formation (% of GDP)\n"
        b"CHN,2024,NE.GDI.TOTL.ZS,41.3,Percent of GDP,Gross capital formation (% of GDP)\n"
        b"CHN,2023,NE.CON.PRVT.ZS,39.2,Percent of GDP,Household consumption (% of GDP)\n"
        b"CHN,2024,NE.CON.PRVT.ZS,39.8,Percent of GDP,Household consumption (% of GDP)\n",
        include_plan_analysis=False,
    )
    entered = await data_command(
        client, data_current, "analysis-subset-enter", {"type": "data_next"}
    )
    automatic = await pipeline_command(
        client,
        entered.json(),
        "analysis-rate-safe-propose",
        {"type": "propose_analysis_assistance", "request": "Compare growth patterns."},
    )
    automatic_operation = automatic.json()["session"]["pipeline"][
        "pendingAssistantProposal"
    ]["operations"][0]
    assert "NY.GDP.MKTP.KD.ZG" not in automatic_operation["indicators"]
    rejected = await pipeline_command(
        client,
        automatic.json(),
        "analysis-rate-safe-reject",
        {"type": "reject_analysis_assistance"},
    )
    request = (
        "Keep NY.GDP.MKTP.KD.ZG unchanged because it is already a growth rate. "
        "Apply a first difference in percentage points only to NE.GDI.TOTL.ZS and "
        "NE.CON.PRVT.ZS, with no duplicate transformation."
    )
    proposed = await pipeline_command(
        client,
        rejected.json(),
        "analysis-subset-propose",
        {"type": "propose_analysis_assistance", "request": request},
    )

    assert proposed.status_code == 200, proposed.text
    proposal = proposed.json()["session"]["pipeline"]["pendingAssistantProposal"]
    assert proposal["models"] == []
    assert len(proposal["operations"]) == 1
    operation = proposal["operations"][0]
    assert operation["id"] == "analysis-difference"
    assert operation["operation"] == "difference"
    assert operation["parameters"] == {"periods": 1, "outputUnit": "percentage points"}
    assert operation["indicators"] == ["NE.CON.PRVT.ZS", "NE.GDI.TOTL.ZS"]
    assert "NY.GDP.MKTP.KD.ZG" in proposal["summary"]
    assert "input dataset:" in proposal["summary"]
    assert "output dataset:" in proposal["summary"]
    assert "output unit: percentage points" in proposal["summary"]

    applied = await pipeline_command(
        client,
        proposed.json(),
        "analysis-subset-apply",
        {
            "type": "apply_analysis_assistance",
            "acceptedItemIds": ["analysis-difference"],
        },
    )
    preview = await client.get(
        "/api/v1/workflow/sessions/planning-1/pipeline/preview?offset=0&limit=20"
    )
    await client.aclose()

    assert applied.status_code == 200, applied.text
    configured = applied.json()["session"]["pipeline"]["operations"][0]
    assert configured["kind"] == "difference"
    assert configured["target"]["indicators"] == ["NE.CON.PRVT.ZS", "NE.GDI.TOTL.ZS"]
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    gdp_rows = [row for row in rows if row["indicator_code"] == "NY.GDP.MKTP.KD.ZG"]
    share_rows = [row for row in rows if row["indicator_code"] != "NY.GDP.MKTP.KD.ZG"]
    assert [row["value"] for row in gdp_rows] == [5.2, 5.0]
    assert {row["unit"] for row in gdp_rows} == {"Percent"}
    assert {row["unit"] for row in share_rows} == {"percentage points"}


@pytest.mark.asyncio
async def test_analysis_assistant_replaces_forecasts_with_exact_var_contract(
    tmp_path: Path,
) -> None:
    indicators = ["NGDP_RPCH", "GGXWDG_NGDP", "NE.CON.PRVT.KD.ZG", "NE.CON.PRVT.ZS"]
    csv_rows = ["country,period,indicator,value"]
    for period in range(2018, 2025):
        csv_rows.extend(
            f"CHN,{period},{indicator},{index + period / 100}"
            for index, indicator in enumerate(indicators)
        )
    client, data_current = await approved_data_client(
        tmp_path,
        ("\n".join(csv_rows) + "\n").encode(),
        include_plan_analysis=False,
    )
    current = (
        await data_command(client, data_current, "var-replacement-enter", {"type": "data_next"})
    ).json()
    for index, kind in enumerate(("descriptive", "correlation", "arima", "arima")):
        current = (
            await pipeline_command(
                client,
                current,
                f"var-replacement-add-{index}",
                {"type": "add_model_job", "model": kind},
            )
        ).json()
    models = current["session"]["pipeline"]["models"]
    for index, model in enumerate(models):
        variables = indicators if model["kind"] in {"descriptive", "correlation"} else [
            indicators[index - 2]
        ]
        current = (
            await pipeline_command(
                client,
                current,
                f"var-replacement-configure-{index}",
                {
                    "type": "update_model_specification",
                    "modelId": model["id"],
                    "variables": variables,
                    "dependentVariables": [],
                    "independentVariables": [],
                    "parameters": {
                        **model["parameters"],
                        **({"forecastSteps": 2} if model["kind"] == "arima" else {}),
                    },
                },
            )
        ).json()
    request = (
        "Replace the two forecast jobs with one VAR over NGDP_RPCH, GGXWDG_NGDP, "
        "NE.CON.PRVT.KD.ZG and NE.CON.PRVT.ZS, forecasting exactly 2 annual periods. "
        "Keep descriptive and correlation jobs. Do not add transformations."
    )
    proposed = await pipeline_command(
        client,
        current,
        "var-replacement-propose",
        {"type": "propose_analysis_assistance", "request": request},
    )
    assert proposed.status_code == 200, proposed.text
    proposal = proposed.json()["session"]["pipeline"]["pendingAssistantProposal"]
    assert proposal["operations"] == []
    assert len(proposal["modelRemovals"]) == 2
    assert {item["label"] for item in proposal["modelRemovals"]} == {"ARIMA model"}
    assert len(proposal["models"]) == 1
    replacement = proposal["models"][0]
    assert replacement["model"] == "var"
    assert replacement["variables"] == sorted(indicators)
    assert replacement["parameters"]["forecastSteps"] == 2

    accepted = [
        *[item["id"] for item in proposal["modelRemovals"]],
        replacement["id"],
    ]
    applied = await pipeline_command(
        client,
        proposed.json(),
        "var-replacement-apply",
        {"type": "apply_analysis_assistance", "acceptedItemIds": accepted},
    )
    await client.aclose()

    assert applied.status_code == 200, applied.text
    configured = applied.json()["session"]["pipeline"]
    assert configured["operations"] == []
    assert [model["kind"] for model in configured["models"]] == [
        "descriptive",
        "correlation",
        "var",
    ]
    var = configured["models"][-1]
    assert var["variables"] == sorted(indicators)
    assert var["parameters"]["forecastSteps"] == 2
