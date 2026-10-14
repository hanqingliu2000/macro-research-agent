from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from macro_research_agent.connectors.adb import AdbConnector
from macro_research_agent.connectors.bis import BisConnector
from macro_research_agent.connectors.ecb import EcbConnector
from macro_research_agent.connectors.eurostat import EurostatConnector
from macro_research_agent.connectors.imf import ImfConnectorError, ImfDataConnector
from macro_research_agent.connectors.oecd import OecdConnector, OecdConnectorError
from macro_research_agent.connectors.un_sdg import UnSdgConnector
from macro_research_agent.connectors.world_bank import (
    WorldBankConnector,
    WorldBankConnectorError,
)
from macro_research_agent.trace.events import TraceEvent
from macro_research_agent.workflow.api_schemas import (
    CreateWorkflowSessionRequest,
    DispatchDataCommandRequest,
    DispatchOutputCommandRequest,
    DispatchPipelineCommandRequest,
    DispatchPlanCommandRequest,
    GeographyResolveRequest,
    StoredWorkflowSession,
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowConflictDetail,
    WorkflowProjection,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.artifact_comparison import ArtifactComparisonReport
from macro_research_agent.workflow.code_workspace import (
    CodeWorkspaceError,
    CodeWorkspaceManager,
)
from macro_research_agent.workflow.data_service import WorkflowDataService
from macro_research_agent.workflow.data_workspace import DataWorkspaceError, DataWorkspaceManager
from macro_research_agent.workflow.geography import (
    ControlledGeography,
    ControlledGeographyResolver,
    GeographyNotFound,
)
from macro_research_agent.workflow.graph.contracts import GraphSnapshot, NodeAttempt, ResearchNode
from macro_research_agent.workflow.graph.service import GraphInvariantError, GraphService
from macro_research_agent.workflow.handoff import record_stage_handoff
from macro_research_agent.workflow.handoff_service import (
    WorkflowHandoffError,
    WorkflowHandoffService,
)
from macro_research_agent.workflow.output_service import WorkflowOutputService
from macro_research_agent.workflow.output_workspace import (
    OutputWorkspaceError,
    OutputWorkspaceManager,
)
from macro_research_agent.workflow.pipeline_service import WorkflowPipelineService
from macro_research_agent.workflow.pipeline_workspace import (
    PipelineWorkspaceError,
    PipelineWorkspaceManager,
)
from macro_research_agent.workflow.planning_adapters import PlanningProviderError
from macro_research_agent.workflow.planning_service import (
    PlanningCommandError,
    WorkflowPlanningService,
)
from macro_research_agent.workflow.portable_sessions import (
    ForkSessionRequest,
    PortableSessionError,
    PortableSessionManager,
)
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.repository import WorkflowConflict, WorkflowSessionNotFound
from macro_research_agent.workflow.states import WorkflowStage
from macro_research_agent.workflow.uploads import (
    LocalUploadService,
    UploadedFileRecord,
    UploadValidationError,
)

workflow_router = APIRouter(prefix="/workflow", tags=["workflow"])
admin_workflow_router = APIRouter(prefix="/admin/workflow", tags=["workflow-admin"])


def workflow_repository(request: Request) -> WorkflowRepository:
    return cast(WorkflowRepository, request.app.state.workflow_repository)


WorkflowRepositoryDependency = Annotated[WorkflowRepository, Depends(workflow_repository)]


def workflow_graph_service(request: Request) -> GraphService:
    return cast(GraphService, request.app.state.workflow_graph_service)


WorkflowGraphServiceDependency = Annotated[GraphService, Depends(workflow_graph_service)]


def workflow_upload_service(request: Request) -> LocalUploadService:
    return cast(LocalUploadService, request.app.state.workflow_upload_service)


WorkflowUploadServiceDependency = Annotated[LocalUploadService, Depends(workflow_upload_service)]


def workflow_planning_service(request: Request) -> WorkflowPlanningService:
    return cast(WorkflowPlanningService, request.app.state.workflow_planning_service)


def geography_resolver(request: Request) -> ControlledGeographyResolver:
    return cast(ControlledGeographyResolver, request.app.state.geography_resolver)


WorkflowPlanningServiceDependency = Annotated[
    WorkflowPlanningService, Depends(workflow_planning_service)
]
GeographyResolverDependency = Annotated[ControlledGeographyResolver, Depends(geography_resolver)]


def workflow_data_service(request: Request) -> WorkflowDataService:
    return cast(WorkflowDataService, request.app.state.workflow_data_service)


def data_workspace_manager(request: Request) -> DataWorkspaceManager:
    return cast(DataWorkspaceManager, request.app.state.data_workspace_manager)


WorkflowDataServiceDependency = Annotated[WorkflowDataService, Depends(workflow_data_service)]
DataWorkspaceManagerDependency = Annotated[DataWorkspaceManager, Depends(data_workspace_manager)]


def workflow_pipeline_service(request: Request) -> WorkflowPipelineService:
    return cast(WorkflowPipelineService, request.app.state.workflow_pipeline_service)


def pipeline_workspace_manager(request: Request) -> PipelineWorkspaceManager:
    return cast(PipelineWorkspaceManager, request.app.state.pipeline_workspace_manager)


WorkflowPipelineServiceDependency = Annotated[
    WorkflowPipelineService, Depends(workflow_pipeline_service)
]
PipelineWorkspaceManagerDependency = Annotated[
    PipelineWorkspaceManager, Depends(pipeline_workspace_manager)
]


def workflow_output_service(request: Request) -> WorkflowOutputService:
    return cast(WorkflowOutputService, request.app.state.workflow_output_service)


WorkflowOutputServiceDependency = Annotated[WorkflowOutputService, Depends(workflow_output_service)]


def workflow_handoff_service(request: Request) -> WorkflowHandoffService:
    return cast(WorkflowHandoffService, request.app.state.workflow_handoff_service)


WorkflowHandoffServiceDependency = Annotated[
    WorkflowHandoffService, Depends(workflow_handoff_service)
]


def portable_session_manager(request: Request) -> PortableSessionManager:
    return cast(PortableSessionManager, request.app.state.portable_session_manager)


PortableSessionManagerDependency = Annotated[
    PortableSessionManager, Depends(portable_session_manager)
]


def _not_found(session_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown session {session_id}"
    )


@workflow_router.get("/sessions", response_model=list[StoredWorkflowSession])
def list_sessions(repository: WorkflowRepositoryDependency) -> list[StoredWorkflowSession]:
    return repository.list_sessions()


@workflow_router.get("/connectors/imf/{dataset}")
async def imf_metadata(dataset: str, manager: DataWorkspaceManagerDependency) -> dict[str, Any]:
    try:
        return await ImfDataConnector(manager.workflow_root / "metadata").metadata(dataset.upper())
    except ImfConnectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@workflow_router.get("/connectors/imf")
def imf_datasets() -> dict[str, Any]:
    return {"datasets": ImfDataConnector.registered_datasets()}


@workflow_router.get("/connectors/world-bank")
def world_bank_contract() -> dict[str, Any]:
    return {
        "dataset": "WDI",
        "source_id": WorldBankConnector.source_id,
        "frequency": "A",
        "query_dimensions": ["country", "indicator"],
        "max_observations": WorldBankConnector.max_observations,
    }


@workflow_router.get("/connectors/world-bank/indicators/{indicator}")
async def world_bank_indicator(
    indicator: str, manager: DataWorkspaceManagerDependency
) -> dict[str, Any]:
    try:
        connector = WorldBankConnector(manager.workflow_root / "metadata" / "world_bank")
        return await connector.indicator_metadata(indicator.upper())
    except WorldBankConnectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@workflow_router.get("/connectors/oecd")
async def oecd_contract(manager: DataWorkspaceManagerDependency) -> dict[str, Any]:
    try:
        connector = OecdConnector(manager.workflow_root / "metadata" / "oecd")
        return {
            "dataset": connector.dataset,
            "dataflow": connector.dataflow,
            "version": connector.registered_version,
            "frequency": "M",
            "indicators": connector.allowed_measures,
            "metadata": await connector.metadata(),
        }
    except OecdConnectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@workflow_router.get("/connectors/eurostat")
def eurostat_contract() -> dict[str, Any]:
    return {
        "dataset": EurostatConnector.dataset,
        "provider_dataset": EurostatConnector.provider_dataset,
        "frequency": "M",
        "unit": "I25",
        "indicators": EurostatConnector.allowed_indicators,
        "country_crosswalk": EurostatConnector.iso3_to_geo,
        "max_observations": EurostatConnector.max_observations,
    }


@workflow_router.get("/connectors/adb")
def adb_contract() -> dict[str, Any]:
    return {
        "dataset": AdbConnector.dataset,
        "dataflow": AdbConnector.dataflow,
        "dataflow_version": AdbConnector.registered_dataflow_version,
        "api_version": "v5",
        "sdmx_version": "3.0",
        "frequency": "A",
        "period": {"start": "2000", "end": "2024"},
        "indicators": AdbConnector.allowed_indicators,
        "country_crosswalk": AdbConnector.iso3_to_adb,
        "max_observations": AdbConnector.max_observations,
    }


@workflow_router.get("/connectors/ecb")
def ecb_contract() -> dict[str, Any]:
    return {
        "dataset": EcbConnector.dataset,
        "dataflow": EcbConnector.dataflow,
        "dataflow_version": EcbConnector.dataflow_version,
        "frequency": "M",
        "quote": "foreign currency per euro",
        "indicators": EcbConnector.allowed_indicators,
        "country_crosswalk": EcbConnector.iso3_to_currency,
        "max_observations": EcbConnector.max_observations,
    }


@workflow_router.get("/connectors/bis")
def bis_contract() -> dict[str, Any]:
    return {
        "dataset": BisConnector.dataset,
        "dataflow": BisConnector.dataflow,
        "api_version": "v2",
        "frequency": "M",
        "collection": "end_of_period",
        "unit": "per cent per year",
        "indicators": BisConnector.allowed_indicators,
        "country_crosswalk": BisConnector.iso3_to_bis,
        "max_observations": BisConnector.max_observations,
    }


@workflow_router.get("/connectors/un-sdg")
def un_sdg_contract() -> dict[str, Any]:
    return {
        "dataset": UnSdgConnector.dataset,
        "indicator": UnSdgConnector.indicator_code,
        "frequency": "A",
        "series": UnSdgConnector.allowed_indicators,
        "country_crosswalk": UnSdgConnector.iso3_to_m49,
        "page_size": UnSdgConnector.page_size,
        "max_pages": UnSdgConnector.max_pages,
        "max_observations": UnSdgConnector.max_observations,
    }


@workflow_router.delete("/sessions/{session_id}", response_model=StoredWorkflowSession)
def delete_session(
    session_id: str, repository: WorkflowRepositoryDependency
) -> StoredWorkflowSession:
    try:
        return repository.set_deleted(session_id, True)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post("/sessions/{session_id}/restore", response_model=StoredWorkflowSession)
def restore_session(
    session_id: str, repository: WorkflowRepositoryDependency
) -> StoredWorkflowSession:
    try:
        return repository.set_deleted(session_id, False)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/import", response_model=StoredWorkflowSession, status_code=status.HTTP_201_CREATED
)
def import_portable_session(
    manager: PortableSessionManagerDependency,
    file: Annotated[UploadFile, File()],
) -> StoredWorkflowSession:
    try:
        return manager.import_archive(file.file.read())
    except PortableSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.get("/sessions/{session_id}/archive")
