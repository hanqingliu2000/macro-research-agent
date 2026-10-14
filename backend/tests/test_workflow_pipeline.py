from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.workflow.code_workspace import _stata_operation
from macro_research_agent.workflow.model_workspace import (
    ModelWorkspaceError,
    ModelWorkspaceManager,
    evaluate_typed_model_frame,
)
from macro_research_agent.workflow.pipeline_workspace import (
    PipelineWorkspaceError,
    PipelineWorkspaceManager,
)
from test_workflow_data_workspace import approved_data_client, command_meta


def pipeline_meta(snapshot_hash: str, key: str, stage: str = "transformation") -> dict[str, str]:
    return command_meta(snapshot_hash, key, stage)


async def pipeline_client(
    tmp_path: Path, content: bytes, request: str | None = None
) -> tuple[httpx.AsyncClient, dict[str, Any]]:
    client, approved = await approved_data_client(
        tmp_path,
        content,
        request=request,
        include_plan_analysis=False,
    )
    entered = await client.post(
        "/api/v1/workflow/sessions/planning-1/data/commands",
        json={
            "meta": command_meta(
                approved["projection"]["current_snapshot_hash"], "pipeline-data-next"
            ),
            "command": {"type": "data_next"},
        },
    )
    assert entered.status_code == 200, entered.text
    return client, entered.json()


async def pipeline_command(
    client: httpx.AsyncClient,
    current: dict[str, Any],
    key: str,
    command: dict[str, Any],
) -> httpx.Response:
    return await client.post(
        "/api/v1/workflow/sessions/planning-1/pipeline/commands",
        json={
            "meta": pipeline_meta(
                current["projection"]["current_snapshot_hash"],
                key,
                current["projection"].get("active_stage", "transformation"),
            ),
            "command": command,
        },
    )


