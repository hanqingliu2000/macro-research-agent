from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.connectors.registry import connector_catalog
from macro_research_agent.knowledge.data_sources import (
    DataSourceKnowledgeCatalog,
    default_data_source_knowledge,
)
from macro_research_agent.knowledge.planning_source_index import PlanningSourceIndex
from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.api_schemas import (
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.data_service import WorkflowDataService
from macro_research_agent.workflow.data_workspace import DataWorkspaceError
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff import AgentRuntimeDescriptor, record_stage_handoff
from macro_research_agent.workflow.model_data_access import WorkflowModelDataAccessService
from macro_research_agent.workflow.model_workspace import SUPPORTED_MODELS
from macro_research_agent.workflow.pipeline_workspace import SUPPORTED_TRANSFORMATIONS
from macro_research_agent.workflow.plan_guidance import normalize_plan_guidance
from macro_research_agent.workflow.planning_provider import (
    WorkflowPlanningContext,
    WorkflowPlanningProvider,
)
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.schemas import (
    ApprovedPlanSnapshot,
    PlanDraft,
)
from macro_research_agent.workflow.states import SessionState, WorkflowStage


class PlanningCommandError(ValueError):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _hash(value: Any) -> str:
    wire = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(wire.encode()).hexdigest()}"


def _aggregation_wire(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "method": value.method,
        "weightIndicator": value.weight_indicator,
        "weightSource": value.weight_source,
        "missingPolicy": value.missing_data_policy,
        "coverageThreshold": value.coverage_threshold,
        "membershipPolicy": value.membership_policy,
    }


def plan_to_wire(plan: PlanDraft) -> dict[str, Any]:
    return {
        "objective": plan.objective,
        "geographyIntent": plan.geography_intent,
        "period": plan.period.model_dump(mode="json"),
        "geographyResolutions": [
            {
                "id": item.resolution_id,
                "label": item.label,
                "kind": item.kind,
                "memberCodes": item.member_codes,
                "membershipSource": item.membership_source,
                "effectivePeriod": item.effective_period,
                "confirmed": item.confirmed,
                "aggregation": _aggregation_wire(item.aggregation),
            }
            for item in plan.geography_resolutions
        ],
        "dataSources": [
            {
                "id": f"source-{index + 1}",
                "connectorId": item.connector_id,
                "provider": item.connector_id,
                "dataset": item.dataset,
                "indicators": item.indicators,
                "queryIntent": item.query_intent,
                "enabled": True,
            }
            for index, item in enumerate(plan.data_sources)
        ],
        "transformationIntents": [
            {
                "id": item.capability_id,
                "label": item.label,
                "enabled": item.enabled,
                "targetIndicators": item.target_indicators,
            }
            for item in plan.transformation_intents
        ],
        "modelIntents": [
            {
                "capabilityId": item.capability_id,
                "id": item.capability_id,
                "label": item.purpose,
                "purpose": item.purpose,
                "enabled": item.enabled,
                "targetIndicators": item.target_indicators,
                "variables": [
                    {
                        "indicatorCode": variable.indicator_code,
                        "role": variable.role,
                        "order": variable.order,
                    }
                    for variable in sorted(item.variables, key=lambda value: value.order)
                ],
                "forecastHorizon": (
                    {
                        "steps": item.forecast_horizon.steps,
                        "unit": item.forecast_horizon.unit,
                        "confidenceLevel": item.forecast_horizon.confidence_level,
                    }
                    if item.forecast_horizon
                    else None
                ),
            }
            for item in plan.model_intents
        ],
        "capabilityInvocations": [
            {
                "capabilityId": item.capability_id,
                "capabilityVersion": item.capability_version,
                "stage": item.stage,
                "purpose": item.purpose,
                "availability": item.availability,
                "approvalGate": item.approval_gate,
            }
            for item in plan.capability_invocations
        ],
        "deliverables": {
            "charts": plan.deliverables.charts,
            "tables": plan.deliverables.tables,
            "cleanData": plan.deliverables.clean_data,
            "python": plan.deliverables.python,
            "stata": plan.deliverables.stata,
            "researchReport": plan.deliverables.research_report,
        },
        "assumptions": plan.assumptions,
        "warnings": plan.warnings,
        "unresolvedItems": plan.unresolved_items,
    }


