from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from macro_research_agent.workflow.codex_output_reviewer import (
    CodexCommandResult,
    CodexLocalOutputReviewer,
    CodexVisualResponse,
    strict_codex_output_schema,
)
from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessGrant,
    ModelDataPage,
    ModelDatasetContext,
)
from macro_research_agent.workflow.output_review import (
    ChartSpec,
    OutputReviewRequest,
    ReportSpec,
    stable_hash,
)
from macro_research_agent.workflow.output_workspace import _png_review_render
from macro_research_agent.workflow.publication_guidelines import PUBLICATION_GUIDELINE_VERSION
from macro_research_agent.workflow.reporting import (
    EvidenceClaimV1,
    ReportCitationV1,
    ReportDraftV1,
    ReportReviewResponseV1,
    ReportSectionV1,
    render_report_markdown,
)
from macro_research_agent.workflow.states import WorkflowStage


class StubDataAccess:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def read_page(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        selected = self.rows[offset : offset + (limit or len(self.rows))]
        return ModelDataPage(
            access_id=access_id,
            offset=offset,
            limit=limit or len(self.rows),
            rows=selected,
            page_hash=f"sha256:page-{offset}",
        )


class StubRenderAccess:
    def __init__(self, render: bytes) -> None:
        self.render = render

    def read_review_render(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        return self.render

    def read_artifact_content(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        raise AssertionError("Chart review must use the direct PNG render.")


class RecordingRunner:
    def __init__(self, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.command: list[str] = []
        self.environment: dict[str, str] = {}
        self.context: dict[str, Any] = {}

    def run(
        self,
        command: Sequence[str],
        *,
        prompt: str,
        timeout_seconds: float,
        environment: dict[str, str],
    ) -> CodexCommandResult:
        self.command = list(command)
        self.environment = environment
        directory = Path(self.command[self.command.index("--cd") + 1])
        self.context = json.loads((directory / "review-context.json").read_text())
        if self.returncode == 0:
            output = Path(self.command[self.command.index("--output-last-message") + 1])
            output.write_text(
                json.dumps(
                    {
                        "observations": [
                            {
                                "artifact_id": "chart-1",
                                "rule_id": "VISUAL-LEGIBILITY",
                                "severity": "warning",
                                "message": "The smallest labels are difficult to read.",
                            }
                        ]
                    }
                )
            )
        return CodexCommandResult(returncode=self.returncode)


class ReportRunner(RecordingRunner):
    def run(
        self,
        command: Sequence[str],
        *,
        prompt: str,
        timeout_seconds: float,
        environment: dict[str, str],
    ) -> CodexCommandResult:
        self.command = list(command)
        self.environment = environment
        directory = Path(self.command[self.command.index("--cd") + 1])
        self.context = json.loads((directory / "report-review-context.json").read_text())
        output = Path(self.command[self.command.index("--output-last-message") + 1])
        output.write_text(
            json.dumps(
                {
                    "status": "fail",
                    "findings": [
                        {
                            "findingId": "finding-report-1",
                            "ruleId": "FORECAST-COVERAGE",
                            "severity": "fail",
                            "message": "The Results section does not state the forecast horizon.",
                            "sectionIds": ["section-results"],
                            "evidenceRefs": ["sha256:data"],
                        }
                    ],
                    "directives": [
                        {
                            "directiveId": "directive-report-1",
                            "artifactId": "report-1",
                            "targetSectionIds": ["section-results"],
                            "issue": "State the approved forecast horizon.",
                            "preserveEvidenceRefs": ["sha256:data"],
                            "acceptanceCriteria": ["Name the horizon and uncertainty."],
                            "requiresUpstreamStage": False,
                        }
                    ],
                }
            )
        )
        return CodexCommandResult(returncode=0)


def test_codex_output_schemas_require_every_property_recursively() -> None:
    for model in (CodexVisualResponse, ReportReviewResponseV1):
        schema = strict_codex_output_schema(model)
        objects = [schema, *schema.get("$defs", {}).values()]
        for item in objects:
            assert item.get("additionalProperties") is False
            assert item.get("required") == list(item.get("properties", {}))
        assert "default" not in json.dumps(schema)


class ReportRenderAccess:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read_review_render(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        raise AssertionError("Report review must not request an image render.")

    def read_artifact_content(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        return self.content


def review_fixture() -> tuple[OutputReviewRequest, StubDataAccess, StubRenderAccess]:
    rows = [
        {
            "entity_code": "CHN",
            "indicator_code": "CPI",
            "period": "2023",
            "value": 100.0,
            "unit": "Index",
        },
        {
            "entity_code": "CHN",
            "indicator_code": "CPI",
            "period": "2024",
            "value": 102.0,
            "unit": "Index",
        },
    ]
    chart_data = pd.DataFrame({"period": ["2023", "2024"], "CHN": [100.0, 102.0]})
    specification = ChartSpec(
        title="China CPI",
        indicator_code="CPI",
        unit="Index",
        source_note="Source: test data",
        x_field="period",
        y_fields=["CHN"],
        alt_text="China CPI index across 2023 and 2024.",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="sha256:data",
    )
    request = OutputReviewRequest(
        session_id="session-1",
        artifact_set_id="set-1",
        artifact_set_hash="sha256:set",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        artifacts=[{"id": "chart-1", "format": "svg", "hash": "sha256:chart"}],
        specifications={"chart-1": specification.model_dump(mode="json")},
        review_render_hashes={"chart-1": "sha256:render"},
        review_render_refs={
            "chart-1": {"id": "render-1", "hash": "sha256:render", "width": 900, "height": 500}
        },
        selected_artifact_ids=["chart-1"],
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
                classification="public",
                provider_profile="codex-local",
                model_id="codex-configured-default",
                columns=list(rows[0]),
                row_count=len(rows),
                page_size=len(rows),
                page_count=1,
                remote_disclosure_allowed=True,
            )
        ),
        iteration=1,
    )
    return (
        request,
        StubDataAccess(rows),
        StubRenderAccess(_png_review_render(chart_data, spec=specification)),
    )


def test_codex_local_reviews_direct_renders_with_versioned_placeholder(tmp_path: Path) -> None:
    request, data_access, render_access = review_fixture()
    runner = RecordingRunner()
    reviewer = CodexLocalOutputReviewer(
        working_root=tmp_path,
        codex_bin="/bin/echo",
        runner=runner,
    )

    report = reviewer.review(  # type: ignore[arg-type]
        request, data_access, render_access
    )

    assert report.status == "warning"
    assert report.provider_profile == "codex-local"
    assert {item.rule_id for item in report.findings} == {
        "VISUAL-RUBRIC-PLACEHOLDER",
        "CODEX-VISUAL-LEGIBILITY",
    }
    assert runner.context["underlying_rows"] == data_access.rows
    assert runner.context["visual_rubric_status"] == "placeholder"
    assert runner.context["visual_rubric"]["version"] == report.visual_rubric_version
    assert runner.context["visual_rubric_hash"] == report.visual_rubric_hash
    assert {rule["rule_id"] for rule in runner.context["visual_rubric"]["rules"]} == {
        "VISUAL-CLIPPING",
        "VISUAL-OVERLAP",
        "VISUAL-LEGIBILITY",
        "VISUAL-LEGEND",
        "VISUAL-RENDER-SPEC-MISMATCH",
        "VISUAL-AXIS-UNIT",
        "VISUAL-UNCERTAINTY",
        "VISUAL-CAPTION-SOURCE",
    }
    assert "--ephemeral" in runner.command
    assert runner.command[runner.command.index("--sandbox") + 1] == "read-only"
    assert "--image" in runner.command
    assert "OPENAI_API_KEY" not in runner.environment
    assert not list(tmp_path.glob("review-*"))


def test_codex_local_fails_closed_when_command_cannot_complete(tmp_path: Path) -> None:
    request, data_access, render_access = review_fixture()
    reviewer = CodexLocalOutputReviewer(
        working_root=tmp_path,
        codex_bin="/bin/echo",
        runner=RecordingRunner(returncode=1),
    )

    report = reviewer.review(  # type: ignore[arg-type]
        request, data_access, render_access
    )

    assert report.status == "fail"
    unavailable = next(
        item for item in report.findings if item.rule_id == "CODEX-LOCAL-REVIEW-UNAVAILABLE"
    )
    assert unavailable.blocking is True


def test_codex_local_returns_section_bound_report_directive(tmp_path: Path) -> None:
    rows = [{"period": "2024", "value": 1.0}]
    claim = EvidenceClaimV1(
        claimId="claim-1",
        statement="The snapshot contains one observation.",
        claimType="descriptive",
        evidenceRefs=["sha256:data"],
        uncertainty="No sampling uncertainty is asserted.",
        limitation="The statement is snapshot-bound.",
        citationRefs=["source-1"],
    )
    headings = [
        "Scope",
        "Data and method",
        "Results",
        "Diagnostics and limitations",
        "Reproducibility",
    ]
    draft = ReportDraftV1(
        title="Research report",
        sections=[
            ReportSectionV1(
                sectionId="section-" + heading.lower().replace(" ", "-"),
                heading=heading,
                body=(
                    "Source: approved analytical snapshot. Reproduction manifest. "
                    "No causal inference is claimed."
                ),
                claimIds=["claim-1"] if heading == "Results" else [],
                evidenceRefs=["sha256:data"] if heading == "Results" else [],
            )
            for heading in headings
        ],
        claims=[claim],
        limitations=["Snapshot-bound."],
        citations=[
            ReportCitationV1(
                citationId="source-1",
                label="Approved analytical snapshot",
                sourceRef="snapshot-1",
            )
        ],
    )
    request = OutputReviewRequest(
        session_id="session-1",
        artifact_set_id="set-1",
        artifact_set_hash="sha256:set",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        artifacts=[
            {
                "id": "report-1",
                "kind": "research_report",
                "format": "report",
                "hash": "sha256:report",
            }
        ],
        specifications={
            "report-1": ReportSpec(
                title="Research report",
                source_note="Source: approved analytical snapshot",
                observation_count=1,
                model_result_count=0,
                required_sections=headings,
                guideline_version=PUBLICATION_GUIDELINE_VERSION,
                data_hash="sha256:data",
                draft_hash=stable_hash(draft.model_dump(mode="json", by_alias=True)),
                evidence_ledger_hash=stable_hash([claim.model_dump(mode="json", by_alias=True)]),
            ).model_dump(mode="json")
        },
        review_render_hashes={},
        review_render_refs={},
        selected_artifact_ids=["report-1"],
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
                classification="public",
                provider_profile="codex-local",
                model_id="codex-configured-default",
                columns=["period", "value"],
                row_count=1,
                page_size=1,
                page_count=1,
                remote_disclosure_allowed=True,
            )
        ),
        iteration=1,
        report_drafts={"report-1": draft.model_dump(mode="json", by_alias=True)},
        evidence_ledgers={"report-1": [claim.model_dump(mode="json", by_alias=True)]},
    )
    runner = ReportRunner()
    reviewer = CodexLocalOutputReviewer(
        working_root=tmp_path,
        codex_bin="/bin/echo",
        runner=runner,
    )

    report = reviewer.review(  # type: ignore[arg-type]
        request,
        StubDataAccess(rows),
        ReportRenderAccess(render_report_markdown(draft).encode()),
    )

    assert report.semantic_report_status == "fail"
    assert report.status == "fail"
    assert report.report_directives[0].target_section_ids == ["section-results"]
    assert runner.context["registeredReads"]["read_rows"] == rows


@pytest.mark.skipif(
    os.getenv("MRA_LIVE_CODEX_OUTPUT_REVIEW") != "1",
    reason="Requires explicit opt-in and a locally authenticated Codex account.",
)
def test_live_codex_local_direct_render_review(tmp_path: Path) -> None:
    request, data_access, render_access = review_fixture()
    reviewer = CodexLocalOutputReviewer(working_root=tmp_path, timeout_seconds=120)

    report = reviewer.review(  # type: ignore[arg-type]
        request, data_access, render_access
    )

    assert report.provider_profile == "codex-local"
    assert report.status != "fail", [item.model_dump() for item in report.findings]
    assert any(item.rule_id == "VISUAL-RUBRIC-PLACEHOLDER" for item in report.findings)
