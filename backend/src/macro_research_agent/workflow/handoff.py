from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Final, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from macro_research_agent.workflow.states import WorkflowStage

HANDOFF_SCHEMA_VERSION: Final = "mra-stage-handoff-v1"
DecisionCategory = Literal[
    "research_scope",
    "historical_period",
    "forecast_horizon",
    "geography",
    "data_source",
    "indicator_role",
    "data_preparation",
    "analysis_specification",
    "deliverable",
    "limitation",
]


class HandoffDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    category: DecisionCategory
    summary: str = Field(min_length=1)
    status: Literal["confirmed", "inferred", "needs_confirmation"]
    source_refs: list[str] = Field(default_factory=list)


class AgentRuntimeDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal[
        "planner", "data_steward", "analyst", "report_author", "report_reviewer"
    ]
    authority: Literal["clarify", "diagnose", "propose", "author", "review"]
    provider_profile: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    status: Literal["available", "unavailable", "degraded"] = "available"
    limitations: list[str] = Field(default_factory=list)


class StageHandoffEnvelopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mra-stage-handoff-v1"] = HANDOFF_SCHEMA_VERSION
    handoff_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    source_stage: WorkflowStage
    source_snapshot_refs: list[str] = Field(default_factory=list)
    source_hash: str = Field(min_length=1)
    research_spec: dict[str, Any] = Field(default_factory=dict)
    data_spec: dict[str, Any] = Field(default_factory=dict)
    analysis_spec: dict[str, Any] = Field(default_factory=dict)
    deliverables: dict[str, bool] = Field(default_factory=dict)
    decisions: list[HandoffDecision] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    agents: list[AgentRuntimeDescriptor] = Field(default_factory=list)
    supersedes_handoff_id: str | None = None
    created_at: datetime


class HandoffIncompleteError(ValueError):
    pass


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _decision(
    category: DecisionCategory,
    summary: str,
    status: Literal["confirmed", "inferred", "needs_confirmation"],
    refs: list[str],
) -> HandoffDecision:
    return HandoffDecision(
        decision_id="decision-" + hashlib.sha256(
            f"{category}|{summary}".encode()
        ).hexdigest()[:20],
        category=category,
        summary=summary,
        status=status,
        source_refs=refs,
    )


