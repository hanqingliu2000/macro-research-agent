from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Literal, Protocol

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessPort,
    ModelDatasetContext,
)
from macro_research_agent.workflow.publication_guidelines import (
    PUBLICATION_GUIDELINE,
    get_publication_guideline,
)
from macro_research_agent.workflow.reporting import ReportRevisionDirectiveV1

OUTPUT_SPEC_VERSION = "mra-output-spec-v2"
OUTPUT_REVIEW_VERSION = "mra-output-review-v1"
OUTPUT_REVIEW_RULESET = "publication-v1"


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def output_artifact_set_hash(
    artifacts: list[dict[str, Any]], specifications: dict[str, dict[str, Any]]
) -> str:
    return stable_hash(
        [
            {
                "artifact_hash": artifact.get("hash"),
                "specification_hash": stable_hash(
                    specifications.get(str(artifact.get("id"))) or {}
                ),
            }
            for artifact in artifacts
        ]
    )


def incomplete_patch_groups(
    patches: list[dict[str, Any]], selected_patch_ids: set[str]
) -> list[str]:
    groups: dict[str, set[str]] = {}
    for patch in patches:
        group_id = str(patch.get("groupId") or "")
        if group_id:
            groups.setdefault(group_id, set()).add(str(patch.get("id")))
    return sorted(
        group_id
        for group_id, patch_ids in groups.items()
        if selected_patch_ids.intersection(patch_ids) and not patch_ids.issubset(selected_patch_ids)
    )


class ChartObservationFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series: str
    period: str
    origin: Literal["imputed", "winsorized"]


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mra-output-spec-v1", "mra-output-spec-v2"] = "mra-output-spec-v2"
    chart_type: Literal["line"] = "line"
    title: str = Field(min_length=1, max_length=160)
    indicator_code: str | None = None
    # Immutable selection, independent of editable unit wording. None means all units.
    source_unit: str | None = None
    unit: str = Field(min_length=1, max_length=80)
    source_note: str = Field(min_length=1, max_length=500)
    x_field: str = Field(min_length=1)
    y_fields: list[str] = Field(min_length=1, max_length=12)
    number_format: str = Field(default="0.00", min_length=1, max_length=40)
    alt_text: str = Field(min_length=1, max_length=500)
    width: int = Field(default=900, ge=320, le=2400)
    height: int = Field(default=500, ge=240, le=1600)
    legend_position: Literal["bottom"] = "bottom"
    palette: list[str] = Field(
        default_factory=lambda: list(PUBLICATION_GUIDELINE.chart.palette),
        min_length=1,
        max_length=6,
    )
    line_patterns: list[Literal["solid", "dash", "dot"]] = Field(
        default_factory=lambda: list(PUBLICATION_GUIDELINE.chart.line_patterns),
        min_length=1,
    )
    missing_value_policy: Literal["gap"] = "gap"
    observation_flags: list[ChartObservationFlag] = Field(default_factory=list)
    guideline_version: str = Field(min_length=1)
    data_hash: str = Field(min_length=1)


class TableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mra-output-spec-v1", "mra-output-spec-v2"] = "mra-output-spec-v2"
    title: str = Field(min_length=1, max_length=160)
    columns: list[str] = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=80)
    source_note: str = Field(min_length=1, max_length=500)
    number_format: str = Field(default="0.00", min_length=1, max_length=40)
    freeze_header: bool = True
    enable_filters: bool = True
    numeric_alignment: Literal["right"] = "right"
    missing_value_display: Literal["…"] = "…"
    guideline_version: str = Field(min_length=1)
    data_hash: str = Field(min_length=1)


class ReportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mra-report-spec-v1", "mra-report-spec-v2"] = "mra-report-spec-v2"
    title: str = Field(min_length=1, max_length=160)
    source_note: str = Field(min_length=1, max_length=500)
    observation_count: int = Field(ge=0)
    model_result_count: int = Field(ge=0)
    citation_refs: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(min_length=1)
    causal_boundary_required: bool = True
    reproduction_note_required: bool = True
    guideline_version: str = Field(min_length=1)
    data_hash: str = Field(min_length=1)
    draft_hash: str | None = Field(default=None, min_length=1)
    evidence_ledger_hash: str | None = Field(default=None, min_length=1)
    semantic_review_required: bool = True

    @model_validator(mode="after")
    def v2_binds_draft_and_evidence(self) -> ReportSpec:
        if self.schema_version == "mra-report-spec-v2" and (
            not self.draft_hash or not self.evidence_ledger_hash
        ):
            raise ValueError("Report specification v2 requires draft and evidence ledger hashes.")
        return self


class ArtifactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_id: str = Field(min_length=1)
    group_id: str | None = None
    artifact_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    changes: dict[
        Literal["title", "unit", "source_note", "number_format", "alt_text", "columns"],
        str | list[str],
    ] = Field(min_length=1)


class OutputReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: Literal["warning", "fail"]
    message: str = Field(min_length=1)
    artifact_ids: list[str] = Field(default_factory=list)
    blocking: bool = False
    proposed_patch_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    requires_upstream_stage: bool = False
    upstream_stage: Literal["data", "transformation"] | None = None


class OutputReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mra-output-review-v1"] = "mra-output-review-v1"
    session_id: str = Field(min_length=1)
    artifact_set_id: str = Field(min_length=1)
    artifact_set_hash: str = Field(min_length=1)
    guideline_version: str = Field(min_length=1)
    artifacts: list[dict[str, Any]]
    specifications: dict[str, dict[str, Any]]
    review_render_hashes: dict[str, str]
    review_render_refs: dict[str, dict[str, Any]]
    selected_artifact_ids: list[str]
    result_summary: dict[str, Any]
    preflight_findings: list[dict[str, Any]]
    dataset: ModelDatasetContext
    iteration: int = Field(ge=1, le=3)
    handoff: dict[str, Any] = Field(default_factory=dict)
    approved_plan: dict[str, Any] = Field(default_factory=dict)
    model_results: list[dict[str, Any]] = Field(default_factory=list)
    result_hashes: dict[str, str] = Field(default_factory=dict)
    hash_semantics: dict[str, str] = Field(default_factory=dict)
    report_drafts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence_ledgers: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    publication_guideline: dict[str, Any] = Field(default_factory=dict)


class OutputReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    schema_version: Literal["mra-output-review-v1"] = "mra-output-review-v1"
    status: Literal["pass", "warning", "fail"]
    provider_profile: str
    model_id: str
    target_artifact_set_hash: str
    guideline_version: str
    iteration: int = Field(ge=1, le=3)
    reviewed_artifact_ids: list[str]
    review_render_hashes: dict[str, str]
    data_access_id: str
    inspected_row_count: int = Field(ge=0)
    findings: list[OutputReviewFinding]
    patches: list[ArtifactPatch]
    report_directives: list[ReportRevisionDirectiveV1] = Field(default_factory=list)
    semantic_report_status: Literal["not_applicable", "pass", "fail", "requires_upstream_stage"] = (
        "not_applicable"
    )
    visual_rubric_version: str | None = None
    visual_rubric_hash: str | None = None
    visual_rubric_status: Literal["placeholder"] | None = None
    created_at: datetime


class OutputReviewPort(Protocol):
    provider_profile: str
    model_id: str
    remote_data_disclosure: bool

    def review(
        self,
        request: OutputReviewRequest,
        data_access: ModelDataAccessPort,
        render_access: OutputRenderAccessPort,
    ) -> OutputReviewReport: ...


class OutputRenderAccessPort(Protocol):
    def read_review_render(
        self, session_id: str, artifact_id: str, expected_hash: str
    ) -> bytes: ...

    def read_artifact_content(
        self, session_id: str, artifact_id: str, expected_hash: str
    ) -> bytes: ...


def inspect_png_pixels(content: bytes) -> tuple[int, int, int]:
    """Decode a bounded review PNG and return dimensions plus distinct RGB pixel count."""

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG":
                raise ValueError("Review render is not a PNG.")
            width, height = image.size
            if not width or not height or width * height > 4_000_000:
                raise ValueError("Review render dimensions are invalid or exceed the safety bound.")
            rgb = image.convert("RGB")
            distinct_pixels = len(set(rgb.get_flattened_data()))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise ValueError("Review render is not a valid bounded PNG.") from error
    return width, height, distinct_pixels