def export_portable_session(session_id: str, manager: PortableSessionManagerDependency) -> Response:
    try:
        content, _ = manager.export(session_id)
        return Response(
            content,
            media_type="application/vnd.macro-research-session+zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="macro-research-session-{session_id}.mra.zip"'
                )
            },
        )
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/{session_id}/fork",
    response_model=StoredWorkflowSession,
    status_code=status.HTTP_201_CREATED,
)
def fork_completed_session(
    session_id: str,
    body: ForkSessionRequest,
    manager: PortableSessionManagerDependency,
) -> StoredWorkflowSession:
    try:
        return manager.fork(session_id, body.title)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except PortableSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.post(
    "/sessions", response_model=StoredWorkflowSession, status_code=status.HTTP_201_CREATED
)
async def create_session(
    body: CreateWorkflowSessionRequest,
    request: Request,
    repository: WorkflowRepositoryDependency,
    planning_service: WorkflowPlanningServiceDependency,
) -> StoredWorkflowSession:
    try:
        if body.session is not None:
            if request.app.state.settings.environment != "test":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "Full session creation is available only to deterministic test fixtures."
                    ),
                )
            return repository.create(body.session)
        now = datetime.now(timezone.utc)
        session_id = f"workflow-session-{uuid4().hex}"
        request_text = str(body.request)
        title = request_text
        initial_message = {
            "id": f"message-{uuid4().hex}",
            "role": "user",
            "stage": "plan",
            "body": request_text,
            "targetSnapshotHash": "request",
            "commandType": "clarification",
            "createdAt": now.isoformat(),
        }
        document = WorkflowSessionDocument.model_validate(
            {
                "id": session_id,
                "title": title,
                "request": request_text,
                "status": "clarifying",
                "activeStage": "plan",
                "reachedStages": ["plan"],
                "stageHealth": {
                    "plan": "current",
                    "data": "not_reached",
                    "transformation": "not_reached",
                    "output": "not_reached",
                },
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
                "archived": False,
                "nodes": [
                    {
                        "id": f"research-request-{uuid4().hex}",
                        "kind": "research_request",
                        "status": "completed",
                        "inputSnapshotIds": [],
                        "outputSnapshotId": "request",
                        "createdAt": now.isoformat(),
                        "updatedAt": now.isoformat(),
                    }
                ],
                "clarification": {
                    "id": f"clarification-{uuid4().hex}",
                    "round": 0,
                    "questions": [],
                    "answers": {},
                    "submitted": False,
                },
                "planThread": [initial_message],
                "outputThread": [],
                "stageThreads": {
                    "plan": [initial_message],
                    "data": [],
                    "transformation": [],
                    "output": [],
                },
                "handoffs": [],
                "planSnapshots": [],
                "data": {"columns": [], "sourceRuns": [], "snapshots": [], "operations": []},
                "pipeline": {
                    "operations": [],
                    "models": [],
                    "runStatus": "editing",
                    "bundleHistory": [],
                    "editHistory": [],
                },
                "output": {
                    "artifacts": [],
                    "artifactHistory": [],
                    "guidelineVersion": "publication-v1",
                    "workbookTemplateVersion": "research-workbook-v1",
                },
            }
        )
        created = repository.create(document)
        response = await planning_service.execute(
            WorkflowCommandMeta(
                command_id=f"command-{uuid4().hex}",
                idempotency_key=f"create-clarification-{session_id}",
                session_id=session_id,
                expected_stage=WorkflowStage.PLAN,
                expected_snapshot_hash=created.projection.current_snapshot_hash,
                actor="user",
                requested_at=now,
            ),
            {"type": "start_clarification"},
        )
        return StoredWorkflowSession(session=response.session, projection=response.projection)
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Workflow session with this ID already exists.",
        ) from error


