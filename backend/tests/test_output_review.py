from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessGrant,
    ModelDatasetContext,
)
from macro_research_agent.workflow.output_review import (
    ChartSpec,
    DeterministicArtifactAuthor,
    DeterministicOutputReviewer,
    OutputReviewFinding,
    OutputReviewRequest,
    ReportSpec,
    deterministic_cross_artifact_review,
    deterministic_preflight,
    incomplete_patch_groups,
    inspect_png_pixels,
    output_artifact_set_hash,
    selected_preflight_findings,
    stable_hash,
)
from macro_research_agent.workflow.output_workspace import _axis_label, _png_review_render
from macro_research_agent.workflow.publication_guidelines import (
    PUBLICATION_GUIDELINE_VERSION,
    get_publication_guideline,
)
from macro_research_agent.workflow.states import WorkflowStage
from pydantic import ValidationError


class ReportContentAccess:
    def __init__(self, content: str) -> None:
        self.content = content.encode("utf-8")

    def read_artifact_content(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        return self.content

    def read_review_render(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        raise AssertionError("A report review must not request a chart render.")


def report_review_request(specification: dict[str, object]) -> OutputReviewRequest:
    return OutputReviewRequest(
        session_id="session-1",
        artifact_set_id="set-1",
        artifact_set_hash="sha256:set",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        artifacts=[
            {"id": "report-1", "format": "report", "hash": "sha256:report"},
            {"id": "chart-1", "format": "svg", "hash": "sha256:chart"},
        ],
        specifications={"report-1": specification},
        review_render_hashes={},
        review_render_refs={},
        selected_artifact_ids=["report-1", "chart-1"],
        result_summary={},
        preflight_findings=[],
        dataset=ModelDatasetContext(
            grant=ModelDataAccessGrant(
                access_id="grant-1",
                session_id="session-1",
                stage=WorkflowStage.OUTPUT,
                source_kind="snapshot",
                source_ref="snapshot-1",
                content_hash="sha256:data",
                classification="user_supplied",
                provider_profile="deterministic-local",
                model_id="deterministic-output-review-v1",
                columns=["entity_code", "value"],
                row_count=2,
                page_size=2,
                page_count=1,
                remote_disclosure_allowed=False,
            )
        ),
        iteration=1,
    )


def test_output_specs_are_strict_and_author_report_preserves_inference_boundary() -> None:
    author = DeterministicArtifactAuthor()
    chart = author.author_chart_spec(
        title="Inflation comparison",
        source_note="Source: approved analytical snapshot",
        y_fields=["USA", "JPN"],
        guideline_version="basic-v1",
        data_hash="sha256:data",
    )
    assert chart.schema_version == "mra-output-spec-v2"
    assert chart.alt_text
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**chart.model_dump(), "unregistered": True})

    report = author.author_report(
        title="Inflation comparison",
        scope="Compare two economies.",
        row_count=6,
        source_note="Source: approved analytical snapshot",
        model_result_count=1,
        diagnostics=["Typed pipeline validation passed."],
        warnings=[],
    )
    assert "Results are descriptive unless" in report
    assert "6 observations" in report


def test_publication_guideline_is_registered_and_specs_use_accessible_defaults() -> None:
    guideline = get_publication_guideline(PUBLICATION_GUIDELINE_VERSION)
    assert guideline.status == "approved"
    assert guideline.chart.maximum_series == 6
    assert len(set(guideline.chart.palette)) == 6
    chart = ChartSpec(
        title="Inflation comparison",
        unit="Percent",
        source_note="Source: approved analytical snapshot",
        x_field="period",
        y_fields=["USA", "JPN"],
        alt_text="Inflation in the United States and Japan over time.",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    )
    assert chart.palette == list(guideline.chart.palette)
    assert chart.line_patterns == ["solid", "dash", "dot"]
    with pytest.raises(ValueError, match="not registered"):
        get_publication_guideline("unknown-v1")
    contract = (
        Path(__file__).resolve().parents[2] / "guidelines" / "publication-v1.yaml"
    ).read_text(encoding="utf-8")
    assert f'version: "{PUBLICATION_GUIDELINE_VERSION}"' in contract
    assert 'output_specification: "mra-output-spec-v2"' in contract
    assert all(color in contract for color in guideline.chart.palette)