@pytest.mark.asyncio
async def test_pipeline_preview_run_snapshots_trace_and_restart(tmp_path: Path) -> None:
    values = [100, 102, 104, 106, 120, 122, 124, 126]
    periods = [
        "2023-Q1",
        "2023-Q2",
        "2023-Q3",
        "2023-Q4",
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
    ]
    content = "country,period,indicator,value\n" + "".join(
        f"USA,{period},CPI,{value}\n" for period, value in zip(periods, values, strict=True)
    )
    client, current = await pipeline_client(tmp_path, content.encode())
    added = await pipeline_command(
        client,
        current,
        "add-yoy",
        {"type": "add_pipeline_operation", "operation": "yoy_growth"},
    )
    assert added.status_code == 200, added.text
    operation = added.json()["session"]["pipeline"]["operations"][0]
    preview = await client.get(
        "/api/v1/workflow/sessions/planning-1/pipeline/preview",
        params={"operation_id": operation["id"], "offset": 0, "limit": 20},
    )
    row = next(item for item in preview.json()["rows"] if item["period"] == "2024-Q1")
    assert row["value"] == pytest.approx(20.0)

    model_added = await pipeline_command(
        client,
        added.json(),
        "add-descriptive-yoy",
        {"type": "add_model_job", "model": "descriptive"},
    )
    model = model_added.json()["session"]["pipeline"]["models"][0]
    model_configured = await pipeline_command(
        client,
        model_added.json(),
        "configure-descriptive-yoy",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": ["CPI"],
        },
    )

    run = await pipeline_command(
        client, model_configured.json(), "run-yoy", {"type": "run_pipeline"}
    )
    replay = await pipeline_command(
        client, model_configured.json(), "run-yoy", {"type": "run_pipeline"}
    )
    pipeline = await client.get("/api/v1/workflow/sessions/planning-1/pipeline")
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")
    graph = await client.get("/api/v1/admin/workflow/sessions/planning-1/graph")
    code_artifacts = run.json()["session"]["pipeline"]["codeArtifacts"]
    python_artifact = next(item for item in code_artifacts if item["language"] == "python")
    stata_artifact = next(item for item in code_artifacts if item["language"] == "stata")
    python_code = await client.get(
        f"/api/v1/workflow/sessions/planning-1/pipeline/code/{python_artifact['id']}"
    )
    stata_download = await client.get(
        f"/api/v1/workflow/sessions/planning-1/pipeline/code/{stata_artifact['id']}/download"
    )
    await client.aclose()

    assert run.status_code == 200, run.text
    body = run.json()
    transition = body["graph_transition"]
    assert transition["created_checkpoint_ids"]
    assert transition["pointer_changes"]["analytical_bundle"]["current_ref"]
    assert transition["pointer_changes"]["artifact"]["current_ref"]
    assert body["session"]["activeStage"] == "output"
    assert body["session"]["status"] == "output_review"
    assert body["session"]["pipeline"]["runStatus"] == "completed"
    bundle = body["session"]["pipeline"]["bundle"]
    assert bundle["finalDatasetRef"].startswith("dataset-")
    assert bundle["operationSnapshotRefs"][operation["id"]] == bundle["finalDatasetRef"]
    lineage = bundle["operationLineage"][0]
    assert lineage["operationId"] == operation["id"]
    assert lineage["inputSnapshotHash"].startswith("sha256:")
    assert lineage["outputSnapshotHash"].startswith("sha256:")
    assert lineage["specificationHash"].startswith("sha256:")
    assert lineage["inputRows"] == lineage["outputRows"] == 8
    assert body["session"]["pipeline"]["operations"][0]["status"] == "completed"
    result = body["session"]["pipeline"]["modelResults"][0]
    assert result["inputSnapshotId"] == bundle["finalDatasetRef"]
    assert result["result"]["statistics"][0]["count"] == 4
    assert bundle["pythonCodeRef"] == python_artifact["id"]
    assert bundle["stataCodeRef"] == stata_artifact["id"]
    assert python_code.status_code == 200
    assert "SPECIFICATION = json.loads" in python_code.json()["content"]
    assert stata_download.status_code == 200
    assert b"by entity_code indicator_code frequency" in stata_download.content
    assert replay.json()["idempotent_replay"] is True
    assert pipeline.json()["bundle"]["id"] == bundle["id"]
    assert graph.status_code == 200, graph.text
    graph_body = graph.json()
    assert graph_body["checkpoints"][-1]["gate"] == "pipeline_execution"
    assert any(
        edge["kind"] == "authorized_by"
        and edge["target_ref"] == graph_body["checkpoints"][-1]["checkpoint_id"]
        for edge in graph_body["edges"]
    )
    run_event = next(event for event in trace.json() if event["event_type"] == "pipeline.executed")
    assert run_event["payload"]["model_result_ids"] == bundle["modelResultIds"]
    assert run_event["payload"]["code_artifact_ids"] == [item["id"] for item in code_artifacts]

    script_path = tmp_path / "reproduce_research.py"
    script_path.write_text(python_code.json()["content"], encoding="utf-8")
    input_path = (
        tmp_path
        / "workflow"
        / "sessions"
        / "planning-1"
        / "data"
        / "snapshots"
        / f"{bundle['inputDatasetId']}.parquet"
    )
    reproduced = tmp_path / "reproduced"
    environment = {**os.environ, "PYTHONPATH": str(Path.cwd() / "backend" / "src")}
    completed = subprocess.run(
        [sys.executable, str(script_path), str(input_path), str(reproduced)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    reproduced_frame = pd.read_parquet(reproduced / "analytical_data.parquet")
    backend_frame = pd.read_parquet(input_path.with_name(f"{bundle['finalDatasetRef']}.parquet"))
    pd.testing.assert_frame_equal(reproduced_frame, backend_frame)
    reproduced_models = json.loads((reproduced / "model_results.json").read_text(encoding="utf-8"))
    assert reproduced_models[0]["result"] == result["result"]

    restarted = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as restarted_client:
        recovered = await restarted_client.get(
            "/api/v1/workflow/sessions/planning-1/pipeline/preview",
            params={"operation_id": operation["id"], "offset": 4, "limit": 1},
        )
        recovered_code = await restarted_client.get(
            f"/api/v1/workflow/sessions/planning-1/pipeline/code/{python_artifact['id']}"
        )
    assert recovered.status_code == 200
    assert recovered.json()["rows"][0]["value"] == pytest.approx(20.0)
    assert recovered_code.json()["checksum"] == python_artifact["checksum"]
    stored_code_path = (
        tmp_path
        / "workflow"
        / "sessions"
        / "planning-1"
        / "code"
        / python_artifact["id"]
        / python_artifact["filename"]
    )
    stored_code_path.write_text("# tampered", encoding="utf-8")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as restarted_client:
        rejected_code = await restarted_client.get(
            f"/api/v1/workflow/sessions/planning-1/pipeline/code/{python_artifact['id']}"
        )
    assert rejected_code.status_code == 404
    assert "checksum" in rejected_code.text
    analytical_files = list(
        (tmp_path / "workflow" / "sessions" / "planning-1" / "data" / "snapshots").glob("*.parquet")
    )
    assert len(analytical_files) == 2


@pytest.mark.asyncio
async def test_pipeline_edits_are_typed_reversible_and_conflict_safe(tmp_path: Path) -> None:
    client, current = await pipeline_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2023,CPI,100\nUSA,2024,CPI,110\n",
    )
    lag = await pipeline_command(
        client,
        current,
        "add-lag",
        {"type": "add_pipeline_operation", "operation": "lag"},
    )
    rolling = await pipeline_command(
        client,
        lag.json(),
        "add-rolling",
        {"type": "add_pipeline_operation", "operation": "rolling_mean"},
    )
    rolling_id = rolling.json()["session"]["pipeline"]["operations"][1]["id"]
    moved = await pipeline_command(
        client,
        rolling.json(),
        "move-rolling",
        {
            "type": "move_pipeline_operation",
            "operationId": rolling_id,
            "direction": "up",
        },
    )
    toggled = await pipeline_command(
        client,
        moved.json(),
        "toggle-rolling",
        {"type": "toggle_pipeline_operation", "operationId": rolling_id},
    )
    undone = await pipeline_command(
        client,
        toggled.json(),
        "undo-toggle",
        {"type": "undo_pipeline_edit"},
    )
    invalid_parameters = await pipeline_command(
        client,
        undone.json(),
        "invalid-window",
        {
            "type": "update_pipeline_parameters",
            "operationId": rolling_id,
            "parameters": {"window": 0, "minimumPeriods": 1},
        },
    )
    malformed_parameters = await pipeline_command(
        client,
        undone.json(),
        "malformed-parameters",
        {
            "type": "update_pipeline_parameters",
            "operationId": rolling_id,
            "parameters": "window=4",
        },
    )
    unsupported = await pipeline_command(
        client,
        undone.json(),
        "unsupported-merge",
        {"type": "add_pipeline_operation", "operation": "merge"},
    )
    stale = await pipeline_command(
        client,
        rolling.json(),
        "stale-edit",
        {"type": "delete_pipeline_operation", "operationId": rolling_id},
    )
    await client.aclose()

    operations = moved.json()["session"]["pipeline"]["operations"]
    assert operations[0]["id"] == rolling_id
    assert operations[0]["inputRef"] == "active_dataset"
    assert operations[1]["inputRef"] == operations[0]["outputRef"]
    restored = next(
        item
        for item in undone.json()["session"]["pipeline"]["operations"]
        if item["id"] == rolling_id
    )
    assert restored["enabled"] is True
    assert invalid_parameters.status_code == 422
    assert "positive integer" in invalid_parameters.json()["detail"]
    assert malformed_parameters.status_code == 422
    assert "structured object" in malformed_parameters.json()["detail"]
    assert unsupported.status_code == 422
    assert "not registered" in unsupported.json()["detail"]
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_model_input_rebinds_when_operations_are_deleted_and_rebuilt(
    tmp_path: Path,
) -> None:
    content = (
        "country,period,indicator,value\n"
        "USA,2021,GDP,100\nUSA,2022,GDP,102\nUSA,2023,GDP,105\n"
    )
    client, current = await pipeline_client(tmp_path, content.encode())
    first = await pipeline_command(
        client,
        current,
        "binding-add-first",
        {"type": "add_pipeline_operation", "operation": "difference"},
    )
    second = await pipeline_command(
        client,
        first.json(),
        "binding-add-second",
        {"type": "add_pipeline_operation", "operation": "rolling_mean"},
    )
    model_added = await pipeline_command(
        client,
        second.json(),
        "binding-add-model",
        {"type": "add_model_job", "model": "descriptive"},
    )
    model = model_added.json()["session"]["pipeline"]["models"][0]
    operations = model_added.json()["session"]["pipeline"]["operations"]
    assert model["inputRef"] == operations[1]["outputRef"]

    removed_last = await pipeline_command(
        client,
        model_added.json(),
        "binding-delete-last",
        {"type": "delete_pipeline_operation", "operationId": operations[1]["id"]},
    )
    pipeline = removed_last.json()["session"]["pipeline"]
    assert pipeline["models"][0]["inputRef"] == pipeline["operations"][0]["outputRef"]
    assert "Rebound DESCRIPTIVE model" in pipeline["lastBindingNotice"]

    removed_first = await pipeline_command(
        client,
        removed_last.json(),
        "binding-delete-first",
        {"type": "delete_pipeline_operation", "operationId": operations[0]["id"]},
    )
    assert removed_first.json()["session"]["pipeline"]["models"][0]["inputRef"] == (
        "active_dataset"
    )
    rebuilt = await pipeline_command(
        client,
        removed_first.json(),
        "binding-rebuild",
        {"type": "add_pipeline_operation", "operation": "difference"},
    )
    rebuilt_operation = rebuilt.json()["session"]["pipeline"]["operations"][0]
    rebound = await pipeline_command(
        client,
        rebuilt.json(),
        "binding-select-rebuilt",
        {
            "type": "update_model_input",
            "modelId": model["id"],
            "inputRef": rebuilt_operation["outputRef"],
        },
    )
    configured = await pipeline_command(
        client,
        rebound.json(),
        "binding-configure-model",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": ["GDP"],
        },
    )
    run = await pipeline_command(
        client, configured.json(), "binding-run", {"type": "run_pipeline"}
    )
    await client.aclose()

    assert run.status_code == 200, run.text
    assert run.json()["session"]["pipeline"]["models"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_registered_models_execute_against_hashed_snapshot_and_survive_restart(
    tmp_path: Path,
) -> None:
    rows = ["country,period,indicator,value\n"]
    for period in range(2015, 2025):
        x = period - 2014
        rows.extend(
            [
                f"USA,{period},X,{x}\n",
                f"USA,{period},Y,{1 + 2 * x}\n",
                f"USA,{period},Z,{3 * x - 2}\n",
            ]
        )
    client, current = await pipeline_client(tmp_path, "".join(rows).encode())

    for kind in ("descriptive", "correlation", "ols"):
        response = await pipeline_command(
            client,
            current,
            f"add-{kind}",
            {"type": "add_model_job", "model": kind},
        )
        assert response.status_code == 200, response.text
        current = response.json()

    descriptive, correlation, ols = current["session"]["pipeline"]["models"]
    for key, model, specification in (
        (
            "spec-descriptive",
            descriptive,
            {"variables": ["X", "Y"]},
        ),
        (
            "spec-correlation",
            correlation,
            {"variables": ["X", "Y", "Z"]},
        ),
        (
            "spec-ols",
            ols,
            {
                "dependentVariables": ["Y"],
                "independentVariables": ["X"],
                "parameters": {
                    "missing": "drop",
                    "addConstant": True,
                    "covariance": "HAC",
                    "maxLags": 2,
                },
            },
        ),
    ):
        response = await pipeline_command(
            client,
            current,
            key,
            {"type": "update_model_specification", "modelId": model["id"], **specification},
        )
        assert response.status_code == 200, response.text
        current = response.json()

    run = await pipeline_command(client, current, "run-models", {"type": "run_pipeline"})
    replay = await pipeline_command(client, current, "run-models", {"type": "run_pipeline"})
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")
    await client.aclose()

    assert run.status_code == 200, run.text
    pipeline = run.json()["session"]["pipeline"]
    assert pipeline["bundle"]["operationIds"] == []
    assert len(pipeline["bundle"]["modelResultIds"]) == 3
    assert pipeline["bundle"]["pythonCodeRef"].startswith("code-")
    assert pipeline["bundle"]["stataCodeRef"] is None
    assert any("Stata HAC is unavailable" in item for item in pipeline["bundle"]["warnings"])
    assert [item["language"] for item in pipeline["codeArtifacts"]] == ["python"]
    assert all(model["status"] == "completed" for model in pipeline["models"])
    results = {result["kind"]: result for result in pipeline["modelResults"]}
    assert results["descriptive"]["sample"] == {"observations": 10, "dropped": 0}
    assert results["correlation"]["result"]["matrix"][0]["Y"] == pytest.approx(1.0)
    coefficients = {
        item["term"]: item["estimate"] for item in results["ols"]["result"]["coefficients"]
    }
    assert coefficients == pytest.approx({"const": 1.0, "X": 2.0})
    assert results["ols"]["result"]["covariance"] == "HAC"
    assert results["ols"]["inputSnapshotHash"].startswith("sha256:")
    assert results["ols"]["specificationHash"].startswith("sha256:")
    assert results["ols"]["resultHash"].startswith("sha256:")
    assert replay.json()["idempotent_replay"] is True
    assert any(event["event_type"] == "pipeline.executed" for event in trace.json())

    restarted = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as restarted_client:
        recovered = await restarted_client.get("/api/v1/workflow/sessions/planning-1/pipeline")
    assert recovered.status_code == 200
    assert len(recovered.json()["modelResults"]) == 3


@pytest.mark.asyncio
async def test_model_failure_preserves_siblings_and_retry_reuses_success(
    tmp_path: Path,
) -> None:
    # LRS-TRANSFORM-08/09: fan-out failure is partial and retry preserves successful siblings.
    client, current = await pipeline_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2023,X,1\nUSA,2024,X,2\n",
    )
    for key in ("good", "missing"):
        added = await pipeline_command(
            client,
            current,
            f"add-{key}",
            {"type": "add_model_job", "model": "descriptive"},
        )
        current = added.json()
    good, missing = current["session"]["pipeline"]["models"]
    for key, model, variables in (
        ("good", good, ["X"]),
        ("missing", missing, ["MISSING"]),
    ):
        configured = await pipeline_command(
            client,
            current,
            f"configure-{key}",
            {
                "type": "update_model_specification",
                "modelId": model["id"],
                "variables": variables,
            },
        )
        current = configured.json()

    partial = await pipeline_command(client, current, "run-partial", {"type": "run_pipeline"})
    assert partial.status_code == 200, partial.text
    partial_pipeline = partial.json()["session"]["pipeline"]
    assert [item["status"] for item in partial_pipeline["models"]] == ["completed", "failed"]
    assert len(partial_pipeline["modelResults"]) == 1
    first_result_id = partial_pipeline["models"][0]["resultRef"]
    assert any("failed" in warning for warning in partial_pipeline["bundle"]["warnings"])

    revision = await pipeline_command(
        client,
        partial.json(),
        "start-partial-model-revision",
        {"type": "start_pipeline_revision"},
    )
    corrected = await pipeline_command(
        client,
        revision.json(),
        "correct-failed-model",
        {
            "type": "update_model_specification",
            "modelId": missing["id"],
            "variables": ["X"],
        },
    )
    retried = await pipeline_command(
        client, corrected.json(), "retry-failed-model", {"type": "run_pipeline"}
    )
    await client.aclose()

    assert retried.status_code == 200, retried.text
    retried_models = retried.json()["session"]["pipeline"]["models"]
    assert [item["status"] for item in retried_models] == ["completed", "completed"]
    assert retried_models[0]["resultRef"] == first_result_id
    assert retried_models[0]["reused"] is True