@workflow_router.get("/sessions/{session_id}", response_model=StoredWorkflowSession)
def get_session(session_id: str, repository: WorkflowRepositoryDependency) -> StoredWorkflowSession:
    try:
        stored = repository.get(session_id)
        wire = stored.session.model_dump(mode="json", by_alias=True)
        if not wire.get("currentHandoff"):
            record_stage_handoff(wire, stored.session.active_stage, inferred=True)
            stored = StoredWorkflowSession(
                session=WorkflowSessionDocument.model_validate(wire),
                projection=stored.projection,
            )
        return stored
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/nodes", response_model=list[dict[str, Any]])
def list_nodes(session_id: str, repository: WorkflowRepositoryDependency) -> list[dict[str, Any]]:
    try:
        return repository.list_nodes(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/projection", response_model=WorkflowProjection)
def get_projection(session_id: str, repository: WorkflowRepositoryDependency) -> WorkflowProjection:
    try:
        return repository.get(session_id).projection
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/handoffs")
def list_stage_handoffs(
    session_id: str, service: WorkflowHandoffServiceDependency
) -> list[dict[str, Any]]:
    try:
        return service.list(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/{session_id}/handoff/commands", response_model=WorkflowCommandResponse
)
def dispatch_handoff_command(
    session_id: str,
    body: DispatchPlanCommandRequest,
    service: WorkflowHandoffServiceDependency,
) -> WorkflowCommandResponse:
    if body.meta.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Command session ID does not match route session ID.",
        )
    try:
        return service.execute(body.meta, body.command)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from conflict
    except WorkflowHandoffError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@admin_workflow_router.get("/sessions/{session_id}/graph", response_model=GraphSnapshot)