def test_selective_review_ignores_findings_for_unselected_artifacts() -> None:
    selected = OutputReviewFinding(
        finding_id="selected",
        rule_id="TABLE-COLUMNS-001",
        severity="fail",
        message="Selected table is too wide.",
        artifact_ids=["table-selected"],
        blocking=True,
    ).model_dump(mode="json")
    unselected = OutputReviewFinding(
        finding_id="unselected",
        rule_id="TABLE-COLUMNS-001",
        severity="fail",
        message="Unselected table is too wide.",
        artifact_ids=["table-unselected"],
        blocking=True,
    ).model_dump(mode="json")
    package = OutputReviewFinding(
        finding_id="package",
        rule_id="DATA-VALUE-001",
        severity="fail",
        message="The approved data is empty.",
        blocking=True,
    ).model_dump(mode="json")

    kept = selected_preflight_findings(
        [selected, unselected, package],
        {"table-selected"},
    )

    assert [item.finding_id for item in kept] == ["selected", "package"]


def test_publication_preflight_enforces_chart_and_table_boundaries() -> None:
    chart = ChartSpec(
        title="A" * 91,
        unit="Percent",
        source_note="Source: approved analytical snapshot",
        x_field="period",
        y_fields=[f"series-{index}" for index in range(7)],
        alt_text="Seven series over time.",
        width=800,
        height=400,
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    ).model_dump(mode="json")
    table = {
        "schema_version": "mra-output-spec-v2",
        "title": "Wide table",
        "columns": [f"column-{index}" for index in range(25)],
        "unit": "Percent",
        "source_note": "Source: approved analytical snapshot",
        "number_format": "0.00",
        "freeze_header": True,
        "enable_filters": True,
        "numeric_alignment": "right",
        "missing_value_display": "…",
        "guideline_version": PUBLICATION_GUIDELINE_VERSION,
        "data_hash": "sha256:data",
    }
    findings = deterministic_preflight(
        [
            {"id": "chart-1", "format": "svg", "hash": "sha256:chart"},
            {"id": "table-1", "format": "csv", "hash": "sha256:table"},
        ],
        {"chart-1": chart, "table-1": table},
        1,
        {},
        review_render_refs={
            "chart-1": {
                "width": 800,
                "height": 400,
                "dataHash": "sha256:data",
                "specHash": stable_hash(chart),
            }
        },
    )
    rule_ids = {item.rule_id for item in findings}
    assert rule_ids >= {
        "CHART-TITLE-001",
        "CHART-SERIES-001",
        "CHART-SIZE-001",
        "TABLE-COLUMNS-001",
    }


def test_publication_preflight_rejects_style_drift() -> None:
    chart = ChartSpec(
        title="Inflation comparison",
        unit="Percent",
        source_note="Source: approved analytical snapshot",
        x_field="period",
        y_fields=["USA", "JPN"],
        alt_text="Two series over time.",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    ).model_dump(mode="json")
    chart["palette"] = ["#FF0000"]
    table = {
        "schema_version": "mra-output-spec-v2",
        "title": "Results",
        "columns": ["period", "value"],
        "unit": "Percent",
        "source_note": "Source: approved analytical snapshot",
        "number_format": "0.00",
        "freeze_header": False,
        "enable_filters": True,
        "numeric_alignment": "right",
        "missing_value_display": "…",
        "guideline_version": PUBLICATION_GUIDELINE_VERSION,
        "data_hash": "sha256:data",
    }
    findings = deterministic_preflight(
        [
            {"id": "chart-1", "format": "svg", "hash": "sha256:chart"},
            {"id": "table-1", "format": "xlsx", "hash": "sha256:table"},
        ],
        {"chart-1": chart, "table-1": table},
        1,
        {},
        review_render_refs={
            "chart-1": {
                "width": 900,
                "height": 500,
                "dataHash": "sha256:data",
                "specHash": stable_hash(chart),
            }
        },
    )
    assert {item.rule_id for item in findings} >= {"CHART-STYLE-001", "TABLE-STYLE-001"}


def test_publication_report_review_checks_content_data_and_references() -> None:
    specification = ReportSpec(
        schema_version="mra-report-spec-v1",
        title="R" * 121,
        source_note="Source: approved snapshot",
        observation_count=1,
        model_result_count=0,
        citation_refs=[],
        required_sections=[
            "Scope",
            "Data and method",
            "Results",
            "Diagnostics and limitations",
            "Reproducibility",
        ],
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    ).model_dump(mode="json")
    findings: list[OutputReviewFinding] = []
    DeterministicOutputReviewer._review_report(
        report_review_request(specification),
        {"id": "report-1", "format": "report", "hash": "sha256:report"},
        specification,
        [{"entity_code": "USA", "value": 2.0}, {"entity_code": "JPN", "value": 1.5}],
        ReportContentAccess("# Incomplete report\n\n## Scope\nComparison.\n"),
        findings,
    )
    rule_ids = {item.rule_id for item in findings}
    assert rule_ids >= {
        "REPORT-SECTIONS-001",
        "REPORT-DATA-001",
        "REPORT-SOURCE-001",
        "REPORT-CAUSAL-001",
        "REPORT-REPRODUCIBILITY-001",
        "REPORT-ARTIFACT-REFERENCE-001",
        "REPORT-CITATION-001",
        "REPORT-TITLE-001",
    }
    title_finding = next(item for item in findings if item.rule_id == "REPORT-TITLE-001")
    assert title_finding.proposed_patch_ids == []