@pytest.mark.asyncio
async def test_adf_runs_per_entity_with_typed_options_and_reproducible_warning(
    tmp_path: Path,
) -> None:
    # Phase 2A-1: ADF never concatenates independent entity time series.
    rng = np.random.default_rng(20260905)
    rows = ["country,period,indicator,value\n"]
    for entity in ("USA", "JPN"):
        for index, value in enumerate(rng.normal(size=80), start=1945):
            rows.append(f"{entity},{index},STATIONARY,{value}\n")
    client, current = await pipeline_client(tmp_path, "".join(rows).encode())
    added = await pipeline_command(
        client,
        current,
        "add-adf",
        {"type": "add_model_job", "model": "adf"},
    )
    model = added.json()["session"]["pipeline"]["models"][0]
    configured = await pipeline_command(
        client,
        added.json(),
        "configure-adf",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": ["STATIONARY"],
            "parameters": {
                "missing": "drop",
                "regression": "c",
                "autolag": "AIC",
                "maxLags": 4,
            },
        },
    )
    run = await pipeline_command(client, configured.json(), "run-adf", {"type": "run_pipeline"})
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")
    await client.aclose()

    assert run.status_code == 200, run.text
    pipeline = run.json()["session"]["pipeline"]
    result = pipeline["modelResults"][0]
    assert result["kind"] == "adf"
    assert result["sample"] == {"observations": 160, "dropped": 0}
    assert {item["entityCode"] for item in result["result"]["groups"]} == {"USA", "JPN"}
    assert all(item["rejectUnitRootAt5Percent"] for item in result["result"]["groups"])
    assert pipeline["bundle"]["stataCodeRef"] is None
    assert any("Stata ADF generation" in item for item in pipeline["bundle"]["warnings"])
    assert any(
        event["event_type"] == "capability.invocation_completed"
        and event["payload"]["capability_id"] == "model.adf"
        for event in trace.json()
    )


