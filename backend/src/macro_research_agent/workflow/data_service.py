from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.connectors.adb import AdbConnector, AdbConnectorError
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.bis import BisConnector, BisConnectorError
from macro_research_agent.connectors.ecb import EcbConnector, EcbConnectorError
from macro_research_agent.connectors.eurostat import EurostatConnector, EurostatConnectorError
from macro_research_agent.connectors.imf import ImfConnectorError, ImfDataConnector
from macro_research_agent.connectors.oecd import OecdConnector, OecdConnectorError
from macro_research_agent.connectors.un_sdg import UnSdgConnector, UnSdgConnectorError
from macro_research_agent.connectors.world_bank import (
    WorldBankConnector,
    WorldBankConnectorError,
)
from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.api_schemas import (
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.data_workspace import (
    DataOperationKind,
    DatasetSnapshotRecord,
    DataWorkspaceError,
    DataWorkspaceManager,
)
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff import (
    AgentRuntimeDescriptor,
    HandoffIncompleteError,
    append_stage_message,
    record_stage_handoff,
    relevant_handoff,
)
from macro_research_agent.workflow.model_data_access import WorkflowModelDataAccessService
from macro_research_agent.workflow.pipeline_draft import build_plan_pipeline_draft
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.stage_adapters import StageProviderError
from macro_research_agent.workflow.stage_assistant import (
    DataAssistantContext,
    StageAssistantPort,
    validate_data_proposal_constraints,
)
from macro_research_agent.workflow.states import SessionState, WorkflowStage


class WorkflowDataService:
    calendar_year_connectors = {"world_bank", "adb", "un_sdg"}
    fiscal_year_pattern = re.compile(
        r"^(?:fy\s*)?([12]\d{3})\s*[-/]\s*(\d{2}|[12]\d{3})$",
        re.IGNORECASE,
    )
    latest_period_tokens = {
        "latest",
        "latest available",
        "latest available period",
        "latest available year",
        "present",
    }
    allowed_mapping_roles = {
        "series_id",
        "entity_code",
        "indicator_code",
        "frequency",
        "period",
        "value",
        "attribute",
        "ignore",
    }
    allowed_commands = {
        "apply_data_operation",
        "undo_data_operation",
        "map_source_column",
        "validate_source_mapping",
        "approve_data_merge",
        "data_next",
        "prepare_round_trip_export",
        "map_round_trip_column",
        "validate_round_trip",
        "commit_round_trip",
        "propose_data_assistance",
        "apply_data_assistance",
        "reject_data_assistance",
    }

    def __init__(
        self,
        repository: WorkflowRepository,
        graph_service: GraphService,
        manager: DataWorkspaceManager,
        assistant: StageAssistantPort | None = None,
        model_data_access: WorkflowModelDataAccessService | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.manager = manager
        self.assistant = assistant
        self.model_data_access = model_data_access
        self.capability_registry = capability_registry

    async def initialize_imf_payload(self, session: dict[str, Any]) -> dict[str, Any]:
        return await self.initialize_registered_connector_payload(session, "imf_data")

    async def initialize_registered_connector_payload(
        self, session: dict[str, Any], connector_id: str
    ) -> dict[str, Any]:
        plan = session["currentPlan"]
        sources = [source for source in plan["dataSources"] if source.get("enabled", True)]
        if len(sources) != 1 or sources[0]["connectorId"] != connector_id:
            raise DataWorkspaceError(
                "Acquisition supports one registered public source at a time; "
                "mixed sources require a reviewed merge."
            )
        members = sorted(
            {code for item in plan["geographyResolutions"] for code in item["memberCodes"]}
        )
        dataset = str(sources[0]["dataset"])
        indicator_dimension = (
            {"CPI": "coicop", "WEO": "indicator"}.get(dataset)
            if connector_id == "imf_data"
            else "indicator"
        )
        if indicator_dimension is None:
            raise DataWorkspaceError(f"IMF dataset {dataset!r} is not registered.")
        requested_start = str(plan["period"]["start"])
        requested_end = str(plan["period"]["end"])
        resolved_start, resolved_end, period_resolution = self._resolve_query_period(
            connector_id,
            requested_start,
            requested_end,
            str(plan["period"]["frequency"]),
        )
        query = DataQuery(
            dataset=dataset,
            dimensions={"country": members, indicator_dimension: sources[0]["indicators"]},
            frequency={"monthly": "M", "quarterly": "Q", "annual": "A"}[
                plan["period"]["frequency"]
            ],
            start_period=resolved_start,
            end_period=resolved_end,
        )
        sessions_root = self.manager.workflow_root / "sessions"
        session_dir = (sessions_root / session["id"]).resolve()
        if session_dir.parent != sessions_root.resolve():
            raise DataWorkspaceError("Invalid session storage path.")
        connector_raw = session_dir / "connector_raw" / connector_id
        shared_cache = self.manager.workflow_root / "connector_cache" / connector_id
        if connector_id == "imf_data":
            connector: (
                ImfDataConnector
                | WorldBankConnector
                | OecdConnector
                | EurostatConnector
                | AdbConnector
                | EcbConnector
                | BisConnector
                | UnSdgConnector
            )
            connector = ImfDataConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "world_bank":
            connector = WorldBankConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "oecd":
            connector = OecdConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "eurostat":
            connector = EurostatConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "adb":
            connector = AdbConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "ecb":
            connector = EcbConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "bis":
            connector = BisConnector(connector_raw, shared_cache_dir=shared_cache)
        elif connector_id == "un_sdg":
            connector = UnSdgConnector(connector_raw, shared_cache_dir=shared_cache)
        else:
            raise DataWorkspaceError(f"Connector {connector_id!r} is not executable.")
        try:
            result = await connector.fetch(query)
        except (
            ImfConnectorError,
            WorldBankConnectorError,
            OecdConnectorError,
            EurostatConnectorError,
            AdbConnectorError,
            EcbConnectorError,
            BisConnectorError,
            UnSdgConnectorError,
        ) as error:
            self._record_connector_attempts(
                str(session["id"]), query, connector_id, connector.version, connector.attempts
            )
            raise DataWorkspaceError(str(error)) from error
        self._record_connector_attempts(
            str(session["id"]), query, connector_id, connector.version, connector.attempts
        )
        payload = self.manager.initialize_connector(session["id"], result)
        if period_resolution is not None:
            resolved_at = datetime.now(timezone.utc).isoformat()
            payload["sourceRuns"][0].update(
                {
                    "requestedPeriodStart": requested_start,
                    "resolvedPeriodStart": resolved_start,
                    "requestedPeriodEnd": requested_end,
                    "resolvedPeriodEnd": resolved_end,
                    "periodResolution": period_resolution,
                }
            )
            self.repository.record_trace_event(
                str(session["id"]),
                "data.period_bound_resolved",
                Actor.SYSTEM,
                {
                    "connector_id": connector_id,
                    "dataset": dataset,
                    "requested_start": requested_start,
                    "resolved_start": resolved_start,
                    "requested_end": requested_end,
                    "resolved_end": resolved_end,
                    "resolved_at": resolved_at,
                    "semantics": period_resolution,
                },
            )
        return payload

    @classmethod
    def _resolve_query_period(
        cls,
        connector_id: str,
        requested_start: str,
        requested_end: str,
        frequency: str,
    ) -> tuple[str, str, str | None]:
        resolved_start = requested_start
        resolved_end = cls._resolve_period_end(requested_end, frequency)
        resolution: str | None = (
            "query_upper_bound" if resolved_end != requested_end else None
        )
        if connector_id in cls.calendar_year_connectors and frequency == "annual":
            resolved_start = cls._resolve_fiscal_year_label(requested_start)
            fiscal_end = cls._resolve_fiscal_year_label(resolved_end)
            if resolved_start != requested_start or fiscal_end != resolved_end:
                resolution = "calendar_year_mapping"
            resolved_end = fiscal_end
        return resolved_start, resolved_end, resolution

    @classmethod
    def _resolve_fiscal_year_label(cls, value: str) -> str:
        match = cls.fiscal_year_pattern.fullmatch(value.strip())
        if match is None:
            return value
        start_year = int(match.group(1))
        end_token = match.group(2)
        if len(end_token) == 2:
            end_year = (start_year // 100) * 100 + int(end_token)
            if end_year < start_year:
                end_year += 100
        else:
            end_year = int(end_token)
        if end_year != start_year + 1:
            raise DataWorkspaceError(
                f"Fiscal-year label {value!r} is invalid; use a consecutive range such as "
                f"{start_year}-{str(start_year + 1)[-2:]}."
            )
        return str(end_year)

    @classmethod
    def _resolve_period_end(cls, value: str, frequency: str) -> str:
        normalized = " ".join(value.strip().casefold().replace("_", " ").split())
        if normalized not in cls.latest_period_tokens:
            return value
        current = datetime.now(timezone.utc)
        if frequency == "annual":
            return f"{current.year:04d}"
        if frequency == "quarterly":
            return f"{current.year:04d}-Q{((current.month - 1) // 3) + 1}"
        if frequency == "monthly":
            return f"{current.year:04d}-{current.month:02d}"
        raise DataWorkspaceError(f"Cannot resolve an open end period for {frequency!r} data.")

    async def initialize_world_bank_payload(self, session: dict[str, Any]) -> dict[str, Any]:
        return await self.initialize_registered_connector_payload(session, "world_bank")

    async def initialize_public_sources_payload(
        self, session: dict[str, Any]
    ) -> dict[str, Any]:
        sources = [
            source
            for source in session["currentPlan"]["dataSources"]
            if source.get("enabled", True) and source.get("connectorId") != "local_file"
        ]
        if not sources:
            raise DataWorkspaceError("The Plan has no executable public data source.")
        if len(sources) == 1:
            return await self.initialize_registered_connector_payload(
                session, str(sources[0]["connectorId"])
            )

        workspaces: list[dict[str, Any]] = []
        merge_inputs: list[tuple[DatasetSnapshotRecord, dict[str, str]]] = []
        for source in sources:
            scoped_session = {
                **session,
                "currentPlan": {
                    **session["currentPlan"],
                    "dataSources": [source],
                },
            }
            workspace = await self.initialize_registered_connector_payload(
                scoped_session, str(source["connectorId"])
            )
            workspaces.append(workspace)
            source_snapshot_id = str(workspace["activeSnapshotId"])
            merge_inputs.append(
                (
                    self.manager.get_snapshot(str(session["id"]), source_snapshot_id),
                    {
                        "connectorId": str(source["connectorId"]),
                        "dataset": str(source["dataset"]),
                    },
                )
            )

        merged = self.manager.merge_connector_snapshots(str(session["id"]), merge_inputs)
        merged_frame = self.manager.frame(merged)
        source_snapshots = [snapshot for item in workspaces for snapshot in item["snapshots"]]
        source_runs = [run for item in workspaces for run in item["sourceRuns"]]
        provenance = [entry for item in workspaces for entry in item["provenance"]]
        return {
            "schemaId": merged.schema_id,
            "columns": merged.columns,
            "sourceRuns": source_runs,
            "snapshots": [*source_snapshots, self.manager.snapshot_wire(merged)],
            "activeSnapshotId": merged.snapshot_id,
            "operations": [],
            "quality": self.manager.diagnostics(merged),
            "entityMappings": {
                str(code): str(code) for code in merged_frame["entity_code"].unique()
            },
            "indicatorMappings": {
                str(code): str(code) for code in merged_frame["indicator_code"].unique()
            },
            "provenance": provenance,
            "mergeReview": {
                "status": "waiting_for_review",
                "strategy": "canonical_union",
                "inputSnapshotIds": [record.snapshot_id for record, _ in merge_inputs],
                "outputSnapshotId": merged.snapshot_id,
                "identityKeys": [
                    "entity_code",
                    "indicator_code",
                    "frequency",
                    "period",
                ],
                "frequencyPolicy": "Preserve each source frequency; no implicit conversion.",
                "unitPolicy": "Preserve source unit metadata; no implicit conversion.",
                "missingPolicy": "Preserve missing observations for Data review.",
                "lineageColumns": [
                    "source_connector_id",
                    "source_dataset",
                    "source_snapshot_id",
                ],
            },
            "previewRef": f"/api/v1/workflow/sessions/{session['id']}/data/preview",
        }

    def _record_connector_attempts(
        self,
        session_id: str,
        query: DataQuery,
        connector_id: str,
        connector_version: str,
        attempts: list[dict[str, Any]],
    ) -> None:
        query_hash = hashlib.sha256(
            json.dumps(query.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        for attempt in attempts:
            self.repository.record_trace_event(
                session_id,
                "connector.fetch_attempt",
                Actor.CONNECTOR,
                {
                    "connector_id": connector_id,
                    "connector_version": connector_version,
                    "dataset": query.dataset,
                    "query_hash": query_hash,
                    "member": attempt["member"],
                    "attempt": attempt["attempt"],
                    "status": attempt["status"],
                    "raw_sha256": attempt.get("raw_sha256"),
                },
            )

    def _record_imf_attempts(
        self, session_id: str, query: DataQuery, attempts: list[dict[str, Any]]
    ) -> None:
        query_hash = hashlib.sha256(
            json.dumps(query.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        for attempt in attempts:
            self.repository.record_trace_event(
                session_id,
                "connector.fetch_attempt",
                Actor.CONNECTOR,
                {
                    "connector_id": "imf_data",
                    "connector_version": ImfDataConnector.version,
                    "dataset": query.dataset,
                    "query_hash": query_hash,
                    "member": attempt["member"],
                    "attempt": attempt["attempt"],
                    "status": attempt["status"],
                    "raw_sha256": attempt.get("raw_sha256"),
                },
            )

    def initialize_payload(
        self,
        session: dict[str, Any],
        upload_id: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        uploads = self.repository.list_uploads(str(session["id"]))
        if not uploads:
            raise DataWorkspaceError(
                "No local file is available. Upload CSV, JSON or XLSX before approving the Plan."
            )
        upload = next(
            (item for item in uploads if item.upload_id == upload_id),
            uploads[-1] if upload_id is None else None,
        )
        if upload is None:
            raise DataWorkspaceError("Unknown local-file upload.")
        return self.manager.initialize(session, upload, mapping)

    def source_mapping_payload(
        self, session: dict[str, Any], error: str, upload_id: str | None = None
    ) -> dict[str, Any]:
        uploads = self.repository.list_uploads(str(session["id"]))
        upload = next(
            (item for item in uploads if item.upload_id == upload_id),
            uploads[-1] if uploads and upload_id is None else None,
        )
        if upload is None:
            raise DataWorkspaceError("Unknown local-file upload.")
        return {
            "schemaId": "pending-mapping",
            "columns": [],
            "sourceRuns": [
                {
                    "id": f"source-run-{upload.upload_id}",
                    "provider": "Local file",
                    "dataset": upload.filename,
                    "connectorId": "local_file",
                    "query": f"Map upload {upload.upload_id}",
                    "status": "ready",
                }
            ],
            "snapshots": [],
            "activeSnapshotId": "",
            "operations": [],
            "quality": {
                "missingShare": 0,
                "duplicateKeys": 0,
                "observations": 0,
                "warning": "Schema mapping is required.",
            },
            "sourceMappingDraft": self.manager.source_mapping_draft(upload, error),
        }

    def execute(
        self, meta: WorkflowCommandMeta, command: dict[str, Any]
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        command_type = str(command.get("type") or "")
        if command_type not in self.allowed_commands:
            raise DataWorkspaceError("Command is not allowed in the Data domain.")
        stored = self.repository.require_current(meta)
        if stored.session.status == SessionState.COMPLETED:
            raise DataWorkspaceError(
                "Completed Workflow sessions are read-only. "
                "Continue or fork the session to revise it."
            )
        session = stored.session.model_dump(mode="json", by_alias=True)
        session["updatedAt"] = datetime.now(timezone.utc).isoformat()
        data = dict(session.get("data") or {})
        if command_type == "map_source_column":
            draft = dict(data.get("sourceMappingDraft") or {})
            source_column = str(command.get("sourceColumn") or "")
            if source_column not in draft.get("sourceColumns", []):
                raise DataWorkspaceError("Unknown uploaded source column.")
            role = str(command.get("role") or "attribute")
            if role not in self.allowed_mapping_roles:
                raise DataWorkspaceError("Unknown source mapping role.")
            mappings = dict(draft.get("mappings") or {})
            mappings[source_column] = role
            draft["mappings"] = mappings
            draft["state"] = "mapping"
            draft["errors"] = []
            data["sourceMappingDraft"] = draft
            session["data"] = data
            result = WorkflowSessionDocument.model_validate(session)
            return self.graph_service.apply_transition(meta, command, result)
        if command_type == "validate_source_mapping":
            draft = dict(data.get("sourceMappingDraft") or {})
            try:
                session["data"] = self.initialize_payload(
                    session,
                    str(draft.get("uploadId") or ""),
                    dict(draft.get("mappings") or {}),
                )
                loaded_id = str(session["data"].get("activeSnapshotId") or "")
                self._update_node(session, "data_acquisition", "completed", loaded_id)
                self._update_node(session, "data_preparation", "waiting_for_review", loaded_id)
            except DataWorkspaceError as error:
                draft["state"] = "invalid"
                draft["errors"] = [str(error)]
                data["sourceMappingDraft"] = draft
                session["data"] = data
            result = WorkflowSessionDocument.model_validate(session)
            return self.graph_service.apply_transition(meta, command, result)
        active_id = str(data.get("activeSnapshotId") or "")

        if command_type == "approve_data_merge":
            merge_review = dict(data.get("mergeReview") or {})
            if merge_review.get("status") != "waiting_for_review":
                raise DataWorkspaceError("There is no cross-source merge awaiting review.")
            if merge_review.get("outputSnapshotId") != active_id:
                raise DataWorkspaceError(
                    "The active dataset changed after the merge was prepared. Rebuild the merge."
                )
            merge_review["status"] = "approved"
            merge_review["reviewedAt"] = session["updatedAt"]
            merge_review["reviewedBy"] = str(meta.actor)
            data["mergeReview"] = merge_review
            self._update_node(session, "data_merge", "approved", active_id)
            self.repository.record_trace_event(
                meta.session_id,
                "data.merge_approved",
                Actor(str(meta.actor)),
                {
                    "strategy": merge_review["strategy"],
                    "input_snapshot_ids": merge_review["inputSnapshotIds"],
                    "output_snapshot_id": active_id,
                },
            )
            session["data"] = data
            result = WorkflowSessionDocument.model_validate(session)
            return self.graph_service.apply_transition(meta, command, result)

        if command_type == "propose_data_assistance":
            if self.assistant is None or self.model_data_access is None:
                raise DataWorkspaceError("The Data assistant is unavailable.")
            if active_id:
                snapshot = self.manager.get_snapshot(meta.session_id, active_id)
                dataset_context = self.model_data_access.context_for_snapshot(
                    meta.session_id,
                    active_id,
                    WorkflowStage.DATA,
                    for_remote_provider=self.assistant.remote_data_disclosure,
                    provider_profile=self.assistant.provider_profile,
                    model_id=self.assistant.model_id,
                )
                target_id = snapshot.snapshot_id
                target_hash = snapshot.snapshot_hash
                proposal_kind = "data_preparation"
            else:
                upload_contexts = self.model_data_access.contexts_for_uploads(
                    meta.session_id,
                    WorkflowStage.DATA,
                    for_remote_provider=self.assistant.remote_data_disclosure,
                    provider_profile=self.assistant.provider_profile,
                    model_id=self.assistant.model_id,
                )
                if not upload_contexts:
                    raise DataWorkspaceError("No local upload is available for schema mapping.")
                dataset_context = upload_contexts[-1]
                target_id = dataset_context.grant.source_ref
                target_hash = dataset_context.grant.content_hash
                proposal_kind = "data_acquisition"
            try:
                handoff = relevant_handoff(session, WorkflowStage.DATA)
            except HandoffIncompleteError as error:
                raise DataWorkspaceError(f"[handoff_incomplete] {error}") from error
            context = DataAssistantContext(
                request=str(command.get("request") or "Review and prepare this dataset."),
                plan=dict(session.get("currentPlan") or {}),
                diagnostics=dict(data.get("quality") or {}),
                source_mapping_draft=dict(data.get("sourceMappingDraft") or {}),
                dataset=dataset_context,
                capability_catalog=(
                    [item.model_dump(mode="json") for item in self.capability_registry.list()]
                    if self.capability_registry is not None
                    else []
                ),
                handoff=handoff,
                recent_messages=list(
                    ((session.get("stageThreads") or {}).get("data") or [])[-10:]
                ),
            )
            try:
                assistant_output = self.assistant.propose_data(
                    str(command.get("request") or "Review and prepare this dataset."),
                    context,
                    self.model_data_access,
                )
                validate_data_proposal_constraints(context.request, assistant_output)
            except StageProviderError as error:
                self.repository.record_trace_event(
                    meta.session_id,
                    "ai.data_assistance_failed",
                    Actor.AGENT,
                    {
                        "provider_profile": self.assistant.provider_profile,
                        "model_id": self.assistant.model_id,
                        "error_code": error.code,
                        "target_snapshot_hash": target_hash,
                    },
                )
                raise DataWorkspaceError(f"[{error.code}] {error}") from error
            except ValueError as error:
                raise DataWorkspaceError(str(error)) from error
            proposal_id = f"data-assistant-{uuid4().hex}"
            data["pendingAssistantProposal"] = {
                "id": proposal_id,
                "request": context.request,
                "summary": assistant_output.summary,
                "operations": [
                    {
                        "id": item.proposal_item_id,
                        "operation": item.operation,
                        "parameters": item.parameters,
                        "rationale": item.rationale,
                    }
                    for item in assistant_output.operations
                ],
                "sourceMappings": [
                    {
                        "id": item.proposal_item_id,
                        "sourceColumn": item.source_column,
                        "role": item.role,
                        "rationale": item.rationale,
                    }
                    for item in assistant_output.source_mappings
                ],
                "diagnostics": [
                    {
                        "kind": item.kind,
                        "summary": item.summary,
                        "details": item.details,
                    }
                    for item in assistant_output.diagnostics
                ],
                "targetSnapshotId": target_id,
                "targetSnapshotHash": target_hash,
                "agent": {
                    "role": "data_steward",
                    "authority": "propose",
                    "providerProfile": self.assistant.provider_profile,
                    "modelId": self.assistant.model_id,
                    "status": "available",
                },
            }
            append_stage_message(
                session,
                WorkflowStage.DATA,
                "user",
                context.request,
                target_hash=target_hash,
                command_type="data_assistance",
                label="Data request",
            )
            append_stage_message(
                session,
                WorkflowStage.DATA,
                "agent",
                assistant_output.summary,
                target_hash=target_hash,
                command_type="data_assistance",
                label="Data Steward proposal",
            )
            self._append_proposal_node(session, proposal_id, target_hash, proposal_kind)
            session["data"] = data
            self.repository.record_trace_event(
                meta.session_id,
                "ai.data_assistance_completed",
                Actor.AGENT,
                {
                    "provider_profile": self.assistant.provider_profile,
                    "model_id": self.assistant.model_id,
                    "target_snapshot_hash": target_hash,
                    "proposal_id": proposal_id,
                    "item_count": len(assistant_output.operations)
                    + len(assistant_output.source_mappings),
                },
            )
            result = WorkflowSessionDocument.model_validate(session)
            return self.graph_service.apply_transition(meta, command, result)

        if command_type in {"apply_data_assistance", "reject_data_assistance"}:
            pending = dict(data.get("pendingAssistantProposal") or {})
            if not pending:
                raise DataWorkspaceError("There is no pending Data assistant proposal.")
            if command_type == "reject_data_assistance":
                self._close_proposal_node(session, str(pending["id"]), applied=False)
                data.pop("pendingAssistantProposal", None)
                append_stage_message(
                    session,
                    WorkflowStage.DATA,
                    "system",
                    "The Data Steward proposal was rejected. No data change was applied.",
                    target_hash=str(pending.get("targetSnapshotHash") or ""),
                    command_type="data_assistance",
                    label="Decision",
                )
                session["data"] = data
                result = WorkflowSessionDocument.model_validate(session)
                return self.graph_service.apply_transition(meta, command, result)
            selected = {str(value) for value in command.get("acceptedItemIds") or []}
            items = list(pending.get("operations") or [])
            mapping_items = list(pending.get("sourceMappings") or [])
            available = {
                *[str(item.get("id")) for item in items],
                *[str(item.get("id")) for item in mapping_items],
            }
            if not selected or not selected.issubset(available):
                raise DataWorkspaceError("Select at least one valid Data proposal item.")
            if mapping_items:
                upload = next(
                    (
                        item
                        for item in self.repository.list_uploads(meta.session_id)
                        if item.upload_id == pending.get("targetSnapshotId")
                    ),
                    None,
                )
                if upload is None or upload.checksum != pending.get("targetSnapshotHash"):
                    raise DataWorkspaceError(
                        "The uploaded source changed after this proposal was created."
                    )
                draft = dict(data.get("sourceMappingDraft") or {})
                mappings = dict(draft.get("mappings") or {})
                for item in mapping_items:
                    if str(item.get("id")) in selected:
                        mappings[str(item["sourceColumn"])] = str(item["role"])
                draft["mappings"] = mappings
                draft["state"] = "mapping"
                draft["errors"] = []
                data["sourceMappingDraft"] = draft
                data.pop("pendingAssistantProposal", None)
                self._close_proposal_node(session, str(pending["id"]), applied=True)
                append_stage_message(
                    session,
                    WorkflowStage.DATA,
                    "system",
                    f"Applied {len(selected)} confirmed source-mapping item(s).",
                    target_hash=str(pending.get("targetSnapshotHash") or ""),
                    command_type="data_assistance",
                    label="Confirmed decision",
                )
                session["data"] = data
                result = WorkflowSessionDocument.model_validate(session)
                return self.graph_service.apply_transition(meta, command, result)
            if not active_id:
                raise DataWorkspaceError("The Data workspace has no active dataset.")
            active = self.manager.get_snapshot(meta.session_id, active_id)
            if (
                pending.get("targetSnapshotId") != active.snapshot_id
                or pending.get("targetSnapshotHash") != active.snapshot_hash
            ):
                raise DataWorkspaceError(
                    "The active dataset changed after this proposal was created. "
                    "Request a new proposal."
                )
            for item in items:
                if str(item.get("id")) not in selected:
                    continue
                snapshot, operation = self.manager.apply_operation(
                    meta.session_id,
                    active_id,
                    cast(DataOperationKind, item.get("operation")),
                    dict(item.get("parameters") or {}),
                )
                active_id = snapshot.snapshot_id
                data["snapshots"] = [
                    *(data.get("snapshots") or []),
                    self.manager.snapshot_wire(snapshot),
                ]
                data["operations"] = [
                    *(data.get("operations") or []),
                    {
                        "id": operation.operation_id,
                        "kind": operation.kind,
                        "label": operation.label,
                        "inputSnapshotId": operation.input_snapshot_id,
                        "outputSnapshotId": operation.output_snapshot_id,
                        "createdAt": operation.created_at.isoformat(),
                        "parameters": operation.parameters,
                    },
                ]
            active = self.manager.get_snapshot(meta.session_id, active_id)
            data["activeSnapshotId"] = active.snapshot_id
            data["schemaId"] = active.schema_id
            data["columns"] = active.columns
            data["quality"] = self.manager.diagnostics(active)
            data.pop("pendingAssistantProposal", None)
            self._close_proposal_node(session, str(pending["id"]), applied=True)
            append_stage_message(
                session,
                WorkflowStage.DATA,
                "system",
                f"Applied {len(selected)} confirmed Data proposal item(s).",
                target_hash=str(pending.get("targetSnapshotHash") or ""),
                command_type="data_assistance",
                label="Confirmed decision",
            )
            self._update_node(session, "data_preparation", "waiting_for_review", active.snapshot_id)
            self._invalidate_downstream(session)
            session["data"] = data
            result = WorkflowSessionDocument.model_validate(session)
            return self.graph_service.apply_transition(meta, command, result)

        if not active_id:
            raise DataWorkspaceError("The Data workspace has no active dataset.")

        if command_type == "apply_data_operation":
            kind = cast(DataOperationKind, command.get("operation"))
            snapshot, operation = self.manager.apply_operation(
                meta.session_id,
                active_id,
                kind,
                dict(command.get("parameters") or {}),
            )
            data["snapshots"] = [
                *(data.get("snapshots") or []),
                self.manager.snapshot_wire(snapshot),
            ]
            data["activeSnapshotId"] = snapshot.snapshot_id
            data["schemaId"] = snapshot.schema_id
            data["columns"] = snapshot.columns
            data["quality"] = self.manager.diagnostics(snapshot)
            data["operations"] = [
                *(data.get("operations") or []),
                {
                    "id": operation.operation_id,
                    "kind": operation.kind,
                    "label": operation.label,
                    "inputSnapshotId": operation.input_snapshot_id,
                    "outputSnapshotId": operation.output_snapshot_id,
                    "createdAt": operation.created_at.isoformat(),
                    "parameters": operation.parameters,
                },
            ]
            self._update_node(
                session,
                "data_preparation",
                "waiting_for_review",
                snapshot.snapshot_id,
            )
            self._invalidate_downstream(session)
        elif command_type == "undo_data_operation":
            operations = list(data.get("operations") or [])
            if not operations:
                raise DataWorkspaceError("There is no Data operation to undo.")
            operation = operations.pop()
            active = self.manager.get_snapshot(meta.session_id, operation["inputSnapshotId"])
            data["operations"] = operations
            data["activeSnapshotId"] = active.snapshot_id
            data["schemaId"] = active.schema_id
            data["columns"] = active.columns
            data["quality"] = self.manager.diagnostics(active)
            self._update_node(
                session,
                "data_preparation",
                "waiting_for_review",
                active.snapshot_id,
            )
            self._invalidate_downstream(session)
        elif command_type == "map_round_trip_column":
            draft = dict(data.get("roundTripDraft") or {})
            source_column = str(command.get("sourceColumn") or "")
            role = str(command.get("role") or "")
            if source_column not in draft.get("sourceColumns", []):
                raise DataWorkspaceError("Unknown round-trip source column.")
            if role not in self.allowed_mapping_roles:
                raise DataWorkspaceError("Unknown round-trip mapping role.")
            mappings = dict(draft.get("mappings") or {})
            mappings[source_column] = role
            draft["mappings"] = mappings
            if draft.get("manifestVerified") and draft.get("formulasMaterialized"):
                draft["state"] = "mapping"
                draft["errors"] = []
            data["roundTripDraft"] = draft
        elif command_type == "validate_round_trip":
            draft = dict(data.get("roundTripDraft") or {})
            if not draft.get("manifestVerified") or not draft.get("formulasMaterialized"):
                raise DataWorkspaceError("Manifest and formula checks must pass before mapping.")
            validated = self.manager.validate_roundtrip_import(
                meta.session_id,
                str(draft.get("id") or ""),
                dict(draft.get("mappings") or {}),
                checksum=str(draft.get("workbookChecksum") or ""),
            )
            draft["errors"] = validated.errors
            draft["warnings"] = validated.warnings
            draft["candidateSnapshotId"] = (
                validated.snapshot.snapshot_id if validated.snapshot else None
            )
            draft["state"] = (
                "validated" if validated.snapshot and not validated.errors else "invalid"
            )
            data["roundTripDraft"] = draft
        elif command_type == "prepare_round_trip_export":
            package = self.manager.export_roundtrip(meta.session_id, active_id)
            data["lastExportedPackage"] = {
                "id": package.package_id,
                "filename": package.filename,
                "sheets": ["Data", "Schema", "Provenance", "Instructions", "_MRA_MANIFEST"],
                "snapshotId": package.source_snapshot_id,
                "schemaId": package.schema_id,
                "checksum": package.workbook_checksum,
                "manifestLocked": True,
                "downloadUrl": (
                    f"/api/v1/workflow/sessions/{meta.session_id}/data/roundtrip/"
                    f"packages/{package.package_id}"
                ),
            }
            self._update_node(session, "external_round_trip", "ready", active_id)
        elif command_type == "data_next":
            if (data.get("mergeReview") or {}).get("status") == "waiting_for_review":
                raise DataWorkspaceError(
                    "Review and approve the cross-source merge before configuring the pipeline."
                )
            active = self.manager.get_snapshot(meta.session_id, active_id)
            self.manager.validate_for_approval(active)
            active_frame = self.manager.frame(active)
            first_transformation_entry = "transformation" not in session["reachedStages"]
            data["approvedSnapshotId"] = active.snapshot_id
            operation_ids = [item["id"] for item in data.get("operations") or []]
            recipe = json.dumps(operation_ids, separators=(",", ":"))
            data["approvedDatasetRef"] = {
                "snapshotId": active.snapshot_id,
                "snapshotHash": active.snapshot_hash,
                "schemaId": active.schema_id,
                "schemaHash": active.schema_id,
                "preparationRecipeRef": ("sha256:" + hashlib.sha256(recipe.encode()).hexdigest()),
                "operationIds": operation_ids,
            }
            session["status"] = "pipeline_editing"
            session["activeStage"] = "transformation"
            session["reachedStages"] = list(
                dict.fromkeys([*session["reachedStages"], "transformation"])
            )
            session["stageHealth"] = {
                **session["stageHealth"],
                "data": "completed",
                "transformation": "current",
            }
            existing_pipeline = dict(session.get("pipeline") or {})
            approved_plan_id = str(session.get("approvedPlanSnapshotId") or "")
            source_plan_id = existing_pipeline.get("sourcePlanSnapshotId")
            plan_changed = bool(source_plan_id and source_plan_id != approved_plan_id)
            prepared_from_plan = first_transformation_entry or plan_changed
            if prepared_from_plan:
                session["pipeline"] = build_plan_pipeline_draft(
                    dict(session.get("currentPlan") or {}),
                    active_frame["indicator_code"].tolist(),
                    plan_snapshot_id=approved_plan_id,
                )
            else:
                existing_pipeline.pop("bundle", None)
                existing_pipeline["runStatus"] = "editing"
                existing_pipeline["operations"] = [
                    {**item, "status": "not_run"}
                    for item in existing_pipeline.get("operations") or []
                ]
                existing_pipeline["models"] = [
                    {**item, "status": "not_run"}
                    for item in existing_pipeline.get("models") or []
                ]
                existing_pipeline["editHistory"] = []
                session["pipeline"] = existing_pipeline
            analysis_count = len(session["pipeline"]["operations"]) + len(
                session["pipeline"]["models"]
            )
            session["lastNotice"] = (
                "Plan analysis draft prepared. Review transformations and model jobs before Run."
                if analysis_count and prepared_from_plan
                else "Approved data linked to the reviewed pipeline. Review it before Run."
                if analysis_count
                else "Active dataset approved. The Plan requests no transformations or model jobs."
            )
            self._update_node(session, "data_preparation", "approved", active.snapshot_id)
            record_stage_handoff(
                session,
                WorkflowStage.DATA,
                agents=[
                    AgentRuntimeDescriptor(
                        role="data_steward",
                        authority="propose",
                        provider_profile=(
                            self.assistant.provider_profile if self.assistant else "unavailable"
                        ),
                        model_id=self.assistant.model_id if self.assistant else "unavailable",
                        status="available" if self.assistant else "unavailable",
                    )
                ],
            )
        else:
            draft = data.get("roundTripDraft") or {}
            candidate_id = draft.get("candidateSnapshotId")
            if not candidate_id or draft.get("state") != "validated":
                raise DataWorkspaceError("Round-trip import must validate before commit.")
            candidate = self.manager.get_snapshot(meta.session_id, candidate_id)
            data["snapshots"] = [
                *(data.get("snapshots") or []),
                self.manager.snapshot_wire(candidate),
            ]
            data["activeSnapshotId"] = candidate.snapshot_id
            data["schemaId"] = candidate.schema_id
            data["columns"] = candidate.columns
            data["quality"] = self.manager.diagnostics(candidate)
            data["operations"] = []
            data["activeRoundTripManifest"] = {
                "workbookChecksum": draft["workbookChecksum"],
                "sourceSnapshotId": draft["sourceSnapshotId"],
                "schemaId": candidate.schema_id,
                "manifestVerified": draft["manifestVerified"],
            }
            data.pop("roundTripDraft", None)
            self._update_node(session, "external_round_trip", "completed", candidate.snapshot_id)
            self._update_node(
                session,
                "data_preparation",
                "waiting_for_review",
                candidate.snapshot_id,
            )
            self._invalidate_downstream(session)

        session["data"] = data
        result = WorkflowSessionDocument.model_validate(session)
        return self.graph_service.apply_transition(meta, command, result)

    def _invalidate_downstream(self, session: dict[str, Any]) -> None:
        health = dict(session.get("stageHealth") or {})
        for stage in ("transformation", "output"):
            if stage in session.get("reachedStages", []):
                health[stage] = "stale"
        session["stageHealth"] = health

    def _update_node(
        self, session: dict[str, Any], kind: str, status: str, output_snapshot_id: str
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
        timestamp = str(session.get("updatedAt") or "")
        if node is None:
            node = {
                "id": f"node-{kind}-{len(nodes) + 1}",
                "kind": kind,
                "status": status,
                "inputSnapshotIds": [],
                "createdAt": timestamp,
                "updatedAt": timestamp,
            }
            nodes.append(node)
        node["status"] = status
        node["outputSnapshotId"] = output_snapshot_id
        node["updatedAt"] = timestamp
        session["nodes"] = nodes

    @staticmethod
    def _append_proposal_node(
        session: dict[str, Any], proposal_id: str, target_hash: str, kind: str
    ) -> None:
        timestamp = str(session.get("updatedAt") or "")
        session["nodes"] = [
            *(session.get("nodes") or []),
            {
                "id": f"node-{proposal_id}",
                "kind": kind,
                "status": "waiting_for_review",
                "authority": "proposal",
                "inputSnapshotIds": [target_hash],
                "outputSnapshotId": proposal_id,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
        ]

    @staticmethod
    def _close_proposal_node(session: dict[str, Any], proposal_id: str, *, applied: bool) -> None:
        for node in session.get("nodes") or []:
            if node.get("id") == f"node-{proposal_id}":
                node["status"] = "completed" if applied else "stale"
                node["updatedAt"] = session["updatedAt"]
                if not applied:
                    node["staleReason"] = "The user rejected this Data assistant proposal."

    def import_roundtrip(
        self,
        meta: WorkflowCommandMeta,
        filename: str,
        content: bytes,
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        stored = self.repository.require_current(meta)
        if stored.session.status == SessionState.COMPLETED:
            raise DataWorkspaceError(
                "Completed Workflow sessions are read-only. "
                "Continue or fork the session to revise it."
            )
        session = stored.session.model_dump(mode="json", by_alias=True)
        session["updatedAt"] = datetime.now(timezone.utc).isoformat()
        result = self.manager.import_roundtrip(meta.session_id, filename, content)
        active_id = str(session["data"]["activeSnapshotId"])
        session["data"]["roundTripDraft"] = {
            "id": result.import_id,
            "filename": result.filename,
            "workbookChecksum": result.workbook_checksum,
            "manifestVerified": result.manifest_verified,
            "formulasMaterialized": result.formulas_materialized,
            "sourceColumns": result.source_columns,
            "mappings": result.mappings,
            "state": (
                "invalid" if result.errors else "validated" if result.snapshot else "mapping"
            ),
            "errors": result.errors,
            "warnings": result.warnings,
            "candidateSnapshotId": result.snapshot.snapshot_id if result.snapshot else None,
            "sourceSnapshotId": result.source_snapshot_id or active_id,
        }
        self._update_node(
            session,
            "external_round_trip",
            "waiting_for_review" if not result.errors else "failed",
            result.snapshot.snapshot_id if result.snapshot else active_id,
        )
        document = WorkflowSessionDocument.model_validate(session)
        return self.graph_service.apply_transition(
            meta,
            {"type": "start_round_trip_import", "filename": result.filename},
            document,
        )
