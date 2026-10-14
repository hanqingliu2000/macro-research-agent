from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from macro_research_agent.workflow.api_schemas import (
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff import record_stage_handoff
from macro_research_agent.workflow.ports import WorkflowRepository


class WorkflowHandoffError(ValueError):
    pass


class WorkflowHandoffService:
    allowed_commands = {"confirm_decisions", "resolve_decision"}

    def __init__(self, repository: WorkflowRepository, graph_service: GraphService) -> None:
        self.repository = repository
        self.graph_service = graph_service

    def list(self, session_id: str) -> list[dict[str, Any]]:
        stored = self.repository.get(session_id)
        session = stored.session.model_dump(mode="json", by_alias=True)
        history = list(session.get("handoffs") or [])
        if history:
            return history
        wire_session = {**session, "handoffs": []}
        return [
            record_stage_handoff(
                wire_session, stored.session.active_stage, inferred=True
            )
        ]

    def execute(
        self, meta: WorkflowCommandMeta, command: dict[str, Any]
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        if meta.actor != "user":
            raise WorkflowHandoffError("Only the user may confirm cross-stage decisions.")
        command_type = str(command.get("type") or "")
        if command_type not in self.allowed_commands:
            raise WorkflowHandoffError("Unsupported handoff command.")
        stored = self.repository.require_current(meta)
        session = stored.session.model_dump(mode="json", by_alias=True)
        current = dict(session.get("currentHandoff") or {})
        if not current:
            current = record_stage_handoff(
                session, stored.session.active_stage, inferred=True
            )
        decisions = [dict(item) for item in current.get("decisions") or []]
        selected = {str(value) for value in command.get("decisionIds") or []}
        if command_type == "confirm_decisions":
            if not selected:
                raise WorkflowHandoffError("Select at least one inferred decision to confirm.")
            changed = False
            for item in decisions:
                if item.get("id") in selected:
                    if item.get("status") != "inferred":
                        raise WorkflowHandoffError(
                            "Only inferred decisions can be confirmed without a replacement value."
                        )
                    item["status"] = "confirmed"
                    changed = True
            if not changed:
                raise WorkflowHandoffError("No matching inferred decisions were found.")
        else:
            decision_id = str(command.get("decisionId") or "")
            value = str(command.get("value") or "").strip()
            if not decision_id or not value:
                raise WorkflowHandoffError("A decision ID and replacement value are required.")
            target_decision: dict[str, Any] | None = next(
                (entry for entry in decisions if entry.get("id") == decision_id), None
            )
            if target_decision is None:
                raise WorkflowHandoffError("Unknown handoff decision.")
            target_decision["summary"] = value
            target_decision["status"] = "confirmed"
        now = datetime.now(timezone.utc)
        revised = {
            **current,
            "handoffId": f"handoff-{uuid4().hex}",
            "decisions": decisions,
            "supersedesHandoffId": current.get("handoffId"),
            "createdAt": now.isoformat(),
        }
        session["handoffs"] = [*(session.get("handoffs") or []), revised]
        session["currentHandoff"] = revised
        session["nodes"] = [
            *(session.get("nodes") or []),
            {
                "id": revised["handoffId"],
                "kind": "stage_handoff",
                "status": "completed",
                "stage": session["activeStage"],
                "schemaVersion": revised.get("schemaVersion"),
                "inputSnapshotIds": revised.get("sourceSnapshotRefs") or [],
                "outputSnapshotId": revised.get("sourceHash"),
                "supersedesNodeId": current.get("handoffId"),
                "createdAt": now.isoformat(),
                "updatedAt": now.isoformat(),
            },
        ]
        session["updatedAt"] = now.isoformat()
        return self.graph_service.apply_transition(
            meta,
            command,
            WorkflowSessionDocument.model_validate(session),
        )