def build_stage_handoff(
    session: dict[str, Any],
    source_stage: WorkflowStage,
    *,
    agents: list[AgentRuntimeDescriptor] | None = None,
    inferred: bool = False,
) -> StageHandoffEnvelopeV1:
    plan = dict(session.get("currentPlan") or {})
    data = dict(session.get("data") or {})
    pipeline = dict(session.get("pipeline") or {})
    output = dict(session.get("output") or {})
    plan_ref = str(
        session.get("approvedPlanSnapshotId")
        or session.get("currentPlanSnapshotId")
        or ""
    )
    data_ref = str(data.get("approvedSnapshotId") or data.get("activeSnapshotId") or "")
    bundle = dict(pipeline.get("bundle") or {})
    bundle_ref = str(bundle.get("id") or "")
    output_ref = str(output.get("artifactSetId") or "")
    refs = [value for value in (plan_ref, data_ref, bundle_ref, output_ref) if value]
    base_status: Literal["confirmed", "inferred"] = "inferred" if inferred else "confirmed"
    decisions: list[HandoffDecision] = []
    if plan.get("objective"):
        decisions.append(
            _decision("research_scope", str(plan["objective"]), base_status, [plan_ref])
        )
    period = dict(plan.get("period") or {})
    if period:
        decisions.append(
            _decision(
                "historical_period",
                f"{period.get('start')} to {period.get('end')} ({period.get('frequency')})",
                base_status,
                [plan_ref],
            )
        )
    for resolution in plan.get("geographyResolutions") or []:
        decisions.append(
            _decision(
                "geography",
                f"{resolution.get('label')}: {', '.join(resolution.get('memberCodes') or [])}",
                base_status if resolution.get("confirmed") else "needs_confirmation",
                [plan_ref],
            )
        )
    for source in plan.get("dataSources") or []:
        if source.get("enabled", True):
            decisions.append(
                _decision(
                    "data_source",
                    f"{source.get('connectorId')} / {source.get('dataset')}: "
                    + ", ".join(source.get("indicators") or []),
                    base_status,
                    [plan_ref],
                )
            )
    for intent in plan.get("modelIntents") or []:
        if not intent.get("enabled", True):
            continue
        variables = list(intent.get("variables") or [])
        targets = [
            str(value.get("indicatorCode"))
            for value in variables
            if value.get("indicatorCode")
        ] or [str(value) for value in intent.get("targetIndicators") or []]
        role_summary = ", ".join(
            f"{value.get('role')}={value.get('indicatorCode')}"
            for value in sorted(variables, key=lambda item: int(item.get("order") or 0))
        )
        decisions.append(
            _decision(
                "indicator_role",
                f"{intent.get('capabilityId') or intent.get('id')}: "
                + (role_summary or f"targets {', '.join(targets) if targets else 'not specified'}"),
                (
                    "needs_confirmation"
                    if intent.get("roleInferenceStatus") == "needs_confirmation"
                    else base_status
                    if variables or not inferred
                    else "needs_confirmation"
                ),
                [plan_ref],
            )
        )
        horizon = intent.get("forecastHorizon")
        if horizon:
            decisions.append(
                _decision(
                    "forecast_horizon",
                    f"{horizon.get('steps')} periods at "
                    f"{horizon.get('confidenceLevel', 0.95)} confidence",
                    base_status,
                    [plan_ref],
                )
            )
    if data_ref:
        decisions.append(
            _decision(
                "data_preparation",
                f"Approved dataset {data_ref} after "
                f"{len(data.get('operations') or [])} operation(s)",
                base_status,
                [data_ref],
            )
        )
    for model in pipeline.get("models") or []:
        variables = [
            *list(model.get("variables") or []),
            *list(model.get("dependentVariables") or []),
            *list(model.get("independentVariables") or []),
        ]
        decisions.append(
            _decision(
                "analysis_specification",
                f"{model.get('kind')} ({', '.join(dict.fromkeys(variables))})",
                base_status,
                [bundle_ref or str(model.get("id") or "")],
            )
        )
    for key, enabled in (plan.get("deliverables") or {}).items():
        if enabled:
            decisions.append(_decision("deliverable", str(key), base_status, [plan_ref]))
    for limitation in [*(plan.get("warnings") or []), *(output.get("limitations") or [])]:
        decisions.append(_decision("limitation", str(limitation), base_status, refs))
    previous = list(session.get("handoffs") or [])
    research_spec = {
        "objective": plan.get("objective"),
        "period": period,
        "geography": plan.get("geographyResolutions") or [],
        "forecastHorizons": [
            item.get("forecastHorizon")
            for item in plan.get("modelIntents") or []
            if item.get("forecastHorizon")
        ],
    }
    data_spec = {
        "sources": plan.get("dataSources") or [],
        "snapshotId": data_ref or None,
        "snapshotHash": (data.get("approvedDatasetRef") or {}).get("snapshotHash"),
        "operations": data.get("operations") or [],
    }
    analysis_spec = {
        "operations": pipeline.get("operations") or [],
        "models": pipeline.get("models") or [],
        "modelResults": pipeline.get("modelResults") or [],
        "bundle": bundle,
    }
    source_hash = _hash(
        {
            "stage": source_stage.value,
            "refs": refs,
            "research": research_spec,
            "data": data_spec,
            "analysis": analysis_spec,
            "deliverables": plan.get("deliverables") or {},
        }
    )
    return StageHandoffEnvelopeV1(
        handoff_id=f"handoff-{uuid4().hex}",
        session_id=str(session.get("id") or ""),
        source_stage=source_stage,
        source_snapshot_refs=refs,
        source_hash=source_hash,
        research_spec=research_spec,
        data_spec=data_spec,
        analysis_spec=analysis_spec,
        deliverables=dict(plan.get("deliverables") or {}),
        decisions=decisions,
        unresolved_items=[str(value) for value in plan.get("unresolvedItems") or []],
        agents=agents or [],
        supersedes_handoff_id=(str(previous[-1].get("handoffId")) if previous else None),
        created_at=datetime.now(timezone.utc),
    )