@pytest.mark.asyncio
async def test_arima_and_sarimax_create_reviewable_forecast_artifacts(tmp_path: Path) -> None:
    # Phase 2A-2: forecasts stay separated by entity/frequency and expose intervals.
    periods = pd.period_range("2019-01", periods=40, freq="M")
    rows = ["country,period,indicator,value\n"]
    for index, period in enumerate(periods):
        exogenous = 2 + index * 0.05
        rows.append(f"USA,{period},POLICY_RATE,{exogenous}\n")
        if index < 36:
            target = 100 + index * 0.3 + np.sin(index / 3)
            rows.append(f"USA,{period},CPI,{target}\n")
    client, current = await pipeline_client(tmp_path, "".join(rows).encode())

    for kind in ("arima", "sarimax"):
        added = await pipeline_command(
            client,
            current,
            f"add-{kind}",
            {"type": "add_model_job", "model": kind},
        )
        assert added.status_code == 200, added.text
        current = added.json()
    arima, sarimax = current["session"]["pipeline"]["models"]
    for key, model, independent in (
        ("configure-arima", arima, []),
        ("configure-sarimax", sarimax, ["POLICY_RATE"]),
    ):
        configured = await pipeline_command(
            client,
            current,
            key,
            {
                "type": "update_model_specification",
                "modelId": model["id"],
                "dependentVariables": ["CPI"],
                "independentVariables": independent,
                "parameters": {
                    "missing": "drop",
                    "orderP": 1,
                    "orderD": 1,
                    "orderQ": 0,
                    "seasonalP": 0,
                    "seasonalD": 0,
                    "seasonalQ": 0,
                    "seasonalPeriod": 0,
                    "trend": "n",
                    "forecastSteps": 4,
                    "confidenceLevel": 0.9,
                    "enforceStationarity": True,
                    "enforceInvertibility": True,
                },
            },
        )
        assert configured.status_code == 200, configured.text
        current = configured.json()

    run = await pipeline_command(client, current, "run-forecasts", {"type": "run_pipeline"})
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")
    assert run.status_code == 200, run.text
    pipeline = run.json()["session"]["pipeline"]
    results = {item["kind"]: item for item in pipeline["modelResults"]}
    assert set(results) == {"arima", "sarimax"}
    assert all(len(item["result"]["forecasts"]) == 4 for item in results.values())
    assert results["arima"]["result"]["forecasts"][0]["period"] == "2022-01"
    assert results["sarimax"]["result"]["independentVariables"] == ["POLICY_RATE"]
    assert all(
        row["lower"] < row["mean"] < row["upper"]
        for item in results.values()
        for row in item["result"]["forecasts"]
    )
    assert pipeline["bundle"]["stataCodeRef"] is None
    assert any("Stata ARIMA/SARIMAX" in item for item in pipeline["bundle"]["warnings"])
    forecast_artifact = next(
        item
        for item in run.json()["session"]["output"]["artifacts"]
        if item["kind"] == "forecast_data"
    )
    preview = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{forecast_artifact['id']}"
    )
    workbook_artifact = next(
        item for item in run.json()["session"]["output"]["artifacts"] if item["format"] == "xlsx"
    )
    workbook_preview = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{workbook_artifact['id']}"
    )
    await client.aclose()
    assert preview.status_code == 200
    assert len(preview.json()["rows"]) == 8
    assert "Forecasts" in workbook_preview.json()["sheetNames"]
    completed_capabilities = {
        event["payload"]["capability_id"]
        for event in trace.json()
        if event["event_type"] == "capability.invocation_completed"
    }
    assert {"model.arima", "model.sarimax"}.issubset(completed_capabilities)


