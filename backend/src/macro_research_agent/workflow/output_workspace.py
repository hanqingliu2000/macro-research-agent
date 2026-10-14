from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sqlite3
import textwrap
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd  # type: ignore[import-untyped]
import resvg_py
from pydantic import BaseModel

from macro_research_agent.research_core.presentation_evidence import (
    PresentationEvidenceError,
    build_presentation_evidence,
)
from macro_research_agent.workflow.artifact_comparison import (
    ArtifactComparisonReport,
    compare_artifacts,
)
from macro_research_agent.workflow.code_workspace import CodeWorkspaceManager
from macro_research_agent.workflow.data_workspace import DataWorkspaceManager
from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessError,
    ModelDatasetContext,
    WorkflowModelDataAccessService,
)
from macro_research_agent.workflow.output_review import (
    ArtifactAuthorPort,
    ChartSpec,
    OutputReviewFinding,
    ReportSpec,
    TableSpec,
    deterministic_preflight,
    output_artifact_set_hash,
    stable_hash,
)
from macro_research_agent.workflow.publication_guidelines import (
    PUBLICATION_GUIDELINE,
    PUBLICATION_GUIDELINE_VERSION,
)
from macro_research_agent.workflow.reporting import (
    ReportAuthorPort,
    ReportAuthorRequestV1,
    ReportCitationV1,
    ReportDraftV1,
    ReportProviderError,
    ReportRevisionDirectiveV1,
    ReportRevisionRequestV1,
    render_report_markdown,
    validate_revised_draft,
)
from macro_research_agent.workflow.states import WorkflowStage
from macro_research_agent.workflow.workbook_templates import (
    WORKBOOK_TEMPLATE_VERSION,
    lint_workbook,
)


class OutputWorkspaceError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "output_workspace_error",
        issues: list[dict[str, str | int]] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.issues = issues or []
        self.retryable = retryable


class OutputArtifactRecord(BaseModel):
    id: str
    session_id: str
    artifact_set_id: str
    bundle_id: str
    kind: str
    name: str
    format: str
    media_type: str
    description: str
    checksum: str
    relative_path: str
    source_snapshot_ids: list[str]
    guideline_version: str
    created_at: datetime


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _publication_title(value: object, fallback: str, maximum: int) -> str:
    normalized = " ".join(str(value or fallback).split()) or fallback
    if len(normalized) <= maximum:
        return normalized
    prefix = normalized[: maximum - 1]
    word_bounded = prefix.rsplit(" ", 1)[0]
    if len(word_bounded) < maximum // 2:
        word_bounded = prefix
    return word_bounded.rstrip(" ,.;:-") + "…"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def publication_columns(frame: pd.DataFrame) -> list[str]:
    priority = [
        "series_id",
        "entity_code",
        "indicator_code",
        "frequency",
        "period",
        "value",
        "entity_name",
        "indicator_name",
        "unit",
        "scale",
        "status",
        "provider",
        "dataset",
        "source_snapshot_id",
    ]
    ordered = [name for name in priority if name in frame.columns]
    ordered.extend(str(name) for name in frame.columns if name not in ordered)
    return ordered[: PUBLICATION_GUIDELINE.table.maximum_columns]


def _xml_text(value: object) -> str:
    text = str(value)
    return "".join(
        character for character in text if character in {"\t", "\n", "\r"} or ord(character) >= 32
    )


@dataclass(frozen=True)
class ChartView:
    indicator_code: str
    unit: str
    frame: pd.DataFrame


def _chart_frame(
    frame: pd.DataFrame,
    indicator_code: str | None = None,
    unit: str | None = None,
) -> pd.DataFrame:
    required = {"period", "entity_code", "indicator_code", "value"}
    if not required.issubset(frame.columns) or frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["value"] = pd.to_numeric(working["value"], errors="coerce")
    indicator = indicator_code or next(
        (str(value) for value in working["indicator_code"].dropna().unique()), None
    )
    if indicator is None:
        return pd.DataFrame()
    filtered = working.loc[working["indicator_code"].astype(str) == indicator]
    if unit and unit != "As reported" and "unit" in filtered.columns:
        filtered = filtered.loc[filtered["unit"].astype(str) == unit]
    entities = [str(value) for value in filtered["entity_code"].dropna().unique()[:6]]
    filtered = filtered.loc[filtered["entity_code"].astype(str).isin(entities)]
    return (
        filtered.pivot_table(index="period", columns="entity_code", values="value", aggfunc="mean")
        .reindex(sorted(filtered["period"].dropna().unique()))
        .sort_index()
        .reset_index()
    )


def _chart_views(frame: pd.DataFrame) -> list[ChartView]:
    if "indicator_code" not in frame.columns:
        return []
    views: list[ChartView] = []
    for raw_indicator in frame["indicator_code"].dropna().unique():
        indicator = str(raw_indicator)
        indicator_rows = frame.loc[frame["indicator_code"].astype(str) == indicator]
        units = (
            list(
                dict.fromkeys(
                    str(value).strip()
                    for value in indicator_rows.get("unit", pd.Series(dtype="object")).dropna()
                    if str(value).strip()
                )
            )
            if "unit" in indicator_rows.columns
            else []
        )
        unit_groups: list[str | None] = (
            [*units] if len(units) > 1 else [units[0] if units else None]
        )
        for unit in unit_groups:
            unit_rows = indicator_rows
            if unit is not None:
                unit_rows = unit_rows[unit_rows["unit"].astype(str) == unit]
            entities = list(unit_rows["entity_code"].dropna().unique())
            for start in range(0, len(entities), 6):
                subset = unit_rows[unit_rows["entity_code"].isin(entities[start : start + 6])]
                chart_frame = _chart_frame(subset, indicator, unit)
                if not chart_frame.empty and len(chart_frame.columns) > 1:
                    views.append(
                        ChartView(
                            indicator_code=indicator,
                            unit=unit or "As reported",
                            frame=chart_frame,
                        )
                    )
    return views


def _artifact_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized[:48] or "series"


def _title_lines(title: str, width: int = 62, maximum_lines: int = 2) -> list[str]:
    lines = textwrap.wrap(title, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) <= maximum_lines:
        return lines or [title]
    visible = lines[:maximum_lines]
    visible[-1] = visible[-1].rstrip(" ,.;:-") + "…"
    return visible


def _axis_label(value: float, number_format: str = "0.00") -> str:
    percentage = number_format.endswith("%")
    pattern = number_format[:-1] if percentage else number_format
    decimals = len(pattern.partition(".")[2])
    displayed = value * 100 if percentage else value
    magnitude = abs(displayed)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if magnitude >= threshold:
            return f"{displayed / threshold:.{decimals}f}{suffix}{'%' if percentage else ''}"
    return f"{displayed:.{decimals}f}{'%' if percentage else ''}"


