from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from macro_research_agent import __version__
from macro_research_agent.capabilities.contracts import (
    CapabilityAvailability,
    CapabilityDescriptor,
    StageId,
)
from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.connectors.registry import connector_catalog
from macro_research_agent.knowledge.data_sources import DataSourceKnowledgeCatalog
from macro_research_agent.knowledge.source_index import SourceIndexRepository
from macro_research_agent.models.specs import ModelKind
from macro_research_agent.reporting.specs import ExportFormat
from macro_research_agent.skills.contracts import RuntimeSkillManifest
from macro_research_agent.skills.registry import SkillRegistry
from macro_research_agent.workflow.states import SessionState, WorkflowStage

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class CapabilityResponse(BaseModel):
    research_modes: list[str]
    workflow_stages: list[str]
    workflow_statuses: list[str]
    connectors: list[str]
    planned_connectors: list[str]
    models: list[str]
    planned_models: list[str]
    exports: list[str]
    planned_exports: list[str]
    llm_provider: str
    data_assistant_provider: str
    data_assistant_model: str
    analysis_assistant_provider: str
    analysis_assistant_model: str
    report_author_provider: str
    report_author_model: str
    chart_author_provider: str
    chart_author_model: str
    chart_author_self_check_rounds: int
    output_review_provider: str | None
    output_review_model: str | None
    output_review_api_credential_configured: bool
    remote_output_review_status: str
    acquisition_policy: str
    visual_test_policy: str


class RegistryInspectionResponse(BaseModel):
    capabilities: list[CapabilityDescriptor]
    skills: list[RuntimeSkillManifest]


class DataSourceKnowledgeResponse(BaseModel):
    schema_version: str
    catalog_version: str
    content_sha256: str
    matches: list[dict[str, Any]]


class SourceIndexResponse(BaseModel):
    schema_version: str
    matches: list[dict[str, Any]]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=request.app.state.settings.environment,
    )


@router.get("/capabilities", response_model=CapabilityResponse)
def capabilities(request: Request) -> CapabilityResponse:
    catalog = connector_catalog()
    settings = request.app.state.settings
    return CapabilityResponse(
        research_modes=["workflow", "agent"],
        workflow_stages=[stage.value for stage in WorkflowStage],
        workflow_statuses=[status.value for status in SessionState],
        connectors=sorted(
            connector_id
            for connector_id, item in catalog.items()
            if item.availability == "available"
        ),
        planned_connectors=sorted(
            connector_id for connector_id, item in catalog.items() if item.availability == "planned"
        ),
        models=["adf", "arima", "correlation", "descriptive", "ols", "sarimax", "var"],
        planned_models=[
            kind.value
            for kind in ModelKind
            if kind.value
            not in {"adf", "arima", "correlation", "descriptive", "ols", "sarimax", "var"}
        ],
        exports=[item.value for item in ExportFormat if item not in {ExportFormat.PNG}],
        planned_exports=[ExportFormat.PNG.value],
        # The public runtime contract exposes the only admitted planning
        # provider, never the internal offline test fake.
        llm_provider="deepseek",
        data_assistant_provider="deepseek",
        data_assistant_model=settings.data_ai_model or settings.deepseek_model,
        analysis_assistant_provider="deepseek",
        analysis_assistant_model=settings.analysis_ai_model or settings.deepseek_model,
        report_author_provider="deepseek",
        report_author_model=settings.report_author_model or settings.deepseek_model,
        chart_author_provider="deepseek",
        chart_author_model=settings.deepseek_model,
        chart_author_self_check_rounds=2,
        output_review_provider="codex-local",
        output_review_model=settings.output_review_model or None,
        output_review_api_credential_configured=False,
        remote_output_review_status="codex_local_enabled",
        acquisition_policy="registered-connectors-only",
        visual_test_policy="structural-codex-local-and-human-review",
    )


