from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from macro_research_agent.workflow.chart_author import ChartCheckResult, DeepSeekChartAuthor
from macro_research_agent.workflow.output_review import DeterministicArtifactAuthor
from macro_research_agent.workflow.output_workspace import OutputWorkspaceError
from test_workflow_output import output_command
from test_workflow_pipeline import pipeline_client, pipeline_command


def author_with_response(handler: Any) -> DeepSeekChartAuthor:
    return DeepSeekChartAuthor(
        api_key="test",
        model_id="test",
        endpoint="https://test/chat",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize("status", [429, 500])
def test_self_check_provider_error_never_falls_back(status: int) -> None:
    author = author_with_response(lambda request: httpx.Response(status, json={}))
    with pytest.raises(OutputWorkspaceError) as caught:
        author.check_delivery({}, 1)
    assert caught.value.code == (
        "provider_rate_limited" if status == 429 else "provider_server_error"
    )


def test_self_check_contract_repair_is_bounded() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"status": "pass", "issues": ["contradiction"]}
                                if len(calls) == 1
                                else {"status": "pass", "issues": []}
                            )
                        }
                    }
                ]
            },
        )

    author = author_with_response(handler)
    assert author.check_delivery({}, 1).status == "pass"
    assert len(calls) == 2
    assert "invalid_model_contract" in calls[1]["messages"][1]["content"]


def test_agent_checks_separate_package_semantics_from_visual_rules() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"status":"pass","issues":[]}'}}]}
        )

    evidence = {
        "checkProtocol": "agent-author-check-v6",
        "publicationGuideline": {"version": "report-policy"},
        "reportDrafts": {"r": {"sections": []}},
        "evidenceLedgers": {"r": []},
        "modelResults": [{"id": "result"}],
        "artifactManifest": [{"id": "c", "name": "chart.svg", "hash": "bound-hash"}],
        "rows": [{"period": "2024", "value": 4.25}],
        "charts": [{"id": "c", "svg": "<svg/>", "specification": {"title": "Wrapped"}}],
    }
    author = author_with_response(handler)
    for number in (1, 2):
        assert author.check_delivery(evidence, number).status == "pass"
    first, second = [json.loads(call["messages"][1]["content"]) for call in calls]
    assert first["reportDrafts"] == evidence["reportDrafts"]
    assert first["modelResults"] == evidence["modelResults"]
    assert "svg" not in first["charts"][0]
    assert not {"reportDrafts", "evidenceLedgers", "modelResults"}.intersection(second)
    assert second["charts"][0]["svg"] == "<svg/>"
    assert second["rows"] == first["rows"] == evidence["rows"]
    assert second["artifactManifest"] == first["artifactManifest"]
    assert "rubric ONLY for charts/tables" in calls[0]["messages"][0]["content"]
    assert "Wrapped SVG title lines" in calls[1]["messages"][0]["content"]
    assert "independent evidence namespaces" in calls[0]["messages"][0]["content"]
    assert "identical specifications for different formats" in calls[0]["messages"][0]["content"]
    # Projection is not a mutation of retained evidence.
    assert evidence["charts"][0]["svg"] == "<svg/>"
    with pytest.raises(ValueError, match="exactly two"):
        author.check_delivery(evidence, 3)


def test_wording_uses_complete_exact_chart_selection(monkeypatch: Any) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "Female unemployment in China",
                                    "unit": "Percent",
                                    "alt_text": "Female unemployment",
                                }
                            )
                        }
                    }
                ]
            },
        )

    rows = [
        {
            "indicator_code": "female",
            "entity_code": "CHN",
            "unit": "Percent",
            "period": str(year),
            "value": 4,
        }
        for year in (2022, 2023, 2024)
    ]
    unrelated = [
        {**rows[0], "indicator_code": "male"},
        {**rows[0], "entity_code": "IND"},
        {**rows[0], "unit": "Number"},
    ]
    author = author_with_response(handler)
    monkeypatch.setattr(author, "_inspect_rows", lambda *args: rows + unrelated)
    kwargs = dict(
        title="female",
        source_note="Source: World Bank",
        y_fields=["CHN"],
        guideline_version="publication-v1",
        data_hash="bound",
        indicator_code="female",
        unit="Percent",
        dataset=SimpleNamespace(grant=SimpleNamespace(row_count=6)),
    )
    spec = author.author_chart_spec(**kwargs)
    assert spec.indicator_code == "female"
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["rows"] == rows
    assert "ONLY specification.indicator_code" in calls[0]["messages"][0]["content"]
    with pytest.raises(OutputWorkspaceError, match="no bound observations"):
        author.author_chart_spec(**{**kwargs, "indicator_code": "missing"})
    assert len(calls) == 1