class ArtifactAuthorPort(Protocol):
    provider_profile: str
    model_id: str
    remote_data_disclosure: bool

    def author_chart_spec(
        self,
        *,
        title: str,
        source_note: str,
        y_fields: list[str],
        guideline_version: str,
        data_hash: str,
        indicator_code: str | None = None,
        unit: str = "As reported",
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> ChartSpec: ...

    def author_table_spec(
        self,
        *,
        title: str,
        columns: list[str],
        source_note: str,
        guideline_version: str,
        data_hash: str,
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> TableSpec: ...

    def author_report(
        self,
        *,
        title: str,
        scope: str,
        row_count: int,
        source_note: str,
        model_result_count: int,
        diagnostics: list[str],
        warnings: list[str],
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> str: ...

    def propose_revision(
        self,
        request: str,
        artifact: dict[str, Any],
        specification: dict[str, Any],
        target_artifact_set_hash: str,
    ) -> list[ArtifactPatch]: ...


class DeterministicArtifactAuthor:
    provider_profile = "deterministic-local"
    model_id = "deterministic-artifact-author-v1"
    remote_data_disclosure = False

    @staticmethod
    def _inspect_rows(
        dataset: ModelDatasetContext | None,
        data_access: ModelDataAccessPort | None,
    ) -> list[dict[str, Any]]:
        if dataset is None or data_access is None:
            return []
        grant = dataset.grant
        rows: list[dict[str, Any]] = []
        for offset in range(0, grant.row_count, grant.page_size):
            rows.extend(
                data_access.read_page(
                    grant.access_id,
                    session_id=grant.session_id,
                    stage=grant.stage,
                    offset=offset,
                ).rows
            )
        return rows

    def author_chart_spec(
        self,
        *,
        title: str,
        source_note: str,
        y_fields: list[str],
        guideline_version: str,
        data_hash: str,
        indicator_code: str | None = None,
        unit: str = "As reported",
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> ChartSpec:
        inspected_rows = self._inspect_rows(dataset, data_access)
        return ChartSpec(
            title=title,
            indicator_code=indicator_code,
            unit=unit,
            source_note=source_note,
            x_field="period",
            y_fields=y_fields or ["value"],
            alt_text=(
                f"Line chart for {indicator_code or title}, measured in {unit}, showing "
                f"{', '.join(y_fields or ['value'])} across time and based on "
                f"{len(inspected_rows)} inspected observations."
            ),
            guideline_version=guideline_version,
            data_hash=data_hash,
        )

    def author_table_spec(
        self,
        *,
        title: str,
        columns: list[str],
        source_note: str,
        guideline_version: str,
        data_hash: str,
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> TableSpec:
        self._inspect_rows(dataset, data_access)
        return TableSpec(
            title=title,
            columns=columns,
            unit="As reported",
            source_note=source_note,
            guideline_version=guideline_version,
            data_hash=data_hash,
        )

    def author_report(
        self,
        *,
        title: str,
        scope: str,
        row_count: int,
        source_note: str,
        model_result_count: int,
        diagnostics: list[str],
        warnings: list[str],
        dataset: ModelDatasetContext | None = None,
        data_access: ModelDataAccessPort | None = None,
    ) -> str:
        inspected_rows = self._inspect_rows(dataset, data_access)
        lines = [
            f"# {title}",
            "",
            "## Scope",
            scope,
            "",
            "## Data and method",
            f"This report uses {row_count} observations from the approved analytical snapshot.",
            f"The author inspected {len(inspected_rows)} actual snapshot rows through its grant.",
            f"{source_note}.",
            "",
            "## Results",
            f"The analytical bundle contains {model_result_count} reviewed model result(s).",
            (
                "Results are descriptive unless the approved model specification supports "
                "causal inference."
            ),
            "",
            "## Diagnostics and limitations",
            *[f"- {item}" for item in (diagnostics or ["No additional diagnostics."])],
            *[f"- {item}" for item in warnings],
            "",
            "## Reproducibility",
            "Figures, tables, underlying data and code are bound by the reproduction manifest.",
        ]
        return "\n".join(lines) + "\n"

    def propose_revision(
        self,
        request: str,
        artifact: dict[str, Any],
        specification: dict[str, Any],
        target_artifact_set_hash: str,
    ) -> list[ArtifactPatch]:
        normalized = request.strip()
        if not normalized:
            return []
        changes: dict[str, str | list[str]] = {}
        lowered = normalized.lower()
        column_request = (
            artifact.get("format") in {"csv", "xlsx"}
            and any(token in lowered for token in ("column", "compact", "only", "keep"))
            or any(token in normalized for token in ("列", "精简", "保留", "仅"))
        )
        if column_request:
            available = [str(value) for value in specification.get("columns") or []]
            aliases = {
                "entity_code": ("entity", "country", "economy", "实体", "国家", "经济体"),
                "indicator_code": ("indicator", "指标"),
                "period": ("period", "date", "time", "year", "期间", "日期", "年份"),
                "value": ("value", "observation", "数值", "值"),
                "unit": ("unit", "单位"),
                "provider": ("provider", "source", "供应商", "来源"),
                "frequency": ("frequency", "频率"),
            }
            selected = [
                column
                for column in available
                if column.casefold() in lowered
                or any(
                    alias in lowered or alias in normalized
                    for alias in aliases.get(column.casefold(), ())
                )
            ]
            if not selected:
                return []
            changes["columns"] = selected
        elif "source" in lowered or "来源" in normalized:
            changes["source_note"] = normalized
        elif "unit" in lowered or "单位" in normalized:
            import re

            changes["unit"] = re.sub(r"^(?:unit|单位)\s*[:：]\s*", "", normalized, flags=re.I)
        elif ("alt" in lowered or "无障碍" in normalized) and artifact.get("format") == "svg":
            changes["alt_text"] = normalized
        else:
            changes["title"] = normalized[:160]
        patch_id = f"patch-{stable_hash([artifact.get('id'), changes])[-16:]}"
        return [
            ArtifactPatch(
                patch_id=patch_id,
                artifact_id=str(artifact["id"]),
                rationale=(
                    "Apply the requested change through the versioned artifact specification."
                ),
                changes=changes,  # type: ignore[arg-type]
            )
        ]


class DeterministicOutputReviewer:
    """Local acceptance reviewer; never sends renders or values to a remote provider."""

    provider_profile = "deterministic-local"
    model_id = "deterministic-output-review-v1"
    remote_data_disclosure = False

    @staticmethod
    def _review_report(
        request: OutputReviewRequest,
        artifact: dict[str, Any],
        specification: dict[str, Any],
        rows: list[dict[str, Any]],
        render_access: OutputRenderAccessPort,
        findings: list[OutputReviewFinding],
    ) -> None:
        artifact_id = str(artifact.get("id") or "")
        try:
            report_spec = ReportSpec.model_validate(specification)
            guideline = get_publication_guideline(report_spec.guideline_version)
            content = render_access.read_artifact_content(
                request.session_id,
                artifact_id,
                str(artifact.get("hash") or ""),
            ).decode("utf-8")
        except (OSError, UnicodeDecodeError, ValidationError, ValueError) as error:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-content'])[-16:]}",
                    rule_id="REPORT-CONTENT-001",
                    severity="fail",
                    message=f"Research Report content could not be inspected: {error}",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
            return

        headings = {
            line.removeprefix("## ").strip()
            for line in content.splitlines()
            if line.startswith("## ")
        }
        if report_spec.schema_version == "mra-report-spec-v2":
            draft = request.report_drafts.get(artifact_id)
            ledger = request.evidence_ledgers.get(artifact_id)
            if (
                draft is None
                or ledger is None
                or stable_hash(draft) != report_spec.draft_hash
                or stable_hash(ledger) != report_spec.evidence_ledger_hash
                or list(draft.get("claims") or []) != ledger
            ):
                findings.append(
                    OutputReviewFinding(
                        finding_id=(
                            f"finding-{stable_hash([artifact_id, 'report-evidence'])[-16:]}"
                        ),
                        rule_id="REPORT-EVIDENCE-BINDING-001",
                        severity="fail",
                        message=(
                            "Research Report draft or evidence ledger does not match its "
                            "specification-bound hash."
                        ),
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
        missing_sections = sorted(set(guideline.report.required_sections) - headings)
        if missing_sections:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, missing_sections])[-16:]}",
                    rule_id="REPORT-SECTIONS-001",
                    severity="fail",
                    message="Research Report is missing sections: "
                    + ", ".join(missing_sections)
                    + ".",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        if report_spec.observation_count != len(rows):
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-data'])[-16:]}",
                    rule_id="REPORT-DATA-001",
                    severity="fail",
                    message="Research Report observation count does not match the reviewed data.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        if report_spec.source_note not in content:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-source'])[-16:]}",
                    rule_id="REPORT-SOURCE-001",
                    severity="fail",
                    message="Research Report does not contain its specification-bound source note.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        if guideline.report.require_causal_boundary and "causal inference" not in content.lower():
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-causal'])[-16:]}",
                    rule_id="REPORT-CAUSAL-001",
                    severity="fail",
                    message="Research Report does not state its causal-inference boundary.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        if (
            guideline.report.require_reproduction_note
            and "reproduction manifest" not in content.lower()
        ):
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-reproduction'])[-16:]}",
                    rule_id="REPORT-REPRODUCIBILITY-001",
                    severity="fail",
                    message="Research Report does not describe its reproduction-manifest binding.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        selected_formats = {
            str(item.get("format"))
            for item in request.artifacts
            if str(item.get("id")) in request.selected_artifact_ids
        }
        structured = request.report_drafts.get(artifact_id)
        if structured is not None:
            selected_visuals = {
                str(item["id"])
                for item in request.artifacts
                if item.get("format") in {"svg", "xlsx"}
                and str(item["id"]) in request.selected_artifact_ids
            }
            refs = structured.get("artifactReferences", structured.get("artifact_references", []))
            has_visual_references = bool(selected_visuals.intersection(refs))
        else:
            has_visual_references = any(word in content.lower() for word in ("figure", "table"))
        if {"svg", "xlsx"}.intersection(selected_formats) and not has_visual_references:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-references'])[-16:]}",
                    rule_id="REPORT-ARTIFACT-REFERENCE-001",
                    severity="warning",
                    message="Research Report should reference its selected figures or tables.",
                    artifact_ids=[artifact_id],
                )
            )
        if not report_spec.citation_refs:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'citations'])[-16:]}",
                    rule_id="REPORT-CITATION-001",
                    severity="warning",
                    message="Research Report has no explicit source citation references.",
                    artifact_ids=[artifact_id],
                )
            )
        if len(report_spec.title) > guideline.report.title_max_characters:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'report-title'])[-16:]}",
                    rule_id="REPORT-TITLE-001",
                    severity="warning",
                    message="Research Report title exceeds the publication guideline.",
                    artifact_ids=[artifact_id],
                )
            )

    def review(
        self,
        request: OutputReviewRequest,
        data_access: ModelDataAccessPort,
        render_access: OutputRenderAccessPort,
    ) -> OutputReviewReport:
        grant = request.dataset.grant
        rows: list[dict[str, Any]] = []
        for offset in range(0, grant.row_count, grant.page_size):
            rows.extend(
                data_access.read_page(
                    grant.access_id,
                    session_id=grant.session_id,
                    stage=grant.stage,
                    offset=offset,
                ).rows
            )
        selected = {str(value) for value in request.selected_artifact_ids}
        findings = selected_preflight_findings(request.preflight_findings, selected)
        coherence_findings, patches = deterministic_cross_artifact_review(
            request.artifacts,
            request.specifications,
            request.selected_artifact_ids,
        )
        findings.extend(coherence_findings)
        chart_artifact_ids = [
            str(artifact.get("id") or "")
            for artifact in request.artifacts
            if artifact.get("format") == "svg" and str(artifact.get("id") or "") in selected
        ]
        available_indicators = {
            str(row.get("indicator_code")) for row in rows if row.get("indicator_code") is not None
        }
        covered_indicators = {
            str((request.specifications.get(artifact_id) or {}).get("indicator_code"))
            for artifact_id in chart_artifact_ids
            if (request.specifications.get(artifact_id) or {}).get("indicator_code")
        }
        missing_indicators = sorted(available_indicators - covered_indicators)
        if chart_artifact_ids and missing_indicators:
            findings.append(
                OutputReviewFinding(
                    finding_id=(
                        f"finding-{stable_hash(['chart-coverage', missing_indicators])[-16:]}"
                    ),
                    rule_id="CHART-INDICATOR-COVERAGE-001",
                    severity="fail",
                    message=(
                        "Generated charts do not cover approved indicators: "
                        + ", ".join(missing_indicators)
                        + "."
                    ),
                    artifact_ids=chart_artifact_ids,
                    blocking=True,
                )
            )
        for artifact in request.artifacts:
            artifact_id = str(artifact.get("id") or "")
            if artifact_id not in selected:
                continue
            specification = request.specifications.get(artifact_id) or {}
            if artifact.get("format") == "svg":
                render_ref = request.review_render_refs.get(artifact_id) or {}
                try:
                    content = render_access.read_review_render(
                        request.session_id,
                        str(render_ref.get("id") or ""),
                        str(render_ref.get("hash") or ""),
                    )
                    width, height, distinct_pixels = inspect_png_pixels(content)
                    if width < 320 or height < 240 or distinct_pixels < 3:
                        raise ValueError("Review render is blank or below the minimum size.")
                except (OSError, ValueError) as error:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'render'])[-16:]}",
                            rule_id="VIS-RENDER-CONTENT-001",
                            severity="fail",
                            message=(
                                f"The chart review render could not be visually inspected: {error}"
                            ),
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                title = str(specification.get("title") or "")
                indicator_code = str(specification.get("indicator_code") or "")
                y_fields = list(specification.get("y_fields") or [])
                source_note = str(specification.get("source_note") or "")
                alt_text = str(specification.get("alt_text") or "")
                if not source_note.lower().startswith("source:"):
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, 'chart-source'])[-16:]}"
                            ),
                            rule_id="CHART-SOURCE-001",
                            severity="fail",
                            message="Chart source note must use an explicit Source label.",
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                if len(alt_text.strip()) < 24 or alt_text.strip() == title.strip():
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'chart-alt'])[-16:]}",
                            rule_id="CHART-ALT-001",
                            severity="warning",
                            message=(
                                "Chart alternative text should describe its series and context."
                            ),
                            artifact_ids=[artifact_id],
                        )
                    )
                indicator_rows = [
                    row
                    for row in rows
                    if not indicator_code or str(row.get("indicator_code")) == indicator_code
                ]
                entity_codes = {
                    str(row.get("entity_code"))
                    for row in indicator_rows
                    if row.get("entity_code") is not None
                }
                missing_series = sorted(set(str(value) for value in y_fields) - entity_codes)
                if entity_codes and missing_series:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, missing_series])[-16:]}"
                            ),
                            rule_id="CHART-SERIES-DATA-001",
                            severity="fail",
                            message=(
                                "Chart series are not present in the approved underlying data: "
                                + ", ".join(missing_series)
                                + "."
                            ),
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                source_unit = specification.get("source_unit")
                if source_unit is not None:
                    indicator_rows = [
                        row for row in indicator_rows if row.get("unit") == source_unit
                    ]
                reported_units = {
                    str(row.get("unit")).strip()
                    for row in indicator_rows
                    if row.get("unit") is not None and str(row.get("unit")).strip()
                }
                declared_unit = str(source_unit or specification.get("unit") or "")
                if len(reported_units) > 1 or (
                    len(reported_units) == 1 and declared_unit not in reported_units
                ):
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, 'chart-unit'])[-16:]}"
                            ),
                            rule_id="CHART-UNIT-CONSISTENCY-001",
                            severity="fail",
                            message=(
                                "Chart unit does not match one homogeneous underlying series."
                            ),
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                if len(title) > 90:
                    patch = ArtifactPatch(
                        patch_id=f"patch-{stable_hash([artifact_id, 'short-title'])[-16:]}",
                        artifact_id=artifact_id,
                        rationale=(
                            "Shorten the title to improve hierarchy in the fixed review render."
                        ),
                        changes={"title": title[:87].rstrip() + "…"},
                    )
                    patches.append(patch)
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'title'])[-16:]}",
                            rule_id="VIS-TITLE-001",
                            severity="warning",
                            message="Chart title may wrap or crowd the plotting area.",
                            artifact_ids=[artifact_id],
                            proposed_patch_ids=[patch.patch_id],
                        )
                    )
                if len(y_fields) > 6:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'series'])[-16:]}",
                            rule_id="VIS-SERIES-001",
                            severity="warning",
                            message=(
                                "More than six visible series may make labels difficult to compare."
                            ),
                            artifact_ids=[artifact_id],
                        )
                    )
            if artifact.get("format") in {"xlsx", "csv"}:
                source_note = str(specification.get("source_note") or "")
                if not source_note.lower().startswith("source:"):
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, 'table-source'])[-16:]}"
                            ),
                            rule_id="TABLE-SOURCE-001",
                            severity="fail",
                            message="Table source note must use an explicit Source label.",
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                columns = [str(value) for value in specification.get("columns") or []]
                if len(columns) != len(set(columns)):
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, 'duplicate-columns'])[-16:]}"
                            ),
                            rule_id="TABLE-DUPLICATE-COLUMNS-001",
                            severity="fail",
                            message="Table specification contains duplicate column names.",
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                if artifact.get("kind") in {"underlying_data", "workbook"} and rows:
                    actual_columns = {str(value) for row in rows for value in row}
                    if not set(columns).issubset(actual_columns):
                        findings.append(
                            OutputReviewFinding(
                                finding_id=(
                                    f"finding-{stable_hash([artifact_id, 'table-data'])[-16:]}"
                                ),
                                rule_id="TABLE-COLUMNS-DATA-001",
                                severity="fail",
                                message=(
                                    "Table columns do not match the approved underlying dataset."
                                ),
                                artifact_ids=[artifact_id],
                                blocking=True,
                            )
                        )
                title = str(specification.get("title") or "")
                if len(title) > PUBLICATION_GUIDELINE.table.title_max_characters:
                    patch = ArtifactPatch(
                        patch_id=f"patch-{stable_hash([artifact_id, 'table-title'])[-16:]}",
                        artifact_id=artifact_id,
                        rationale="Shorten the table title for publication hierarchy.",
                        changes={"title": title[:87].rstrip() + "…"},
                    )
                    patches.append(patch)
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'table-title'])[-16:]}",
                            rule_id="TABLE-TITLE-001",
                            severity="warning",
                            message="Table title exceeds the publication guideline.",
                            artifact_ids=[artifact_id],
                            proposed_patch_ids=[patch.patch_id],
                        )
                    )
            if artifact.get("format") == "report":
                self._review_report(
                    request,
                    artifact,
                    specification,
                    rows,
                    render_access,
                    findings,
                )
        if any(item.severity == "fail" or item.blocking for item in findings):
            status: Literal["pass", "warning", "fail"] = "fail"
        elif findings:
            status = "warning"
        else:
            status = "pass"
        return OutputReviewReport(
            report_id=f"review-{stable_hash([request.artifact_set_hash, request.iteration])[-16:]}",
            status=status,
            provider_profile=self.provider_profile,
            model_id=self.model_id,
            target_artifact_set_hash=request.artifact_set_hash,
            guideline_version=request.guideline_version,
            iteration=request.iteration,
            reviewed_artifact_ids=sorted(selected),
            review_render_hashes=request.review_render_hashes,
            data_access_id=grant.access_id,
            inspected_row_count=len(rows),
            findings=findings,
            patches=patches,
            semantic_report_status=(
                "pass"
                if any(
                    item.get("format") == "report" and str(item.get("id")) in selected
                    for item in request.artifacts
                )
                and not any(
                    item.blocking
                    for item in findings
                    if any(
                        str(artifact.get("id")) in item.artifact_ids
                        and artifact.get("format") == "report"
                        for artifact in request.artifacts
                    )
                )
                else "fail"
                if any(
                    item.get("format") == "report" and str(item.get("id")) in selected
                    for item in request.artifacts
                )
                else "not_applicable"
            ),
            created_at=datetime.now(timezone.utc),
        )