def test_structured_artifact_refs_do_not_require_english_figure_table_keywords() -> None:
    specification = ReportSpec(
        schema_version="mra-report-spec-v1",
        title="研究结果",
        source_note="Source: approved snapshot",
        observation_count=2,
        model_result_count=0,
        citation_refs=["source-1"],
        required_sections=["Scope"],
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    ).model_dump(mode="json")
    request = report_review_request(specification)
    request.report_drafts = {"report-1": {"artifactReferences": ["chart-1"]}}
    findings = []
    DeterministicOutputReviewer._review_report(
        request,
        {"id": "report-1", "format": "report", "hash": "sha256:report"},
        specification,
        [{"value": 2}, {"value": 3}],
        ReportContentAccess(
            "## Scope\nSource: approved snapshot\n图：chart_1.svg\n"
            "No causal inference; reproduction manifest."
        ),
        findings,
    )
    assert not any(finding.rule_id == "REPORT-ARTIFACT-REFERENCE-001" for finding in findings)


def test_report_review_rejects_a_mismatched_draft_or_evidence_hash() -> None:
    specification = ReportSpec(
        title="Bound report",
        source_note="Source: approved snapshot",
        observation_count=2,
        model_result_count=0,
        citation_refs=["Approved snapshot"],
        required_sections=[
            "Scope",
            "Data and method",
            "Results",
            "Diagnostics and limitations",
            "Reproducibility",
        ],
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
        draft_hash="sha256:expected-draft",
        evidence_ledger_hash="sha256:expected-ledger",
    ).model_dump(mode="json")
    request = report_review_request(specification)
    request.report_drafts = {"report-1": {"claims": []}}
    request.evidence_ledgers = {"report-1": []}
    findings: list[OutputReviewFinding] = []

    DeterministicOutputReviewer._review_report(
        request,
        {"id": "report-1", "format": "report", "hash": "sha256:report"},
        specification,
        [{"entity_code": "USA", "value": 2.0}, {"entity_code": "JPN", "value": 1.5}],
        ReportContentAccess(
            "# Bound report\n\n"
            "## Scope\nScope.\n## Data and method\nTwo observations.\n"
            "## Results\nUSA and JPN.\n## Diagnostics and limitations\nNo causal claim.\n"
            "## Reproducibility\nManifest.\nSource: approved snapshot.\n"
            "Approved snapshot\nchart-1\n"
        ),
        findings,
    )

    assert "REPORT-EVIDENCE-BINDING-001" in {item.rule_id for item in findings}


def test_visual_review_decodes_render_pixels_instead_of_trusting_metadata() -> None:
    # LRS-OUTPUT-04: visual evidence is the immutable render bytes, not a hash or UI screenshot.
    data = pd.DataFrame({"period": ["2023", "2024"], "USA": [2.0, 2.5]})
    content = _png_review_render(data)
    width, height, distinct_pixels = inspect_png_pixels(content)
    assert (width, height) == (900, 500)
    assert distinct_pixels >= 3
    titled = _png_review_render(
        data,
        spec=ChartSpec(
            title="A title that must be present in the raster",
            unit="Percent",
            source_note="Source: test",
            x_field="period",
            y_fields=["USA"],
            alt_text="A test chart.",
            guideline_version=PUBLICATION_GUIDELINE_VERSION,
            data_hash="sha256:test",
        ),
    )
    assert titled != content
    with pytest.raises(ValueError):
        inspect_png_pixels(b"not-a-png" + content[9:])


def test_axis_labels_follow_the_chart_number_format() -> None:
    assert _axis_label(4.1, "0.00") == "4.10"
    assert _axis_label(0.002, "0.0%") == "0.2%"
    assert _axis_label(1_250_000, "0.00") == "1.25M"