def plan_from_wire(value: dict[str, Any]) -> PlanDraft:
    geographies = []
    for item in value.get("geographyResolutions", []):
        aggregation = item.get("aggregation")
        geographies.append(
            {
                "resolution_id": item["id"],
                "label": item["label"],
                "kind": item["kind"],
                "member_codes": item["memberCodes"],
                "membership_source": item["membershipSource"],
                "effective_period": item["effectivePeriod"],
                "confirmed": item.get("confirmed", False),
                "aggregation": (
                    {
                        "method": aggregation["method"],
                        "weight_indicator": aggregation.get("weightIndicator"),
                        "weight_source": aggregation.get("weightSource"),
                        "missing_data_policy": aggregation["missingPolicy"],
                        "coverage_threshold": aggregation["coverageThreshold"],
                        "membership_policy": aggregation["membershipPolicy"],
                    }
                    if aggregation
                    else None
                ),
            }
        )
    deliverables = value.get("deliverables", {})
    planned_indicators = list(
        dict.fromkeys(
            str(code)
            for source in value.get("dataSources", [])
            if source.get("enabled", True)
            for code in source.get("indicators", [])
        )
    )

    def model_variables(item: dict[str, Any]) -> list[dict[str, Any]]:
        explicit = list(item.get("variables") or [])
        if explicit:
            return [
                {
                    "indicator_code": variable["indicatorCode"],
                    "role": variable["role"],
                    "order": variable["order"],
                }
                for variable in explicit
            ]
        indicators = list(item.get("targetIndicators") or planned_indicators)
        kind = str(item.get("capabilityId") or item.get("id") or "")
        roles = (
            ["system"] * len(indicators)
            if kind == "var"
            else ["descriptive"] * len(indicators)
            if kind in {"descriptive", "correlation"}
            else ["dependent", *(["independent"] * max(0, len(indicators) - 1))]
            if kind == "ols"
            else ["dependent", *(["exogenous"] * max(0, len(indicators) - 1))]
            if kind == "sarimax"
            else ["dependent"] * len(indicators)
        )
        return [
            {"indicator_code": code, "role": roles[index], "order": index + 1}
            for index, code in enumerate(indicators)
        ]

    return PlanDraft.model_validate(
        {
            "objective": value["objective"],
            "geography_intent": value["geographyIntent"],
            "period": value["period"],
            "geography_resolutions": geographies,
            "data_sources": [
                {
                    "connector_id": item["connectorId"],
                    "dataset": item["dataset"],
                    "indicators": item["indicators"],
                    "query_intent": item["queryIntent"],
                }
                for item in value.get("dataSources", [])
                if item.get("enabled", True)
            ],
            "transformation_intents": [
                {
                    "capability_id": item["id"],
                    "label": item["label"],
                    "enabled": item.get("enabled", True),
                    "target_indicators": item.get("targetIndicators", []),
                }
                for item in value.get("transformationIntents", [])
            ],
            "model_intents": [
                {
                    "capability_id": item.get("capabilityId") or item["id"],
                    "purpose": item.get("purpose") or item.get("label") or item["id"],
                    "enabled": item.get("enabled", True),
                    "variables": model_variables(item),
                    "forecast_horizon": (
                        {
                            "steps": item["forecastHorizon"]["steps"],
                            "unit": item["forecastHorizon"].get("unit", "periods"),
                            "confidence_level": item["forecastHorizon"].get(
                                "confidenceLevel", 0.95
                            ),
                        }
                        if item.get("forecastHorizon")
                        else None
                    ),
                }
                for item in value.get("modelIntents", [])
            ],
            "capability_invocations": [
                {
                    "capability_id": item["capabilityId"],
                    "capability_version": item["capabilityVersion"],
                    "stage": item["stage"],
                    "purpose": item["purpose"],
                    "availability": item["availability"],
                    "approval_gate": item.get("approvalGate"),
                }
                for item in value.get("capabilityInvocations", [])
            ],
            "deliverables": {
                "charts": deliverables.get("charts", True),
                "tables": deliverables.get("tables", True),
                "clean_data": deliverables.get("cleanData", True),
                "python": deliverables.get("python", True),
                "stata": deliverables.get("stata", True),
                "research_report": deliverables.get("researchReport", False),
            },
            "assumptions": value.get("assumptions", []),
            "warnings": value.get("warnings", []),
            "unresolved_items": value.get("unresolvedItems", []),
        }
    )