def get_graph(session_id: str, graph_service: WorkflowGraphServiceDependency) -> GraphSnapshot:
    try:
        return graph_service.snapshot(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except GraphInvariantError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workflow_graph_invalid", "message": str(error)},
        ) from error


@admin_workflow_router.get(
    "/sessions/{session_id}/graph/nodes/{node_id}", response_model=ResearchNode
)
def get_graph_node(
    session_id: str, node_id: str, repository: WorkflowRepositoryDependency
) -> ResearchNode:
    try:
        return repository.get_graph_node(session_id, node_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(f"{session_id}/{node_id}") from error


@admin_workflow_router.get(
    "/sessions/{session_id}/graph/attempts", response_model=list[NodeAttempt]
)
def list_graph_attempts(
    session_id: str, repository: WorkflowRepositoryDependency
) -> list[NodeAttempt]:
    try:
        return repository.list_graph_attempts(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/plan/snapshots")
def list_plan_snapshots(
    session_id: str, repository: WorkflowRepositoryDependency
) -> list[dict[str, Any]]:
    try:
        return repository.list_plan_snapshots(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/{session_id}/plan/commands", response_model=WorkflowCommandResponse
)
async def dispatch_plan_command(
    session_id: str,
    body: DispatchPlanCommandRequest,
    planning: WorkflowPlanningServiceDependency,
) -> WorkflowCommandResponse:
    if body.meta.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Command session ID does not match route session ID.",
        )
    try:
        return await planning.execute(body.meta, body.command)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from conflict
    except (PlanningCommandError, PlanningProviderError, ValueError) as error:
        code = getattr(error, "code", None)
        error_detail: str | dict[str, str] = (
            {"code": code, "message": str(error)} if code else str(error)
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error_detail,
        ) from error


@workflow_router.post("/geographies/resolve", response_model=ControlledGeography)
def resolve_geography(
    body: GeographyResolveRequest, resolver: GeographyResolverDependency
) -> ControlledGeography:
    try:
        return resolver.resolve(body.intent)
    except GeographyNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geography is not present in the controlled registry.",
        ) from error


