from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from macro_research_agent.workflow.publication_rubric import AcademicVisualRubric

PUBLICATION_GUIDELINE_VERSION = "publication-v1"


class ChartGuideline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supported_types: tuple[Literal["line"], ...] = ("line",)
    title_max_characters: int = Field(default=90, ge=1)
    maximum_series: int = Field(default=6, ge=1)
    minimum_width: int = Field(default=900, ge=320)
    minimum_height: int = Field(default=500, ge=240)
    legend_position: Literal["bottom"] = "bottom"
    palette: tuple[str, ...] = (
        "#0072B2",
        "#D55E00",
        "#009E73",
        "#CC79A7",
        "#E69F00",
        "#56B4E9",
    )
    line_patterns: tuple[Literal["solid", "dash", "dot"], ...] = (
        "solid",
        "dash",
        "dot",
    )
    missing_value_policy: Literal["gap"] = "gap"


class TableGuideline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    maximum_columns: int = Field(default=24, ge=1)
    title_max_characters: int = Field(default=90, ge=1)
    freeze_header: bool = True
    enable_filters: bool = True
    numeric_alignment: Literal["right"] = "right"
    missing_value_display: Literal["…"] = "…"
    source_note_required: bool = True
    allowed_number_formats: tuple[str, ...] = (
        "0",
        "0.0",
        "0.00",
        "0.000",
        "0%",
        "0.0%",
        "0.00%",
    )


class ReportGuideline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title_max_characters: int = Field(default=120, ge=1)
    required_sections: tuple[str, ...] = (
        "Scope",
        "Data and method",
        "Results",
        "Diagnostics and limitations",
        "Reproducibility",
    )
    require_source_note: bool = True
    require_causal_boundary: bool = True
    require_reproduction_note: bool = True
    missing_citations_severity: Literal["warning"] = "warning"


class PublicationGuideline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal["publication-v1"] = "publication-v1"
    status: Literal["approved"] = "approved"
    locale: Literal["en-US"] = "en-US"
    chart: ChartGuideline = Field(default_factory=ChartGuideline)
    table: TableGuideline = Field(default_factory=TableGuideline)
    report: ReportGuideline = Field(default_factory=ReportGuideline)
    visual_rubric: AcademicVisualRubric = Field(default_factory=AcademicVisualRubric)


PUBLICATION_GUIDELINE = PublicationGuideline()


def get_publication_guideline(version: str) -> PublicationGuideline:
    if version != PUBLICATION_GUIDELINE_VERSION:
        raise ValueError(f"Publication guideline is not registered: {version}.")
    return PUBLICATION_GUIDELINE