@router.get("/registry/capabilities", response_model=list[CapabilityDescriptor])
def capability_descriptors(
    request: Request,
    stage: StageId | None = None,
    availability: CapabilityAvailability | None = None,
) -> list[CapabilityDescriptor]:
    registry = cast(CapabilityRegistry, request.app.state.capability_registry)
    return registry.list(stage=stage, availability=availability)


@router.get("/data-source-knowledge", response_model=DataSourceKnowledgeResponse)
def data_source_knowledge(
    request: Request,
    q: str = Query(default="", max_length=500),
    limit: int = Query(default=12, ge=1, le=50),
) -> DataSourceKnowledgeResponse:
    catalog = cast(DataSourceKnowledgeCatalog, request.app.state.data_source_knowledge)
    available = sorted(
        connector_id
        for connector_id, item in connector_catalog().items()
        if item.availability == "available"
    )
    return DataSourceKnowledgeResponse(
        schema_version=catalog.schema_version,
        catalog_version=catalog.catalog_version,
        content_sha256=catalog.content_sha256 or "",
        matches=catalog.for_planning(q, available, max_datasets=limit),
    )


@router.get("/source-index/providers", response_model=list[dict[str, Any]])
def source_index_providers(request: Request) -> list[dict[str, Any]]:
    index = cast(SourceIndexRepository, request.app.state.source_index)
    return index.provider_summaries()


@router.get("/source-index/search", response_model=SourceIndexResponse)
def source_index_search(
    request: Request,
    q: str = Query(default="", max_length=500),
    provider: str | None = Query(default=None, max_length=100),
    executable_only: bool = False,
    limit: int = Query(default=12, ge=1, le=50),
) -> SourceIndexResponse:
    index = cast(SourceIndexRepository, request.app.state.source_index)
    return SourceIndexResponse(
        schema_version=index.schema_version,
        matches=[
            item.model_dump(mode="json")
            for item in index.search(
                q,
                provider_id=provider,
                executable_only=executable_only,
                limit=limit,
            )
        ],
    )


@router.get("/source-index/providers/{provider_id}/datasets", response_model=list[dict[str, Any]])
def source_index_datasets(
    request: Request,
    provider_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    index = cast(SourceIndexRepository, request.app.state.source_index)
    return index.datasets(provider_id, offset=offset, limit=limit)


@router.get(
    "/source-index/providers/{provider_id}/dimensions/{dimension_id}",
    response_model=dict[str, Any],
)
def source_index_provider_dimension_values(
    request: Request,
    provider_id: str,
    dimension_id: str,
    q: str = Query(default="", max_length=500),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    index = cast(SourceIndexRepository, request.app.state.source_index)
    return index.provider_dimension_values(
        provider_id,
        dimension_id,
        query=q,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/source-index/providers/{provider_id}/datasets/{dataset_id}/dimensions/{dimension_id}",
    response_model=dict[str, Any],
)
def source_index_dimension_values(
    request: Request,
    provider_id: str,
    dataset_id: str,
    dimension_id: str,
    q: str = Query(default="", max_length=500),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    index = cast(SourceIndexRepository, request.app.state.source_index)
    return index.dimension_values(
        provider_id,
        dataset_id,
        dimension_id,
        query=q,
        offset=offset,
        limit=limit,
    )


@router.get("/registry/skills", response_model=list[RuntimeSkillManifest])
def runtime_skills(
    request: Request,
    stage: StageId | None = None,
    availability: CapabilityAvailability | None = None,
) -> list[RuntimeSkillManifest]:
    registry = cast(SkillRegistry, request.app.state.skill_registry)
    return registry.list(stage=stage, availability=availability)


@router.get("/admin/registry", response_model=RegistryInspectionResponse)
def inspect_registry(request: Request) -> RegistryInspectionResponse:
    capabilities_registry = cast(CapabilityRegistry, request.app.state.capability_registry)
    skill_registry = cast(SkillRegistry, request.app.state.skill_registry)
    return RegistryInspectionResponse(
        capabilities=capabilities_registry.list(),
        skills=skill_registry.list(),
    )