@workflow_router.get("/sessions/{session_id}/data")
def get_data_workspace(session_id: str, repository: WorkflowRepositoryDependency) -> dict[str, Any]:
    try:
        payload = repository.get(session_id).session.model_dump(mode="json", by_alias=True)
        return cast(dict[str, Any], payload.get("data") or {})
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/data/preview")
def preview_data_workspace(
    session_id: str,
    repository: WorkflowRepositoryDependency,
    manager: DataWorkspaceManagerDependency,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        payload = repository.get(session_id).session.model_dump(mode="json", by_alias=True)
        snapshot_id = str((payload.get("data") or {}).get("activeSnapshotId") or "")
        snapshot = manager.get_snapshot(session_id, snapshot_id)
        return {
            "snapshot_id": snapshot.snapshot_id,
            "offset": offset,
            "limit": limit,
            "total_rows": snapshot.row_count,
            "rows": manager.preview(snapshot, offset, limit),
        }
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except DataWorkspaceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.post(
    "/sessions/{session_id}/data/commands", response_model=WorkflowCommandResponse
)
def dispatch_data_command(
    session_id: str,
    body: DispatchDataCommandRequest,
    data_service: WorkflowDataServiceDependency,
) -> WorkflowCommandResponse:
    if body.meta.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Command session ID does not match route session ID.",
        )
    try:
        return data_service.execute(body.meta, body.command)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from conflict
    except DataWorkspaceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.get("/sessions/{session_id}/pipeline")