def test_sarimax_fails_closed_without_future_exogenous_values() -> None:
    periods = pd.period_range("2020", periods=10, freq="Y")
    frame = pd.DataFrame(
        [
            {
                "series_id": f"{indicator}:USA",
                "entity_code": "USA",
                "indicator_code": indicator,
                "frequency": "annual",
                "period": str(period),
                "value": value,
            }
            for index, period in enumerate(periods)
            for indicator, value in (("Y", 10 + index), ("X", 2 + index / 10))
        ]
    )
    job = {
        "id": "sarimax-no-future-exog",
        "kind": "sarimax",
        "inputRef": "active_dataset",
        "variables": [],
        "dependentVariables": ["Y"],
        "independentVariables": ["X"],
        "parameters": {
            "missing": "drop",
            "orderP": 1,
            "orderD": 0,
            "orderQ": 0,
            "seasonalP": 0,
            "seasonalD": 0,
            "seasonalQ": 0,
            "seasonalPeriod": 0,
            "trend": "c",
            "forecastSteps": 2,
            "confidenceLevel": 0.95,
        },
    }

    with pytest.raises(ModelWorkspaceError, match="future exogenous rows"):
        evaluate_typed_model_frame(frame, job)


@pytest.mark.asyncio
async def test_var_runs_per_entity_and_exports_optional_irf(tmp_path: Path) -> None:
    # Phase 2A-3: systems and shocks never cross entity/frequency boundaries.
    rng = np.random.default_rng(20260906)
    rows = ["country,period,indicator,value\n"]
    for entity in ("USA", "JPN"):
        x_value = 0.0
        y_value = 0.0
        for period in range(1960, 2020):
            previous_x = x_value
            x_value = 0.45 * x_value + 0.15 * y_value + rng.normal(scale=0.4)
            y_value = 0.2 * previous_x + 0.4 * y_value + rng.normal(scale=0.4)
            rows.extend(
                [
                    f"{entity},{period},X,{x_value}\n",
                    f"{entity},{period},Y,{y_value}\n",
                ]
            )
    client, current = await pipeline_client(tmp_path, "".join(rows).encode())
    added = await pipeline_command(
        client,
        current,
        "add-var",
        {"type": "add_model_job", "model": "var"},
    )
    assert added.status_code == 200, added.text
    model = added.json()["session"]["pipeline"]["models"][0]
    configured = await pipeline_command(
        client,
        added.json(),
        "configure-var",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": ["X", "Y"],
            "parameters": {
                "missing": "drop",
                "maxLags": 2,
                "lagSelection": "fixed",
                "trend": "c",
                "includeIrf": True,
                "irfPeriods": 5,
                "forecastSteps": 2,
                "impulseVariables": ["X"],
                "orthogonalized": True,
                "confidenceLevel": 0.9,
            },
        },
    )
    assert configured.status_code == 200, configured.text
    run = await pipeline_command(client, configured.json(), "run-var", {"type": "run_pipeline"})
    trace = await client.get("/api/v1/admin/workflow/sessions/planning-1/trace")

    assert run.status_code == 200, run.text
    session = run.json()["session"]
    result = session["pipeline"]["modelResults"][0]
    assert result["kind"] == "var"
    assert result["sample"] == {"observations": 120, "dropped": 0}
    assert {item["entityCode"] for item in result["result"]["groups"]} == {"USA", "JPN"}
    assert all(item["lagOrder"] == 2 for item in result["result"]["groups"])
    assert {item["equation"] for item in result["result"]["coefficients"]} == {"X", "Y"}
    forecasts = result["result"]["forecasts"]
    assert len(forecasts) == 8
    assert {item["variable"] for item in forecasts} == {"X", "Y"}
    assert {item["step"] for item in forecasts} == {1, 2}
    assert {item["period"] for item in forecasts} == {"2020", "2021"}
    impulse_responses = result["result"]["impulseResponses"]
    assert len(impulse_responses) == 24
    assert {item["impulse"] for item in impulse_responses} == {"X"}
    assert {item["response"] for item in impulse_responses} == {"X", "Y"}
    assert session["pipeline"]["bundle"]["stataCodeRef"] is None
    assert any("Stata VAR/IRF" in warning for warning in session["pipeline"]["bundle"]["warnings"])
    irf_artifact = next(
        item for item in session["output"]["artifacts"] if item["kind"] == "irf_data"
    )
    forecast_artifact = next(
        item for item in session["output"]["artifacts"] if item["kind"] == "forecast_data"
    )
    forecast_preview = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{forecast_artifact['id']}"
    )
    irf_preview = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{irf_artifact['id']}"
    )
    workbook_artifact = next(
        item for item in session["output"]["artifacts"] if item["format"] == "xlsx"
    )
    workbook_preview = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{workbook_artifact['id']}"
    )
    await client.aclose()

    assert len(irf_preview.json()["rows"]) == 24
    assert len(forecast_preview.json()["rows"]) == 8
    assert "Forecasts" in workbook_preview.json()["sheetNames"]
    assert "Impulse Responses" in workbook_preview.json()["sheetNames"]
    assert any(
        event["event_type"] == "capability.invocation_completed"
        and event["payload"]["capability_id"] == "model.var"
        for event in trace.json()
    )