def selected_preflight_findings(
    findings: list[dict[str, Any]],
    selected_artifact_ids: set[str],
) -> list[OutputReviewFinding]:
    """Keep package findings and findings that affect the current selective export."""
    parsed = [OutputReviewFinding.model_validate(item) for item in findings]
    return [
        item
        for item in parsed
        if not item.artifact_ids or selected_artifact_ids.intersection(item.artifact_ids)
    ]


def deterministic_cross_artifact_review(
    artifacts: list[dict[str, Any]],
    specifications: dict[str, dict[str, Any]],
    selected_artifact_ids: list[str],
) -> tuple[list[OutputReviewFinding], list[ArtifactPatch]]:
    """Check package-wide invariants and propose coherent cosmetic patch groups."""

    selected = set(selected_artifact_ids)
    comparable_ids = [
        str(artifact.get("id"))
        for artifact in artifacts
        if str(artifact.get("id")) in selected
        and artifact.get("format") in {"svg", "xlsx", "csv", "report"}
        and specifications.get(str(artifact.get("id")))
    ]
    findings: list[OutputReviewFinding] = []
    patches: list[ArtifactPatch] = []
    for invariant, rule_id, label in (
        ("data_hash", "PACKAGE-DATA-001", "underlying data hash"),
        ("guideline_version", "PACKAGE-GUIDELINE-001", "guideline version"),
    ):
        values = {
            str(specifications[artifact_id].get(invariant))
            for artifact_id in comparable_ids
            if specifications[artifact_id].get(invariant)
        }
        if len(values) > 1:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([rule_id, sorted(values)])[-16:]}",
                    rule_id=rule_id,
                    severity="fail",
                    message=f"Selected artifacts do not share one {label}.",
                    artifact_ids=comparable_ids,
                    blocking=True,
                )
            )
    for field_name, rule_id, label in (("source_note", "PACKAGE-SOURCE-001", "source note"),):
        values_by_artifact = {
            artifact_id: str(specifications[artifact_id].get(field_name))
            for artifact_id in comparable_ids
            if specifications[artifact_id].get(field_name)
        }
        value_counts = Counter(values_by_artifact.values())
        if len(value_counts) < 2:
            continue
        value_order = list(values_by_artifact.values())
        canonical = max(
            value_counts,
            key=lambda value: (value_counts[value], -value_order.index(value)),
        )
        mismatched_ids = sorted(
            artifact_id for artifact_id, value in values_by_artifact.items() if value != canonical
        )
        group_id = f"patch-group-{stable_hash([rule_id, canonical, mismatched_ids])[-16:]}"
        group_patch_ids: list[str] = []
        for artifact_id in mismatched_ids:
            patch_id = f"patch-{stable_hash([group_id, artifact_id])[-16:]}"
            group_patch_ids.append(patch_id)
            patches.append(
                ArtifactPatch(
                    patch_id=patch_id,
                    group_id=group_id,
                    artifact_id=artifact_id,
                    rationale=f"Align this artifact's {label} with the selected package.",
                    changes={field_name: canonical},  # type: ignore[dict-item]
                )
            )
        findings.append(
            OutputReviewFinding(
                finding_id=f"finding-{stable_hash([group_id, 'finding'])[-16:]}",
                rule_id=rule_id,
                severity="warning",
                message=f"Selected artifacts use inconsistent {label}s.",
                artifact_ids=sorted(values_by_artifact),
                proposed_patch_ids=group_patch_ids,
            )
        )
    return findings, patches