def get_pipeline_workspace(
    session_id: str, repository: WorkflowRepositoryDependency
) -> dict[str, Any]:
    try:
        payload = repository.get(session_id).session.model_dump(mode="json", by_alias=True)
        return cast(dict[str, Any], payload.get("pipeline") or {})
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.get("/sessions/{session_id}/pipeline/preview")
def preview_pipeline_workspace(
    session_id: str,
    pipeline_service: WorkflowPipelineServiceDependency,
    operation_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        return pipeline_service.preview(session_id, operation_id, offset, limit)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except (PipelineWorkspaceError, DataWorkspaceError, OutputWorkspaceError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.post(
    "/sessions/{session_id}/pipeline/commands", response_model=WorkflowCommandResponse
)
def dispatch_pipeline_command(
    session_id: str,
    body: DispatchPipelineCommandRequest,
    pipeline_service: WorkflowPipelineServiceDependency,
) -> WorkflowCommandResponse:
    if body.meta.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Command session ID does not match route session ID.",
        )
    try:
        return pipeline_service.execute(body.meta, body.command)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from conflict
    except (PipelineWorkspaceError, DataWorkspaceError, OutputWorkspaceError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.get("/sessions/{session_id}/pipeline/code/{artifact_id}")
def get_pipeline_code(
    session_id: str,
    artifact_id: str,
    pipeline_service: WorkflowPipelineServiceDependency,
) -> dict[str, Any]:
    try:
        return pipeline_service.code_content(session_id, artifact_id)
    except CodeWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@workflow_router.get("/sessions/{session_id}/pipeline/code/{artifact_id}/download")
def download_pipeline_code(
    session_id: str,
    artifact_id: str,
    request: Request,
) -> FileResponse:
    manager = cast(CodeWorkspaceManager, request.app.state.code_workspace_manager)
    try:
        record, path = manager.get(session_id, artifact_id)
    except CodeWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return FileResponse(path, media_type=record.media_type, filename=record.filename)


@workflow_router.get("/sessions/{session_id}/output")
def get_output_workspace(
    session_id: str, repository: WorkflowRepositoryDependency
) -> dict[str, Any]:
    try:
        payload = repository.get(session_id).session.model_dump(mode="json", by_alias=True)
        return cast(dict[str, Any], payload.get("output") or {})
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/{session_id}/output/commands", response_model=WorkflowCommandResponse
)
def dispatch_output_command(
    session_id: str,
    body: DispatchOutputCommandRequest,
    output_service: WorkflowOutputServiceDependency,
) -> WorkflowCommandResponse:
    if body.meta.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Command session ID does not match route session ID.",
        )
    try:
        return output_service.execute(body.meta, body.command)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=detail.model_dump(mode="json")
        ) from conflict
    except OutputWorkspaceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@workflow_router.get("/sessions/{session_id}/output/artifacts/{artifact_id}/download")
def download_output_artifact(session_id: str, artifact_id: str, request: Request) -> FileResponse:
    manager = cast(OutputWorkspaceManager, request.app.state.output_workspace_manager)
    try:
        record, path = manager.get(session_id, artifact_id)
    except OutputWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return FileResponse(path, media_type=record.media_type, filename=record.name)