def test_var_rejects_an_impulse_outside_the_ordered_system() -> None:
    job = {
        "kind": "var",
        "variables": ["X", "Y"],
        "dependentVariables": [],
        "independentVariables": [],
        "parameters": {
            "missing": "drop",
            "maxLags": 1,
            "lagSelection": "fixed",
            "trend": "c",
            "includeIrf": True,
            "irfPeriods": 4,
            "impulseVariables": ["Z"],
            "orthogonalized": True,
            "confidenceLevel": 0.95,
        },
    }

    with pytest.raises(ModelWorkspaceError, match="selected model indicators"):
        ModelWorkspaceManager.validate_job(job)


@pytest.mark.asyncio
async def test_model_validation_rejects_missing_variables_and_unregistered_kinds(
    tmp_path: Path,
) -> None:
    client, current = await pipeline_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2023,X,1\nUSA,2024,X,2\n",
    )
    unsupported = await pipeline_command(
        client,
        current,
        "add-garch",
        {"type": "add_model_job", "model": "garch"},
    )
    assert unsupported.status_code == 422
    added = await pipeline_command(
        client,
        current,
        "add-correlation",
        {"type": "add_model_job", "model": "correlation"},
    )
    invalid = await pipeline_command(
        client,
        added.json(),
        "run-invalid-correlation",
        {"type": "run_pipeline"},
    )
    await client.aclose()
    assert invalid.status_code == 422
    assert "at least two indicator codes" in invalid.text


