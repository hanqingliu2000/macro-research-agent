from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.api_schemas import (
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.code_workspace import CodeWorkspaceManager
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff import (
    AgentRuntimeDescriptor,
    HandoffIncompleteError,
    append_stage_message,
    record_stage_handoff,
    relevant_handoff,
)
from macro_research_agent.workflow.model_data_access import WorkflowModelDataAccessService
from macro_research_agent.workflow.model_workspace import (
    SUPPORTED_MODELS,
    ModelWorkspaceError,
    ModelWorkspaceManager,
)
from macro_research_agent.workflow.output_workspace import (
    OutputWorkspaceError,
    OutputWorkspaceManager,
)
from macro_research_agent.workflow.pipeline_draft import (
    default_model_parameters,
    default_transformation_parameters,
)
from macro_research_agent.workflow.pipeline_workspace import (
    SUPPORTED_TRANSFORMATIONS,
    TRANSFORMATION_LABELS,
    PipelineWorkspaceError,
    PipelineWorkspaceManager,
)
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.stage_adapters import StageProviderError
from macro_research_agent.workflow.stage_assistant import (
    AnalysisAssistantContext,
    StageAssistantPort,
    assistant_state_hash,
    read_all_dataset_rows,
    validate_analysis_proposal_constraints,
)
from macro_research_agent.workflow.states import SessionState, WorkflowStage


class WorkflowPipelineService:
    allowed_commands = {
        "add_pipeline_operation",
        "move_pipeline_operation",
        "toggle_pipeline_operation",
        "delete_pipeline_operation",
        "undo_pipeline_edit",
        "select_pipeline_operation",
        "update_pipeline_target",
        "update_pipeline_parameters",
        "add_model_job",
        "update_model_input",
        "update_model_specification",
        "delete_model_job",
        "start_pipeline_revision",
        "run_pipeline",
        "retry_output_generation",
        "propose_analysis_assistance",
        "apply_analysis_assistance",
        "reject_analysis_assistance",
    }

    def __init__(
        self,
        repository: WorkflowRepository,
        graph_service: GraphService,
        manager: PipelineWorkspaceManager,
        model_manager: ModelWorkspaceManager,
        code_manager: CodeWorkspaceManager,
        output_manager: OutputWorkspaceManager,
        assistant: StageAssistantPort | None = None,
        model_data_access: WorkflowModelDataAccessService | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.manager = manager
        self.model_manager = model_manager
        self.code_manager = code_manager
        self.output_manager = output_manager
        self.assistant = assistant
        self.model_data_access = model_data_access
        self.capability_registry = capability_registry

    @staticmethod
    def _identifier(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex}"

    @staticmethod
    def _default_parameters(kind: str) -> dict[str, Any]:
        return default_transformation_parameters(kind)

    @staticmethod
    def _edit_snapshot(pipeline: dict[str, Any]) -> dict[str, Any]:
        return {
            "operations": deepcopy(pipeline.get("operations") or []),
            "models": deepcopy(pipeline.get("models") or []),
            "selectedOperationId": pipeline.get("selectedOperationId"),
        }

    @staticmethod
    def _archive_current_analysis(pipeline: dict[str, Any]) -> None:
        prior_bundle = pipeline.get("bundle")
        if prior_bundle:
            pipeline["bundleHistory"] = [
                *(pipeline.get("bundleHistory") or []),
                prior_bundle,
            ]
        prior_results = list(pipeline.get("modelResults") or [])
        if prior_results:
            pipeline["modelResultHistory"] = [
                *(pipeline.get("modelResultHistory") or []),
                *prior_results,
            ]
        pipeline.pop("bundle", None)
        pipeline["modelResults"] = []
        prior_code = list(pipeline.get("codeArtifacts") or [])
        if prior_code:
            pipeline["codeArtifactHistory"] = [
                *(pipeline.get("codeArtifactHistory") or []),
                *prior_code,
            ]
        pipeline["codeArtifacts"] = []

    def _begin_edit(self, session: dict[str, Any]) -> dict[str, Any]:
        pipeline = dict(session.get("pipeline") or {})
        history = list(pipeline.get("editHistory") or [])
        history.append(self._edit_snapshot(pipeline))
        pipeline["editHistory"] = history
        self._archive_current_analysis(pipeline)
        pipeline["runStatus"] = "editing"
        pipeline.pop("lastValidationError", None)
        pipeline["operations"] = [
            {**operation, "status": "not_run"} for operation in pipeline.get("operations") or []
        ]
        pipeline["models"] = [
            {**model, "status": "not_run"} for model in pipeline.get("models") or []
        ]
        session["pipeline"] = pipeline
        session["status"] = "pipeline_editing"
        session["activeStage"] = "transformation"
        session["stageHealth"] = {
            **session.get("stageHealth", {}),
            "transformation": "current",
            **({"output": "stale"} if "output" in session.get("reachedStages", []) else {}),
        }
        output = dict(session.get("output") or {})
        current_artifacts = list(output.get("artifacts") or [])
        if current_artifacts and any(item.get("status") != "stale" for item in current_artifacts):
            specifications = dict(output.get("artifactSpecifications") or {})
            stale_artifacts = [
                {
                    **item,
                    "status": "stale",
                    "specification": dict(specifications.get(str(item.get("id"))) or {}),
                }
                for item in current_artifacts
            ]
            output["artifactHistory"] = [
                *(output.get("artifactHistory") or []),
                stale_artifacts,
            ]
            output["artifacts"] = stale_artifacts
            output.pop("finalizedAt", None)
            output.pop("manifestArtifactId", None)
            session["output"] = output
        self._stale_analysis_nodes(session)
        self._stale_output_nodes(session)
        return pipeline

    @staticmethod
    def _stale_analysis_nodes(session: dict[str, Any]) -> None:
        for node in session.get("nodes") or []:
            if node.get("kind") in {
                "transformation_pipeline",
                "model_execution",
            } and node.get("status") not in {"pending", "stale"}:
                node["status"] = "stale"
                node["staleReason"] = "The reviewed pipeline or model specification changed."
                node["updatedAt"] = session["updatedAt"]

    @staticmethod
    def _stale_output_nodes(session: dict[str, Any]) -> None:
        for node in session.get("nodes") or []:
            if node.get("kind") in {
                "output_generation",
                "output_revision",
                "output_compliance_review",
                "visual_artifact_review",
                "semantic_report_review",
                "reproduction_manifest",
            } and node.get("status") not in {"pending", "stale"}:
                node["status"] = "stale"
                node["staleReason"] = "The transformation pipeline changed."
                node["updatedAt"] = session["updatedAt"]

    @staticmethod
    def _relink(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        input_ref = "active_dataset"
        linked: list[dict[str, Any]] = []
        for operation in operations:
            output_ref = f"step:{operation['id']}"
            linked.append(
                {
                    **operation,
                    "inputRef": input_ref,
                    "outputRef": output_ref,
                    "target": {
                        **(operation.get("target") or {}),
                        "inputRef": input_ref,
                    },
                }
            )
            input_ref = output_ref
        return linked

    @staticmethod
    def _validate_model_inputs(
        operations: list[dict[str, Any]], models: list[dict[str, Any]]
    ) -> None:
        allowed = {"active_dataset", *[str(item["outputRef"]) for item in operations]}
        invalid = [
            str(model.get("label") or model.get("id") or "Model")
            for model in models
            if str(model.get("inputRef") or "") not in allowed
        ]
        if invalid:
            raise PipelineWorkspaceError(
                "Model input references a deleted pipeline output: " + ", ".join(invalid)
            )

    @staticmethod
    def _rebind_models_after_delete(
        pipeline: dict[str, Any], deleted_index: int, operations: list[dict[str, Any]]
    ) -> None:
        models = list(pipeline.get("models") or [])
        allowed = {"active_dataset", *[str(item["outputRef"]) for item in operations]}
        fallback = (
            str(operations[deleted_index - 1]["outputRef"])
            if deleted_index > 0 and operations
            else "active_dataset"
        )
        rebound: list[str] = []
        for model in models:
            if str(model.get("inputRef") or "") in allowed:
                continue
            rebound.append(str(model.get("label") or model.get("id") or "Model"))
            model["inputRef"] = fallback
        pipeline["models"] = models
        if rebound:
            pipeline["lastBindingNotice"] = (
                f"Rebound {', '.join(rebound)} to {fallback} because its input operation "
                "was deleted."
            )
        else:
            pipeline.pop("lastBindingNotice", None)

    def _dispatch(
        self,
        meta: WorkflowCommandMeta,
        command: dict[str, Any],
        session: dict[str, Any],
    ) -> WorkflowCommandResponse:
        document = WorkflowSessionDocument.model_validate(session)
        return self.graph_service.apply_transition(meta, command, document)

    def _generate_output(
        self,
        meta: WorkflowCommandMeta,
        command: dict[str, Any],
        session: dict[str, Any],
        pipeline: dict[str, Any],
    ) -> WorkflowCommandResponse:
        bundle = dict(pipeline.get("bundle") or {})
        bundle_id = str(bundle.get("id") or "")
        prior_generation = dict(pipeline.get("outputGeneration") or {})
        attempt = int(prior_generation.get("attempt") or 0) + 1
        try:
            output = self.output_manager.generate(meta.session_id, session)
        except OutputWorkspaceError as error:
            pipeline["outputGeneration"] = {
                "status": "failed",
                "attempt": attempt,
                "bundleId": bundle_id,
                "retryable": error.retryable,
                "lastAttemptAt": str(session["updatedAt"]).replace("+00:00", "Z"),
                "error": {
                    "code": error.code,
                    "message": str(error),
                    "issues": error.issues,
                },
            }
            session["pipeline"] = pipeline
            session["output"] = {
                "artifacts": [],
                "artifactHistory": [],
                "guidelineVersion": "publication-v1",
                "workbookTemplateVersion": "research-workbook-v1",
                **dict(session.get("output") or {}),
            }
            session["status"] = "failed"
            session["activeStage"] = "output"
            session["reachedStages"] = list(
                dict.fromkeys([*(session.get("reachedStages") or []), "output"])
            )
            session["stageHealth"] = {
                **session.get("stageHealth", {}),
                "transformation": "completed",
                "output": "current",
            }
            self._update_node(
                session,
                "output_generation",
                "failed",
                f"output-generation-failed:{bundle_id}:{attempt}",
                [bundle_id],
                error_code=error.code,
                attempt=attempt,
            )
            append_stage_message(
                session,
                WorkflowStage.OUTPUT,
                "agent",
                "Analysis results were preserved, but Output generation needs attention. "
                "Retrying will regenerate Output only and will not rerun the analysis.",
                target_hash=bundle_id,
                command_type="report_authoring",
                label="Output Author",
            )
            session["lastNotice"] = (
                "Analysis completed. Output generation needs attention; the analytical bundle "
                "is preserved and can be retried without rerunning models."
            )
            self.repository.record_trace_event(
                meta.session_id,
                "output.generation_failed",
                Actor.AGENT,
                {
                    "bundle_id": bundle_id,
                    "attempt": attempt,
                    "error_code": error.code,
                    "issues": error.issues,
                    "retryable": error.retryable,
                    "provider_profile": (
                        self.output_manager.report_author.provider_profile
                        if self.output_manager.report_author
                        else "unavailable"
                    ),
                    "model_id": (
                        self.output_manager.report_author.model_id
                        if self.output_manager.report_author
                        else "unavailable"
                    ),
                },
            )
            return self._dispatch(meta, command, session)

        prior_output = dict(session.get("output") or {})
        prior_specifications = dict(prior_output.get("artifactSpecifications") or {})
        prior_artifacts = [
            {
                **item,
                "specification": dict(prior_specifications.get(str(item.get("id"))) or {}),
            }
            for item in prior_output.get("artifacts") or []
        ]
        if prior_artifacts and any(item.get("status") != "stale" for item in prior_artifacts):
            output["artifactHistory"] = [
                *(prior_output.get("artifactHistory") or []),
                [{**artifact, "status": "stale"} for artifact in prior_artifacts],
            ]
        pipeline["outputGeneration"] = {
            "status": "completed",
            "attempt": attempt,
            "bundleId": bundle_id,
            "artifactSetId": str(output["artifactSetId"]),
            "completedAt": str(session["updatedAt"]).replace("+00:00", "Z"),
            "retryable": False,
        }
        session["pipeline"] = pipeline
        session["output"] = output
        session["status"] = "output_review"
        session["activeStage"] = "output"
        session["reachedStages"] = list(
            dict.fromkeys([*(session.get("reachedStages") or []), "output"])
        )
        session["stageHealth"] = {
            **session.get("stageHealth", {}),
            "transformation": "completed",
            "output": "current",
        }
        self._update_node(
            session,
            "output_generation",
            "waiting_for_review",
            str(output["artifactSetId"]),
            [bundle_id],
            attempt=attempt,
        )
        record_stage_handoff(
            session,
            WorkflowStage.OUTPUT,
            agents=[
                AgentRuntimeDescriptor(
                    role="report_author",
                    authority="author",
                    provider_profile=(
                        self.output_manager.report_author.provider_profile
                        if self.output_manager.report_author
                        else "unavailable"
                    ),
                    model_id=(
                        self.output_manager.report_author.model_id
                        if self.output_manager.report_author
                        else "unavailable"
                    ),
                    status="available" if self.output_manager.report_author else "unavailable",
                    limitations=[
                        "May author evidence-bound report sections; cannot alter data, "
                        "analysis, approvals or frozen outputs."
                    ],
                )
            ],
        )
        if output.get("reportDrafts"):
            append_stage_message(
                session,
                WorkflowStage.OUTPUT,
                "agent",
                "Created an evidence-bound Research Report draft for independent review.",
                target_hash=str(output.get("artifactSetHash") or ""),
                command_type="report_authoring",
                label="Report Author",
            )
        has_model_failures = any(
            item.get("status") == "failed" for item in pipeline.get("models") or []
        )
        session["lastNotice"] = (
            "Analysis completed with partial model failures; successful results and governed "
            "artifacts are ready for review."
            if has_model_failures
            else "Registered analysis completed and governed artifacts are ready for review."
        )
        return self._dispatch(meta, command, session)

    def execute(
        self,
        meta: WorkflowCommandMeta,
        command: dict[str, Any],
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        command_type = str(command.get("type") or "")
        if command_type not in self.allowed_commands:
            raise PipelineWorkspaceError("Command is not allowed in the Pipeline domain.")
        stored = self.repository.require_current(meta)
        if stored.session.status == SessionState.COMPLETED:
            raise PipelineWorkspaceError(
                "Completed Workflow sessions are read-only. "
                "Continue or fork the session to revise it."
            )
        session = stored.session.model_dump(mode="json", by_alias=True)
        if session.get("activeStage") not in {"transformation", "output"}:
            raise PipelineWorkspaceError(
                "Pipeline commands require a reached Transformation stage."
            )
        if not (session.get("data") or {}).get("approvedSnapshotId"):
            raise PipelineWorkspaceError("Approve the active dataset before editing the pipeline.")
        session["updatedAt"] = datetime.now(timezone.utc).isoformat()
        pipeline = dict(session.get("pipeline") or {})
        operations: list[dict[str, Any]] = list(pipeline.get("operations") or [])

        if command_type == "retry_output_generation":
            generation = dict(pipeline.get("outputGeneration") or {})
            if meta.actor != "user":
                raise PipelineWorkspaceError("Only a user may retry Output generation.")
            if (
                pipeline.get("runStatus") != "completed"
                or not pipeline.get("bundle")
                or generation.get("status") != "failed"
            ):
                raise PipelineWorkspaceError(
                    "Output generation can be retried only after a preserved analysis run fails."
                )
            if not generation.get("retryable"):
                raise PipelineWorkspaceError(
                    "This Output generation error requires an upstream analysis revision."
                )
            return self._generate_output(meta, command, session, pipeline)

        if session.get("activeStage") == "output":
            if command_type == "start_pipeline_revision":
                if pipeline.get("runStatus") != "completed":
                    raise PipelineWorkspaceError(
                        "The analytical pipeline is already being revised."
                    )
                self._begin_edit(session)
                session["lastNotice"] = (
                    "Analysis revision started. Previous Output is stale and preserved in history; "
                    "review the changes and run the updated analysis."
                )
                return self._dispatch(meta, command, session)
            if command_type != "select_pipeline_operation":
                raise PipelineWorkspaceError(
                    "Completed analysis is read-only. Start an analysis revision before editing."
                )
        elif command_type == "start_pipeline_revision":
            raise PipelineWorkspaceError(
                "An analysis revision can start only from the current Output stage."
            )

        if command_type == "propose_analysis_assistance":
            if self.assistant is None or self.model_data_access is None:
                raise PipelineWorkspaceError("The Analysis assistant is unavailable.")
            approved_id = str(session["data"]["approvedSnapshotId"])
            target_hash = self._assistant_target_hash(session)
            request = str(command.get("request") or "Propose a suitable registered analysis.")
            try:
                handoff = relevant_handoff(session, WorkflowStage.TRANSFORMATION)
            except HandoffIncompleteError as error:
                raise PipelineWorkspaceError(f"[handoff_incomplete] {error}") from error
            context = AnalysisAssistantContext(
                request=request,
                plan=dict(session.get("currentPlan") or {}),
                pipeline=pipeline,
                dataset=self.model_data_access.context_for_snapshot(
                    meta.session_id,
                    approved_id,
                    WorkflowStage.TRANSFORMATION,
                    for_remote_provider=self.assistant.remote_data_disclosure,
                    provider_profile=self.assistant.provider_profile,
                    model_id=self.assistant.model_id,
                ),
                capability_catalog=(
                    [item.model_dump(mode="json") for item in self.capability_registry.list()]
                    if self.capability_registry is not None
                    else []
                ),
                handoff=handoff,
                recent_messages=list(
                    ((session.get("stageThreads") or {}).get("transformation") or [])[-10:]
                ),
            )
            try:
                assistant_output = self.assistant.propose_analysis(
                    request, context, self.model_data_access
                )
                validate_analysis_proposal_constraints(
                    request,
                    read_all_dataset_rows(context.dataset, self.model_data_access),
                    assistant_output,
                    context.pipeline,
                )
            except StageProviderError as error:
                self.repository.record_trace_event(
                    meta.session_id,
                    "ai.analysis_assistance_failed",
                    Actor.AGENT,
                    {
                        "provider_profile": self.assistant.provider_profile,
                        "model_id": self.assistant.model_id,
                        "error_code": error.code,
                        "target_state_hash": target_hash,
                    },
                )
                raise PipelineWorkspaceError(f"[{error.code}] {error}") from error
            except ValueError as error:
                raise PipelineWorkspaceError(str(error)) from error
            proposal_id = self._identifier("analysis-assistant")
            pipeline["pendingAssistantProposal"] = {
                "id": proposal_id,
                "request": request,
                "summary": assistant_output.summary,
                "operations": [
                    {
                        "id": item.proposal_item_id,
                        "operation": item.operation,
                        "parameters": item.parameters,
                        "indicators": item.indicators,
                        "entities": item.entities,
                        "fields": item.fields,
                        "rationale": item.rationale,
                    }
                    for item in assistant_output.operations
                ],
                "models": [
                    {
                        "id": item.proposal_item_id,
                        "model": item.model,
                        "variables": item.variables,
                        "dependentVariables": item.dependent_variables,
                        "independentVariables": item.independent_variables,
                        "parameters": item.parameters,
                        "rationale": item.rationale,
                    }
                    for item in assistant_output.models
                ],
                "modelRemovals": [
                    {
                        "id": item.proposal_item_id,
                        "modelJobId": item.model_job_id,
                        "label": item.label,
                        "rationale": item.rationale,
                    }
                    for item in assistant_output.model_removals
                ],
                "targetStateHash": target_hash,
                "targetSnapshotId": approved_id,
                "agent": {
                    "role": "analyst",
                    "authority": "propose",
                    "providerProfile": self.assistant.provider_profile,
                    "modelId": self.assistant.model_id,
                    "status": "available",
                },
            }
            append_stage_message(
                session,
                WorkflowStage.TRANSFORMATION,
                "user",
                request,
                target_hash=target_hash,
                command_type="analysis_assistance",
                label="Analysis request",
            )
            append_stage_message(
                session,
                WorkflowStage.TRANSFORMATION,
                "agent",
                assistant_output.summary,
                target_hash=target_hash,
                command_type="analysis_assistance",
                label="Analyst proposal",
            )
            session["pipeline"] = pipeline
            self._append_proposal_node(session, proposal_id, target_hash, "transformation_pipeline")
            self.repository.record_trace_event(
                meta.session_id,
                "ai.analysis_assistance_completed",
                Actor.AGENT,
                {
                    "provider_profile": self.assistant.provider_profile,
                    "model_id": self.assistant.model_id,
                    "target_state_hash": target_hash,
                    "proposal_id": proposal_id,
                    "item_count": (
                        len(assistant_output.operations)
                        + len(assistant_output.models)
                        + len(assistant_output.model_removals)
                    ),
                },
            )
            return self._dispatch(meta, command, session)

        if command_type in {"apply_analysis_assistance", "reject_analysis_assistance"}:
            pending = dict(pipeline.get("pendingAssistantProposal") or {})
            if not pending:
                raise PipelineWorkspaceError("There is no pending Analysis assistant proposal.")
            if pending.get("targetStateHash") != self._assistant_target_hash(session):
                raise PipelineWorkspaceError(
                    "The Pipeline changed after this proposal was created. Request a new proposal."
                )
            if command_type == "reject_analysis_assistance":
                self._close_proposal_node(session, str(pending["id"]), applied=False)
                pipeline.pop("pendingAssistantProposal", None)
                append_stage_message(
                    session,
                    WorkflowStage.TRANSFORMATION,
                    "system",
                    "The Analyst proposal was rejected. No pipeline change was applied.",
                    target_hash=str(pending.get("targetStateHash") or ""),
                    command_type="analysis_assistance",
                    label="Decision",
                )
                session["pipeline"] = pipeline
                return self._dispatch(meta, command, session)
            items = [
                *list(pending.get("operations") or []),
                *list(pending.get("models") or []),
                *list(pending.get("modelRemovals") or []),
            ]
            available = {str(item.get("id")) for item in items}
            selected = {str(value) for value in command.get("acceptedItemIds") or []}
            if not selected or not selected.issubset(available):
                raise PipelineWorkspaceError("Select at least one valid Analysis proposal item.")
            pipeline = self._begin_edit(session)
            operations = list(pipeline.get("operations") or [])
            models = list(pipeline.get("models") or [])
            removal_ids = {
                str(item.get("modelJobId"))
                for item in pending.get("modelRemovals") or []
                if str(item.get("id")) in selected
            }
            if removal_ids:
                existing_ids = {str(model.get("id")) for model in models}
                if not removal_ids.issubset(existing_ids):
                    raise PipelineWorkspaceError(
                        "A model selected for replacement no longer exists. Request a new proposal."
                    )
                models = [model for model in models if str(model.get("id")) not in removal_ids]
            for item in pending.get("operations") or []:
                if str(item.get("id")) not in selected:
                    continue
                kind = str(item.get("operation") or "")
                if kind not in SUPPORTED_TRANSFORMATIONS:
                    raise PipelineWorkspaceError("The proposed transformation is unavailable.")
                operation_id = self._identifier("pipeline-operation")
                input_ref = operations[-1]["outputRef"] if operations else "active_dataset"
                operations.append(
                    {
                        "id": operation_id,
                        "kind": kind,
                        "label": TRANSFORMATION_LABELS[kind],
                        "enabled": True,
                        "target": {
                            "inputRef": input_ref,
                            "indicators": list(item.get("indicators") or []),
                            "entities": list(item.get("entities") or []),
                            "fields": list(item.get("fields") or ["value"]),
                        },
                        "parameters": {
                            **self._default_parameters(kind),
                            **dict(item.get("parameters") or {}),
                        },
                        "inputRef": input_ref,
                        "outputRef": f"step:{operation_id}",
                        "status": "not_run",
                    }
                )
            pipeline["operations"] = operations
            for item in pending.get("models") or []:
                if str(item.get("id")) not in selected:
                    continue
                kind = str(item.get("model") or "")
                if kind not in SUPPORTED_MODELS:
                    raise PipelineWorkspaceError("The proposed model is unavailable.")
                models.append(
                    {
                        "id": self._identifier("model-job"),
                        "kind": kind,
                        "label": f"{kind.upper()} model",
                        "inputRef": operations[-1]["outputRef"] if operations else "active_dataset",
                        "variables": list(item.get("variables") or []),
                        "dependentVariables": list(item.get("dependentVariables") or []),
                        "independentVariables": list(item.get("independentVariables") or []),
                        "parameters": {
                            **default_model_parameters(kind),
                            **dict(item.get("parameters") or {}),
                        },
                        "status": "not_run",
                    }
                )
            pipeline["models"] = models
            self.manager.validate_pipeline(operations)
            for model in models:
                self.model_manager.validate_job(model)
            pipeline.pop("pendingAssistantProposal", None)
            self._close_proposal_node(session, str(pending["id"]), applied=True)
            append_stage_message(
                session,
                WorkflowStage.TRANSFORMATION,
                "system",
                f"Applied {len(selected)} confirmed Analysis proposal item(s).",
                target_hash=str(pending.get("targetStateHash") or ""),
                command_type="analysis_assistance",
                label="Confirmed decision",
            )
            session["pipeline"] = pipeline
            return self._dispatch(meta, command, session)

        if command_type == "select_pipeline_operation":
            operation_id = str(command.get("operationId") or "")
            if operation_id not in {str(item.get("id")) for item in operations}:
                raise PipelineWorkspaceError("Unknown pipeline operation.")
            pipeline["selectedOperationId"] = operation_id
            session["pipeline"] = pipeline
            return self._dispatch(meta, command, session)

        if command_type == "undo_pipeline_edit":
            history = list(pipeline.get("editHistory") or [])
            if not history:
                raise PipelineWorkspaceError("There is no pipeline edit to undo.")
            previous = history.pop()
            self._archive_current_analysis(pipeline)
            pipeline.update(previous)
            pipeline["editHistory"] = history
            pipeline["runStatus"] = "editing"
            pipeline.pop("bundle", None)
            pipeline.pop("lastValidationError", None)
            self.manager.validate_pipeline(list(pipeline.get("operations") or []))
            session["pipeline"] = pipeline
            session["status"] = "pipeline_editing"
            session["activeStage"] = "transformation"
            session["stageHealth"] = {
                **session.get("stageHealth", {}),
                "transformation": "current",
                **({"output": "stale"} if "output" in session.get("reachedStages", []) else {}),
            }
            self._stale_analysis_nodes(session)
            self._stale_output_nodes(session)
            return self._dispatch(meta, command, session)

        if command_type == "run_pipeline":
            enabled = [item for item in operations if item.get("enabled", True)]
            models = list(pipeline.get("models") or [])
            if not enabled and not models:
                raise PipelineWorkspaceError("Add a transformation or model job before running.")
            self.manager.validate_pipeline(operations)
            self._validate_model_inputs(operations, models)
            for model in models:
                try:
                    self.model_manager.validate_job(model)
                except ModelWorkspaceError as error:
                    raise PipelineWorkspaceError(str(error)) from error
            approved_snapshot_id = str(session["data"]["approvedSnapshotId"])
            record = self.manager.execute_pipeline(
                meta.session_id,
                approved_snapshot_id,
                operations,
            )
            model_results = []
            new_model_results = []
            model_failures: dict[str, str] = {}
            reused_model_ids: set[str] = set()
            for model in models:
                snapshot_id = record.output_snapshot_refs.get(str(model["inputRef"]))
                if not snapshot_id:
                    raise PipelineWorkspaceError(
                        "Model input did not resolve to a pipeline snapshot."
                    )
                try:
                    compatible = self.model_manager.find_compatible(
                        meta.session_id, snapshot_id, model
                    )
                    if compatible is not None:
                        model_results.append(compatible)
                        reused_model_ids.add(str(model["id"]))
                    else:
                        result = self.model_manager.execute(
                            meta.session_id, snapshot_id, model, persist=False
                        )
                        model_results.append(result)
                        new_model_results.append(result)
                except ModelWorkspaceError as error:
                    model_failures[str(model["id"])] = str(error)
            self.model_manager.persist(new_model_results)
            code_artifacts, code_warnings = self.code_manager.generate(
                meta.session_id,
                record.bundle_id,
                operations,
                models,
            )
            self._archive_current_analysis(pipeline)
            pipeline["runStatus"] = "completed"
            pipeline["operations"] = [
                {
                    **operation,
                    "status": "completed" if operation.get("enabled", True) else "not_run",
                }
                for operation in operations
            ]
            pipeline["models"] = [
                {
                    **model,
                    "status": "failed" if model["id"] in model_failures else "completed",
                    **(
                        {"error": model_failures[model["id"]]}
                        if model["id"] in model_failures
                        else {
                            "resultRef": next(
                                result.id
                                for result in model_results
                                if result.job_id == model["id"]
                            ),
                            "reused": model["id"] in reused_model_ids,
                        }
                    ),
                }
                for model in models
            ]
            pipeline["modelResults"] = [
                {
                    "id": result.id,
                    "jobId": result.job_id,
                    "kind": result.kind,
                    "inputSnapshotId": result.input_snapshot_id,
                    "inputSnapshotHash": result.input_snapshot_hash,
                    "specificationHash": result.specification_hash,
                    "resultHash": result.result_hash,
                    "sample": result.sample,
                    "result": result.result,
                    "diagnostics": result.diagnostics,
                    "warnings": result.warnings,
                    "createdAt": result.created_at.isoformat(),
                }
                for result in model_results
            ]
            pipeline["codeArtifacts"] = [
                {
                    "id": artifact.id,
                    "bundleId": artifact.bundle_id,
                    "language": artifact.language,
                    "filename": artifact.filename,
                    "mediaType": artifact.media_type,
                    "checksum": artifact.checksum,
                    "specificationHash": artifact.specification_hash,
                    "warnings": artifact.warnings,
                    "createdAt": artifact.created_at.isoformat(),
                }
                for artifact in code_artifacts
            ]
            python_artifact = next(
                artifact for artifact in code_artifacts if artifact.language == "python"
            )
            stata_artifact = next(
                (artifact for artifact in code_artifacts if artifact.language == "stata"),
                None,
            )
            pipeline["bundle"] = {
                "id": record.bundle_id,
                "inputDatasetId": record.input_snapshot_id,
                "finalDatasetRef": record.final_snapshot_id,
                "operationIds": record.operation_ids,
                "operationSnapshotRefs": record.operation_snapshot_refs,
                "outputSnapshotRefs": record.output_snapshot_refs,
                "operationLineage": [
                    {
                        "operationId": item.operation_id,
                        "operation": item.operation,
                        "inputRef": item.input_ref,
                        "outputRef": item.output_ref,
                        "inputSnapshotId": item.input_snapshot_id,
                        "inputSnapshotHash": item.input_snapshot_hash,
                        "outputSnapshotId": item.output_snapshot_id,
                        "outputSnapshotHash": item.output_snapshot_hash,
                        "specificationHash": item.specification_hash,
                        "inputRows": item.input_rows,
                        "outputRows": item.output_rows,
                    }
                    for item in record.operation_lineage
                ],
                "modelResultIds": [result.id for result in model_results],
                "pythonCodeRef": python_artifact.id,
                "stataCodeRef": stata_artifact.id if stata_artifact else None,
                "diagnostics": [
                    *record.diagnostics,
                    f"Executed {len(model_results)} registered model jobs.",
                ],
                "warnings": [
                    *record.warnings,
                    *[warning for result in model_results for warning in result.warnings],
                    *[
                        "Model "
                        + str(
                            next(
                                (item.get("label") for item in models if item.get("id") == job_id),
                                job_id,
                            )
                        )
                        + f" failed: {message}"
                        for job_id, message in model_failures.items()
                    ],
                    *code_warnings,
                ],
                "createdAt": record.created_at.isoformat(),
            }
            pipeline["lastRunApprovedAt"] = session["updatedAt"]
            session["pipeline"] = pipeline
            self._update_node(
                session,
                "transformation_pipeline",
                "completed",
                record.bundle_id,
                [approved_snapshot_id],
            )
            if models:
                self._update_node(
                    session,
                    "model_execution",
                    "completed",
                    record.bundle_id,
                    sorted(
                        {
                            str(record.output_snapshot_refs.get(str(model["inputRef"])))
                            for model in models
                        }
                    ),
                )
            analyst = AgentRuntimeDescriptor(
                role="analyst",
                authority="propose",
                provider_profile=(
                    self.assistant.provider_profile if self.assistant else "unavailable"
                ),
                model_id=self.assistant.model_id if self.assistant else "unavailable",
                status="available" if self.assistant else "unavailable",
                limitations=["May diagnose and propose; cannot execute or approve the Run gate."],
            )
            record_stage_handoff(
                session,
                WorkflowStage.TRANSFORMATION,
                agents=[analyst],
            )
            return self._generate_output(meta, command, session, pipeline)

        pipeline = self._begin_edit(session)
        operations = list(pipeline.get("operations") or [])

        if command_type == "add_pipeline_operation":
            kind = str(command.get("operation") or "")
            if kind not in SUPPORTED_TRANSFORMATIONS:
                raise PipelineWorkspaceError("Transformation is not registered for Phase 1D-1.")
            operation_id = self._identifier("pipeline-operation")
            input_ref = operations[-1]["outputRef"] if operations else "active_dataset"
            operation = {
                "id": operation_id,
                "kind": kind,
                "label": TRANSFORMATION_LABELS[kind],
                "enabled": True,
                "target": {
                    "inputRef": input_ref,
                    "indicators": [],
                    "entities": [],
                    "fields": ["value"],
                },
                "parameters": self._default_parameters(kind),
                "inputRef": input_ref,
                "outputRef": f"step:{operation_id}",
                "status": "not_run",
            }
            operations.append(operation)
            pipeline["operations"] = operations
            pipeline["selectedOperationId"] = operation_id
        elif command_type == "move_pipeline_operation":
            operation_id = str(command.get("operationId") or "")
            index = next(
                (i for i, item in enumerate(operations) if item.get("id") == operation_id),
                -1,
            )
            target_index = index - 1 if command.get("direction") == "up" else index + 1
            if index < 0 or target_index < 0 or target_index >= len(operations):
                raise PipelineWorkspaceError("Pipeline operation cannot move in that direction.")
            operations[index], operations[target_index] = (
                operations[target_index],
                operations[index],
            )
            pipeline["operations"] = self._relink(operations)
        elif command_type == "toggle_pipeline_operation":
            operation_id = str(command.get("operationId") or "")
            found = False
            for operation in operations:
                if operation.get("id") == operation_id:
                    operation["enabled"] = not operation.get("enabled", True)
                    found = True
            if not found:
                raise PipelineWorkspaceError("Unknown pipeline operation.")
            pipeline["operations"] = operations
        elif command_type == "delete_pipeline_operation":
            operation_id = str(command.get("operationId") or "")
            deleted_index = next(
                (index for index, item in enumerate(operations) if item.get("id") == operation_id),
                -1,
            )
            filtered = [item for item in operations if item.get("id") != operation_id]
            if deleted_index < 0:
                raise PipelineWorkspaceError("Unknown pipeline operation.")
            pipeline["operations"] = self._relink(filtered)
            self._rebind_models_after_delete(pipeline, deleted_index, pipeline["operations"])
            if pipeline.get("selectedOperationId") == operation_id:
                pipeline["selectedOperationId"] = filtered[0]["id"] if filtered else None
        elif command_type == "update_pipeline_target":
            operation_id = str(command.get("operationId") or "")
            index = next(
                (i for i, item in enumerate(operations) if item.get("id") == operation_id),
                -1,
            )
            if index < 0:
                raise PipelineWorkspaceError("Unknown pipeline operation.")
            if not isinstance(command.get("target"), dict):
                raise PipelineWorkspaceError("Pipeline target must be a structured object.")
            changes = dict(command["target"])
            allowed_inputs = {
                "active_dataset",
                *[str(item["outputRef"]) for item in operations[:index]],
            }
            input_ref = str(changes.get("inputRef") or operations[index]["inputRef"])
            if input_ref not in allowed_inputs:
                raise PipelineWorkspaceError(
                    "A transformation may only read the active dataset or an upstream output."
                )
            operations[index] = {
                **operations[index],
                "inputRef": input_ref,
                "target": {
                    **(operations[index].get("target") or {}),
                    **changes,
                    "inputRef": input_ref,
                },
            }
            pipeline["operations"] = operations
        elif command_type == "update_pipeline_parameters":
            operation_id = str(command.get("operationId") or "")
            operation = next((item for item in operations if item.get("id") == operation_id), {})
            if not operation:
                raise PipelineWorkspaceError("Unknown pipeline operation.")
            if not isinstance(command.get("parameters"), dict):
                raise PipelineWorkspaceError("Pipeline parameters must be a structured object.")
            operation["parameters"] = dict(command["parameters"])
            pipeline["operations"] = operations
        elif command_type == "add_model_job":
            kind = str(command.get("model") or "")
            if kind not in SUPPORTED_MODELS:
                raise PipelineWorkspaceError("Model kind is not registered for Phase 1D-2.")
            model_id = self._identifier("model-job")
            pipeline["models"] = [
                *(pipeline.get("models") or []),
                {
                    "id": model_id,
                    "kind": kind,
                    "label": f"{kind.upper()} model",
                    "inputRef": operations[-1]["outputRef"] if operations else "active_dataset",
                    "variables": [],
                    "dependentVariables": [],
                    "independentVariables": [],
                    "parameters": default_model_parameters(kind),
                    "status": "not_run",
                },
            ]
        elif command_type == "update_model_input":
            model_id = str(command.get("modelId") or "")
            input_ref = str(command.get("inputRef") or "")
            allowed = {"active_dataset", *[str(item["outputRef"]) for item in operations]}
            if input_ref not in allowed:
                raise PipelineWorkspaceError("Model input must be a registered pipeline output.")
            found = False
            models = list(pipeline.get("models") or [])
            for model in models:
                if model.get("id") == model_id:
                    model["inputRef"] = input_ref
                    found = True
            if not found:
                raise PipelineWorkspaceError("Unknown model job.")
            pipeline["models"] = models
            pipeline.pop("lastBindingNotice", None)
        elif command_type == "update_model_specification":
            model_id = str(command.get("modelId") or "")
            models = list(pipeline.get("models") or [])
            model = next((item for item in models if item.get("id") == model_id), None)
            if model is None:
                raise PipelineWorkspaceError("Unknown model job.")
            for key in ("variables", "dependentVariables", "independentVariables"):
                if key in command:
                    value = command[key]
                    if not isinstance(value, list) or not all(
                        isinstance(item, str) for item in value
                    ):
                        raise PipelineWorkspaceError("Model variables must be code lists.")
                    model[key] = [item.strip().upper() for item in value if item.strip()]
            if "parameters" in command:
                if not isinstance(command["parameters"], dict):
                    raise PipelineWorkspaceError("Model parameters must be structured.")
                model["parameters"] = {**(model.get("parameters") or {}), **command["parameters"]}
            pipeline["models"] = models
        elif command_type == "delete_model_job":
            model_id = str(command.get("modelId") or "")
            models = list(pipeline.get("models") or [])
            filtered = [item for item in models if item.get("id") != model_id]
            if len(filtered) == len(models):
                raise PipelineWorkspaceError("Unknown model job.")
            pipeline["models"] = filtered

        self.manager.validate_pipeline(list(pipeline.get("operations") or []))
        self._validate_model_inputs(
            list(pipeline.get("operations") or []), list(pipeline.get("models") or [])
        )
        session["pipeline"] = pipeline
        return self._dispatch(meta, command, session)

    @staticmethod
    def _update_node(
        session: dict[str, Any],
        kind: str,
        status: str,
        output_snapshot_id: str,
        input_snapshot_ids: list[str],
        *,
        error_code: str | None = None,
        attempt: int | None = None,
    ) -> None:
        nodes = list(session.get("nodes") or [])
        node = next(
            (
                item
                for item in reversed(nodes)
                if item.get("kind") == kind and item.get("authority") != "proposal"
            ),
            None,
        )
        if node is None or node.get("status") == "stale":
            supersedes_node_id = str(node.get("id")) if node is not None else None
            node = {
                "id": f"node-{kind}-{len(nodes) + 1}",
                "kind": kind,
                "createdAt": session["updatedAt"],
            }
            if supersedes_node_id:
                node["supersedesNodeId"] = supersedes_node_id
            nodes.append(node)
        node.update(
            {
                "status": status,
                "inputSnapshotIds": input_snapshot_ids,
                "outputSnapshotId": output_snapshot_id,
                "updatedAt": session["updatedAt"],
            }
        )
        if error_code:
            node["errorCode"] = error_code
        else:
            node.pop("errorCode", None)
        if attempt is not None:
            node["attempt"] = attempt
        session["nodes"] = nodes

    @staticmethod
    def _assistant_target_hash(session: dict[str, Any]) -> str:
        pipeline = dict(session.get("pipeline") or {})
        return assistant_state_hash(
            {
                "approvedSnapshotId": (session.get("data") or {}).get("approvedSnapshotId"),
                "operations": pipeline.get("operations") or [],
                "models": pipeline.get("models") or [],
            }
        )

    @staticmethod
    def _append_proposal_node(
        session: dict[str, Any], proposal_id: str, target_hash: str, kind: str
    ) -> None:
        session["nodes"] = [
            *(session.get("nodes") or []),
            {
                "id": f"node-{proposal_id}",
                "kind": kind,
                "status": "waiting_for_review",
                "authority": "proposal",
                "inputSnapshotIds": [target_hash],
                "outputSnapshotId": proposal_id,
                "createdAt": session["updatedAt"],
                "updatedAt": session["updatedAt"],
            },
        ]

    @staticmethod
    def _close_proposal_node(session: dict[str, Any], proposal_id: str, *, applied: bool) -> None:
        for node in session.get("nodes") or []:
            if node.get("id") == f"node-{proposal_id}":
                node["status"] = "completed" if applied else "stale"
                node["updatedAt"] = session["updatedAt"]
                if not applied:
                    node["staleReason"] = "The user rejected this Analysis assistant proposal."

    def preview(
        self,
        session_id: str,
        operation_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        stored = self.repository.get(session_id)
        session = stored.session.model_dump(mode="json", by_alias=True)
        approved_snapshot_id = str((session.get("data") or {}).get("approvedSnapshotId") or "")
        if not approved_snapshot_id:
            raise PipelineWorkspaceError("Approve the active dataset before previewing a pipeline.")
        operations = list((session.get("pipeline") or {}).get("operations") or [])
        return self.manager.preview_pipeline(
            session_id,
            approved_snapshot_id,
            operations,
            operation_id,
            offset,
            limit,
        )

    def code_content(self, session_id: str, artifact_id: str) -> dict[str, Any]:
        return self.code_manager.content(session_id, artifact_id)