def deterministic_preflight(
    artifacts: list[dict[str, Any]],
    specifications: dict[str, dict[str, Any]],
    row_count: int,
    requested_deliverables: dict[str, Any],
    *,
    review_render_refs: dict[str, dict[str, Any]] | None = None,
    workbook_structure_valid: bool = True,
    workbook_lint_findings: list[dict[str, Any]] | None = None,
) -> list[OutputReviewFinding]:
    findings: list[OutputReviewFinding] = []
    formats = {str(item.get("format")) for item in artifacts}
    required = {
        "charts": "svg",
        "cleanData": "csv",
        "workbook": "xlsx",
        "researchReport": "report",
    }
    for deliverable, artifact_format in required.items():
        if requested_deliverables.get(deliverable) and artifact_format not in formats:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([deliverable, artifact_format])[-16:]}",
                    rule_id="PKG-DELIVERABLE-001",
                    severity="fail",
                    message=f"Requested deliverable is missing: {deliverable}.",
                    blocking=True,
                )
            )
    if row_count < 1:
        findings.append(
            OutputReviewFinding(
                finding_id=f"finding-{stable_hash('empty-data')[-16:]}",
                rule_id="DATA-VALUE-001",
                severity="fail",
                message="Underlying analytical data contains no rows.",
                blocking=True,
            )
        )
    for artifact in artifacts:
        artifact_id = str(artifact.get("id") or "")
        if artifact.get("format") in {"svg", "xlsx", "csv", "report"} and not artifact.get("hash"):
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'hash'])[-16:]}",
                    rule_id="PKG-HASH-001",
                    severity="fail",
                    message="Artifact checksum is missing.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        spec = specifications.get(artifact_id)
        if artifact.get("format") in {"svg", "xlsx", "csv", "report"} and not spec:
            findings.append(
                OutputReviewFinding(
                    finding_id=f"finding-{stable_hash([artifact_id, 'spec'])[-16:]}",
                    rule_id="SPEC-BINDING-001",
                    severity="fail",
                    message="Artifact is not bound to a versioned output specification.",
                    artifact_ids=[artifact_id],
                    blocking=True,
                )
            )
        if artifact.get("format") == "report" and spec:
            try:
                report_spec = ReportSpec.model_validate(spec)
                report_guideline = get_publication_guideline(report_spec.guideline_version)
                if (
                    report_spec.required_sections != list(report_guideline.report.required_sections)
                    or report_spec.causal_boundary_required
                    is not report_guideline.report.require_causal_boundary
                    or report_spec.reproduction_note_required
                    is not report_guideline.report.require_reproduction_note
                ):
                    raise ValueError("Report sections do not match the registered guideline.")
            except (ValidationError, ValueError):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'report-spec'])[-16:]}",
                        rule_id="REPORT-METADATA-001",
                        severity="fail",
                        message="Research Report specification is incomplete or unregistered.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
        if artifact.get("format") == "svg" and spec:
            try:
                guideline = get_publication_guideline(str(spec.get("guideline_version") or ""))
            except ValueError:
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'guideline'])[-16:]}",
                        rule_id="GUIDELINE-VERSION-001",
                        severity="fail",
                        message="Chart is not bound to a registered publication guideline.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
                guideline = None
            if (
                spec.get("guideline_version") == PUBLICATION_GUIDELINE.version
                and spec.get("schema_version") != OUTPUT_SPEC_VERSION
            ):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'spec-version'])[-16:]}",
                        rule_id="SPEC-VERSION-001",
                        severity="fail",
                        message="Publication-v1 requires the current output specification version.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
            required_fields = {
                "title",
                "unit",
                "source_note",
                "number_format",
                "alt_text",
                "width",
                "height",
                "legend_position",
                "palette",
                "line_patterns",
                "missing_value_policy",
                "data_hash",
                "guideline_version",
            }
            if not required_fields.issubset(spec):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'chart-fields'])[-16:]}",
                        rule_id="CHART-METADATA-001",
                        severity="fail",
                        message="Chart specification is missing required publication metadata.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
            if guideline is not None:
                style_matches = (
                    spec.get("legend_position") == guideline.chart.legend_position
                    and spec.get("palette") == list(guideline.chart.palette)
                    and spec.get("line_patterns") == list(guideline.chart.line_patterns)
                    and spec.get("missing_value_policy") == guideline.chart.missing_value_policy
                )
                if not style_matches:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'chart-style'])[-16:]}",
                            rule_id="CHART-STYLE-001",
                            severity="fail",
                            message="Chart style does not conform to the registered guideline.",
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                if len(str(spec.get("title") or "")) > guideline.chart.title_max_characters:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'chart-title'])[-16:]}",
                            rule_id="CHART-TITLE-001",
                            severity="warning",
                            message=(
                                "Chart title exceeds the publication guideline's preferred length."
                            ),
                            artifact_ids=[artifact_id],
                        )
                    )
                if len(spec.get("y_fields") or []) > guideline.chart.maximum_series:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=(
                                f"finding-{stable_hash([artifact_id, 'chart-series'])[-16:]}"
                            ),
                            rule_id="CHART-SERIES-001",
                            severity="fail",
                            message=(
                                "Chart contains more series than the publication guideline permits."
                            ),
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
                if (
                    int(spec.get("width") or 0) < guideline.chart.minimum_width
                    or int(spec.get("height") or 0) < guideline.chart.minimum_height
                ):
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'chart-size'])[-16:]}",
                            rule_id="CHART-SIZE-001",
                            severity="fail",
                            message=(
                                "Chart render is smaller than the publication guideline permits."
                            ),
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
            render_ref = (review_render_refs or {}).get(artifact_id) or {}
            if (
                render_ref.get("width") != spec.get("width")
                or render_ref.get("height") != spec.get("height")
                or render_ref.get("dataHash") != spec.get("data_hash")
                or render_ref.get("specHash") != stable_hash(spec)
            ):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'render'])[-16:]}",
                        rule_id="VIS-RENDER-BINDING-001",
                        severity="fail",
                        message=(
                            "Direct review render is not bound to the current chart spec and data."
                        ),
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
        if artifact.get("format") in {"xlsx", "csv"} and spec:
            try:
                guideline = get_publication_guideline(str(spec.get("guideline_version") or ""))
            except ValueError:
                guideline = None
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'guideline'])[-16:]}",
                        rule_id="GUIDELINE-VERSION-001",
                        severity="fail",
                        message="Table is not bound to a registered publication guideline.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
            if (
                spec.get("guideline_version") == PUBLICATION_GUIDELINE.version
                and spec.get("schema_version") != OUTPUT_SPEC_VERSION
            ):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'spec-version'])[-16:]}",
                        rule_id="SPEC-VERSION-001",
                        severity="fail",
                        message="Publication-v1 requires the current output specification version.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
            required_fields = {
                "title",
                "columns",
                "unit",
                "source_note",
                "number_format",
                "freeze_header",
                "enable_filters",
                "numeric_alignment",
                "missing_value_display",
                "data_hash",
                "guideline_version",
            }
            if not required_fields.issubset(spec):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'table-fields'])[-16:]}",
                        rule_id="TABLE-METADATA-001",
                        severity="fail",
                        message="Table specification is missing required publication metadata.",
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
            if guideline is not None:
                style_matches = (
                    spec.get("freeze_header") is guideline.table.freeze_header
                    and spec.get("enable_filters") is guideline.table.enable_filters
                    and spec.get("numeric_alignment") == guideline.table.numeric_alignment
                    and spec.get("missing_value_display") == guideline.table.missing_value_display
                    and spec.get("number_format") in guideline.table.allowed_number_formats
                )
                if not style_matches:
                    findings.append(
                        OutputReviewFinding(
                            finding_id=f"finding-{stable_hash([artifact_id, 'table-style'])[-16:]}",
                            rule_id="TABLE-STYLE-001",
                            severity="fail",
                            message="Table style does not conform to the registered guideline.",
                            artifact_ids=[artifact_id],
                            blocking=True,
                        )
                    )
            if (
                guideline is not None
                and len(spec.get("columns") or []) > guideline.table.maximum_columns
            ):
                findings.append(
                    OutputReviewFinding(
                        finding_id=f"finding-{stable_hash([artifact_id, 'table-columns'])[-16:]}",
                        rule_id="TABLE-COLUMNS-001",
                        severity="fail",
                        message=(
                            "Table contains more columns than the publication guideline permits."
                        ),
                        artifact_ids=[artifact_id],
                        blocking=True,
                    )
                )
    for item in workbook_lint_findings or []:
        artifact_id = str(item.get("artifact_id") or "")
        location = str(item.get("location") or "")
        message = str(item.get("message") or "Workbook template validation failed.")
        if location:
            message = f"{location}: {message}"
        findings.append(
            OutputReviewFinding(
                finding_id=(
                    f"finding-{stable_hash([artifact_id, item.get('rule_id'), location])[-16:]}"
                ),
                rule_id=str(item.get("rule_id") or "WORKBOOK-STRUCTURE-001"),
                severity="warning" if item.get("severity") == "warning" else "fail",
                message=message,
                artifact_ids=[artifact_id] if artifact_id else [],
                blocking=bool(item.get("blocking", True)),
            )
        )
    if not workbook_structure_valid:
        findings.append(
            OutputReviewFinding(
                finding_id=f"finding-{stable_hash('workbook-structure')[-16:]}",
                rule_id="WORKBOOK-STRUCTURE-001",
                severity="fail",
                message="Workbook is missing one or more required governed sheets.",
                blocking=True,
            )
        )
    return findings