def test_missing_credentials_timeout_and_invalid_output_fail_closed() -> None:
    calls = []

    def invalid(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    author = author_with_response(invalid)
    with pytest.raises(OutputWorkspaceError, match="after repair"):
        author.check_delivery({}, 2)
    assert len(calls) == 2
    author.api_key = ""
    with pytest.raises(OutputWorkspaceError, match="credentials"):
        author.check_delivery({}, 1)
    assert len(calls) == 2

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture", request=request)

    with pytest.raises(OutputWorkspaceError, match="timed out"):
        author_with_response(timeout).check_delivery({}, 1)


class CheckingAuthor(DeterministicArtifactAuthor):
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail = True

    def check_delivery(self, evidence: dict[str, Any], number: int) -> ChartCheckResult:
        self.calls.append(number)
        assert evidence["rows"] and evidence["charts"][0]["svg"].startswith("<svg")
        return ChartCheckResult(
            status="fail" if self.fail else "pass", issues=["Test defect"] if self.fail else []
        )


@pytest.mark.asyncio
async def test_two_checks_block_then_retry_and_recheck_after_unit_revision(tmp_path: Path) -> None:
    content = b"country,period,indicator,value\nUSA,2021,CPI,100\nUSA,2022,CPI,108\n"
    client, current = await pipeline_client(tmp_path, content)
    added = await pipeline_command(
        client, current, "add", {"type": "add_model_job", "model": "descriptive"}
    )
    current = added.json()
    run = await pipeline_command(client, current, "generate", {"type": "run_pipeline"})
    assert run.status_code == 200, run.text
    current = run.json()
    app = client._transport.app  # type: ignore[attr-defined]
    author = CheckingAuthor()
    app.state.workflow_output_service.artifact_author = author
    checked = await output_command(client, current, "blocked", {"type": "request_output_review"})
    assert checked.status_code == 200, checked.text
    current = checked.json()
    output = current["session"]["output"]
    assert output["reviewIteration"] == 0 and output["reviewReport"] is None
    assert author.calls == [1, 2]
    assert output["chartSelfChecks"][-1]["status"] == "fail"
    finished = await output_command(client, current, "early-finish", {"type": "finalize_output"})
    assert finished.status_code == 422
    # Same idempotency key replays without new model calls.
    replay = await output_command(client, current, "blocked", {"type": "request_output_review"})
    assert replay.status_code == 200 and author.calls == [1, 2]
    author.fail = False
    reviewed = await output_command(client, current, "retry", {"type": "request_output_review"})
    assert reviewed.status_code == 200, reviewed.text
    current = reviewed.json()
    assert current["session"]["output"]["reviewIteration"] == 1
    assert author.calls == [1, 2, 1, 2]
    chart = next(a for a in output["artifacts"] if a["format"] == "svg")
    _, old_path = app.state.output_workspace_manager.get("planning-1", chart["id"])
    old_svg = ET.fromstring(old_path.read_bytes())
    selected = await output_command(
        client, current, "select", {"type": "select_artifact", "artifactId": chart["id"]}
    )
    proposed = await output_command(
        client,
        selected.json(),
        "propose",
        {"type": "propose_output_revision", "request": "Unit: Index (2021=100)"},
    )
    proposal = proposed.json()["session"]["output"]["pendingProposal"]
    assert proposal["patches"][0]["changes"] == {"unit": "Index (2021=100)"}
    applied = await output_command(
        client,
        proposed.json(),
        "apply",
        {"type": "apply_output_revision", "acceptedPatchIds": [proposal["patches"][0]["id"]]},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()["session"]["output"]
    assert result["reviewIteration"] == 2 and author.calls == [1, 2, 1, 2, 1, 2]
    new_chart = next(a for a in result["artifacts"] if a["format"] == "svg")
    _, new_path = app.state.output_workspace_manager.get("planning-1", new_chart["id"])
    new_svg = ET.fromstring(new_path.read_bytes())
    tag = "{http://www.w3.org/2000/svg}polyline"
    assert [e.attrib for e in old_svg.findall(tag)] == [e.attrib for e in new_svg.findall(tag)]
    spec = result["artifactSpecifications"][new_chart["id"]]
    assert spec["source_unit"] is None and spec["unit"] == "Index (2021=100)"
    # Old specs lacking the selection field migrate before a wording patch is applied.
    legacy = json.loads(json.dumps(run.json()["session"]))
    legacy["output"]["artifactSpecifications"][chart["id"]].pop("source_unit")
    replacement, migrated, _ = app.state.output_workspace_manager.regenerate(
        "planning-1", legacy, chart["id"], {"unit": "Index (2021=100)"}
    )
    assert migrated["source_unit"] is None
    _, migrated_path = app.state.output_workspace_manager.get("planning-1", replacement["id"])
    assert b"No plottable" not in migrated_path.read_bytes()
    with pytest.raises(OutputWorkspaceError, match="unsupported field"):
        app.state.output_workspace_manager.regenerate(
            "planning-1", legacy, chart["id"], {"source_unit": "Percent"}
        )
    reloaded = await client.get("/api/v1/workflow/sessions/planning-1")
    assert reloaded.json()["session"]["output"]["chartSelfChecks"] == result["chartSelfChecks"]
    await client.aclose()


@pytest.mark.skipif(os.getenv("MRA_LIVE_CHART_DELIVERY") != "1", reason="Opt-in real models")
@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["explicit_unit", "missing_unit"])
async def test_live_chart_author_two_checks_codex_delivery(tmp_path: Path, case: str) -> None:
    """Isolated delivery slice with synthetic data, not a public-source browser E2E."""
    from macro_research_agent.config import Settings
    from macro_research_agent.workflow.codex_output_reviewer import CodexLocalOutputReviewer

    content = (
        b"country,period,indicator,value,unit\n"
        b"USA,2021,CPI,100,Index\nUSA,2022,CPI,108,Index\n"
        b"USA,2023,CPI,110,Index\nUSA,2024,CPI,112,Index\n"
    )
    unit_request = "Unit: Index (2021=100)"
    if case == "missing_unit":
        content = (
            b"country,period,indicator,value,unit,indicator_name\n"
            b"USA,2021,FE_UNEMP,6,,Female unemployment (% of female labor force)\n"
            b"USA,2022,FE_UNEMP,5,,Female unemployment (% of female labor force)\n"
            b"USA,2023,FE_UNEMP,4.5,,Female unemployment (% of female labor force)\n"
            b"USA,2024,FE_UNEMP,4.2,,Female unemployment (% of female labor force)\n"
        )
        unit_request = "Unit: Percent of female labor force"
    client, current = await pipeline_client(tmp_path, content)
    added = await pipeline_command(
        client, current, "live-add", {"type": "add_model_job", "model": "descriptive"}
    )
    current = added.json()
    settings = Settings.from_environment()
    author = DeepSeekChartAuthor(
        api_key=settings.deepseek_api_key,
        model_id=settings.deepseek_model,
        endpoint=settings.deepseek_endpoint,
        timeout_seconds=settings.stage_ai_timeout_seconds,
    )
    app = client._transport.app  # type: ignore[attr-defined]
    app.state.output_workspace_manager.artifact_author = author
    app.state.workflow_output_service.artifact_author = author
    app.state.workflow_output_service.output_reviewer = CodexLocalOutputReviewer(
        working_root=tmp_path / "codex-review", timeout_seconds=240
    )
    run = await pipeline_command(client, current, "live-generate", {"type": "run_pipeline"})
    assert run.status_code == 200, run.text
    current = run.json()
    assert current["session"]["output"]["artifacts"]
    reviewed = await output_command(
        client, current, "live-review", {"type": "request_output_review"}
    )
    assert reviewed.status_code == 200, reviewed.text
    current = reviewed.json()
    output = current["session"]["output"]
    print(
        json.dumps(
            {"selfChecks": output.get("chartSelfChecks"), "review": output.get("reviewReport")},
            ensure_ascii=False,
        )
    )
    assert output["chartSelfChecks"][-1]["status"] == "pass"
    assert output["reviewIteration"] == 1
    assert output["reviewReport"]["status"] in {"pass", "warning"}
    chart = next(item for item in output["artifacts"] if item["format"] == "svg")
    selected = await output_command(
        client, current, "live-select", {"type": "select_artifact", "artifactId": chart["id"]}
    )
    proposed = await output_command(
        client,
        selected.json(),
        "live-propose",
        {"type": "propose_output_revision", "request": unit_request},
    )
    patches = proposed.json()["session"]["output"]["pendingProposal"]["patches"]
    applied = await output_command(
        client,
        proposed.json(),
        "live-apply",
        {"type": "apply_output_revision", "acceptedPatchIds": [patches[0]["id"]]},
    )
    assert applied.status_code == 200, applied.text
    current = applied.json()
    revised = current["session"]["output"]
    print(
        json.dumps(
            {
                "revisedSelfChecks": revised.get("chartSelfChecks"),
                "revisedReview": revised.get("reviewReport"),
            },
            ensure_ascii=False,
        )
    )
    assert len(revised["chartSelfChecks"]) == 2
    assert revised["chartSelfChecks"][-1]["status"] == "pass"
    assert revised["reviewIteration"] == 2
    assert revised["reviewReport"]["status"] in {"pass", "warning"}
    frozen = await output_command(
        client, current, "live-finish", {"type": "finalize_output", "acceptWarnings": True}
    )
    assert frozen.status_code == 200, frozen.text
    manifest_id = frozen.json()["session"]["output"]["manifestArtifactId"]
    manifest = await client.get(
        f"/api/v1/workflow/sessions/planning-1/output/artifacts/{manifest_id}/download"
    )
    assert manifest.status_code == 200
    assert manifest.json()["chartSelfChecks"] == revised["chartSelfChecks"]
    reload = await client.get("/api/v1/workflow/sessions/planning-1")
    assert reload.json()["session"]["status"] == "completed"
    print(json.dumps({"manifestId": manifest_id, "reloadStatus": "completed"}))
    await client.aclose()