def record_stage_handoff(
    session: dict[str, Any],
    source_stage: WorkflowStage,
    *,
    agents: list[AgentRuntimeDescriptor] | None = None,
    inferred: bool = False,
) -> dict[str, Any]:
    handoff = build_stage_handoff(session, source_stage, agents=agents, inferred=inferred)
    wire = {
        "schemaVersion": handoff.schema_version,
        "handoffId": handoff.handoff_id,
        "sessionId": handoff.session_id,
        "sourceStage": handoff.source_stage.value,
        "sourceSnapshotRefs": handoff.source_snapshot_refs,
        "sourceHash": handoff.source_hash,
        "researchSpec": handoff.research_spec,
        "dataSpec": handoff.data_spec,
        "analysisSpec": handoff.analysis_spec,
        "deliverables": handoff.deliverables,
        "decisions": [
            {
                "id": item.decision_id,
                "category": item.category,
                "summary": item.summary,
                "status": item.status,
                "sourceRefs": item.source_refs,
            }
            for item in handoff.decisions
        ],
        "unresolvedItems": handoff.unresolved_items,
        "agents": [
            {
                "role": item.role,
                "authority": item.authority,
                "providerProfile": item.provider_profile,
                "modelId": item.model_id,
                "status": item.status,
                "limitations": item.limitations,
            }
            for item in handoff.agents
        ],
        "supersedesHandoffId": handoff.supersedes_handoff_id,
        "createdAt": handoff.created_at.isoformat(),
    }
    session["handoffs"] = [*(session.get("handoffs") or []), wire]
    session["currentHandoff"] = wire
    nodes = list(session.get("nodes") or [])
    nodes.append(
        {
            "id": handoff.handoff_id,
            "kind": "stage_handoff",
            "status": "completed",
            "stage": source_stage.value,
            "schemaVersion": HANDOFF_SCHEMA_VERSION,
            "inputSnapshotIds": handoff.source_snapshot_refs,
            "outputSnapshotId": handoff.source_hash,
            "supersedesNodeId": handoff.supersedes_handoff_id,
            "createdAt": handoff.created_at.isoformat(),
            "updatedAt": handoff.created_at.isoformat(),
        }
    )
    session["nodes"] = nodes
    return wire


def relevant_handoff(session: dict[str, Any], stage: WorkflowStage) -> dict[str, Any]:
    current = session.get("currentHandoff")
    handoff = (
        dict(current) if current else record_stage_handoff(session, stage, inferred=True)
    )
    pending = [
        item for item in handoff.get("decisions") or []
        if item.get("status") == "needs_confirmation"
    ]
    if pending:
        raise HandoffIncompleteError(
            "Confirm unresolved cross-stage decisions before asking this AI role: "
            + "; ".join(str(item.get("summary")) for item in pending)
        )
    return handoff


def append_stage_message(
    session: dict[str, Any],
    stage: WorkflowStage,
    role: Literal["user", "agent", "system"],
    body: str,
    *,
    target_hash: str,
    command_type: str,
    label: str,
) -> None:
    threads = dict(session.get("stageThreads") or {})
    messages = list(threads.get(stage.value) or [])
    messages.append(
        {
            "id": f"message-{uuid4().hex}",
            "stage": stage.value,
            "role": role,
            "body": body,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "targetSnapshotHash": target_hash,
            "commandType": command_type,
            "label": label,
        }
    )
    threads[stage.value] = messages
    session["stageThreads"] = threads
    if stage == WorkflowStage.PLAN:
        session["planThread"] = messages
    elif stage == WorkflowStage.OUTPUT:
        session["outputThread"] = messages