@pytest.mark.asyncio
async def test_model_edit_archives_generated_code_and_clears_current_bundle(
    tmp_path: Path,
) -> None:
    client, current = await pipeline_client(
        tmp_path,
        b"country,period,indicator,value\nUSA,2022,X,1\nUSA,2023,X,2\n",
    )
    added = await pipeline_command(
        client,
        current,
        "add-descriptive-archive",
        {"type": "add_model_job", "model": "descriptive"},
    )
    model = added.json()["session"]["pipeline"]["models"][0]
    configured = await pipeline_command(
        client,
        added.json(),
        "configure-descriptive-archive",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": ["X"],
        },
    )
    run = await pipeline_command(
        client, configured.json(), "run-descriptive-archive", {"type": "run_pipeline"}
    )
    blocked = await pipeline_command(
        client,
        run.json(),
        "block-completed-model-edit",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": [],
        },
    )
    revision = await pipeline_command(
        client,
        run.json(),
        "start-analysis-revision",
        {"type": "start_pipeline_revision"},
    )
    edited = await pipeline_command(
        client,
        revision.json(),
        "edit-descriptive-archive",
        {
            "type": "update_model_specification",
            "modelId": model["id"],
            "variables": [],
        },
    )
    reloaded = await client.get("/api/v1/workflow/sessions/planning-1")
    await client.aclose()

    assert run.status_code == 200
    assert blocked.status_code == 422
    assert "Start an analysis revision" in blocked.json()["detail"]
    assert revision.status_code == 200, revision.text
    revision_session = revision.json()["session"]
    assert revision_session["activeStage"] == "transformation"
    assert revision_session["stageHealth"]["output"] == "stale"
    assert revision_session["pipeline"]["runStatus"] == "editing"
    assert len(run.json()["session"]["pipeline"]["codeArtifacts"]) == 2
    edited_session = edited.json()["session"]
    pipeline = edited_session["pipeline"]
    assert pipeline.get("bundle") is None
    assert pipeline["modelResults"] == []
    assert pipeline["codeArtifacts"] == []
    assert len(pipeline["codeArtifactHistory"]) == 2
    assert edited_session["activeStage"] == "transformation"
    assert edited_session["stageHealth"]["output"] == "stale"
    assert edited_session["output"]["artifacts"]
    assert all(item["status"] == "stale" for item in edited_session["output"]["artifacts"])
    assert edited_session["output"]["artifactHistory"]
    transition = revision.json()["graph_transition"]
    assert transition["invalidated_node_ids"]
    assert transition["pointer_changes"]["analytical_bundle"]["current_ref"] is None

    assert reloaded.status_code == 200, reloaded.text
    persisted_model = reloaded.json()["session"]["pipeline"]["models"][0]
    assert persisted_model["variables"] == []


def operation(
    kind: str,
    *,
    parameters: dict[str, Any] | None = None,
    entities: list[str] | None = None,
    indicators: list[str] | None = None,
    frequency: str = "quarterly",
) -> dict[str, Any]:
    return {
        "id": f"operation-{kind}",
        "kind": kind,
        "label": kind,
        "enabled": True,
        "target": {
            "inputRef": "active_dataset",
            "indicators": indicators or ["CPI"],
            "entities": entities or ["USA"],
            "fields": ["value"],
            "frequency": frequency,
        },
        "parameters": parameters or {},
        "inputRef": "active_dataset",
        "outputRef": f"step:{kind}",
        "status": "not_run",
    }


def quarterly_frame() -> pd.DataFrame:
    periods = [
        "2023-Q1",
        "2023-Q2",
        "2023-Q3",
        "2023-Q4",
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
    ]
    return pd.DataFrame(
        {
            "series_id": ["CPI:USA"] * 8,
            "entity_code": ["USA"] * 8,
            "indicator_code": ["CPI"] * 8,
            "frequency": ["quarterly"] * 8,
            "period": periods,
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )


def monthly_frame(periods: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["RATE:USA"] * len(periods),
            "entity_code": ["USA"] * len(periods),
            "indicator_code": ["RATE"] * len(periods),
            "frequency": ["monthly"] * len(periods),
            "period": periods,
            "value": values,
            "unit": ["percent"] * len(periods),
        }
    )


