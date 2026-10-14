"""Pure numerical and rendering facade; no Workflow repository/manager is constructed."""

from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.workflow.code_workspace import CodeWorkspaceManager
from macro_research_agent.workflow.data_workspace import DataWorkspaceManager
from macro_research_agent.workflow.model_workspace import (
    SUPPORTED_MODELS as SUPPORTED_MODELS,
)
from macro_research_agent.workflow.model_workspace import (
    ModelWorkspaceManager,
)
from macro_research_agent.workflow.model_workspace import (
    evaluate_typed_model_frame as evaluate_typed_model_frame,
)
from macro_research_agent.workflow.output_workspace import (
    _chart_frame as chart_frame,
)
from macro_research_agent.workflow.output_workspace import (
    _chart_views as chart_views,
)
from macro_research_agent.workflow.output_workspace import (
    _forecast_frame as forecast_frame,
)
from macro_research_agent.workflow.output_workspace import (
    _irf_frame as irf_frame,
)
from macro_research_agent.workflow.output_workspace import (
    _png_review_render as png_review_render,
)
from macro_research_agent.workflow.output_workspace import (
    _svg_chart as svg_chart,
)
from macro_research_agent.workflow.output_workspace import (
    publication_columns as publication_columns,
)
from macro_research_agent.workflow.pipeline_draft import (
    default_model_parameters as default_model_parameters,
)

CANONICAL_KEYS = ["entity_code", "indicator_code", "frequency", "period"]
CANONICAL_COLUMNS = ["series_id", *CANONICAL_KEYS, "value"]

__all__ = [
    "chart_frame",
    "chart_views",
    "forecast_frame",
    "irf_frame",
    "png_review_render",
    "svg_chart",
]


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return DataWorkspaceManager._normalize(frame)


def validate_model_job(job: dict[str, Any]) -> None:
    ModelWorkspaceManager.validate_job(job)


def reproduction_specification(
    operations: list[dict[str, Any]], models: list[dict[str, Any]]
) -> dict[str, Any]:
    return CodeWorkspaceManager.specification(operations, models)


def python_reproduction(specification: dict[str, Any], specification_hash: str) -> str:
    return CodeWorkspaceManager.python_source(specification, specification_hash)


def stata_reproduction(specification: dict[str, Any], specification_hash: str) -> str:
    return CodeWorkspaceManager.stata_source(specification, specification_hash)