def _is_geography_confirmation_item(value: object) -> bool:
    lowered = str(value).casefold()
    return "geograph" in lowered and ("confirm" in lowered or "confirmation" in lowered)


def _message(
    role: str, body: str, target_hash: str, command_type: str, label: str
) -> dict[str, Any]:
    return {
        "id": _id("message"),
        "stage": "plan",
        "role": role,
        "body": body,
        "createdAt": _now(),
        "targetSnapshotHash": target_hash,
        "commandType": command_type,
        "label": label,
    }


def _upsert_node(
    session: dict[str, Any],
    kind: str,
    status: str,
    *,
    output_snapshot_id: str | None = None,
) -> None:
    nodes = list(session.get("nodes") or [])
    existing = next(
        (
            item
            for item in reversed(nodes)
            if item.get("kind") == kind and item.get("authority", "record") == "record"
        ),
        None,
    )
    previous = existing
    if (
        existing is not None
        and output_snapshot_id
        and existing.get("outputSnapshotId") not in {None, output_snapshot_id}
    ):
        existing["status"] = "stale"
        existing["staleReason"] = "Superseded by a new immutable Plan version."
        existing = None
    if existing is None:
        existing = {
            "id": _id(f"node-{kind}"),
            "kind": kind,
            "status": status,
            "inputSnapshotIds": [],
            "createdAt": _now(),
            "updatedAt": _now(),
        }
        nodes.append(existing)
        if previous is not None:
            existing["supersedesNodeId"] = previous["id"]
    existing["status"] = status
    existing["updatedAt"] = _now()
    if output_snapshot_id:
        existing["outputSnapshotId"] = output_snapshot_id
    session["nodes"] = nodes


def _append_plan_proposal_node(session: dict[str, Any], proposal_id: str, target_hash: str) -> None:
    now = _now()
    session["nodes"] = [
        *(session.get("nodes") or []),
        {
            "id": f"node-{proposal_id}",
            "kind": "research_plan",
            "status": "waiting_for_review",
            "authority": "proposal",
            "inputSnapshotIds": [target_hash],
            "outputSnapshotId": proposal_id,
            "createdAt": now,
            "updatedAt": now,
        },
    ]


def _append_clarification_proposal_node(
    session: dict[str, Any], batch_id: str, target_hash: str
) -> None:
    now = _now()
    session["nodes"] = [
        *(session.get("nodes") or []),
        {
            "id": f"node-{batch_id}",
            "kind": "clarification_batch",
            "status": "in_progress",
            "authority": "proposal",
            "inputSnapshotIds": [target_hash],
            "outputSnapshotId": batch_id,
            "createdAt": now,
            "updatedAt": now,
        },
    ]


def _close_plan_proposal_node(session: dict[str, Any], proposal_id: str, *, applied: bool) -> None:
    for node in session.get("nodes") or []:
        if node.get("id") == f"node-{proposal_id}":
            node["status"] = "completed" if applied else "stale"
            node["updatedAt"] = _now()
            if not applied:
                node["staleReason"] = "The user rejected or superseded this Plan proposal."


