from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    XLSX = "xlsx"
    PNG = "png"
    SVG = "svg"
    CSV = "csv"
    JSON = "json"
    PYTHON = "python"
    STATA_DO = "stata_do"


class ChartSpecification(BaseModel):
    chart_type: str
    title: str
    source_note: str
    x_field: str
    y_fields: list[str]
    style_guide_version: str
    options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class TableSpecification(BaseModel):
    title: str
    columns: list[str]
    source_note: str
    style_guide_version: str
    options: dict[str, str | int | float | bool] = Field(default_factory=dict)
