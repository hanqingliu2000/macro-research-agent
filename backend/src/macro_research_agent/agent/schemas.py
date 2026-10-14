from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from macro_research_agent.models.specs import ModelSpecification
from macro_research_agent.reporting.specs import ExportFormat


class AgentAttachmentMetadata(BaseModel):
    attachment_id: str
    filename: str
    media_type: Literal[
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]
    size_bytes: int = Field(ge=0)
    schema_summary: dict[str, Any] = Field(default_factory=dict)


class AgentRoutingContext(BaseModel):
    research_request: str
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    attachments: list[AgentAttachmentMetadata] = Field(default_factory=list)
    available_connector_ids: list[str]


class AgentConnectorQuery(BaseModel):
    connector_id: str
    dataset: str
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    start_period: str | None = None
    end_period: str | None = None
    frequency: str | None = None


class AgentTransformSpecification(BaseModel):
    operation: Literal[
        "filter",
        "rename",
        "map_codes",
        "reshape",
        "merge",
        "lag",
        "growth_rate",
        "index",
        "align_frequency",
    ]
    parameters: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)


class AgentRouteDecision(BaseModel):
    attachment_ids: list[str] = Field(default_factory=list)
    connector_queries: list[AgentConnectorQuery] = Field(default_factory=list)
    transformations: list[AgentTransformSpecification] = Field(default_factory=list)
    models: list[ModelSpecification] = Field(default_factory=list)
    exports: list[ExportFormat] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    conclusion: str
    key_findings: list[str]
    caveats: list[str]
    artifact_ids: list[str]
    route_summary: str