@workflow_router.get("/sessions/{session_id}/output/artifacts/{artifact_id}")
def preview_output_artifact(session_id: str, artifact_id: str, request: Request) -> dict[str, Any]:
    manager = cast(OutputWorkspaceManager, request.app.state.output_workspace_manager)
    try:
        return manager.preview(session_id, artifact_id)
    except OutputWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@workflow_router.get(
    "/sessions/{session_id}/output/artifacts/{current_artifact_id}/compare/{baseline_artifact_id}",
    response_model=ArtifactComparisonReport,
)
def compare_output_artifacts(
    session_id: str,
    current_artifact_id: str,
    baseline_artifact_id: str,
    request: Request,
    repository: WorkflowRepositoryDependency,
) -> ArtifactComparisonReport:
    manager = cast(OutputWorkspaceManager, request.app.state.output_workspace_manager)
    try:
        stored = repository.get(session_id)
        output = stored.session.model_dump(mode="json", by_alias=True).get("output") or {}
        current_artifacts = list(output.get("artifacts") or [])
        historical_artifacts = [
            item for version in output.get("artifactHistory") or [] for item in version
        ]
        known_artifacts = {
            str(item.get("id")): item for item in [*current_artifacts, *historical_artifacts]
        }
        if (
            current_artifact_id not in known_artifacts
            or baseline_artifact_id not in known_artifacts
        ):
            raise OutputWorkspaceError(
                "Artifact comparison requires two visible session artifacts."
            )
        specifications = dict(output.get("artifactSpecifications") or {})
        baseline_payload = known_artifacts[baseline_artifact_id]
        current_payload = known_artifacts[current_artifact_id]
        return manager.compare(
            session_id,
            baseline_artifact_id,
            current_artifact_id,
            baseline_specification=dict(
                baseline_payload.get("specification")
                or specifications.get(baseline_artifact_id)
                or {}
            ),
            current_specification=dict(
                current_payload.get("specification")
                or specifications.get(current_artifact_id)
                or {}
            ),
        )
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except OutputWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@workflow_router.post(
    "/sessions/{session_id}/data/roundtrip/imports",
    response_model=WorkflowCommandResponse,
)
def import_roundtrip(
    session_id: str,
    data_service: WorkflowDataServiceDependency,
    meta_json: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> WorkflowCommandResponse:
    try:
        meta = WorkflowCommandMeta.model_validate_json(meta_json)
        if meta.session_id != session_id:
            raise DataWorkspaceError("Command session ID does not match route session ID.")
        return data_service.import_roundtrip(
            meta, file.filename or "cleaned.xlsx", file.file.read()
        )
    except (DataWorkspaceError, ValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    except WorkflowConflict as conflict:
        detail = WorkflowConflictDetail(
            message=conflict.message,
            current_stage=conflict.projection.active_stage,
            current_snapshot_hash=conflict.projection.current_snapshot_hash,
            projection=conflict.projection,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from conflict


@workflow_router.get(
    "/sessions/{session_id}/data/roundtrip/packages/{package_id}",
    response_class=FileResponse,
)
def download_roundtrip_package(
    session_id: str,
    package_id: str,
    manager: DataWorkspaceManagerDependency,
) -> FileResponse:
    try:
        package = manager.get_roundtrip_package(session_id, package_id)
        return FileResponse(
            package.path,
            filename=package.filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except DataWorkspaceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@workflow_router.get(
    "/sessions/{session_id}/sources/uploads", response_model=list[UploadedFileRecord]
)
def list_uploads(
    session_id: str, repository: WorkflowRepositoryDependency
) -> list[UploadedFileRecord]:
    try:
        return repository.list_uploads(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error


@workflow_router.post(
    "/sessions/{session_id}/sources/uploads",
    response_model=UploadedFileRecord,
    status_code=status.HTTP_201_CREATED,
)
def upload_source(
    session_id: str,
    repository: WorkflowRepositoryDependency,
    upload_service: WorkflowUploadServiceDependency,
    file: Annotated[UploadFile, File()],
) -> UploadedFileRecord:
    try:
        repository.get(session_id)
        record = upload_service.store(
            session_id,
            file.filename or "upload",
            file.file,
            file.content_type or "application/octet-stream",
        )
        return repository.record_upload(record)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
    except (UploadValidationError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@admin_workflow_router.get("/sessions/{session_id}/trace", response_model=list[TraceEvent])
def get_trace(session_id: str, repository: WorkflowRepositoryDependency) -> list[TraceEvent]:
    try:
        return repository.trace(session_id)
    except WorkflowSessionNotFound as error:
        raise _not_found(session_id) from error
