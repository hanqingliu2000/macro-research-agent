from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from macro_research_agent import __version__
from macro_research_agent.agent.repository import AgentRepository
from macro_research_agent.agent.runtime import AgentRuntime
from macro_research_agent.api.agent_routes import admin_agent_router, agent_router
from macro_research_agent.api.routes import router
from macro_research_agent.api.workflow_routes import admin_workflow_router, workflow_router
from macro_research_agent.capabilities.executor import CapabilityExecutor
from macro_research_agent.capabilities.inventory import (
    GeographyResolveArguments,
    GeographyResolveOutput,
    default_capability_registry,
)
from macro_research_agent.config import Settings
from macro_research_agent.knowledge.data_sources import default_data_source_knowledge
from macro_research_agent.knowledge.planning_source_index import (
    default_planning_source_index,
)
from macro_research_agent.knowledge.source_index import SourceIndexRepository, seed_source_index
from macro_research_agent.skills.inventory import default_skill_registry
from macro_research_agent.trace.writer import JsonlTraceWriter
from macro_research_agent.workflow.capability_audit import WorkflowCapabilityAuditWriter
from macro_research_agent.workflow.code_workspace import CodeWorkspaceManager
from macro_research_agent.workflow.codex_output_reviewer import CodexLocalOutputReviewer
from macro_research_agent.workflow.data_service import WorkflowDataService
from macro_research_agent.workflow.data_workspace import DataWorkspaceManager
from macro_research_agent.workflow.geography import ControlledGeographyResolver
from macro_research_agent.workflow.graph.executor import NodeExecutor
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff_service import WorkflowHandoffService
from macro_research_agent.workflow.model_data_access import WorkflowModelDataAccessService
from macro_research_agent.workflow.model_workspace import ModelWorkspaceManager
from macro_research_agent.workflow.output_review import (
    DeterministicArtifactAuthor,
    DeterministicOutputReviewer,
)
from macro_research_agent.workflow.output_service import WorkflowOutputService
from macro_research_agent.workflow.output_workspace import OutputWorkspaceManager
from macro_research_agent.workflow.pipeline_service import WorkflowPipelineService
from macro_research_agent.workflow.pipeline_workspace import PipelineWorkspaceManager
from macro_research_agent.workflow.planning_adapters import (
    DeepSeekPlanningProvider,
    PlanningProviderError,
)
from macro_research_agent.workflow.planning_provider import DeterministicPlanningProvider
from macro_research_agent.workflow.planning_service import WorkflowPlanningService
from macro_research_agent.workflow.portable_sessions import PortableSessionManager
from macro_research_agent.workflow.reporting import (
    DeepSeekReportAuthor,
    DeterministicReportAuthor,
)
from macro_research_agent.workflow.repository import SQLiteWorkflowRepository
from macro_research_agent.workflow.stage_adapters import DeepSeekStageAssistant
from macro_research_agent.workflow.stage_assistant import DeterministicStageAssistant
from macro_research_agent.workflow.uploads import LocalUploadService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        application.state.agent_runtime.close()

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description="Local-first, review-gated macroeconomic research workspace",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    workflow_root = resolved.runtime_dir / "workflow"
    trace_writer = JsonlTraceWriter(
        lambda session_id: workflow_root / "sessions" / session_id / "trace.jsonl"
    )
    app.state.workflow_repository = SQLiteWorkflowRepository(
        workflow_root / "workflow.sqlite3", trace_writer
    )
    app.state.workflow_graph_service = GraphService(app.state.workflow_repository)
    app.state.node_executor = NodeExecutor(app.state.workflow_graph_service)
    orphan_cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=resolved.graph_orphan_timeout_seconds
    )
    app.state.recovered_orphan_attempts = [
        attempt
        for stored in app.state.workflow_repository.list_sessions()
        for attempt in app.state.workflow_graph_service.recover_orphans(
            stored.session.id, orphan_cutoff, datetime.now(timezone.utc)
        )
    ]
    if resolved.llm_provider not in {"deepseek", "test"}:
        raise PlanningProviderError(
            "The backend planning provider is locked to DeepSeek; "
            f"unsupported provider: {resolved.llm_provider}."
        )
    if resolved.llm_provider == "test" or (
        resolved.environment == "test" and not resolved.deepseek_api_key
    ):
        # Offline fake for automated tests only. It is neither selectable nor
        # reported by the public capability contract.
        app.state.planning_provider = DeterministicPlanningProvider()
    else:
        if not resolved.deepseek_api_key:
            raise PlanningProviderError(
                "DeepSeek planning requires DEEPSEEK_API_KEY; "
                "the deterministic fallback is disabled."
            )
        app.state.planning_provider = DeepSeekPlanningProvider(
            api_key=resolved.deepseek_api_key,
            model_id=resolved.deepseek_model,
            endpoint=resolved.deepseek_endpoint,
            max_attempts=resolved.planning_max_attempts,
            timeout_seconds=resolved.planning_timeout_seconds,
            max_data_rows=resolved.planning_max_data_rows,
            max_prompt_chars=resolved.planning_max_prompt_chars,
            max_output_tokens=resolved.planning_max_output_tokens,
        )
    app.state.geography_resolver = ControlledGeographyResolver()
    app.state.capability_registry = default_capability_registry(codex_local_visual_review=True)
    app.state.data_source_knowledge = default_data_source_knowledge()
    app.state.planning_source_index = default_planning_source_index()
    app.state.agent_runtime = AgentRuntime(
        AgentRepository(resolved.runtime_dir / "agent"),
        resolved,
        app.state.capability_registry,
        app.state.planning_source_index,
        autorun=resolved.environment != "test",
    )
    app.state.source_index = SourceIndexRepository(workflow_root / "source_index.sqlite3")
    seed_source_index(app.state.source_index, app.state.data_source_knowledge)

    def resolve_geography(arguments: BaseModel) -> dict[str, object]:
        parsed = GeographyResolveArguments.model_validate(arguments)
        result = app.state.geography_resolver.resolve(parsed.intent)
        return {
            **result.model_dump(mode="json"),
            "result_refs": [f"geography:{result.geography_id}@{result.registry_version}"],
        }

    app.state.capability_registry.bind(
        "geography.resolve",
        "1.0.0",
        GeographyResolveArguments,
        GeographyResolveOutput,
        resolve_geography,
    )
    app.state.skill_registry = default_skill_registry(app.state.capability_registry)

    app.state.capability_executor = CapabilityExecutor(
        app.state.capability_registry,
        WorkflowCapabilityAuditWriter(
            app.state.workflow_repository, app.state.workflow_graph_service
        ),
        app.state.skill_registry,
        lambda intent, policy: any(
            checkpoint.checkpoint_id == intent.checkpoint_ref
            and checkpoint.gate.value == policy.value
            and checkpoint.target_hash == intent.target_snapshot_hash
            and checkpoint.revoked_at is None
            for checkpoint in app.state.workflow_repository.graph_snapshot(
                intent.session_id
            ).checkpoints
        ),
    )
    app.state.data_workspace_manager = DataWorkspaceManager(
        workflow_root / "workflow.sqlite3", workflow_root
    )
    app.state.model_data_access_service = WorkflowModelDataAccessService(
        app.state.workflow_repository,
        app.state.data_workspace_manager,
        enabled=resolved.ai_data_access_enabled,
        page_size=resolved.ai_data_page_size,
        remote_user_data_allowed=resolved.ai_remote_user_data_allowed,
        remote_licensed_data_allowed=resolved.ai_remote_licensed_data_allowed,
    )
    if resolved.environment == "test" or resolved.llm_provider == "test":
        app.state.data_stage_assistant = DeterministicStageAssistant()
        app.state.analysis_stage_assistant = DeterministicStageAssistant()
    else:
        app.state.data_stage_assistant = DeepSeekStageAssistant(
            role="data",
            api_key=resolved.deepseek_api_key,
            model_id=resolved.data_ai_model or resolved.deepseek_model,
            endpoint=resolved.deepseek_endpoint,
            max_attempts=resolved.stage_ai_max_attempts,
            timeout_seconds=resolved.stage_ai_timeout_seconds,
            max_prompt_chars=resolved.stage_ai_max_prompt_chars,
            max_output_tokens=resolved.stage_ai_max_output_tokens,
        )
        app.state.analysis_stage_assistant = DeepSeekStageAssistant(
            role="analysis",
            api_key=resolved.deepseek_api_key,
            model_id=resolved.analysis_ai_model or resolved.deepseek_model,
            endpoint=resolved.deepseek_endpoint,
            max_attempts=resolved.stage_ai_max_attempts,
            timeout_seconds=resolved.stage_ai_timeout_seconds,
            max_prompt_chars=resolved.stage_ai_max_prompt_chars,
            max_output_tokens=resolved.stage_ai_max_output_tokens,
        )
    # Compatibility handle for integrations that inspect the former shared port.
    app.state.stage_assistant = app.state.data_stage_assistant
    app.state.workflow_data_service = WorkflowDataService(
        app.state.workflow_repository,
        app.state.workflow_graph_service,
        app.state.data_workspace_manager,
        app.state.data_stage_assistant,
        app.state.model_data_access_service,
        app.state.capability_registry,
    )
    app.state.pipeline_workspace_manager = PipelineWorkspaceManager(
        workflow_root / "workflow.sqlite3", app.state.data_workspace_manager
    )
    app.state.model_workspace_manager = ModelWorkspaceManager(
        workflow_root / "workflow.sqlite3", app.state.data_workspace_manager
    )
    app.state.code_workspace_manager = CodeWorkspaceManager(
        workflow_root / "workflow.sqlite3", workflow_root
    )
    if resolved.environment == "test" or resolved.llm_provider == "test":
        app.state.artifact_author = DeterministicArtifactAuthor()
    else:
        from macro_research_agent.workflow.chart_author import DeepSeekChartAuthor

        app.state.artifact_author = DeepSeekChartAuthor(
            api_key=resolved.deepseek_api_key,
            model_id=resolved.deepseek_model,
            endpoint=resolved.deepseek_endpoint,
            timeout_seconds=resolved.stage_ai_timeout_seconds,
            max_prompt_chars=resolved.stage_ai_max_prompt_chars,
            max_data_rows=resolved.report_author_max_data_rows,
        )
    if resolved.environment == "test":
        # Network-free structural fake for automated tests only. It cannot be
        # selected by production configuration and is never advertised by the
        # public runtime contract.
        app.state.output_reviewer = DeterministicOutputReviewer()
    else:
        app.state.output_reviewer = CodexLocalOutputReviewer(
            working_root=workflow_root / ".codex-output-review",
            model_id=resolved.output_review_model,
            codex_bin=resolved.output_review_codex_bin,
            timeout_seconds=resolved.output_review_timeout_seconds,
        )
    if resolved.environment == "test" or resolved.llm_provider == "test":
        app.state.report_author = DeterministicReportAuthor()
    else:
        app.state.report_author = DeepSeekReportAuthor(
            api_key=resolved.deepseek_api_key,
            model_id=resolved.report_author_model or resolved.deepseek_model,
            endpoint=resolved.deepseek_endpoint,
            repository=app.state.workflow_repository,
            max_attempts=resolved.stage_ai_max_attempts,
            timeout_seconds=resolved.stage_ai_timeout_seconds,
            max_prompt_chars=resolved.stage_ai_max_prompt_chars,
            max_output_tokens=resolved.report_author_max_output_tokens,
            max_data_rows=resolved.report_author_max_data_rows,
        )
    app.state.output_workspace_manager = OutputWorkspaceManager(
        workflow_root / "workflow.sqlite3",
        workflow_root,
        app.state.data_workspace_manager,
        app.state.code_workspace_manager,
        app.state.artifact_author,
        app.state.model_data_access_service,
        report_author=app.state.report_author,
        capability_receipt_provider=lambda session_id: [
            event.payload
            for event in app.state.workflow_repository.trace(session_id)
            if event.event_type.startswith("capability.invocation_")
        ],
    )
    app.state.workflow_pipeline_service = WorkflowPipelineService(
        app.state.workflow_repository,
        app.state.workflow_graph_service,
        app.state.pipeline_workspace_manager,
        app.state.model_workspace_manager,
        app.state.code_workspace_manager,
        app.state.output_workspace_manager,
        app.state.analysis_stage_assistant,
        app.state.model_data_access_service,
        app.state.capability_registry,
    )
    app.state.workflow_output_service = WorkflowOutputService(
        app.state.workflow_repository,
        app.state.workflow_graph_service,
        app.state.output_workspace_manager,
        app.state.artifact_author,
        app.state.output_reviewer,
        app.state.model_data_access_service,
    )
    app.state.workflow_planning_service = WorkflowPlanningService(
        app.state.workflow_repository,
        app.state.workflow_graph_service,
        app.state.planning_provider,
        app.state.workflow_data_service,
        app.state.model_data_access_service,
        app.state.capability_registry,
        app.state.planning_source_index,
    )
    app.state.workflow_handoff_service = WorkflowHandoffService(
        app.state.workflow_repository,
        app.state.workflow_graph_service,
    )
    app.state.workflow_upload_service = LocalUploadService(workflow_root, resolved.max_upload_mb)
    app.state.portable_session_manager = PortableSessionManager(
        workflow_root / "workflow.sqlite3",
        workflow_root,
        app.state.workflow_repository,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(workflow_router, prefix="/api/v1")
    app.include_router(admin_workflow_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(admin_agent_router, prefix="/api/v1")
    return app