def _forecast_frame(model_results: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in model_results:
        for forecast in (item.get("result") or {}).get("forecasts") or []:
            rows.append(
                {
                    "job_id": item.get("jobId"),
                    "model": item.get("kind"),
                    "result_hash": item.get("resultHash"),
                    **forecast,
                }
            )
    return pd.DataFrame(rows)


def forecast_delivery_findings(
    model_jobs: list[dict[str, Any]],
    forecast_data: pd.DataFrame,
    *,
    artifact_id: str | None = None,
) -> list[OutputReviewFinding]:
    expected: dict[str, set[int]] = {}
    for job in model_jobs:
        if not job.get("enabled", True) or str(job.get("kind") or "") not in {
            "arima",
            "sarimax",
            "var",
        }:
            continue
        steps = int((job.get("parameters") or {}).get("forecastSteps") or 0)
        if steps < 1:
            continue
        targets = (
            job.get("variables") if job.get("kind") == "var" else job.get("dependentVariables")
        ) or []
        for target in targets:
            normalized = str(target).strip().upper()
            if normalized:
                expected.setdefault(normalized, set()).update(range(1, steps + 1))
    if not expected:
        return []
    missing: dict[str, list[int]] = {}
    for target, expected_steps in expected.items():
        if forecast_data.empty or "variable" not in forecast_data.columns:
            present_steps: set[int] = set()
        else:
            target_rows = forecast_data[forecast_data["variable"] == target]
            present_steps = {
                int(value)
                for value in target_rows.get("step", pd.Series(dtype=int)).dropna().tolist()
            }
        absent = sorted(expected_steps - present_steps)
        if absent:
            missing[str(target)] = absent
    if not missing:
        return []
    details = "; ".join(
        f"{target}: periods {', '.join(str(value) for value in periods)}"
        for target, periods in missing.items()
    )
    return [
        OutputReviewFinding(
            finding_id=f"finding-{stable_hash(['forecast-delivery', missing])[-16:]}",
            rule_id="FORECAST-DELIVERABLE-001",
            severity="fail",
            message=f"Required forecast output is missing ({details}).",
            artifact_ids=[artifact_id] if artifact_id else [],
            blocking=True,
        )
    ]


def _irf_frame(model_results: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in model_results:
        for response in (item.get("result") or {}).get("impulseResponses") or []:
            rows.append(
                {
                    "job_id": item.get("jobId"),
                    "model": item.get("kind"),
                    "result_hash": item.get("resultHash"),
                    **response,
                }
            )
    return pd.DataFrame(rows)


def _svg_chart(chart_data: pd.DataFrame, spec: ChartSpec) -> str:
    width, height = spec.width, spec.height
    title_lines = _title_lines(spec.title)
    left, right, top, bottom = 82, 32, 88 if len(title_lines) > 1 else 64, 72
    note_lines = textwrap.wrap(
        f"Unit: {spec.unit} · {spec.source_note}"
        + (
            " · Hollow circles: imputed; outlined squares: winsorized."
            if spec.observation_flags
            else ""
        ),
        width=max(30, (width - left - right) // 6),
        break_long_words=True,
    )
    bottom += max(0, len(note_lines) - 1) * 14
    if chart_data.empty or len(chart_data.columns) < 2:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#ffffff"/>'
            + "".join(
                f'<text x="40" y="{40 + index * 24}" font-family="Arial" font-size="20">'
                f"{html.escape(_xml_text(line))}</text>"
                for index, line in enumerate(title_lines)
            )
            + '<text x="40" y="125" font-family="Arial" font-size="15" fill="#57606a">'
            "No plottable numeric series are available.</text></svg>"
        )
    series_columns = list(chart_data.columns[1:])
    values = pd.to_numeric(chart_data[series_columns].stack(), errors="coerce").dropna()
    if values.empty:
        return _svg_chart(pd.DataFrame(), spec)
    minimum, maximum = float(values.min()), float(values.max())
    if minimum == maximum:
        minimum -= 1
        maximum += 1
    plot_width, plot_height = width - left - right, height - top - bottom
    palette = spec.palette
    line_patterns = {"solid": None, "dash": "8 5", "dot": "2 4"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="chart-title chart-desc">',
        f'<title id="chart-title">{html.escape(_xml_text(spec.title))}</title>',
        f'<desc id="chart-desc">{html.escape(_xml_text(spec.alt_text))}</desc>',
        '<metadata id="coordinate-system">'
        + html.escape(
            json.dumps(
                {
                    "minimum": minimum,
                    "maximum": maximum,
                    "top": top,
                    "plot_height": plot_height,
                    "left": left,
                    "plot_width": plot_width,
                    "period_count": len(chart_data),
                    "tick_text_baseline_offset": 4,
                    "coordinate_rounding_pixels": 0.1,
                }
            )
        )
        + "</metadata>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *[
            f'<text x="{left}" y="{31 + index * 24}" font-family="Arial" font-size="20" '
            f'font-weight="600">{html.escape(_xml_text(line))}</text>'
            for index, line in enumerate(title_lines)
        ],
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#8c959f"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#8c959f"/>',
    ]
    denominator = max(len(chart_data) - 1, 1)
    for tick in range(5):
        fraction = tick / 4
        y = top + plot_height * fraction
        value = maximum - (maximum - minimum) * fraction
        parts.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
                'stroke="#d8dee4" stroke-width="1"/>',
                f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
                f'font-family="Arial" font-size="12">'
                f"{_axis_label(value, spec.number_format)}</text>",
            ]
        )
    for index, column in enumerate(series_columns):
        points: list[str] = []
        segments: list[list[str]] = []
        markers: list[str] = []
        for row_index, raw_value in enumerate(chart_data[column]):
            if pd.isna(raw_value):
                if points:
                    segments.append(points)
                    points = []
                continue
            x = left + plot_width * row_index / denominator
            y = top + plot_height * (maximum - float(raw_value)) / (maximum - minimum)
            points.append(f"{x:.1f},{y:.1f}")
            flag = next(
                (
                    flag
                    for flag in spec.observation_flags
                    if flag.series == str(column)
                    and flag.period == str(chart_data.iloc[row_index, 0])
                ),
                None,
            )
            if flag:
                color = palette[index % len(palette)]
                marker = (
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="white" stroke="{color}"/>'
                    if flag.origin == "imputed"
                    else (
                        f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" '
                        f'fill="white" stroke="{color}"/>'
                    )
                )
                markers.append(
                    '<g data-observation-origin="' + flag.origin + '">' + marker + "</g>"
                )
        if points:
            segments.append(points)
        color = palette[index % len(palette)]
        pattern = spec.line_patterns[index % len(spec.line_patterns)]
        dash = f' stroke-dasharray="{line_patterns[pattern]}"' if line_patterns[pattern] else ""
        for segment in segments:
            if len(segment) == 1:
                point_x, point_y = segment[0].split(",")
                parts.append(f'<circle cx="{point_x}" cy="{point_y}" r="3" fill="{color}"/>')
            else:
                parts.append(
                    f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" '
                    f'stroke-width="3"{dash}/>'
                )
        parts.extend(markers)
        legend_x = left + index * plot_width / max(len(series_columns), 1)
        parts.extend(
            [
                f'<line x1="{legend_x}" y1="{height - bottom + 41}" x2="{legend_x + 22}" '
                f'y2="{height - bottom + 41}" stroke="{color}" stroke-width="3"{dash}/>',
                f'<text x="{legend_x + 28}" y="{height - bottom + 47}" font-family="Arial" '
                f'font-size="13">{html.escape(str(column))}</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="{left}" y="{height - bottom + 28}" font-family="Arial" '
            f'font-size="12">{html.escape(str(chart_data.iloc[0, 0]))}</text>',
            f'<text x="{left + plot_width}" y="{height - bottom + 28}" '
            f'text-anchor="end" font-family="Arial" font-size="12">'
            f"{html.escape(str(chart_data.iloc[-1, 0]))}</text>",
            *[
                f'<text x="{left}" y="{height - 7 - (len(note_lines) - 1 - index) * 14}" '
                f'font-family="Arial" font-size="11" fill="#57606a">'
                f"{html.escape(_xml_text(line))}</text>"
                for index, line in enumerate(note_lines)
            ],
            "</svg>",
        ]
    )
    return "".join(parts)