def test_supported_transformation_numerics(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    manager: PipelineWorkspaceManager = app.state.pipeline_workspace_manager
    frame = quarterly_frame()

    assert np.isnan(manager.transform_frame(frame, operation("lag"))["value"].iloc[0])
    assert manager.transform_frame(frame, operation("lag"))["value"].iloc[1] == 1
    assert manager.transform_frame(frame, operation("lead"))["value"].iloc[0] == 2
    assert manager.transform_frame(frame, operation("difference"))["value"].iloc[1] == 1
    assert manager.transform_frame(frame, operation("period_growth"))["value"].iloc[1] == 100
    assert manager.transform_frame(frame, operation("yoy_growth"))["value"].iloc[4] == 400
    assert manager.transform_frame(frame, operation("log"))["value"].iloc[1] == pytest.approx(
        np.log(2)
    )
    rebased = manager.transform_frame(
        frame, operation("rebase_index", parameters={"basePeriod": "first", "baseValue": 100})
    )
    assert rebased["value"].iloc[1] == 200
    rolling = manager.transform_frame(
        frame, operation("rolling_mean", parameters={"window": 2, "minimumPeriods": 1})
    )
    assert rolling["value"].iloc[1] == 1.5
    annual = manager.transform_frame(
        frame,
        operation(
            "frequency_conversion",
            parameters={"targetFrequency": "annual", "method": "mean"},
        ),
    )
    assert annual["value"].tolist() == [2.5, 6.5]

    japan = frame.iloc[[0]].copy()
    japan["series_id"] = "CPI:JPN"
    japan["entity_code"] = "JPN"
    japan["value"] = 3.0
    aggregate_input = pd.concat([frame.iloc[[0]], japan], ignore_index=True)
    aggregate = manager.transform_frame(
        aggregate_input,
        operation(
            "group_aggregation",
            parameters={
                "method": "mean",
                "groupCode": "PAIR",
                "coverageThreshold": 1,
            },
            entities=["USA", "JPN"],
        ),
    )
    assert aggregate["entity_code"].tolist() == ["PAIR"]
    assert aggregate["value"].iloc[0] == 2
    assert aggregate["aggregation_coverage"].iloc[0] == 1


def test_unit_and_fiscal_calendar_harmonization(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    manager: PipelineWorkspaceManager = app.state.pipeline_workspace_manager
    frame = monthly_frame(
        ["2023-07", "2023-08", "2023-09", "2024-04", "2024-05", "2024-06"],
        [1, 2, 3, 4, 5, 6],
    )
    converted = manager.transform_frame(
        frame,
        operation(
            "unit_conversion",
            parameters={
                "sourceUnit": "percent",
                "targetUnit": "basis points",
                "factor": 100,
                "offset": 0,
            },
            indicators=["RATE"],
            frequency="monthly",
        ),
    )
    assert converted["value"].tolist() == [100, 200, 300, 400, 500, 600]
    assert converted["unit"].unique().tolist() == ["basis points"]
    stata = _stata_operation(
        operation(
            "unit_conversion",
            parameters={
                "sourceUnit": "percent",
                "targetUnit": "basis points",
                "factor": 100,
                "offset": 0,
            },
            indicators=["RATE"],
            frequency="monthly",
        ),
        0,
    )
    assert 'replace unit = "basis points"' in "\n".join(stata)

    fiscal = manager.transform_frame(
        converted,
        operation(
            "frequency_conversion",
            parameters={
                "targetFrequency": "quarterly",
                "method": "mean",
                "calendar": "fiscal",
                "fiscalYearEndMonth": 6,
                "incompletePeriod": "error",
            },
            indicators=["RATE"],
            frequency="monthly",
        ),
    )
    assert fiscal["period"].tolist() == ["2024-Q1", "2024-Q4"]
    assert fiscal["value"].tolist() == [200, 500]
    assert fiscal["unit"].unique().tolist() == ["basis points"]
    assert fiscal["calendar"].unique().tolist() == ["fiscal-year-ending-06"]
    assert fiscal["frequency_coverage"].tolist() == [1, 1]


def test_frequency_harmonization_controls_incomplete_periods(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    manager: PipelineWorkspaceManager = app.state.pipeline_workspace_manager
    frame = monthly_frame(["2024-01", "2024-02"], [1, 2])
    parameters = {
        "targetFrequency": "quarterly",
        "method": "mean",
        "calendar": "calendar",
        "fiscalYearEndMonth": 12,
    }
    kept = manager.transform_frame(
        frame,
        operation(
            "frequency_conversion",
            parameters={**parameters, "incompletePeriod": "keep"},
            indicators=["RATE"],
            frequency="monthly",
        ),
    )
    assert kept["frequency_coverage"].tolist() == [pytest.approx(2 / 3)]
    dropped = manager.transform_frame(
        frame,
        operation(
            "frequency_conversion",
            parameters={**parameters, "incompletePeriod": "drop"},
            indicators=["RATE"],
            frequency="monthly",
        ),
    )
    assert dropped.empty
    with pytest.raises(PipelineWorkspaceError, match="incomplete target periods"):
        manager.transform_frame(
            frame,
            operation(
                "frequency_conversion",
                parameters={**parameters, "incompletePeriod": "error"},
                indicators=["RATE"],
                frequency="monthly",
            ),
        )
