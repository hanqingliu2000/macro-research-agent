import hashlib
import json

import httpx
import pandas as pd
import pytest
from macro_research_agent.agent.data_access import frame_rows
from macro_research_agent.research_core.delivery_evidence import (
    chart_geometry_receipt,
    report_result_facts,
)
from macro_research_agent.research_core.numerics import chart_frame, svg_chart
from macro_research_agent.workflow.chart_author import DeepSeekChartAuthor
from macro_research_agent.workflow.output_review import ChartSpec
from macro_research_agent.workflow.output_workspace import OutputWorkspaceError
from macro_research_agent.workflow.plan_guidance import normalize_plan_guidance


def bound_chart():
    rows = [
        {
            "entity_code": "CHN",
            "indicator_code": "DEBT",
            "unit": "Percent of GDP",
            "period": year,
            "value": value,
        }
        for year, value in [("2010", 33.184085), ("2024", 90.421028)]
    ]
    spec = ChartSpec(
        title="Debt",
        unit="Percent of GDP",
        source_unit="Percent of GDP",
        indicator_code="DEBT",
        source_note="Source: IMF",
        x_field="period",
        y_fields=["CHN"],
        alt_text="Annual general government debt",
        data_hash="sha256:data",
        guideline_version="publication-v1",
    )
    svg = svg_chart(chart_frame(pd.DataFrame(rows), "DEBT", "Percent of GDP"), spec)
    return rows, spec, svg


def inspect(svg=None):
    rows, spec, original = bound_chart()
    content = svg if svg is not None else original
    return chart_geometry_receipt(
        artifact_id="chart",
        artifact_hash="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        dataset_hash="sha256:data",
        specification=spec.model_dump(),
        svg=content,
        rows=rows,
    )


def test_native_tick_math_is_bound_and_not_a_model_approval():
    receipt = inspect()
    assert all(c["status"] == "pass" for c in receipt["checks"])
    ticks = next(c["ticks"] for c in receipt["checks"] if c["rule"] == "axis_ticks")
    assert [round(t["expectedValue"], 2) for t in ticks[1:4]] == [76.11, 61.80, 47.49]
    assert [t["textBaselineY"] for t in ticks[1:4]] == [159, 250, 341]
    assert [t["gridlineY"] for t in ticks[1:4]] == [155, 246, 337]
    assert receipt["approval"] is False and receipt["artifactHash"].startswith("sha256:")


def test_true_tick_and_point_corruption_and_unverifiable_inputs_fail_closed():
    _, _, svg = bound_chart()
    changed = inspect(svg.replace(">76.11<", ">75.76<"))
    assert next(c for c in changed["checks"] if c["rule"] == "axis_ticks")["status"] == "fail"
    changed = inspect(svg.replace('points="82.0,428.0', 'points="82.0,100.0'))
    assert (
        next(c for c in changed["checks"] if c["rule"] == "series_coordinates")["status"] == "fail"
    )
    assert inspect("<svg/>")["checks"][-1]["status"] == "unverifiable"
    rows, spec, svg = bound_chart()
    corrupt = chart_geometry_receipt(
        artifact_id="chart",
        artifact_hash="sha256:wrong",
        dataset_hash="sha256:data",
        specification=spec.model_dump(),
        svg=svg,
        rows=rows,
    )
    assert corrupt["checks"][-1]["status"] == "unverifiable"


@pytest.mark.parametrize("recovers", [True, False])
def test_model_numeric_false_positive_is_repaired_once_not_silently_approved(recovers):
    receipt = inspect()
    fail = {
        "status": "fail",
        "issues": ["Bad tick math"],
        "findings": [
            {
                "category": "numeric_geometry",
                "artifact_id": "chart",
                "evidence_refs": ["chart:axis_ticks"],
                "message": "Bad tick math",
            }
        ],
    }
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        body = (
            {"status": "pass", "issues": [], "findings": []}
            if recovers and len(calls) == 2
            else fail
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    author = DeepSeekChartAuthor(
        api_key="fixture",
        model_id="fixture",
        endpoint="https://fixture",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    evidence = {
        "checkProtocol": "agent-author-check-v7",
        "geometryReceipts": [receipt],
        "artifactManifest": [{"id": "chart"}],
        "availableEvidenceRefs": ["chart:axis_ticks"],
    }
    if recovers:
        assert author.check_delivery(evidence, 2).status == "pass"
    else:
        with pytest.raises(OutputWorkspaceError, match="after repair"):
            author.check_delivery(evidence, 2)
    assert len(calls) == 2
    assert "numeric_evidence_conflict" in calls[1]["messages"][1]["content"]


def test_fact_projection_does_not_invent_analysis_or_mix_phase_and_endpoint_samples():
    result = {
        "id": "r",
        "kind": "descriptive",
        "window": {"start": "2010", "end": "2019"},
        "sample": {"observations": 10},
        "result": {"statistics": [{"variable": "DEBT", "count": 10, "mean": 40}]},
    }
    fact = report_result_facts([result])[0]
    assert fact["sample"]["observations"] == fact["perVariableStatistics"][0]["count"] == 10
    assert fact["endpointComparisons"] == [] and "recordHash" in fact


def test_granted_rows_keep_snapshot_float_precision_and_nonfinite_nulls():
    value = 2.33950385203023
    frame = pd.DataFrame(
        {
            "value": [value, 1.234567890123456e-20, float("nan"), float("inf")],
            "count": [2**54 + 1] * 4,
            "flag": [True] * 4,
        }
    )
    rows = frame_rows(frame)
    assert rows[0]["value"] == value and rows[1]["value"] == 1.234567890123456e-20
    assert rows[2]["value"] is None and rows[3]["value"] is None
    assert rows[0]["count"] == 2**54 + 1 and rows[0]["flag"] is True
    assert json.loads(json.dumps(rows))[0]["value"] == value


def test_geometry_from_granted_full_precision_gdp_rows_matches_raw_renderer():
    rows, spec, _ = bound_chart()
    rows[0]["value"], rows[1]["value"] = 2.33950385203023, 10.5916903885704
    frame = pd.DataFrame(rows)
    svg = svg_chart(chart_frame(frame, "DEBT", "Percent of GDP"), spec)
    receipt = chart_geometry_receipt(
        artifact_id="chart",
        artifact_hash="sha256:" + hashlib.sha256(svg.encode()).hexdigest(),
        dataset_hash="sha256:data",
        specification=spec.model_dump(),
        svg=svg,
        rows=frame_rows(frame),
    )
    assert all(c["status"] == "pass" for c in receipt["checks"])


def test_post_acquisition_confirmation_is_not_a_blocker_but_credentials_remain_one():
    text = (
        "Whether WDI publishes complete 2024 annual values for both series for China "
        "is confirmed only after acquisition."
    )
    assert normalize_plan_guidance([text], [])[0] == []
    credential = "Missing connector credential; availability is confirmed only after acquisition."
    assert normalize_plan_guidance([credential], [])[0] == [credential]