def test_preflight_returns_rule_addressed_blocking_findings() -> None:
    artifacts = [
        {
            "id": "chart-1",
            "format": "svg",
            "hash": "sha256:chart",
        }
    ]
    findings = deterministic_preflight(
        artifacts,
        {"chart-1": {"title": "Incomplete"}},
        0,
        {"charts": True, "researchReport": True},
        review_render_refs={},
        workbook_structure_valid=False,
    )
    rule_ids = {item.rule_id for item in findings}
    assert rule_ids >= {
        "PKG-DELIVERABLE-001",
        "DATA-VALUE-001",
        "CHART-METADATA-001",
        "VIS-RENDER-BINDING-001",
        "WORKBOOK-STRUCTURE-001",
    }
    assert all(item.blocking for item in findings)


def test_preflight_preserves_workbook_lint_rule_and_artifact_binding() -> None:
    findings = deterministic_preflight(
        [],
        {},
        1,
        {},
        workbook_lint_findings=[
            {
                "rule_id": "WORKBOOK-COLUMNS-001",
                "severity": "fail",
                "message": "Required column is missing.",
                "location": "Analytical Data",
                "blocking": True,
                "artifact_id": "workbook-1",
            }
        ],
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "WORKBOOK-COLUMNS-001"
    assert findings[0].artifact_ids == ["workbook-1"]
    assert findings[0].message.startswith("Analytical Data:")


def test_output_review_request_rejects_browser_or_arbitrary_fields() -> None:
    with pytest.raises(ValidationError):
        OutputReviewRequest.model_validate(
            {
                "schema_version": "mra-output-review-v1",
                "artifact_set_id": "set-1",
                "artifact_set_hash": "sha256:set",
                "guideline_version": "basic-v1",
                "artifacts": [],
                "specifications": {},
                "review_render_hashes": {},
                "selected_artifact_ids": [],
                "result_summary": {},
                "preflight_findings": [],
                "dataset": {},
                "iteration": 1,
                "browser_screenshot": "forbidden",
            }
        )


def test_cross_artifact_review_groups_cosmetic_fixes_and_blocks_data_mismatch() -> None:
    artifacts = [
        {"id": "chart-1", "format": "svg"},
        {"id": "table-1", "format": "xlsx"},
        {"id": "data-1", "format": "csv"},
    ]
    specifications = {
        "chart-1": {
            "source_note": "Source: approved snapshot",
            "unit": "Percent",
            "data_hash": "sha256:data-a",
            "guideline_version": "basic-v1",
        },
        "table-1": {
            "source_note": "Source: approved snapshot",
            "unit": "Percent",
            "data_hash": "sha256:data-a",
            "guideline_version": "basic-v1",
        },
        "data-1": {
            "source_note": "Source: older snapshot",
            "unit": "Percent",
            "data_hash": "sha256:data-a",
            "guideline_version": "basic-v1",
        },
    }
    findings, patches = deterministic_cross_artifact_review(
        artifacts, specifications, ["chart-1", "table-1", "data-1"]
    )
    source_finding = next(item for item in findings if item.rule_id == "PACKAGE-SOURCE-001")
    assert source_finding.severity == "warning"
    assert len(patches) == 1
    assert patches[0].artifact_id == "data-1"
    assert patches[0].group_id
    assert patches[0].changes == {"source_note": "Source: approved snapshot"}

    specifications["data-1"]["data_hash"] = "sha256:data-b"
    findings, _ = deterministic_cross_artifact_review(
        artifacts, specifications, ["chart-1", "table-1", "data-1"]
    )
    mismatch = next(item for item in findings if item.rule_id == "PACKAGE-DATA-001")
    assert mismatch.blocking is True
    assert mismatch.severity == "fail"


def test_artifact_set_hash_includes_specs_and_patch_groups_are_atomic() -> None:
    artifacts = [
        {"id": "chart-1", "hash": "sha256:chart"},
        {"id": "table-1", "hash": "sha256:table"},
    ]
    original = output_artifact_set_hash(
        artifacts, {"chart-1": {"unit": "Index"}, "table-1": {"unit": "Index"}}
    )
    revised = output_artifact_set_hash(
        artifacts, {"chart-1": {"unit": "Percent"}, "table-1": {"unit": "Index"}}
    )
    assert revised != original

    patches = [
        {"id": "patch-1", "groupId": "group-1"},
        {"id": "patch-2", "groupId": "group-1"},
        {"id": "patch-3"},
    ]
    assert incomplete_patch_groups(patches, {"patch-1"}) == ["group-1"]
    assert incomplete_patch_groups(patches, {"patch-1", "patch-2"}) == []
    assert incomplete_patch_groups(patches, {"patch-3"}) == []