def _png_review_render(
    chart_data: pd.DataFrame,
    width: int = 900,
    height: int = 500,
    spec: ChartSpec | None = None,
) -> bytes:
    """Rasterize the complete deliverable SVG for checksum-bound visual review."""

    active_spec = spec or ChartSpec(
        title="Review render",
        unit="As reported",
        source_note="Source: approved analytical snapshot",
        x_field="period",
        y_fields=[str(value) for value in chart_data.columns[1:]] or ["value"],
        alt_text="Direct review render of selected macroeconomic series.",
        guideline_version=PUBLICATION_GUIDELINE_VERSION,
        data_hash="review-render",
        width=width,
        height=height,
    )
    svg = _svg_chart(chart_data, active_spec)
    rendered = resvg_py.svg_to_bytes(
        svg_string=svg,
        background="#ffffff",
        width=width,
        height=height,
        text_rendering="optimize_legibility",
    )
    if not rendered:
        raise OutputWorkspaceError("The chart review render could not be rasterized.")
    return rendered


class OutputWorkspaceManager:
    def __init__(
        self,
        database_path: Path,
        workflow_root: Path,
        data_manager: DataWorkspaceManager,
        code_manager: CodeWorkspaceManager,
        artifact_author: ArtifactAuthorPort,
        model_data_access: WorkflowModelDataAccessService,
        report_author: ReportAuthorPort | None = None,
        capability_receipt_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.database_path = database_path
        self.workflow_root = workflow_root
        self.data_manager = data_manager
        self.code_manager = code_manager
        self.artifact_author = artifact_author
        self.report_author = report_author
        self.model_data_access = model_data_access
        self.capability_receipt_provider = capability_receipt_provider
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_output_artifacts (
                    session_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, artifact_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _write(
        self,
        session_id: str,
        artifact_set_id: str,
        bundle_id: str,
        kind: str,
        filename: str,
        artifact_format: str,
        media_type: str,
        description: str,
        content: bytes,
        source_snapshot_ids: list[str],
    ) -> OutputArtifactRecord:
        artifact_id = f"artifact-{uuid4().hex}"
        relative_path = f"sessions/{session_id}/output/{artifact_id}/{filename}"
        path = self.workflow_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return OutputArtifactRecord(
            id=artifact_id,
            session_id=session_id,
            artifact_set_id=artifact_set_id,
            bundle_id=bundle_id,
            kind=kind,
            name=filename,
            format=artifact_format,
            media_type=media_type,
            description=description,
            checksum=_hash_bytes(content),
            relative_path=relative_path,
            source_snapshot_ids=source_snapshot_ids,
            guideline_version=PUBLICATION_GUIDELINE_VERSION,
            created_at=datetime.now(timezone.utc),
        )

    def _discard_uncommitted_artifacts(
        self, records: list[OutputArtifactRecord], staging_path: Path
    ) -> None:
        output_root = (self.workflow_root / "sessions").resolve()
        for record in records:
            artifact_directory = (self.workflow_root / record.relative_path).resolve().parent
            if artifact_directory.is_relative_to(output_root):
                shutil.rmtree(artifact_directory, ignore_errors=True)
        resolved_staging = staging_path.resolve()
        if resolved_staging.is_relative_to(output_root):
            shutil.rmtree(resolved_staging, ignore_errors=True)

    @staticmethod
    def _artifact_payload(record: OutputArtifactRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "kind": record.kind,
            "name": record.name,
            "format": record.format,
            "mediaType": record.media_type,
            "description": record.description,
            "hash": record.checksum,
            "status": "ready",
            "exportSelected": True,
            "createdAt": record.created_at.isoformat(),
        }

    def _workbook(
        self,
        path: Path,
        frame: pd.DataFrame,
        chart_entries: list[tuple[pd.DataFrame, ChartSpec | None]],
        session: dict[str, Any],
        bundle: dict[str, Any],
    ) -> None:
        model_rows = [
            {
                "job_id": item.get("jobId"),
                "model": item.get("kind"),
                "observations": (item.get("sample") or {}).get("observations"),
                "dropped": (item.get("sample") or {}).get("dropped"),
                "result_hash": item.get("resultHash"),
                "result_json": _canonical(item.get("result") or {}),
            }
            for item in (session.get("pipeline") or {}).get("modelResults") or []
        ]
        model_frame = pd.DataFrame(
            model_rows,
            columns=[
                "job_id",
                "model",
                "observations",
                "dropped",
                "result_hash",
                "result_json",
            ],
        )
        forecast_rows = _forecast_frame(
            list((session.get("pipeline") or {}).get("modelResults") or [])
        )
        irf_rows = _irf_frame(list((session.get("pipeline") or {}).get("modelResults") or []))
        provenance_rows = [
            {"field": "approved_plan_snapshot", "value": session.get("approvedPlanSnapshotId")},
            {"field": "active_dataset_snapshot", "value": bundle.get("finalDatasetRef")},
            {"field": "analytical_bundle", "value": bundle.get("id")},
            {"field": "guideline_version", "value": PUBLICATION_GUIDELINE_VERSION},
        ]
        for run in (session.get("data") or {}).get("sourceRuns") or []:
            provenance_rows.append(
                {
                    "field": f"source:{run.get('id', 'unknown')}",
                    "value": _canonical(run),
                }
            )
        diagnostic_rows = [
            {"level": "diagnostic", "message": message}
            for message in bundle.get("diagnostics") or []
        ] + [{"level": "warning", "message": message} for message in bundle.get("warnings") or []]
        diagnostic_frame = pd.DataFrame(diagnostic_rows, columns=["level", "message"])
        chart_sheets = [
            ("Chart Data" if index == 0 else f"Chart Data {index + 1}", chart_data, chart_spec)
            for index, (chart_data, chart_spec) in enumerate(chart_entries)
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(
            path,
            engine="xlsxwriter",
            engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
        ) as writer:
            missing = PUBLICATION_GUIDELINE.table.missing_value_display
            frame.to_excel(writer, sheet_name="Analytical Data", index=False, na_rep=missing)
            model_frame.to_excel(writer, sheet_name="Model Results", index=False, na_rep=missing)
            pd.DataFrame(provenance_rows).to_excel(
                writer, sheet_name="Provenance", index=False, na_rep=missing
            )
            diagnostic_frame.to_excel(writer, sheet_name="Diagnostics", index=False, na_rep=missing)
            for sheet_name, chart_data, _ in chart_sheets:
                chart_data.to_excel(writer, sheet_name=sheet_name, index=False, na_rep=missing)
            if not forecast_rows.empty:
                forecast_rows.to_excel(writer, sheet_name="Forecasts", index=False, na_rep=missing)
            if not irf_rows.empty:
                irf_rows.to_excel(
                    writer, sheet_name="Impulse Responses", index=False, na_rep=missing
                )
            workbook = writer.book
            workbook.set_properties(
                {
                    "title": "Macro Research Analytical Workbook",
                    "comments": PUBLICATION_GUIDELINE_VERSION,
                }
            )
            header = workbook.add_format(
                {"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "border": 0}
            )
            number = workbook.add_format({"num_format": "0.00"})
            sheets = [
                ("Analytical Data", frame),
                ("Model Results", model_frame),
                ("Provenance", pd.DataFrame(provenance_rows)),
                ("Diagnostics", diagnostic_frame),
                *((sheet_name, chart_data) for sheet_name, chart_data, _ in chart_sheets),
            ]
            if not forecast_rows.empty:
                sheets.append(("Forecasts", forecast_rows))
            if not irf_rows.empty:
                sheets.append(("Impulse Responses", irf_rows))
            for sheet_name, dataframe in sheets:
                worksheet = writer.sheets[sheet_name]
                worksheet.freeze_panes(1, 0)
                if len(dataframe.columns) and len(dataframe):
                    worksheet.autofilter(0, 0, len(dataframe), len(dataframe.columns) - 1)
                worksheet.set_row(0, 22, header)
                for column_index, column in enumerate(dataframe.columns):
                    width = min(max(len(str(column)) + 2, 12), 48)
                    worksheet.set_column(column_index, column_index, width)
                for column_index, column in enumerate(dataframe.columns):
                    if pd.api.types.is_numeric_dtype(dataframe[column]):
                        worksheet.set_column(column_index, column_index, None, number)
            for sheet_name, chart_data, chart_spec in chart_sheets:
                if chart_data.empty or len(chart_data.columns) < 2:
                    continue
                active_chart_spec = chart_spec or ChartSpec(
                    title="Selected macroeconomic series",
                    unit="As reported",
                    source_note="Source: approved analytical snapshot",
                    x_field="period",
                    y_fields=[str(value) for value in chart_data.columns[1:]],
                    alt_text="Line chart of selected macroeconomic series.",
                    guideline_version=PUBLICATION_GUIDELINE_VERSION,
                    data_hash="workbook-embedded",
                )
                chart = workbook.add_chart({"type": "line"})
                for column_index in range(1, len(chart_data.columns)):
                    pattern = active_chart_spec.line_patterns[
                        (column_index - 1) % len(active_chart_spec.line_patterns)
                    ]
                    chart.add_series(
                        {
                            "name": [sheet_name, 0, column_index],
                            "categories": [sheet_name, 1, 0, len(chart_data), 0],
                            "values": [
                                sheet_name,
                                1,
                                column_index,
                                len(chart_data),
                                column_index,
                            ],
                            "line": {
                                "width": 2.25,
                                "color": active_chart_spec.palette[
                                    (column_index - 1) % len(active_chart_spec.palette)
                                ],
                                "dash_type": {
                                    "solid": "solid",
                                    "dash": "dash",
                                    "dot": "round_dot",
                                }[pattern],
                            },
                        }
                    )
                chart.set_title({"name": active_chart_spec.title})
                chart.set_legend({"position": "bottom"})
                chart.set_y_axis(
                    {"major_gridlines": {"visible": True, "line": {"color": "#D8DEE4"}}}
                )
                writer.sheets[sheet_name].insert_chart(
                    "H2", chart, {"x_scale": 1.45, "y_scale": 1.35}
                )

    def generate(self, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        pipeline = session.get("pipeline") or {}
        bundle = pipeline.get("bundle") or {}
        bundle_id = str(bundle.get("id") or "")
        final_snapshot_id = str(bundle.get("finalDatasetRef") or "")
        if not bundle_id or not final_snapshot_id:
            raise OutputWorkspaceError(
                "A completed analytical bundle is required for output generation."
            )
        snapshot = self.data_manager.get_snapshot(session_id, final_snapshot_id)
        frame = self.data_manager.frame(snapshot)
        try:
            author_dataset = self.model_data_access.context_for_snapshot(
                session_id,
                final_snapshot_id,
                WorkflowStage.OUTPUT,
                for_remote_provider=self.artifact_author.remote_data_disclosure,
                provider_profile=self.artifact_author.provider_profile,
                model_id=self.artifact_author.model_id,
            )
        except ModelDataAccessError as error:
            raise OutputWorkspaceError(
                "Output author data access is unavailable under the current disclosure policy.",
                code="data_access_denied",
                retryable=False,
            ) from error
        chart_views = _chart_views(frame)
        plan = session.get("currentPlan") or {}
        deliverables = plan.get("deliverables") or {}
        artifact_set_id = f"artifact-set-{uuid4().hex}"
        source_ids = [final_snapshot_id]
        records: list[OutputArtifactRecord] = []
        internal_records: list[OutputArtifactRecord] = []
        specifications: dict[str, dict[str, Any]] = {}
        review_render_hashes: dict[str, str] = {}
        review_render_refs: dict[str, dict[str, Any]] = {}
        workbook_lint_findings: list[dict[str, Any]] = []
        source_runs = list((session.get("data") or {}).get("sourceRuns") or [])
        source_names = [
            str(item.get("sourceLabel") or item.get("connectorId") or item.get("id"))
            for item in source_runs
        ]
        source_note = "Source: " + (
            ", ".join(source_names) if source_names else "approved input data"
        )
        objective = plan.get("objective")
        table_title = _publication_title(
            objective,
            "Analytical data",
            PUBLICATION_GUIDELINE.table.title_max_characters,
        )
        display_columns = publication_columns(frame)
        table_spec_template = self.artifact_author.author_table_spec(
            title=table_title,
            columns=[str(column) for column in display_columns],
            source_note=source_note,
            guideline_version=PUBLICATION_GUIDELINE_VERSION,
            data_hash=snapshot.snapshot_hash,
            dataset=author_dataset,
            data_access=self.model_data_access,
        )
        forecast_data = _forecast_frame(list(pipeline.get("modelResults") or []))
        irf_data = _irf_frame(list(pipeline.get("modelResults") or []))
        chart_entries: list[tuple[pd.DataFrame, ChartSpec | None]] = []
        limitations: list[str] = []

        if deliverables.get("cleanData", True):
            record = self._write(
                session_id,
                artifact_set_id,
                bundle_id,
                "underlying_data",
                "analytical_data.csv",
                "csv",
                "text/csv",
                "Canonical analytical data used by the reviewed pipeline",
                frame[display_columns].to_csv(index=False).encode("utf-8"),
                source_ids,
            )
            records.append(record)
            specifications[record.id] = table_spec_template.model_dump(mode="json")
        if not forecast_data.empty:
            forecast_spec = self.artifact_author.author_table_spec(
                title="Model forecasts",
                columns=[str(column) for column in forecast_data.columns],
                source_note=source_note,
                guideline_version=PUBLICATION_GUIDELINE_VERSION,
                data_hash=snapshot.snapshot_hash,
                dataset=author_dataset,
                data_access=self.model_data_access,
            )
            record = self._write(
                session_id,
                artifact_set_id,
                bundle_id,
                "forecast_data",
                "model_forecasts.csv",
                "csv",
                "text/csv",
                "Forecast means and confidence intervals from reviewed model specifications",
                forecast_data.to_csv(index=False).encode("utf-8"),
                source_ids,
            )
            records.append(record)
            specifications[record.id] = forecast_spec.model_dump(mode="json")
        if not irf_data.empty:
            irf_spec = self.artifact_author.author_table_spec(
                title="Impulse responses",
                columns=[str(column) for column in irf_data.columns],
                source_note=source_note,
                guideline_version=PUBLICATION_GUIDELINE_VERSION,
                data_hash=snapshot.snapshot_hash,
                dataset=author_dataset,
                data_access=self.model_data_access,
            )
            record = self._write(
                session_id,
                artifact_set_id,
                bundle_id,
                "irf_data",
                "impulse_responses.csv",
                "csv",
                "text/csv",
                "Impulse responses and confidence intervals from a reviewed VAR specification",
                irf_data.to_csv(index=False).encode("utf-8"),
                source_ids,
            )
            records.append(record)
            specifications[record.id] = irf_spec.model_dump(mode="json")
        if deliverables.get("charts", True):
            maximum_charts = 12
            if len(chart_views) > maximum_charts:
                limitations.append(
                    f"Chart generation is limited to {maximum_charts} indicator/unit views; "
                    f"{len(chart_views) - maximum_charts} view(s) remain in Analytical Data only."
                )
            active_views = chart_views[:maximum_charts]
            for index, view in enumerate(active_views):
                title = _publication_title(
                    f"{view.indicator_code} — {objective or 'Selected macroeconomic series'}",
                    view.indicator_code,
                    PUBLICATION_GUIDELINE.chart.title_max_characters,
                )
                y_fields = [str(column) for column in view.frame.columns[1:]] or ["value"]
                try:
                    chart_spec = self.artifact_author.author_chart_spec(
                        title=title,
                        source_note=source_note,
                        y_fields=y_fields,
                        guideline_version=PUBLICATION_GUIDELINE_VERSION,
                        data_hash=snapshot.snapshot_hash,
                        indicator_code=view.indicator_code,
                        unit=view.unit,
                        dataset=author_dataset,
                        data_access=self.model_data_access,
                    )
                except OutputWorkspaceError:
                    self._discard_uncommitted_artifacts(
                        [*records, *internal_records],
                        self.workflow_root
                        / f"sessions/{session_id}/output/.staging/{artifact_set_id}",
                    )
                    raise
                chart_spec.source_unit = None if view.unit == "As reported" else view.unit
                suffix = "" if len(active_views) == 1 else f"_{_artifact_slug(view.indicator_code)}"
                if (
                    len(active_views) > 1
                    and sum(item.indicator_code == view.indicator_code for item in active_views) > 1
                ):
                    suffix += f"_{index + 1}"
                record = self._write(
                    session_id,
                    artifact_set_id,
                    bundle_id,
                    "chart",
                    f"analytical_chart{suffix}.svg",
                    "svg",
                    "image/svg+xml",
                    f"Guideline-controlled line chart ({PUBLICATION_GUIDELINE_VERSION})",
                    _svg_chart(view.frame, chart_spec).encode("utf-8"),
                    source_ids,
                )
                records.append(record)
                specifications[record.id] = chart_spec.model_dump(mode="json")
                render = self._write(
                    session_id,
                    artifact_set_id,
                    bundle_id,
                    "review_render",
                    f"analytical_chart{suffix}.review.png",
                    "png",
                    "image/png",
                    "Fixed-size direct artifact render for local or authorized visual review",
                    _png_review_render(view.frame, chart_spec.width, chart_spec.height, chart_spec),
                    source_ids,
                )
                internal_records.append(render)
                review_render_hashes[record.id] = render.checksum
                review_render_refs[record.id] = {
                    "id": render.id,
                    "hash": render.checksum,
                    "width": chart_spec.width,
                    "height": chart_spec.height,
                    "specHash": stable_hash(chart_spec.model_dump(mode="json")),
                    "dataHash": snapshot.snapshot_hash,
                }
                chart_entries.append((view.frame, chart_spec))
        if deliverables.get("tables", True) or deliverables.get("charts", True):
            workbook_path = (
                self.workflow_root
                / f"sessions/{session_id}/output/.staging/{artifact_set_id}/research_workbook.xlsx"
            )
            self._workbook(workbook_path, frame[display_columns], chart_entries, session, bundle)
            record = self._write(
                session_id,
                artifact_set_id,
                bundle_id,
                "workbook",
                "research_workbook.xlsx",
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Analytical data, model results, provenance and chart "
                f"({PUBLICATION_GUIDELINE_VERSION})",
                workbook_path.read_bytes(),
                source_ids,
            )
            records.append(record)
            specifications[record.id] = table_spec_template.model_dump(mode="json")
            lint_report = lint_workbook(
                self.workflow_root / record.relative_path,
                template_version=WORKBOOK_TEMPLATE_VERSION,
                required_optional_sheets={
                    name
                    for name, required in (
                        ("Forecasts", not forecast_data.empty),
                        ("Impulse Responses", not irf_data.empty),
                    )
                    if required
                },
                require_chart=bool(deliverables.get("charts", True)) and bool(chart_entries),
            )
            workbook_lint_findings.extend(
                {**item.model_dump(mode="json"), "artifact_id": record.id}
                for item in lint_report.findings
            )
            shutil.rmtree(workbook_path.parent, ignore_errors=True)
        code_refs = (
            ("python", "python", "pythonCodeRef", deliverables.get("python", True)),
            ("stata", "stata_do", "stataCodeRef", deliverables.get("stata", True)),
        )
        for kind, artifact_format, reference_key, selected in code_refs:
            reference = bundle.get(reference_key)
            if not selected or not reference:
                continue
            code_record, code_path = self.code_manager.get(session_id, str(reference))
            records.append(
                self._write(
                    session_id,
                    artifact_set_id,
                    bundle_id,
                    kind,
                    code_record.filename,
                    artifact_format,
                    code_record.media_type,
                    "Generated from reviewed typed specifications "
                    f"({code_record.specification_hash})",
                    code_path.read_bytes(),
                    source_ids,
                )
            )
        report_drafts: dict[str, dict[str, Any]] = {}
        report_author_requests: dict[str, dict[str, Any]] = {}
        evidence_ledgers: dict[str, list[dict[str, Any]]] = {}
        if deliverables.get("researchReport"):
            if self.report_author is None:
                raise OutputWorkspaceError("A governed Report Author is not configured.")
            report_title = _publication_title(
                objective,
                "Macro research report",
                PUBLICATION_GUIDELINE.report.title_max_characters,
            )
            report_dataset = ModelDatasetContext(
                grant=self.model_data_access.context_for_snapshot(
                    session_id,
                    final_snapshot_id,
                    WorkflowStage.OUTPUT,
                    for_remote_provider=self.report_author.remote_data_disclosure,
                    provider_profile=self.report_author.provider_profile,
                    model_id=self.report_author.model_id,
                ).grant
            )
            model_results = [dict(item) for item in pipeline.get("modelResults") or []]
            result_hashes = {
                str(item.get("id") or f"result-{index + 1}"): stable_hash(item)
                for index, item in enumerate(model_results)
            }
            citation_names = source_names or ["Approved analytical snapshot"]
            citations = [
                ReportCitationV1(
                    citationId=f"source-{index + 1}",
                    label=name,
                    sourceRef=str(
                        (source_runs[index] if index < len(source_runs) else {}).get("snapshotId")
                        or (source_runs[index] if index < len(source_runs) else {}).get("id")
                        or final_snapshot_id
                        or name
                    ),
                )
                for index, name in enumerate(citation_names)
            ]
            candidate_metadata = [
                {"id": item.id, "format": item.format, "hash": item.checksum} for item in records
            ]
            staged = {item.id: item for item in records}
            try:
                presentation = build_presentation_evidence(
                    candidate_metadata,
                    specifications,
                    lambda artifact_id, expected: (
                        self.workflow_root / staged[artifact_id].relative_path
                    ).read_bytes(),
                )
            except PresentationEvidenceError as error:
                self._discard_uncommitted_artifacts(
                    [*records, *internal_records],
                    self.workflow_root / f"sessions/{session_id}/output/.staging/{artifact_set_id}",
                )
                raise OutputWorkspaceError(str(error), code=error.code) from error
            report_request = ReportAuthorRequestV1(
                sessionId=session_id,
                handoff=dict((session.get("handoffs") or [{}])[-1]),
                approvedPlan=plan,
                deliverables={str(key): bool(value) for key, value in deliverables.items()},
                dataset=report_dataset,
                modelResults=model_results,
                diagnostics=[
                    *[str(item) for item in bundle.get("diagnostics") or []],
                    *[str(item) for item in bundle.get("warnings") or []],
                ],
                forecasts=_json_safe(forecast_data.to_dict(orient="records")),
                resultHashes=result_hashes,
                hashSemantics={
                    "resultHashes": "hash of each complete typed model-result record",
                    "modelResults[].resultHash": (
                        "hash of only the nested numerical result payload; expected to differ "
                        "from resultHashes for the same result ID"
                    ),
                },
                artifacts=[
                    {
                        "id": item.id,
                        "kind": item.kind,
                        "format": item.format,
                        "hash": item.checksum,
                        "lifecycle": "generated-candidate",
                        "exportSelected": True,
                        "frozen": False,
                    }
                    for item in records
                ],
                citations=citations,
                presentationEvidence=presentation,
                publicationGuideline=PUBLICATION_GUIDELINE.model_dump(mode="json"),
                requiredSections=list(PUBLICATION_GUIDELINE.report.required_sections),
                title=report_title,
                sourceNote=source_note,
            )
            try:
                report_draft = self.report_author.author(report_request, self.model_data_access)
            except ReportProviderError as error:
                self._discard_uncommitted_artifacts(
                    [*records, *internal_records],
                    self.workflow_root / f"sessions/{session_id}/output/.staging/{artifact_set_id}",
                )
                raise OutputWorkspaceError(
                    str(error),
                    code=error.code,
                    issues=error.issues,
                    retryable=error.code in {"invalid_report_contract", "provider_unavailable"},
                ) from error
            report_content = render_report_markdown(report_draft)
            report = self._write(
                session_id,
                artifact_set_id,
                bundle_id,
                "research_report",
                "research_report.md",
                "report",
                "text/markdown",
                f"Governed research narrative ({PUBLICATION_GUIDELINE_VERSION})",
                report_content.encode("utf-8"),
                source_ids,
            )
            records.append(report)
            report_drafts[report.id] = report_draft.model_dump(mode="json", by_alias=True)
            report_author_requests[report.id] = report_request.model_dump(
                mode="json", by_alias=True
            )
            evidence_ledgers[report.id] = [
                item.model_dump(mode="json", by_alias=True) for item in report_draft.claims
            ]
            specifications[report.id] = ReportSpec(
                title=report_title,
                source_note=source_note,
                observation_count=len(frame),
                model_result_count=len(pipeline.get("modelResults") or []),
                citation_refs=citation_names,
                required_sections=list(PUBLICATION_GUIDELINE.report.required_sections),
                guideline_version=PUBLICATION_GUIDELINE_VERSION,
                data_hash=snapshot.snapshot_hash,
                draft_hash=stable_hash(report_drafts[report.id]),
                evidence_ledger_hash=stable_hash(evidence_ledgers[report.id]),
            ).model_dump(mode="json")
        all_records = [*records, *internal_records]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO workflow_output_artifacts(session_id, artifact_id, record_json)
                VALUES (?, ?, ?)
                """,
                [(session_id, item.id, item.model_dump_json()) for item in all_records],
            )
        artifacts = [self._artifact_payload(item) for item in records]
        preflight = deterministic_preflight(
            artifacts,
            specifications,
            len(frame),
            deliverables,
            review_render_refs=review_render_refs,
            workbook_lint_findings=workbook_lint_findings,
        )
        forecast_artifact = next((item for item in records if item.kind == "forecast_data"), None)
        preflight.extend(
            forecast_delivery_findings(
                list(pipeline.get("models") or []),
                forecast_data,
                artifact_id=forecast_artifact.id if forecast_artifact else None,
            )
        )
        return {
            "artifactSetId": artifact_set_id,
            "artifactSetHash": output_artifact_set_hash(artifacts, specifications),
            "artifacts": artifacts,
            "selectedArtifactId": artifacts[0]["id"] if artifacts else None,
            "guidelineVersion": PUBLICATION_GUIDELINE_VERSION,
            "workbookTemplateVersion": WORKBOOK_TEMPLATE_VERSION,
            "limitations": limitations,
            "revisionCapability": True,
            "artifactHistory": session.get("output", {}).get("artifactHistory") or [],
            "artifactSpecifications": specifications,
            "reviewRenderHashes": review_render_hashes,
            "reviewRenderRefs": review_render_refs,
            "preflightFindings": [item.model_dump(mode="json") for item in preflight],
            "reviewReport": None,
            "reviewHistory": [],
            "revisionHistory": [],
            "reviewIteration": 0,
            "maxReviewIterations": 3,
            "reportDrafts": report_drafts,
            "reportAuthorRequests": report_author_requests,
            "evidenceLedgers": evidence_ledgers,
            "reportSemanticStatus": "pending" if report_drafts else "not_applicable",
        }

    def regenerate(
        self,
        session_id: str,
        session: dict[str, Any],
        artifact_id: str,
        changes: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        """Create one new immutable artifact version from an approved typed patch."""

        output = session.get("output") or {}
        specification = dict((output.get("artifactSpecifications") or {}).get(artifact_id) or {})
        if not specification:
            raise OutputWorkspaceError("The selected artifact has no versioned specification.")
        old_record, _ = self.get(session_id, artifact_id)
        allowed = {"title", "unit", "source_note", "number_format", "alt_text", "columns"}
        if not changes or not set(changes).issubset(allowed):
            raise OutputWorkspaceError("The artifact patch contains an unsupported field.")
        if "columns" in changes:
            requested_columns = changes["columns"]
            available_columns = [str(value) for value in specification.get("columns") or []]
            if (
                old_record.format not in {"csv", "xlsx"}
                or not isinstance(requested_columns, list)
                or not requested_columns
                or len(requested_columns) != len(set(requested_columns))
                or not set(requested_columns).issubset(available_columns)
            ):
                raise OutputWorkspaceError(
                    "Table columns must be a non-empty unique subset of the current artifact."
                )
        # Capture legacy selection before applying any display-only patch.
        if old_record.format == "svg" and "source_unit" not in specification:
            old_unit = specification.get("unit")
            specification["source_unit"] = None if old_unit == "As reported" else old_unit
        specification.update(changes)
        pipeline = session.get("pipeline") or {}
        bundle = pipeline.get("bundle") or {}
        snapshot_id = str(bundle.get("finalDatasetRef") or "")
        snapshot = self.data_manager.get_snapshot(session_id, snapshot_id)
        frame = self.data_manager.frame(snapshot)
        review_ref: dict[str, Any] | None = None
        internal_records: list[OutputArtifactRecord] = []
        if old_record.format == "svg":
            chart_spec = ChartSpec.model_validate(specification)
            chart_data = _chart_frame(frame, chart_spec.indicator_code, chart_spec.source_unit)
            selected_fields = [
                field for field in chart_spec.y_fields if field in chart_data.columns
            ]
            if not selected_fields or chart_data[selected_fields].notna().sum().sum() == 0:
                raise OutputWorkspaceError(
                    "Chart revision has no numeric observations; return upstream."
                )
            chart_data = chart_data[[chart_spec.x_field, *selected_fields]]
            content = _svg_chart(chart_data, chart_spec).encode("utf-8")
            review_name = f"{Path(old_record.name).stem}.review.png"
            review = self._write(
                session_id,
                old_record.artifact_set_id,
                old_record.bundle_id,
                "review_render",
                review_name,
                "png",
                "image/png",
                "Fixed-size direct artifact render for local or authorized visual review",
                _png_review_render(chart_data, chart_spec.width, chart_spec.height, chart_spec),
                old_record.source_snapshot_ids,
            )
            review_ref = {
                "id": review.id,
                "hash": review.checksum,
                "width": chart_spec.width,
                "height": chart_spec.height,
                "specHash": stable_hash(chart_spec.model_dump(mode="json")),
                "dataHash": snapshot.snapshot_hash,
            }
            internal_records.append(review)
        elif old_record.format == "csv":
            table_spec = TableSpec.model_validate(specification)
            if old_record.kind == "forecast_data":
                regenerated_frame = _forecast_frame(list(pipeline.get("modelResults") or []))
            elif old_record.kind == "irf_data":
                regenerated_frame = _irf_frame(list(pipeline.get("modelResults") or []))
            else:
                regenerated_frame = frame
            regenerated_frame = regenerated_frame.loc[:, table_spec.columns]
            content = regenerated_frame.to_csv(index=False).encode("utf-8")
        elif old_record.format == "xlsx":
            table_spec = TableSpec.model_validate(specification)
            workbook_path = (
                self.workflow_root
                / f"sessions/{session_id}/output/.staging/{uuid4().hex}/research_workbook.xlsx"
            )
            chart_entries: list[tuple[pd.DataFrame, ChartSpec | None]] = [
                (view.frame, None)
                for view in _chart_views(frame)[:12]
                if (session.get("currentPlan") or {}).get("deliverables", {}).get("charts", True)
            ]
            self._workbook(
                workbook_path,
                frame.loc[:, table_spec.columns],
                chart_entries,
                session,
                bundle,
            )
            content = workbook_path.read_bytes()
            shutil.rmtree(workbook_path.parent, ignore_errors=True)
        else:
            raise OutputWorkspaceError(
                "Selective regeneration supports only chart and table artifacts."
            )
        record = self._write(
            session_id,
            old_record.artifact_set_id,
            old_record.bundle_id,
            old_record.kind,
            old_record.name,
            old_record.format,
            old_record.media_type,
            f"Regenerated from approved typed patch ({PUBLICATION_GUIDELINE_VERSION})",
            content,
            old_record.source_snapshot_ids,
        )
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO workflow_output_artifacts(session_id, artifact_id, record_json)
                VALUES (?, ?, ?)
                """,
                [
                    (session_id, item.id, item.model_dump_json())
                    for item in [record, *internal_records]
                ],
            )
        return self._artifact_payload(record), specification, review_ref

    def revise_report(
        self,
        session_id: str,
        session: dict[str, Any],
        artifact_id: str,
        directive: ReportRevisionDirectiveV1,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Rewrite only reviewer-authorized report sections into a new immutable version."""

        if self.report_author is None:
            raise OutputWorkspaceError("A governed Report Author is not configured.")
        if directive.requires_upstream_stage:
            raise OutputWorkspaceError(
                "This report finding requires an upstream stage and cannot be rewritten."
            )
        output = dict(session.get("output") or {})
        old_record, _ = self.get(session_id, artifact_id)
        if old_record.format != "report" or directive.artifact_id != artifact_id:
            raise OutputWorkspaceError("The revision directive is not bound to this report.")
        draft_wire = dict((output.get("reportDrafts") or {}).get(artifact_id) or {})
        request_wire = dict((output.get("reportAuthorRequests") or {}).get(artifact_id) or {})
        if not draft_wire or not request_wire:
            raise OutputWorkspaceError("The report has no evidence-bound authoring record.")
        bundle = dict((session.get("pipeline") or {}).get("bundle") or {})
        snapshot_id = str(bundle.get("finalDatasetRef") or "")
        dataset = ModelDatasetContext(
            grant=self.model_data_access.context_for_snapshot(
                session_id,
                snapshot_id,
                WorkflowStage.OUTPUT,
                for_remote_provider=self.report_author.remote_data_disclosure,
                provider_profile=self.report_author.provider_profile,
                model_id=self.report_author.model_id,
            ).grant
        )
        request_wire["dataset"] = dataset.model_dump(mode="json")
        request_wire["artifacts"] = [
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "format": item.get("format"),
                "hash": item.get("hash"),
                "lifecycle": "generated-candidate",
                "exportSelected": bool(item.get("exportSelected")),
                "frozen": False,
            }
            for item in output.get("artifacts") or []
            if item.get("format") != "report"
        ]
        author_request = ReportAuthorRequestV1.model_validate(request_wire)
        try:
            author_request.presentation_evidence = build_presentation_evidence(
                author_request.artifacts,
                output.get("artifactSpecifications") or {},
                lambda artifact_id, expected: self.read_artifact_content(
                    session_id, artifact_id, expected
                ),
            )
        except PresentationEvidenceError as error:
            raise OutputWorkspaceError(str(error), code=error.code) from error
        revision_request = ReportRevisionRequestV1(
            authorRequest=author_request,
            currentDraft=ReportDraftV1.model_validate(draft_wire),
            directive=directive,
        )
        try:
            revised_draft = self.report_author.revise(revision_request, self.model_data_access)
        except ReportProviderError as error:
            raise OutputWorkspaceError(f"[{error.code}] {error}") from error
        validate_revised_draft(revision_request, revised_draft)
        content = render_report_markdown(revised_draft).encode("utf-8")
        record = self._write(
            session_id,
            old_record.artifact_set_id,
            old_record.bundle_id,
            old_record.kind,
            old_record.name,
            old_record.format,
            old_record.media_type,
            f"Revised from an approved semantic directive ({PUBLICATION_GUIDELINE_VERSION})",
            content,
            old_record.source_snapshot_ids,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_output_artifacts(session_id, artifact_id, record_json)
                VALUES (?, ?, ?)
                """,
                (session_id, record.id, record.model_dump_json()),
            )
        specification = ReportSpec.model_validate(
            (output.get("artifactSpecifications") or {}).get(artifact_id) or {}
        ).model_copy(
            update={
                "draft_hash": stable_hash(revised_draft.model_dump(mode="json", by_alias=True)),
                "evidence_ledger_hash": stable_hash(
                    [item.model_dump(mode="json", by_alias=True) for item in revised_draft.claims]
                ),
            }
        )
        revised_request = author_request.model_dump(mode="json", by_alias=True)
        return (
            self._artifact_payload(record),
            specification.model_dump(mode="json"),
            revised_draft.model_dump(mode="json", by_alias=True),
            revised_request,
        )

    def finalize_manifest(
        self, session_id: str, session: dict[str, Any], selected_ids: list[str]
    ) -> OutputArtifactRecord:
        output = session.get("output") or {}
        pipeline = session.get("pipeline") or {}
        bundle = pipeline.get("bundle") or {}
        artifacts = [
            item for item in output.get("artifacts") or [] if item.get("id") in selected_ids
        ]
        if not artifacts:
            raise OutputWorkspaceError("Select at least one ready artifact before final approval.")
        capability_invocations = (
            self.capability_receipt_provider(session_id)
            if self.capability_receipt_provider is not None
            else []
        )
        payload = {
            "schemaVersion": "mra-reproduction-manifest-v1",
            "sessionId": session_id,
            "artifactSetId": output.get("artifactSetId"),
            "artifactSetHash": output.get("artifactSetHash"),
            "guidelineVersion": output.get("guidelineVersion"),
            "workbookTemplateVersion": output.get("workbookTemplateVersion"),
            "approvedPlanSnapshotId": session.get("approvedPlanSnapshotId"),
            "approvedDatasetSnapshotId": (session.get("data") or {}).get("approvedSnapshotId"),
            "analyticalBundle": _json_safe(bundle),
            "operations": _json_safe(pipeline.get("operations") or []),
            "modelResults": _json_safe(pipeline.get("modelResults") or []),
            "artifacts": [
                {"id": item.get("id"), "name": item.get("name"), "hash": item.get("hash")}
                for item in artifacts
            ],
            "limitations": output.get("limitations") or [],
            "artifactSpecifications": output.get("artifactSpecifications") or {},
            "preflightFindings": output.get("preflightFindings") or [],
            "outputReview": output.get("reviewReport"),
            "chartSelfChecks": output.get("chartSelfChecks", []),
            "capabilityInvocations": capability_invocations,
        }
        record = self._write(
            session_id,
            str(output.get("artifactSetId")),
            str(bundle.get("id")),
            "manifest",
            "reproduction_manifest.json",
            "json",
            "application/json",
            "Frozen provenance, lineage, specifications and artifact checksums",
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
            [str(bundle.get("finalDatasetRef"))],
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_output_artifacts(session_id, artifact_id, record_json)
                VALUES (?, ?, ?)
                """,
                (session_id, record.id, record.model_dump_json()),
            )
        return record

    def get(self, session_id: str, artifact_id: str) -> tuple[OutputArtifactRecord, Path]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT record_json FROM workflow_output_artifacts
                WHERE session_id = ? AND artifact_id = ?
                """,
                (session_id, artifact_id),
            ).fetchone()
        if row is None:
            raise OutputWorkspaceError("Output artifact was not found for this Workflow session.")
        record = OutputArtifactRecord.model_validate_json(row["record_json"])
        path = self.workflow_root / record.relative_path
        if not path.is_file() or _hash_bytes(path.read_bytes()) != record.checksum:
            raise OutputWorkspaceError("Output artifact is missing or failed checksum validation.")
        return record, path

    def read_review_render(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        record, path = self.get(session_id, artifact_id)
        if record.kind != "review_render" or record.format != "png":
            raise OutputWorkspaceError("The referenced artifact is not a review render.")
        content = path.read_bytes()
        actual_hash = _hash_bytes(content)
        if not expected_hash or actual_hash != expected_hash or record.checksum != expected_hash:
            raise OutputWorkspaceError("The review render checksum does not match its reference.")
        return content

    def read_artifact_content(self, session_id: str, artifact_id: str, expected_hash: str) -> bytes:
        record, path = self.get(session_id, artifact_id)
        if not expected_hash or record.checksum != expected_hash:
            raise OutputWorkspaceError("The artifact checksum does not match its review reference.")
        return path.read_bytes()

    def preview(self, session_id: str, artifact_id: str) -> dict[str, Any]:
        record, path = self.get(session_id, artifact_id)
        payload: dict[str, Any] = {**record.model_dump(mode="json")}
        if record.format == "csv":
            frame = pd.read_csv(path, nrows=25)
            payload.update(
                {
                    "previewKind": "table",
                    "columns": [str(column) for column in frame.columns],
                    "rows": [_json_safe(item) for item in frame.to_dict(orient="records")],
                }
            )
        elif record.format in {"python", "stata_do", "json", "report"}:
            payload.update(
                {"previewKind": "text", "content": path.read_text(encoding="utf-8")[:200_000]}
            )
        elif record.format == "xlsx":
            workbook = pd.ExcelFile(path)
            payload.update({"previewKind": "workbook", "sheetNames": workbook.sheet_names})
        elif record.format == "svg":
            payload.update({"previewKind": "image"})
        return payload

    def compare(
        self,
        session_id: str,
        baseline_artifact_id: str,
        current_artifact_id: str,
        baseline_specification: dict[str, Any] | None = None,
        current_specification: dict[str, Any] | None = None,
    ) -> ArtifactComparisonReport:
        baseline, baseline_path = self.get(session_id, baseline_artifact_id)
        current, current_path = self.get(session_id, current_artifact_id)
        return compare_artifacts(
            baseline_artifact_id=baseline.id,
            current_artifact_id=current.id,
            baseline_format=baseline.format,
            current_format=current.format,
            baseline_hash=baseline.checksum,
            current_hash=current.checksum,
            baseline_path=baseline_path,
            current_path=current_path,
            baseline_specification=baseline_specification,
            current_specification=current_specification,
        )