class WorkflowPlanningService:
    allowed_commands = {
        "start_clarification",
        "request_plan_clarification",
        "submit_clarification",
        "propose_plan_patch",
        "apply_plan_patch",
        "reject_plan_patch",
        "save_plan",
        "confirm_geography",
        "plan_next",
    }

    def __init__(
        self,
        repository: WorkflowRepository,
        graph_service: GraphService,
        provider: WorkflowPlanningProvider,
        data_service: WorkflowDataService | None = None,
        model_data_access: WorkflowModelDataAccessService | None = None,
        capability_registry: CapabilityRegistry | None = None,
        source_knowledge: DataSourceKnowledgeCatalog | PlanningSourceIndex | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.provider = provider
        self.data_service = data_service
        self.model_data_access = model_data_access
        self.capability_registry = capability_registry
        self.source_knowledge = source_knowledge or default_data_source_knowledge()

    def _record_provider_receipt(
        self, session_id: str, output_schema: str, target_hash: str
    ) -> None:
        receipt = getattr(self.provider, "last_receipt", None)
        self.repository.record_trace_event(
            session_id,
            "ai.planning_completed",
            Actor.AGENT,
            {
                "provider_profile": self.provider.provider_profile,
                "model_id": self.provider.model_id,
                "prompt_version": getattr(receipt, "prompt_version", "planning-v1"),
                "output_schema": getattr(receipt, "output_schema", output_schema),
                "target_snapshot_hash": target_hash,
                "attempt": getattr(receipt, "attempt", 1),
                "latency_ms": getattr(receipt, "latency_ms", 0.0),
                "status": "completed",
                "source_knowledge_catalog_version": self.source_knowledge.catalog_version,
                "source_knowledge_catalog_sha256": self.source_knowledge.content_sha256,
            },
        )

    def _record_provider_failure(
        self, session_id: str, output_schema: str, target_hash: str
    ) -> None:
        receipt = getattr(self.provider, "last_receipt", None)
        self.repository.record_trace_event(
            session_id,
            "ai.planning_failed",
            Actor.AGENT,
            {
                "provider_profile": self.provider.provider_profile,
                "model_id": self.provider.model_id,
                "prompt_version": getattr(receipt, "prompt_version", "planning-v1"),
                "output_schema": getattr(receipt, "output_schema", output_schema),
                "target_snapshot_hash": target_hash,
                "attempt": getattr(receipt, "attempt", 1),
                "latency_ms": getattr(receipt, "latency_ms", 0.0),
                "status": "failed",
                "error_code": getattr(receipt, "error_code", "provider_failed"),
                "source_knowledge_catalog_version": self.source_knowledge.catalog_version,
                "source_knowledge_catalog_sha256": self.source_knowledge.content_sha256,
            },
        )

    def _provider_error(self, error: ValueError) -> ValueError:
        if getattr(error, "code", None):
            return error
        if self.provider.provider_profile == "deterministic-local":
            return PlanningCommandError(str(error), code="deterministic_contract_violation")
        return PlanningCommandError(str(error), code="provider_unavailable")

    def _context(
        self,
        session: dict[str, Any],
        answers: dict[str, str] | None = None,
        knowledge_query: str | None = None,
    ) -> WorkflowPlanningContext:
        schemas = [
            record.model_dump(mode="json") for record in self.repository.list_uploads(session["id"])
        ]
        current = plan_from_wire(session["currentPlan"]) if session.get("currentPlan") else None
        data_contexts = (
            self.model_data_access.contexts_for_uploads(
                str(session["id"]),
                WorkflowStage.PLAN,
                for_remote_provider=self.provider.remote_data_disclosure,
                provider_profile=self.provider.provider_profile,
                model_id=self.provider.model_id,
            )
            if self.model_data_access is not None
            else []
        )
        available_connector_ids = sorted(
            connector_id
            for connector_id, item in connector_catalog().items()
            if item.availability == "available"
        )
        active_answers = (
            answers
            if answers is not None
            else (session.get("clarification") or {}).get("answers", {})
        )
        knowledge_text = "\n".join(
            [
                str(session["request"]),
                *(str(item["body"]) for item in (session.get("planThread") or [])[-10:]),
                *(str(value) for value in active_answers.values()),
                *([knowledge_query] if knowledge_query else []),
            ]
        )
        return WorkflowPlanningContext(
            research_request=session["request"],
            reference_date=datetime.now(timezone.utc).date().isoformat(),
            conversation_history=[
                {"role": str(item["role"]), "body": str(item["body"])}
                for item in (session.get("planThread") or [])[-40:]
            ],
            clarification_questions=(session.get("clarification") or {}).get("questions", []),
            clarification_answers=active_answers,
            current_plan=current,
            available_connector_ids=available_connector_ids,
            available_transformation_ids=sorted(SUPPORTED_TRANSFORMATIONS),
            available_model_ids=sorted(SUPPORTED_MODELS),
            available_deliverable_ids=[
                "charts",
                "tables",
                "clean_data",
                "python",
                "stata",
                "research_report",
            ],
            capability_catalog=(
                [
                    descriptor.model_dump(mode="json")
                    for descriptor in self.capability_registry.list()
                ]
                if self.capability_registry is not None
                else []
            ),
            source_knowledge_catalog_version=self.source_knowledge.catalog_version,
            source_knowledge_catalog_sha256=self.source_knowledge.content_sha256,
            source_knowledge=self.source_knowledge.for_planning(
                knowledge_text, available_connector_ids
            ),
            uploaded_schema_summaries=schemas,
            uploaded_data_contexts=data_contexts,
        )

    async def execute(
        self, meta: WorkflowCommandMeta, command: dict[str, Any]
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        command_type = str(command.get("type") or "")
        if command_type not in self.allowed_commands:
            raise PlanningCommandError("Command is not allowed in the Plan domain.")
        stored = self.repository.require_current(meta)
        if stored.session.status == SessionState.COMPLETED:
            raise PlanningCommandError(
                "Completed Workflow sessions are read-only. "
                "Continue or fork the session to revise it."
            )
        session = stored.session.model_dump(mode="json", by_alias=True)
        now = _now()
        session["updatedAt"] = now

        if command_type in {"start_clarification", "request_plan_clarification"}:
            if command_type == "request_plan_clarification" and not session.get("currentPlan"):
                raise PlanningCommandError(
                    "A current Plan is required for follow-up clarification."
                )
            try:
                batch = await self.provider.clarification_batch(
                    self._context(session), self.model_data_access
                )
            except ValueError as error:
                self._record_provider_failure(
                    meta.session_id, "ClarificationBatch", meta.expected_snapshot_hash
                )
                raise self._provider_error(error) from error
            self._record_provider_receipt(
                meta.session_id, "ClarificationBatch", meta.expected_snapshot_hash
            )
            batch_id = _id("clarification")
            prior_round = int((session.get("clarification") or {}).get("round") or 0)
            session["clarification"] = {
                "id": batch_id,
                "round": prior_round + 1,
                "questions": [
                    {"id": item.question_id, "prompt": item.prompt, "options": item.options}
                    for item in batch.questions
                ],
                "answers": {},
                "submitted": False,
            }
            session["planThread"] = [
                *(session.get("planThread") or []),
                _message(
                    "agent",
                    "Please confirm the research frame.",
                    batch_id,
                    "clarification",
                    "Clarification",
                ),
            ]
            _append_clarification_proposal_node(session, batch_id, meta.expected_snapshot_hash)
        elif command_type == "submit_clarification":
            answers = dict(command.get("answers") or {})
            try:
                plan = await self.provider.draft_plan(
                    self._context(session, answers), self.model_data_access
                )
            except ValueError as error:
                self._record_provider_failure(
                    meta.session_id, "PlanDraft", meta.expected_snapshot_hash
                )
                raise self._provider_error(error) from error
            self._record_provider_receipt(meta.session_id, "PlanDraft", meta.expected_snapshot_hash)
            wire_plan = plan_to_wire(plan)
            if not session.get("currentPlan"):
                title = getattr(plan, "session_title", None)
                if title:
                    session["title"] = title.strip()
            # The model cannot confirm geography on the user's behalf.
            for resolution in wire_plan["geographyResolutions"]:
                resolution["confirmed"] = False
            snapshot_hash = _hash(wire_plan)
            snapshot_id = _id("plan")
            snapshot = {
                "id": snapshot_id,
                "hash": snapshot_hash,
                "plan": wire_plan,
                "actor": "agent",
                "createdAt": now,
            }
            session["clarification"] = {
                **session["clarification"],
                "answers": answers,
                "submitted": True,
            }
            _close_plan_proposal_node(session, str(session["clarification"]["id"]), applied=True)
            session["currentPlan"] = wire_plan
            session["currentPlanSnapshotId"] = snapshot_id
            session["planSnapshots"] = [*(session.get("planSnapshots") or []), snapshot]
            session["status"] = "plan_review"
            question_prompts = {q["id"]: q["prompt"] for q in session["clarification"]["questions"]}
            session["planThread"] = [
                *(session.get("planThread") or []),
                _message(
                    "user",
                    " · ".join(
                        f"{question_prompts.get(key, key)}: {answer}"
                        for key, answer in answers.items()
                    ),
                    snapshot_hash,
                    "clarification",
                    "Clarification answers",
                ),
                _message(
                    "agent",
                    "A structured Plan is ready for review.",
                    snapshot_hash,
                    "notice",
                    "Plan ready",
                ),
            ]
            _upsert_node(session, "clarification_batch", "completed")
            _upsert_node(
                session, "research_plan", "waiting_for_review", output_snapshot_id=snapshot_id
            )
            _upsert_node(session, "geography_resolution", "waiting_for_review")
        elif command_type == "propose_plan_patch":
            request = str(command.get("request") or "").strip()
            try:
                patch = await self.provider.propose_patch(
                    request,
                    self._context(session, knowledge_query=request),
                    self.model_data_access,
                )
            except ValueError as error:
                self._record_provider_failure(
                    meta.session_id, "PlanPatch", meta.expected_snapshot_hash
                )
                raise self._provider_error(error) from error
            self._record_provider_receipt(meta.session_id, "PlanPatch", meta.expected_snapshot_hash)
            target_hash = (session.get("planSnapshots") or [{}])[-1].get("hash", "plan")
            changes = patch.changes.model_dump(exclude_none=True)
            context_plan = plan_from_wire(session["currentPlan"])
            proposed_plan = PlanDraft.model_validate({**context_plan.model_dump(), **changes})
            current_wire = plan_to_wire(context_plan)
            proposed_wire = plan_to_wire(proposed_plan)
            for resolution in proposed_wire["geographyResolutions"]:
                prior = next(
                    (
                        item
                        for item in current_wire["geographyResolutions"]
                        if item["id"] == resolution["id"]
                    ),
                    None,
                )
                resolution["confirmed"] = bool(
                    prior
                    and prior["confirmed"]
                    and {k: v for k, v in prior.items() if k != "confirmed"}
                    == {k: v for k, v in resolution.items() if k != "confirmed"}
                )
            wire_changes = {
                key: value for key, value in proposed_wire.items() if current_wire.get(key) != value
            }
            proposal_id = _id("plan-patch")
            session["pendingPlanPatch"] = {
                "id": proposal_id,
                "summary": patch.summary,
                "request": request,
                "changes": wire_changes,
                "affectedStages": [stage.value for stage in patch.affected_stages],
                "targetSnapshotHash": target_hash,
            }
            _append_plan_proposal_node(session, proposal_id, str(target_hash))
            session["planThread"] = [
                *(session.get("planThread") or []),
                _message("user", request, target_hash, "plan_patch", "Plan change"),
                _message(
                    "agent",
                    "A typed Plan patch is ready for review.",
                    target_hash,
                    "plan_patch",
                    "Patch proposed",
                ),
            ]
        elif command_type == "apply_plan_patch":
            proposal = session.get("pendingPlanPatch")
            if not proposal:
                raise PlanningCommandError("There is no pending Plan patch.")
            current_hash = str((session.get("planSnapshots") or [{}])[-1].get("hash") or "")
            if proposal.get("targetSnapshotHash") != current_hash:
                raise PlanningCommandError(
                    "The Plan changed after this proposal was created. Request a new proposal."
                )
            proposed_changes = dict(proposal["changes"])
            accepted_fields = command.get("acceptedFields")
            if accepted_fields is None:
                accepted = set(proposed_changes)
            elif not isinstance(accepted_fields, list):
                raise PlanningCommandError("acceptedFields must be a list of proposed fields.")
            else:
                accepted = {str(field) for field in accepted_fields}
            if not accepted or not accepted.issubset(proposed_changes):
                raise PlanningCommandError("Select at least one valid proposed field to apply.")
            self._save_plan(
                session,
                {field: proposed_changes[field] for field in accepted},
                "agent",
            )
            _close_plan_proposal_node(session, str(proposal["id"]), applied=True)
            session.pop("pendingPlanPatch", None)
            _upsert_node(
                session,
                "research_plan",
                "waiting_for_review",
                output_snapshot_id=str(session.get("currentPlanSnapshotId") or ""),
            )
        elif command_type == "reject_plan_patch":
            proposal = session.get("pendingPlanPatch")
            if not proposal:
                raise PlanningCommandError("There is no pending Plan patch.")
            _close_plan_proposal_node(session, str(proposal["id"]), applied=False)
            session.pop("pendingPlanPatch", None)
            session["planThread"] = [
                *(session.get("planThread") or []),
                _message(
                    "user",
                    "Rejected the proposed Plan change.",
                    str(proposal.get("targetSnapshotHash") or "plan"),
                    "plan_patch",
                    "Patch rejected",
                ),
            ]
        elif command_type == "save_plan":
            self._save_plan(
                session, dict(command.get("changes") or {}), str(command.get("actor") or "user")
            )
            _upsert_node(
                session,
                "research_plan",
                "waiting_for_review",
                output_snapshot_id=str(session.get("currentPlanSnapshotId") or ""),
            )
        elif command_type == "confirm_geography":
            current_wire = dict(session.get("currentPlan") or {})
            resolution_id = command.get("resolutionId")
            if not any(
                item["id"] == resolution_id for item in current_wire.get("geographyResolutions", [])
            ):
                raise PlanningCommandError("Unknown geography resolution.")
            resolutions = [
                {**item, "confirmed": True} if item.get("id") == resolution_id else item
                for item in current_wire.get("geographyResolutions", [])
            ]
            changes = {"geographyResolutions": resolutions}
            if resolutions and all(item.get("confirmed") for item in resolutions):
                changes["unresolvedItems"] = [
                    item
                    for item in current_wire.get("unresolvedItems", [])
                    if not _is_geography_confirmation_item(item)
                ]
            self._save_plan(session, changes, "user")
            _upsert_node(session, "geography_resolution", "approved")
        else:
            current_wire = dict(session.get("currentPlan") or {})
            blockers, cautions = normalize_plan_guidance(
                current_wire.get("unresolvedItems", []), current_wire.get("warnings", [])
            )
            if blockers != current_wire.get("unresolvedItems", []) or cautions != current_wire.get(
                "warnings", []
            ):
                self._save_plan(
                    session,
                    {"unresolvedItems": blockers, "warnings": cautions},
                    "agent",
                )
            current = plan_from_wire(session.get("currentPlan") or {})
            if current.unresolved_items:
                raise PlanningCommandError(
                    "Resolve every Plan requirement before approval: "
                    + "; ".join(current.unresolved_items),
                    code=(
                        "connector_unavailable"
                        if any(
                            "unavailable" in item.casefold() for item in current.unresolved_items
                        )
                        else None
                    ),
                )
            catalog = connector_catalog()
            unavailable = sorted(
                {
                    source.connector_id
                    for source in current.data_sources
                    if source.connector_id not in catalog
                    or catalog[source.connector_id].availability != "available"
                }
            )
            if unavailable:
                raise PlanningCommandError(
                    "Plan approval requires executable connectors: " + ", ".join(unavailable),
                    code="connector_unavailable",
                )
            approved = ApprovedPlanSnapshot(
                snapshot_id=str(session["currentPlanSnapshotId"]),
                snapshot_hash=str((session.get("planSnapshots") or [{}])[-1]["hash"]),
                approved_at=datetime.now(timezone.utc),
                plan=current,
            )
            if self.data_service is None:
                raise PlanningCommandError("The Data workspace service is unavailable.")
            public_sources = [
                source for source in current.data_sources if source.connector_id != "local_file"
            ]
            if public_sources:
                session["data"] = await self.data_service.initialize_public_sources_payload(session)
            else:
                try:
                    session["data"] = self.data_service.initialize_payload(session)
                except DataWorkspaceError as error:
                    session["data"] = self.data_service.source_mapping_payload(session, str(error))
            session["approvedPlanSnapshotId"] = approved.snapshot_id
            session["status"] = "data_review"
            session["activeStage"] = "data"
            session["reachedStages"] = list(dict.fromkeys([*session["reachedStages"], "data"]))
            session["stageHealth"] = {
                **session["stageHealth"],
                "plan": "completed",
                "data": "current",
            }
            _upsert_node(
                session,
                "research_plan",
                "approved",
                output_snapshot_id=approved.snapshot_id,
            )
            _upsert_node(session, "geography_resolution", "approved")
            active_data_id = str(session["data"].get("activeSnapshotId") or "")
            _upsert_node(
                session,
                "data_acquisition",
                "completed" if active_data_id else "waiting_for_review",
                output_snapshot_id=active_data_id or None,
            )
            if session["data"].get("mergeReview"):
                _upsert_node(
                    session,
                    "data_merge",
                    "waiting_for_review",
                    output_snapshot_id=active_data_id or None,
                )
            _upsert_node(
                session,
                "data_preparation",
                "waiting_for_review",
                output_snapshot_id=active_data_id or None,
            )
            record_stage_handoff(
                session,
                WorkflowStage.PLAN,
                agents=[
                    AgentRuntimeDescriptor(
                        role="planner",
                        authority="propose",
                        provider_profile=self.provider.provider_profile,
                        model_id=self.provider.model_id,
                    )
                ],
            )

        stage_threads = dict(session.get("stageThreads") or {})
        stage_threads["plan"] = list(session.get("planThread") or [])
        stage_threads.setdefault("data", [])
        stage_threads.setdefault("transformation", [])
        stage_threads.setdefault("output", list(session.get("outputThread") or []))
        session["stageThreads"] = stage_threads
        result = WorkflowSessionDocument.model_validate(session)
        return self.graph_service.apply_transition(meta, command, result)

    def _save_plan(self, session: dict[str, Any], changes: dict[str, Any], actor: str) -> None:
        current = dict(session.get("currentPlan") or {})
        legacy_role_ids = {
            str(item.get("capabilityId") or item.get("id") or "")
            for item in current.get("modelIntents") or []
            if not item.get("variables")
        }
        current.update(changes)
        validated = plan_from_wire(current)
        validated.unresolved_items, validated.warnings = normalize_plan_guidance(
            validated.unresolved_items, validated.warnings
        )
        wire = plan_to_wire(validated)
        if "modelIntents" not in changes:
            for intent in wire.get("modelIntents") or []:
                if str(intent.get("capabilityId") or intent.get("id") or "") in legacy_role_ids:
                    intent["roleInferenceStatus"] = "needs_confirmation"
        snapshot_hash = _hash(wire)
        snapshot_id = _id("plan")
        session["currentPlan"] = wire
        session["currentPlanSnapshotId"] = snapshot_id
        session["planSnapshots"] = [
            *(session.get("planSnapshots") or []),
            {
                "id": snapshot_id,
                "hash": snapshot_hash,
                "plan": wire,
                "actor": actor,
                "createdAt": _now(),
            },
        ]
