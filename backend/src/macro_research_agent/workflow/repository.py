from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from macro_research_agent.trace.events import Actor, TraceEvent
from macro_research_agent.trace.writer import JsonlTraceWriter, redact_trace_value
from macro_research_agent.workflow.api_schemas import (
    GraphPointerChange,
    GraphTransitionPlan,
    GraphTransitionSummary,
    StoredWorkflowSession,
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowProjection,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.graph.contracts import (
    ActivePointer,
    CheckpointRecord,
    GraphEdge,
    GraphEdgeKind,
    GraphSnapshot,
    NodeAttempt,
    NodeAttemptStatus,
    NodeAuthority,
    NodeLifecycle,
    ResearchNode,
    ResearchNodeKind,
)
from macro_research_agent.workflow.graph.projection import WorkflowProjectionService
from macro_research_agent.workflow.states import ApprovalGate, WorkflowStage
from macro_research_agent.workflow.uploads import UploadedFileRecord


class WorkflowSessionNotFound(LookupError):
    pass


@dataclass(frozen=True)
class WorkflowConflict(Exception):
    message: str
    projection: WorkflowProjection


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _checksum(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _wire_document(document: WorkflowSessionDocument) -> dict[str, Any]:
    return document.model_dump(mode="json", by_alias=True)


def _snapshot_refs(document: WorkflowSessionDocument) -> dict[str, str | None]:
    payload = _wire_document(document)
    data = payload.get("data") or {}
    pipeline = payload.get("pipeline") or {}
    output = payload.get("output") or {}
    return {
        "plan": payload.get("currentPlanSnapshotId"),
        "data": data.get("activeSnapshotId"),
        "analytical_bundle": (pipeline.get("bundle") or {}).get("id"),
        "artifact": output.get("selectedArtifactId"),
    }


def _capability_receipts(
    meta: WorkflowCommandMeta,
    command: dict[str, Any],
    previous_document: WorkflowSessionDocument,
    result_document: WorkflowSessionDocument,
    graph: GraphSnapshot,
) -> list[dict[str, Any]]:
    """Describe typed stage executions without copying validated argument values."""

    command_type = str(command.get("type") or "")
    previous_refs = sorted(
        str(value) for value in _snapshot_refs(previous_document).values() if value
    )
    wire = _wire_document(result_document)
    data = wire.get("data") or {}
    pipeline = wire.get("pipeline") or {}
    output = wire.get("output") or {}
    elapsed_ms = max(
        0.0,
        (datetime.now(timezone.utc) - meta.requested_at).total_seconds() * 1000,
    )
    checkpoint_refs = {
        checkpoint.gate: checkpoint.checkpoint_id
        for checkpoint in graph.checkpoints
        if checkpoint.revoked_at is None
    }

    def receipt(
        capability_id: str,
        suffix: str,
        result_refs: list[str],
        checkpoint_ref: str | None = None,
    ) -> dict[str, Any]:
        return {
            "invocation_id": f"{meta.command_id}:{suffix}",
            "capability_id": capability_id,
            "capability_version": "1.0.0",
            "skill_id": None,
            "skill_version": None,
            "stage": meta.expected_stage.value,
            "target_snapshot_hash": meta.expected_snapshot_hash,
            "argument_checksum": _checksum(command),
            "input_refs": previous_refs,
            "result_refs": result_refs,
            "checkpoint_ref": checkpoint_ref,
            "provider_profile": "local-typed-runtime",
            "actor": meta.actor,
            "attempt": 1,
            "latency_ms": elapsed_ms,
            "status": "completed",
            "error_code": None,
        }

    receipts: list[dict[str, Any]] = []
    if command_type == "plan_next" and data.get("activeSnapshotId"):
        source_runs = data.get("sourceRuns", [])
        connector_id = (
            str(source_runs[0].get("connectorId", "local_file")) if source_runs else "local_file"
        )
        receipts.append(
            receipt(
                f"connector.{connector_id}",
                "source-acquisition",
                [str(data["activeSnapshotId"])],
                checkpoint_refs.get(ApprovalGate.RESEARCH_PLAN),
            )
        )
    elif command_type == "apply_data_operation" and data.get("activeSnapshotId"):
        receipts.append(receipt("data.prepare", "data-operation", [str(data["activeSnapshotId"])]))
    elif command_type == "commit_round_trip" and data.get("activeSnapshotId"):
        receipts.append(
            receipt("connector.local_file", "round-trip", [str(data["activeSnapshotId"])])
        )
    elif command_type == "run_pipeline":
        bundle = pipeline.get("bundle") or {}
        operation_refs = [
            str(value) for value in (bundle.get("operationSnapshotRefs") or {}).values()
        ]
        if operation_refs:
            receipts.append(
                receipt(
                    "transformation.apply",
                    "transformations",
                    operation_refs,
                    checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                )
            )
        for model_result in pipeline.get("modelResults") or []:
            kind = str(model_result.get("kind") or "")
            if kind in {"descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"}:
                receipts.append(
                    receipt(
                        f"model.{kind}",
                        f"model-{model_result.get('id')}",
                        [str(model_result.get("id"))],
                        checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                    )
                )
        code_refs = [str(item.get("id")) for item in pipeline.get("codeArtifacts") or []]
        if code_refs:
            receipts.append(
                receipt(
                    "code.generate",
                    "code",
                    code_refs,
                    checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                )
            )
        artifacts = output.get("artifacts") or []
        chart_refs = [str(item.get("id")) for item in artifacts if item.get("format") == "svg"]
        table_refs = [
            str(item.get("id")) for item in artifacts if item.get("format") in {"csv", "xlsx"}
        ]
        if chart_refs:
            receipts.append(
                receipt(
                    "artifact.chart.render",
                    "charts",
                    chart_refs,
                    checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                )
            )
        if table_refs:
            receipts.append(
                receipt(
                    "artifact.table.render",
                    "tables",
                    table_refs,
                    checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                )
            )
        report_refs = [str(item.get("id")) for item in artifacts if item.get("format") == "report"]
        if report_refs:
            receipts.append(
                receipt(
                    "artifact.report.generate",
                    "report",
                    report_refs,
                    checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                )
            )
    elif command_type == "retry_output_generation":
        artifacts = output.get("artifacts") or []
        artifact_groups = (
            (
                "artifact.chart.render",
                "charts",
                [str(item.get("id")) for item in artifacts if item.get("format") == "svg"],
            ),
            (
                "artifact.table.render",
                "tables",
                [
                    str(item.get("id"))
                    for item in artifacts
                    if item.get("format") in {"csv", "xlsx"}
                ],
            ),
            (
                "artifact.report.generate",
                "report",
                [
                    str(item.get("id"))
                    for item in artifacts
                    if item.get("format") == "report"
                ],
            ),
        )
        for capability_id, suffix, refs in artifact_groups:
            if refs:
                receipts.append(
                    receipt(
                        capability_id,
                        suffix,
                        refs,
                        checkpoint_refs.get(ApprovalGate.PIPELINE_EXECUTION),
                    )
                )
    elif command_type == "request_output_review":
        report = output.get("reviewReport") or {}
        report_refs = [str(report.get("id"))] if report.get("id") else []
        if report_refs:
            receipts.extend(
                [
                    receipt("output.review.structural", "structural-review", report_refs),
                    receipt("output.review.visual", "visual-review", report_refs),
                ]
            )
            if output.get("reportSemanticStatus") != "not_applicable":
                receipts.append(
                    receipt(
                        "output.review.semantic_report",
                        "semantic-report-review",
                        report_refs,
                    )
                )
    elif command_type == "apply_output_revision":
        revision = (output.get("revisionHistory") or [{}])[-1]
        if revision.get("acceptedPatchIds"):
            receipts.append(
                receipt(
                    "artifact.regenerate",
                    "selective-regeneration",
                    [str(item.get("id")) for item in output.get("artifacts") or []],
                )
            )
        if revision.get("acceptedDirectiveIds"):
            receipts.append(
                receipt(
                    "artifact.report.revise",
                    "report-revision",
                    [str(item.get("id")) for item in output.get("artifacts") or []],
                )
            )
        review = output.get("reviewReport") or {}
        review_refs = [str(review.get("id"))] if review.get("id") else []
        if review_refs:
            receipts.extend(
                [
                    receipt("output.review.structural", "structural-review", review_refs),
                    receipt("output.review.visual", "visual-review", review_refs),
                ]
            )
            if output.get("reportSemanticStatus") != "not_applicable":
                receipts.append(
                    receipt(
                        "output.review.semantic_report",
                        "semantic-report-review",
                        review_refs,
                    )
                )
    elif command_type == "finalize_output" and output.get("manifestArtifactId"):
        receipts.append(
            receipt(
                "manifest.freeze",
                "manifest",
                [str(output["manifestArtifactId"])],
                checkpoint_refs.get(ApprovalGate.FINAL_OUTPUTS),
            )
        )
    return receipts


class SQLiteWorkflowRepository:
    def __init__(self, database_path: Path, trace_writer: JsonlTraceWriter) -> None:
        self.database_path = database_path
        self.trace_writer = trace_writer
        self._lock = threading.RLock()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._backfill_graph()
        self.recover_traces()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_stage TEXT NOT NULL,
                    reached_stages_json TEXT NOT NULL,
                    current_snapshot_hash TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    next_trace_sequence INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS workflow_nodes (
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, node_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_commands (
                    session_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, idempotency_key),
                    UNIQUE (session_id, command_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_trace_events (
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_uploads (
                    session_id TEXT NOT NULL,
                    upload_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, upload_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_plan_snapshots (
                    session_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, snapshot_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_graph_nodes (
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, node_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_graph_edges (
                    session_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    provenance TEXT NOT NULL DEFAULT 'native',
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, edge_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_graph_attempts (
                    session_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, attempt_id),
                    UNIQUE (session_id, node_id, attempt_number),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_graph_checkpoints (
                    session_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, checkpoint_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS workflow_graph_active_pointers (
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, role),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                );
                """
            )

    @staticmethod
    def _graph_snapshot_from_connection(
        connection: sqlite3.Connection, session_id: str
    ) -> GraphSnapshot:
        node_rows = connection.execute(
            """
            SELECT document_json FROM workflow_graph_nodes
            WHERE session_id = ? ORDER BY rowid
            """,
            (session_id,),
        ).fetchall()
        edge_rows = connection.execute(
            """
            SELECT document_json FROM workflow_graph_edges
            WHERE session_id = ? ORDER BY rowid
            """,
            (session_id,),
        ).fetchall()
        attempt_rows = connection.execute(
            """
            SELECT document_json FROM workflow_graph_attempts
            WHERE session_id = ? ORDER BY node_id, attempt_number
            """,
            (session_id,),
        ).fetchall()
        checkpoint_rows = connection.execute(
            """
            SELECT document_json FROM workflow_graph_checkpoints
            WHERE session_id = ? ORDER BY rowid
            """,
            (session_id,),
        ).fetchall()
        pointer_rows = connection.execute(
            """
            SELECT document_json FROM workflow_graph_active_pointers
            WHERE session_id = ? ORDER BY role
            """,
            (session_id,),
        ).fetchall()
        return GraphSnapshot(
            session_id=session_id,
            nodes=[ResearchNode.model_validate_json(row["document_json"]) for row in node_rows],
            edges=[GraphEdge.model_validate_json(row["document_json"]) for row in edge_rows],
            attempts=[
                NodeAttempt.model_validate_json(row["document_json"]) for row in attempt_rows
            ],
            checkpoints=[
                CheckpointRecord.model_validate_json(row["document_json"])
                for row in checkpoint_rows
            ],
            active_pointers=[
                ActivePointer.model_validate_json(row["document_json"]) for row in pointer_rows
            ],
        )

    def _projection_from_row(
        self, row: sqlite3.Row, connection: sqlite3.Connection | None = None
    ) -> WorkflowProjection:
        document = WorkflowSessionDocument.model_validate_json(row["document_json"])
        fallback_status = document.status
        fallback_stage = document.active_stage
        fallback_reachable = document.reached_stages
        if connection is None:
            with self._connect() as graph_connection:
                graph = self._graph_snapshot_from_connection(
                    graph_connection, str(row["session_id"])
                )
        else:
            graph = self._graph_snapshot_from_connection(connection, str(row["session_id"]))
        facts = WorkflowProjectionService.derive(
            graph,
            fallback_status=fallback_status,
            fallback_stage=fallback_stage,
            fallback_reachable=fallback_reachable,
        )
        return WorkflowProjection(
            session_id=row["session_id"],
            status=facts.status,
            active_stage=facts.active_stage,
            reachable_stages=facts.reachable_stages,
            current_snapshot_hash=row["current_snapshot_hash"],
            current_snapshot_refs=facts.current_snapshot_refs,
            review_requirements=facts.review_requirements,
            updated_at=row["updated_at"],
        )

    def _backfill_graph(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    "SELECT session_id, document_json FROM workflow_sessions"
                ).fetchall()
                for row in rows:
                    document = WorkflowSessionDocument.model_validate_json(row["document_json"])
                    self._sync_graph(connection, str(row["session_id"]), document)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _stored_from_row(self, row: sqlite3.Row) -> StoredWorkflowSession:
        return StoredWorkflowSession(
            session=WorkflowSessionDocument.model_validate_json(row["document_json"]),
            projection=self._projection_from_row(row),
        )

    def _allocate_event(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        event_type: str,
        actor: Actor,
        payload: dict[str, Any],
    ) -> TraceEvent:
        row = connection.execute(
            "SELECT next_trace_sequence FROM workflow_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise WorkflowSessionNotFound(session_id)
        sequence = int(row["next_trace_sequence"])
        connection.execute(
            "UPDATE workflow_sessions SET next_trace_sequence = ? WHERE session_id = ?",
            (sequence + 1, session_id),
        )
        event = TraceEvent(
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            actor=actor,
            payload=redact_trace_value(payload),
        )
        connection.execute(
            "INSERT INTO workflow_trace_events(session_id, sequence, event_json) VALUES (?, ?, ?)",
            (session_id, sequence, event.model_dump_json()),
        )
        return event

    def _sync_nodes(
        self, connection: sqlite3.Connection, session_id: str, document: WorkflowSessionDocument
    ) -> None:
        for item in document.nodes:
            node_id = str(item.get("id") or item.get("node_id") or "")
            kind = str(item.get("kind") or item.get("node_kind") or "")
            status = str(item.get("status") or "")
            if not node_id or not kind or not status:
                continue
            connection.execute(
                """
                INSERT INTO workflow_nodes(session_id, node_id, kind, status, document_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, node_id) DO UPDATE SET
                    kind = excluded.kind,
                    status = excluded.status,
                    document_json = excluded.document_json
                """,
                (session_id, node_id, kind, status, _canonical_json(item)),
            )

    @staticmethod
    def _graph_edge_id(
        session_id: str,
        kind: GraphEdgeKind,
        source_node_id: str,
        target: str,
    ) -> str:
        value = f"{session_id}|{kind.value}|{source_node_id}|{target}"
        return f"edge-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _legacy_graph_node(
        session_id: str, item: dict[str, Any], fallback_time: datetime
    ) -> ResearchNode | None:
        node_id = str(item.get("id") or item.get("node_id") or "")
        kind_value = str(item.get("kind") or item.get("node_kind") or "")
        lifecycle_value = str(item.get("status") or item.get("lifecycle") or "")
        if not node_id or not kind_value or not lifecycle_value:
            return None
        try:
            kind = ResearchNodeKind(kind_value)
            lifecycle = NodeLifecycle(lifecycle_value)
        except ValueError:
            return None
        output_ref = item.get("outputSnapshotId") or item.get("output_snapshot_ref")
        input_refs = item.get("inputSnapshotIds") or item.get("input_snapshot_refs") or []
        stale_reason = item.get("staleReason") or item.get("stale_reason")
        if lifecycle == NodeLifecycle.STALE and not stale_reason:
            stale_reason = "Superseded by an accepted upstream change."
        error_code = item.get("errorCode") or item.get("error_code")
        if lifecycle == NodeLifecycle.FAILED and not error_code:
            error_code = "legacy_node_failed"
        default_checkpoint = {
            ResearchNodeKind.DATA_ACQUISITION: ApprovalGate.RESEARCH_PLAN,
            ResearchNodeKind.TRANSFORMATION_PIPELINE: ApprovalGate.PIPELINE_EXECUTION,
            ResearchNodeKind.MODEL_EXECUTION: ApprovalGate.PIPELINE_EXECUTION,
            ResearchNodeKind.OUTPUT_GENERATION: ApprovalGate.PIPELINE_EXECUTION,
            ResearchNodeKind.REPRODUCTION_MANIFEST: ApprovalGate.FINAL_OUTPUTS,
        }.get(kind)
        default_stage = {
            ResearchNodeKind.RESEARCH_REQUEST: WorkflowStage.PLAN,
            ResearchNodeKind.CLARIFICATION_BATCH: WorkflowStage.PLAN,
            ResearchNodeKind.RESEARCH_PLAN: WorkflowStage.PLAN,
            ResearchNodeKind.GEOGRAPHY_RESOLUTION: WorkflowStage.PLAN,
            ResearchNodeKind.DATA_ACQUISITION: WorkflowStage.DATA,
            ResearchNodeKind.DATA_PREPARATION: WorkflowStage.DATA,
            ResearchNodeKind.EXTERNAL_ROUND_TRIP: WorkflowStage.DATA,
            ResearchNodeKind.TRANSFORMATION_PIPELINE: WorkflowStage.TRANSFORMATION,
            ResearchNodeKind.MODEL_EXECUTION: WorkflowStage.TRANSFORMATION,
            ResearchNodeKind.STAGE_HANDOFF: None,
            ResearchNodeKind.OUTPUT_GENERATION: WorkflowStage.OUTPUT,
            ResearchNodeKind.OUTPUT_REVISION: WorkflowStage.OUTPUT,
            ResearchNodeKind.OUTPUT_COMPLIANCE_REVIEW: WorkflowStage.OUTPUT,
            ResearchNodeKind.VISUAL_ARTIFACT_REVIEW: WorkflowStage.OUTPUT,
            ResearchNodeKind.SEMANTIC_REPORT_REVIEW: WorkflowStage.OUTPUT,
            ResearchNodeKind.REPRODUCTION_MANIFEST: WorkflowStage.OUTPUT,
        }.get(kind)
        raw_stage = item.get("stage")
        stage = WorkflowStage(str(raw_stage)) if raw_stage is not None else default_stage
        authority = item.get("authority") or NodeAuthority.RECORD
        required_checkpoint = (
            None
            if authority == NodeAuthority.PROPOSAL or authority == NodeAuthority.PROPOSAL.value
            else item.get("requiredCheckpoint")
            or item.get("required_checkpoint")
            or default_checkpoint
        )
        return ResearchNode(
            session_id=session_id,
            node_id=node_id,
            kind=kind,
            lifecycle=lifecycle,
            authority=authority,
            stage=stage,
            schema_version=str(item.get("schemaVersion") or item.get("schema_version") or "1"),
            attempt=int(item.get("attempt") or 1),
            input_refs=[str(value) for value in input_refs],
            output_refs=[str(output_ref)] if output_ref else [],
            capability_id=item.get("capabilityId") or item.get("capability_id"),
            capability_version=item.get("capabilityVersion") or item.get("capability_version"),
            required_checkpoint=required_checkpoint,
            rationale=item.get("rationale"),
            stale_reason=stale_reason,
            error_code=error_code,
            created_at=item.get("createdAt") or item.get("created_at") or fallback_time,
            updated_at=item.get("updatedAt") or item.get("updated_at") or fallback_time,
        )

    @staticmethod
    def _write_graph_node(connection: sqlite3.Connection, node: ResearchNode) -> None:
        existing = connection.execute(
            """
            SELECT document_json FROM workflow_graph_nodes
            WHERE session_id = ? AND node_id = ?
            """,
            (node.session_id, node.node_id),
        ).fetchone()
        if existing is not None:
            previous = ResearchNode.model_validate_json(existing["document_json"])
            if previous.lifecycle in {NodeLifecycle.APPROVED, NodeLifecycle.COMPLETED} and (
                previous.input_refs != node.input_refs or previous.output_refs != node.output_refs
            ):
                raise ValueError(f"completed graph node references are immutable: {node.node_id}")
        connection.execute(
            """
            INSERT INTO workflow_graph_nodes(session_id, node_id, document_json)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id, node_id) DO UPDATE SET
                document_json = excluded.document_json
            """,
            (node.session_id, node.node_id, node.model_dump_json()),
        )

    def _sync_graph(
        self, connection: sqlite3.Connection, session_id: str, document: WorkflowSessionDocument
    ) -> None:
        fallback_time = document.updated_at
        nodes = [
            node
            for item in document.nodes
            if (node := self._legacy_graph_node(session_id, item, fallback_time)) is not None
        ]
        for node in nodes:
            self._write_graph_node(connection, node)

        connection.execute(
            "DELETE FROM workflow_graph_edges WHERE session_id = ? AND provenance = 'legacy_sync'",
            (session_id,),
        )
        produced_by = {
            output_ref: node.node_id for node in nodes for output_ref in node.output_refs
        }
        legacy_items = {
            str(item.get("id") or item.get("node_id") or ""): item for item in document.nodes
        }
        edges: list[GraphEdge] = []
        for node in nodes:
            item = legacy_items[node.node_id]
            parents = item.get("parentNodeIds") or item.get("parent_node_ids") or []
            dependency_ids = {str(parent) for parent in parents}
            dependency_ids.update(
                produced_by[input_ref]
                for input_ref in node.input_refs
                if input_ref in produced_by and produced_by[input_ref] != node.node_id
            )
            for parent_id in sorted(dependency_ids):
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        edge_id=self._graph_edge_id(
                            session_id, GraphEdgeKind.DEPENDS_ON, node.node_id, parent_id
                        ),
                        kind=GraphEdgeKind.DEPENDS_ON,
                        source_node_id=node.node_id,
                        target_node_id=parent_id,
                        created_at=node.updated_at,
                    )
                )
            for input_ref in node.input_refs:
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        edge_id=self._graph_edge_id(
                            session_id, GraphEdgeKind.CONSUMES, node.node_id, input_ref
                        ),
                        kind=GraphEdgeKind.CONSUMES,
                        source_node_id=node.node_id,
                        target_ref=input_ref,
                        created_at=node.updated_at,
                    )
                )
            for output_ref in node.output_refs:
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        edge_id=self._graph_edge_id(
                            session_id, GraphEdgeKind.PRODUCES, node.node_id, output_ref
                        ),
                        kind=GraphEdgeKind.PRODUCES,
                        source_node_id=node.node_id,
                        target_ref=output_ref,
                        created_at=node.updated_at,
                    )
                )
            superseded = item.get("supersedesNodeId") or item.get("supersedes_node_id")
            if superseded:
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        edge_id=self._graph_edge_id(
                            session_id,
                            GraphEdgeKind.SUPERSEDES,
                            node.node_id,
                            str(superseded),
                        ),
                        kind=GraphEdgeKind.SUPERSEDES,
                        source_node_id=node.node_id,
                        target_node_id=str(superseded),
                        created_at=node.updated_at,
                    )
                )
        for edge in edges:
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_graph_edges(
                    session_id, edge_id, provenance, document_json
                ) VALUES (?, ?, 'legacy_sync', ?)
                """,
                (session_id, edge.edge_id, edge.model_dump_json()),
            )

        payload = _wire_document(document)
        plan_snapshots = {str(item.get("id")): item for item in payload.get("planSnapshots") or []}
        approved_plan_id = payload.get("approvedPlanSnapshotId")
        pipeline = payload.get("pipeline") or {}
        bundle = pipeline.get("bundle") or {}
        output = payload.get("output") or {}
        checkpoints: dict[ApprovalGate, CheckpointRecord] = {}
        if approved_plan_id:
            approved_plan = plan_snapshots.get(str(approved_plan_id), {})
            checkpoints[ApprovalGate.RESEARCH_PLAN] = CheckpointRecord(
                session_id=session_id,
                checkpoint_id=f"checkpoint-plan-{approved_plan_id}",
                gate=ApprovalGate.RESEARCH_PLAN,
                target_hash=str(approved_plan.get("hash") or approved_plan_id),
                input_refs=[str(approved_plan_id)],
                authorized_by="legacy-confirmed-user",
                authorized_at=approved_plan.get("createdAt") or document.updated_at,
            )
        bundle_id = bundle.get("id")
        if bundle_id and pipeline.get("lastRunApprovedAt"):
            pipeline_target = _checksum(
                {
                    "operations": pipeline.get("operations") or [],
                    "models": pipeline.get("models") or [],
                    "input": bundle.get("inputDatasetId"),
                }
            )
            checkpoints[ApprovalGate.PIPELINE_EXECUTION] = CheckpointRecord(
                session_id=session_id,
                checkpoint_id=f"checkpoint-pipeline-{bundle_id}",
                gate=ApprovalGate.PIPELINE_EXECUTION,
                target_hash=pipeline_target,
                input_refs=[
                    str(value) for value in [bundle.get("inputDatasetId"), bundle_id] if value
                ],
                authorized_by="legacy-confirmed-user",
                authorized_at=pipeline["lastRunApprovedAt"],
            )
        manifest_id = output.get("manifestArtifactId")
        if manifest_id and output.get("finalizedAt"):
            checkpoints[ApprovalGate.FINAL_OUTPUTS] = CheckpointRecord(
                session_id=session_id,
                checkpoint_id=f"checkpoint-output-{manifest_id}",
                gate=ApprovalGate.FINAL_OUTPUTS,
                target_hash=str(output.get("artifactSetHash") or manifest_id),
                input_refs=[
                    str(item.get("id"))
                    for item in output.get("artifacts") or []
                    if item.get("exportSelected") and item.get("id")
                ],
                authorized_by="legacy-confirmed-user",
                authorized_at=output["finalizedAt"],
            )
        for checkpoint_record in checkpoints.values():
            connection.execute(
                """
                INSERT INTO workflow_graph_checkpoints(session_id, checkpoint_id, document_json)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, checkpoint_id) DO NOTHING
                """,
                (
                    session_id,
                    checkpoint_record.checkpoint_id,
                    checkpoint_record.model_dump_json(),
                ),
            )
        for node in nodes:
            if node.required_checkpoint is None:
                continue
            authorization_checkpoint = checkpoints.get(node.required_checkpoint)
            if authorization_checkpoint is None:
                continue
            edge = GraphEdge(
                session_id=session_id,
                edge_id=self._graph_edge_id(
                    session_id,
                    GraphEdgeKind.AUTHORIZED_BY,
                    node.node_id,
                    authorization_checkpoint.checkpoint_id,
                ),
                kind=GraphEdgeKind.AUTHORIZED_BY,
                source_node_id=node.node_id,
                target_ref=authorization_checkpoint.checkpoint_id,
                created_at=node.updated_at,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_graph_edges(
                    session_id, edge_id, provenance, document_json
                ) VALUES (?, ?, 'legacy_sync', ?)
                """,
                (session_id, edge.edge_id, edge.model_dump_json()),
            )

        prior_pointers = {
            item.role: item
            for item in self._graph_snapshot_from_connection(connection, session_id).active_pointers
        }
        connection.execute(
            "DELETE FROM workflow_graph_active_pointers WHERE session_id = ?", (session_id,)
        )
        for role, ref_id in _snapshot_refs(document).items():
            if not ref_id:
                continue
            pointer = ActivePointer(
                session_id=session_id,
                role=role,
                ref_id=ref_id,
                node_id=produced_by.get(ref_id),
                updated_at=document.updated_at,
            )
            previous = prior_pointers.get(role)
            if (
                previous
                and previous.ref_id == pointer.ref_id
                and previous.node_id == pointer.node_id
            ):
                pointer.updated_at = previous.updated_at
            connection.execute(
                """
                INSERT INTO workflow_graph_active_pointers(session_id, role, document_json)
                VALUES (?, ?, ?)
                """,
                (session_id, role, pointer.model_dump_json()),
            )

    def _sync_plan_snapshots(
        self, connection: sqlite3.Connection, session_id: str, document: WorkflowSessionDocument
    ) -> None:
        payload = _wire_document(document)
        approved_id = payload.get("approvedPlanSnapshotId")
        for snapshot in payload.get("planSnapshots") or []:
            snapshot_id = str(snapshot.get("id") or "")
            snapshot_hash = str(snapshot.get("hash") or "")
            plan = snapshot.get("plan")
            if not snapshot_id or not snapshot_hash or not isinstance(plan, dict):
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_plan_snapshots(
                    session_id, snapshot_id, snapshot_hash, plan_json, approved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    snapshot_id,
                    snapshot_hash,
                    _canonical_json(plan),
                    int(snapshot_id == approved_id),
                    str(snapshot.get("createdAt") or datetime.now(timezone.utc).isoformat()),
                ),
            )
        if approved_id:
            connection.execute(
                """
                UPDATE workflow_plan_snapshots SET approved = 1
                WHERE session_id = ? AND snapshot_id = ?
                """,
                (session_id, approved_id),
            )

    def create(self, document: WorkflowSessionDocument) -> StoredWorkflowSession:
        wire = _wire_document(document)
        snapshot_hash = _checksum(wire)
        event: TraceEvent
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_sessions(
                        session_id, title, request, status, active_stage, reached_stages_json,
                        current_snapshot_hash, document_json, created_at, updated_at, archived
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.id,
                        document.title,
                        document.request,
                        document.status.value,
                        document.active_stage.value,
                        _canonical_json([stage.value for stage in document.reached_stages]),
                        snapshot_hash,
                        _canonical_json(wire),
                        document.created_at.isoformat(),
                        document.updated_at.isoformat(),
                        int(document.archived),
                    ),
                )
                self._sync_nodes(connection, document.id, document)
                self._sync_graph(connection, document.id, document)
                self._sync_plan_snapshots(connection, document.id, document)
                event = self._allocate_event(
                    connection,
                    document.id,
                    "session.created",
                    Actor.USER,
                    {
                        "document_checksum": _checksum(wire),
                        "snapshot_hash": snapshot_hash,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.trace_writer.append(event)
        return self.get(document.id)

    def list_sessions(self) -> list[StoredWorkflowSession]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [self._stored_from_row(row) for row in rows]

    def set_deleted(self, session_id: str, deleted: bool) -> StoredWorkflowSession:
        """Recoverable deletion: preserve files, graph and audit history without advancing gates."""
        event = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM workflow_sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    raise WorkflowSessionNotFound(session_id)
                document = WorkflowSessionDocument.model_validate_json(row["document_json"])
                if document.archived != deleted:
                    document.archived = deleted
                    document.updated_at = datetime.now(timezone.utc)
                    wire = _wire_document(document)
                    connection.execute(
                        "UPDATE workflow_sessions SET archived = ?, document_json = ?, "
                        "current_snapshot_hash = ?, updated_at = ? WHERE session_id = ?",
                        (
                            int(deleted),
                            _canonical_json(wire),
                            _checksum(wire),
                            document.updated_at.isoformat(),
                            session_id,
                        ),
                    )
                    event = self._allocate_event(
                        connection,
                        session_id,
                        "session.deleted" if deleted else "session.restored",
                        Actor.USER,
                        {"recoverable": True},
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if event is not None:
            self.trace_writer.append(event)
        return self.get(session_id)

    def get(self, session_id: str) -> StoredWorkflowSession:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise WorkflowSessionNotFound(session_id)
        return self._stored_from_row(row)

    def require_current(self, meta: WorkflowCommandMeta) -> StoredWorkflowSession:
        stored = self.get(meta.session_id)
        if (
            stored.session.archived
            or stored.projection.active_stage != meta.expected_stage
            or stored.projection.current_snapshot_hash != meta.expected_snapshot_hash
        ):
            raise WorkflowConflict(
                "Workflow session changed since it was loaded.", stored.projection
            )
        return stored

    def list_nodes(self, session_id: str) -> list[dict[str, Any]]:
        self.get(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT document_json FROM workflow_nodes WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
        return [json.loads(row["document_json"]) for row in rows]

    def graph_snapshot(self, session_id: str) -> GraphSnapshot:
        self.get(session_id)
        with self._connect() as connection:
            return self._graph_snapshot_from_connection(connection, session_id)

    def get_graph_node(self, session_id: str, node_id: str) -> ResearchNode:
        self.get(session_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM workflow_graph_nodes
                WHERE session_id = ? AND node_id = ?
                """,
                (session_id, node_id),
            ).fetchone()
        if row is None:
            raise WorkflowSessionNotFound(f"{session_id}/{node_id}")
        return ResearchNode.model_validate_json(row["document_json"])

    def list_graph_attempts(self, session_id: str) -> list[NodeAttempt]:
        return self.graph_snapshot(session_id).attempts

    def save_graph_node(self, node: ResearchNode) -> ResearchNode:
        self.get(node.session_id)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._write_graph_node(connection, node)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return node

    def save_graph_edges(self, edges: list[GraphEdge]) -> None:
        if not edges:
            return
        session_id = edges[0].session_id
        if any(edge.session_id != session_id for edge in edges):
            raise ValueError("all graph edges must belong to one session")
        self.get(session_id)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for edge in edges:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO workflow_graph_edges(
                            session_id, edge_id, provenance, document_json
                        ) VALUES (?, ?, 'native', ?)
                        """,
                        (session_id, edge.edge_id, edge.model_dump_json()),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        self.get(checkpoint.session_id)
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                """
                SELECT document_json FROM workflow_graph_checkpoints
                WHERE session_id = ? AND checkpoint_id = ?
                """,
                (checkpoint.session_id, checkpoint.checkpoint_id),
            ).fetchone()
            if existing is not None:
                stored = CheckpointRecord.model_validate_json(existing["document_json"])
                if stored != checkpoint:
                    raise ValueError(
                        f"checkpoint records are immutable: {checkpoint.checkpoint_id}"
                    )
                return stored
            connection.execute(
                """
                INSERT INTO workflow_graph_checkpoints(session_id, checkpoint_id, document_json)
                VALUES (?, ?, ?)
                """,
                (
                    checkpoint.session_id,
                    checkpoint.checkpoint_id,
                    checkpoint.model_dump_json(),
                ),
            )
        return checkpoint

    def replace_active_pointers(self, session_id: str, pointers: list[ActivePointer]) -> None:
        if any(pointer.session_id != session_id for pointer in pointers):
            raise ValueError("all active pointers must belong to the requested session")
        self.get(session_id)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM workflow_graph_active_pointers WHERE session_id = ?",
                    (session_id,),
                )
                for pointer in pointers:
                    connection.execute(
                        """
                        INSERT INTO workflow_graph_active_pointers(session_id, role, document_json)
                        VALUES (?, ?, ?)
                        """,
                        (session_id, pointer.role, pointer.model_dump_json()),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def save_attempt(self, attempt: NodeAttempt) -> NodeAttempt:
        self.get(attempt.session_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_graph_attempts(
                    session_id, attempt_id, node_id, attempt_number, document_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    attempt.session_id,
                    attempt.attempt_id,
                    attempt.node_id,
                    attempt.attempt_number,
                    attempt.model_dump_json(),
                ),
            )
        return attempt

    @staticmethod
    def _graph_attempt_id(session_id: str, node_id: str, idempotency_key: str) -> str:
        value = f"{session_id}|{node_id}|{idempotency_key}"
        return f"attempt-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _graph_transition_summary(
        previous: GraphSnapshot, current: GraphSnapshot
    ) -> GraphTransitionSummary:
        previous_nodes = {item.node_id: item for item in previous.nodes}
        current_nodes = {item.node_id: item for item in current.nodes}
        previous_edges = {item.edge_id for item in previous.edges}
        previous_checkpoints = {item.checkpoint_id for item in previous.checkpoints}
        previous_pointers = {item.role: item.ref_id for item in previous.active_pointers}
        current_pointers = {item.role: item.ref_id for item in current.active_pointers}
        pointer_changes = {
            role: GraphPointerChange(
                previous_ref=previous_pointers.get(role),
                current_ref=current_pointers.get(role),
            )
            for role in sorted(previous_pointers.keys() | current_pointers.keys())
            if previous_pointers.get(role) != current_pointers.get(role)
        }
        invalidated = [
            node_id
            for node_id, node in current_nodes.items()
            if node.lifecycle == NodeLifecycle.STALE
            and (
                node_id not in previous_nodes
                or previous_nodes[node_id].lifecycle != NodeLifecycle.STALE
            )
        ]
        return GraphTransitionSummary(
            created_node_ids=sorted(current_nodes.keys() - previous_nodes.keys()),
            created_edge_ids=sorted(
                edge.edge_id for edge in current.edges if edge.edge_id not in previous_edges
            ),
            created_checkpoint_ids=sorted(
                item.checkpoint_id
                for item in current.checkpoints
                if item.checkpoint_id not in previous_checkpoints
            ),
            pointer_changes=pointer_changes,
            invalidated_node_ids=sorted(invalidated),
        )

    def claim_graph_node(
        self,
        session_id: str,
        node_id: str,
        idempotency_key: str,
        claimed_at: datetime,
        allow_retry: bool = False,
    ) -> NodeAttempt:
        from macro_research_agent.workflow.graph.service import GraphService

        attempt_id = self._graph_attempt_id(session_id, node_id, idempotency_key)
        event: TraceEvent | None = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_attempts
                    WHERE session_id = ? AND attempt_id = ?
                    """,
                    (session_id, attempt_id),
                ).fetchone()
                if existing is not None:
                    connection.rollback()
                    return NodeAttempt.model_validate_json(existing["document_json"])
                snapshot = self._graph_snapshot_from_connection(connection, session_id)
                GraphService.validate(snapshot)
                node = next((item for item in snapshot.nodes if item.node_id == node_id), None)
                if node is None:
                    raise WorkflowSessionNotFound(f"{session_id}/{node_id}")
                if node.authority != NodeAuthority.EXECUTION:
                    raise ValueError(f"graph node has no execution authority: {node_id}")
                candidate = node
                if allow_retry and node.lifecycle in {
                    NodeLifecycle.FAILED,
                    NodeLifecycle.CANCELLED,
                }:
                    candidate = node.model_copy(
                        update={
                            "lifecycle": NodeLifecycle.READY,
                            "error_code": None,
                            "updated_at": claimed_at,
                        }
                    )
                    snapshot = snapshot.model_copy(
                        update={
                            "nodes": [
                                candidate if item.node_id == node_id else item
                                for item in snapshot.nodes
                            ]
                        }
                    )
                if not GraphService.is_ready(snapshot, candidate):
                    raise ValueError(f"graph node is not ready: {node_id}")
                row = connection.execute(
                    """
                    SELECT MAX(attempt_number) AS maximum FROM workflow_graph_attempts
                    WHERE session_id = ? AND node_id = ?
                    """,
                    (session_id, node_id),
                ).fetchone()
                prior_maximum = int(row["maximum"]) if row and row["maximum"] is not None else 0
                attempt_number = prior_maximum + 1
                attempt = NodeAttempt(
                    session_id=session_id,
                    attempt_id=attempt_id,
                    node_id=node_id,
                    attempt_number=attempt_number,
                    status=NodeAttemptStatus.CLAIMED,
                    idempotency_key=idempotency_key,
                    claimed_at=claimed_at,
                )
                connection.execute(
                    """
                    INSERT INTO workflow_graph_attempts(
                        session_id, attempt_id, node_id, attempt_number, document_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        attempt_id,
                        node_id,
                        attempt_number,
                        attempt.model_dump_json(),
                    ),
                )
                claimed_node = candidate.model_copy(
                    update={
                        "lifecycle": NodeLifecycle.IN_PROGRESS,
                        "attempt": attempt_number,
                        "updated_at": claimed_at,
                        "error_code": None,
                    }
                )
                self._write_graph_node(connection, claimed_node)
                event = self._allocate_event(
                    connection,
                    session_id,
                    "graph.node_started",
                    Actor.SYSTEM,
                    {
                        "node_id": node_id,
                        "attempt_id": attempt_id,
                        "attempt_number": attempt_number,
                        "idempotency_key": idempotency_key,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        assert event is not None
        self.trace_writer.append(event)
        return attempt

    def complete_graph_attempt(
        self,
        session_id: str,
        attempt_id: str,
        output_refs: list[str],
        completed_at: datetime,
    ) -> NodeAttempt:
        event: TraceEvent | None = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_attempts
                    WHERE session_id = ? AND attempt_id = ?
                    """,
                    (session_id, attempt_id),
                ).fetchone()
                if row is None:
                    raise WorkflowSessionNotFound(f"{session_id}/{attempt_id}")
                attempt = NodeAttempt.model_validate_json(row["document_json"])
                if attempt.status == NodeAttemptStatus.COMPLETED:
                    connection.rollback()
                    return attempt
                if attempt.status != NodeAttemptStatus.CLAIMED:
                    raise ValueError(f"graph attempt is already terminal: {attempt_id}")
                node_row = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_nodes
                    WHERE session_id = ? AND node_id = ?
                    """,
                    (session_id, attempt.node_id),
                ).fetchone()
                if node_row is None:
                    raise WorkflowSessionNotFound(f"{session_id}/{attempt.node_id}")
                node = ResearchNode.model_validate_json(node_row["document_json"])
                if node.lifecycle != NodeLifecycle.IN_PROGRESS:
                    raise ValueError(f"graph node is not in progress: {node.node_id}")
                completed_attempt = attempt.model_copy(
                    update={
                        "status": NodeAttemptStatus.COMPLETED,
                        "completed_at": completed_at,
                    }
                )
                completed_node = node.model_copy(
                    update={
                        "lifecycle": NodeLifecycle.COMPLETED,
                        "output_refs": output_refs,
                        "updated_at": completed_at,
                    }
                )
                connection.execute(
                    """
                    UPDATE workflow_graph_attempts SET document_json = ?
                    WHERE session_id = ? AND attempt_id = ?
                    """,
                    (completed_attempt.model_dump_json(), session_id, attempt_id),
                )
                self._write_graph_node(connection, completed_node)
                for output_ref in output_refs:
                    edge = GraphEdge(
                        session_id=session_id,
                        edge_id=self._graph_edge_id(
                            session_id,
                            GraphEdgeKind.PRODUCES,
                            node.node_id,
                            output_ref,
                        ),
                        kind=GraphEdgeKind.PRODUCES,
                        source_node_id=node.node_id,
                        target_ref=output_ref,
                        created_at=completed_at,
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO workflow_graph_edges(
                            session_id, edge_id, provenance, document_json
                        ) VALUES (?, ?, 'native', ?)
                        """,
                        (session_id, edge.edge_id, edge.model_dump_json()),
                    )
                event = self._allocate_event(
                    connection,
                    session_id,
                    "graph.node_completed",
                    Actor.SYSTEM,
                    {
                        "node_id": node.node_id,
                        "attempt_id": attempt_id,
                        "output_refs": output_refs,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        assert event is not None
        self.trace_writer.append(event)
        return completed_attempt

    def stop_graph_attempt(
        self,
        session_id: str,
        attempt_id: str,
        status: str,
        error_code: str,
        completed_at: datetime,
    ) -> NodeAttempt:
        terminal_status = NodeAttemptStatus(status)
        if terminal_status not in {NodeAttemptStatus.FAILED, NodeAttemptStatus.CANCELLED}:
            raise ValueError("a stopped graph attempt must be failed or cancelled")
        event: TraceEvent | None = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_attempts
                    WHERE session_id = ? AND attempt_id = ?
                    """,
                    (session_id, attempt_id),
                ).fetchone()
                if row is None:
                    raise WorkflowSessionNotFound(f"{session_id}/{attempt_id}")
                attempt = NodeAttempt.model_validate_json(row["document_json"])
                if attempt.status == terminal_status:
                    connection.rollback()
                    return attempt
                if attempt.status != NodeAttemptStatus.CLAIMED:
                    raise ValueError(f"graph attempt is already terminal: {attempt_id}")
                node_row = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_nodes
                    WHERE session_id = ? AND node_id = ?
                    """,
                    (session_id, attempt.node_id),
                ).fetchone()
                assert node_row is not None
                node = ResearchNode.model_validate_json(node_row["document_json"])
                stopped_attempt = attempt.model_copy(
                    update={
                        "status": terminal_status,
                        "completed_at": completed_at,
                        "error_code": error_code,
                    }
                )
                stopped_node = node.model_copy(
                    update={
                        "lifecycle": (
                            NodeLifecycle.FAILED
                            if terminal_status == NodeAttemptStatus.FAILED
                            else NodeLifecycle.CANCELLED
                        ),
                        "error_code": (
                            error_code if terminal_status == NodeAttemptStatus.FAILED else None
                        ),
                        "updated_at": completed_at,
                    }
                )
                connection.execute(
                    """
                    UPDATE workflow_graph_attempts SET document_json = ?
                    WHERE session_id = ? AND attempt_id = ?
                    """,
                    (stopped_attempt.model_dump_json(), session_id, attempt_id),
                )
                self._write_graph_node(connection, stopped_node)
                event = self._allocate_event(
                    connection,
                    session_id,
                    f"graph.attempt_{terminal_status.value}",
                    Actor.SYSTEM,
                    {
                        "node_id": node.node_id,
                        "attempt_id": attempt_id,
                        "error_code": error_code,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        assert event is not None
        self.trace_writer.append(event)
        return stopped_attempt

    def mark_graph_nodes_stale(
        self,
        session_id: str,
        node_ids: set[str],
        invalidated_by: set[str],
        reason: str,
        changed_at: datetime,
    ) -> list[ResearchNode]:
        if not node_ids:
            return []
        changed: list[ResearchNode] = []
        event: TraceEvent | None = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                snapshot = self._graph_snapshot_from_connection(connection, session_id)
                nodes = {node.node_id: node for node in snapshot.nodes}
                missing = (node_ids | invalidated_by) - nodes.keys()
                if missing:
                    raise ValueError(f"unknown graph nodes: {sorted(missing)}")
                for node_id in sorted(node_ids):
                    node = nodes[node_id]
                    if node.lifecycle == NodeLifecycle.STALE:
                        continue
                    stale_node = node.model_copy(
                        update={
                            "lifecycle": NodeLifecycle.STALE,
                            "stale_reason": reason,
                            "updated_at": changed_at,
                        }
                    )
                    self._write_graph_node(connection, stale_node)
                    changed.append(stale_node)
                    for source_id in sorted(invalidated_by):
                        edge = GraphEdge(
                            session_id=session_id,
                            edge_id=self._graph_edge_id(
                                session_id,
                                GraphEdgeKind.INVALIDATES,
                                source_id,
                                node_id,
                            ),
                            kind=GraphEdgeKind.INVALIDATES,
                            source_node_id=source_id,
                            target_node_id=node_id,
                            created_at=changed_at,
                        )
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO workflow_graph_edges(
                                session_id, edge_id, provenance, document_json
                            ) VALUES (?, ?, 'native', ?)
                            """,
                            (session_id, edge.edge_id, edge.model_dump_json()),
                        )
                event = self._allocate_event(
                    connection,
                    session_id,
                    "graph.nodes_stale",
                    Actor.SYSTEM,
                    {
                        "invalidated_by": sorted(invalidated_by),
                        "node_ids": [node.node_id for node in changed],
                        "reason": reason,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        assert event is not None
        self.trace_writer.append(event)
        return changed

    def recover_orphaned_graph_attempts(
        self, session_id: str, cutoff: datetime, recovered_at: datetime
    ) -> list[NodeAttempt]:
        recovered: list[NodeAttempt] = []
        event: TraceEvent | None = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    """
                    SELECT document_json FROM workflow_graph_attempts
                    WHERE session_id = ? ORDER BY node_id, attempt_number
                    """,
                    (session_id,),
                ).fetchall()
                for row in rows:
                    attempt = NodeAttempt.model_validate_json(row["document_json"])
                    if attempt.status != NodeAttemptStatus.CLAIMED or attempt.claimed_at >= cutoff:
                        continue
                    orphaned = attempt.model_copy(
                        update={
                            "status": NodeAttemptStatus.ORPHANED,
                            "completed_at": recovered_at,
                            "error_code": "execution_interrupted",
                        }
                    )
                    connection.execute(
                        """
                        UPDATE workflow_graph_attempts SET document_json = ?
                        WHERE session_id = ? AND attempt_id = ?
                        """,
                        (orphaned.model_dump_json(), session_id, attempt.attempt_id),
                    )
                    node_row = connection.execute(
                        """
                        SELECT document_json FROM workflow_graph_nodes
                        WHERE session_id = ? AND node_id = ?
                        """,
                        (session_id, attempt.node_id),
                    ).fetchone()
                    if node_row is not None:
                        node = ResearchNode.model_validate_json(node_row["document_json"])
                        failed_node = node.model_copy(
                            update={
                                "lifecycle": NodeLifecycle.FAILED,
                                "error_code": "execution_interrupted",
                                "updated_at": recovered_at,
                            }
                        )
                        self._write_graph_node(connection, failed_node)
                    recovered.append(orphaned)
                if recovered:
                    event = self._allocate_event(
                        connection,
                        session_id,
                        "graph.attempts_orphaned",
                        Actor.SYSTEM,
                        {"attempt_ids": [item.attempt_id for item in recovered]},
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if event is not None:
            self.trace_writer.append(event)
        return recovered

    def replay_command(
        self, session_id: str, idempotency_key: str
    ) -> WorkflowCommandResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json FROM workflow_commands
                WHERE session_id = ? AND idempotency_key = ?
                """,
                (session_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        response = WorkflowCommandResponse.model_validate_json(row["response_json"])
        return response.model_copy(update={"idempotent_replay": True})

    def record_upload(self, record: UploadedFileRecord) -> UploadedFileRecord:
        event: TraceEvent
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if (
                    connection.execute(
                        "SELECT 1 FROM workflow_sessions WHERE session_id = ?", (record.session_id,)
                    ).fetchone()
                    is None
                ):
                    raise WorkflowSessionNotFound(record.session_id)
                connection.execute(
                    """
                    INSERT INTO workflow_uploads(session_id, upload_id, record_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        record.session_id,
                        record.upload_id,
                        record.model_dump_json(),
                        record.stored_at.isoformat(),
                    ),
                )
                event = self._allocate_event(
                    connection,
                    record.session_id,
                    "source.uploaded",
                    Actor.USER,
                    {
                        "upload_id": record.upload_id,
                        "filename": record.filename,
                        "byte_size": record.byte_size,
                        "checksum": record.checksum,
                        "tables": [
                            {
                                "name": table.name,
                                "row_count": table.row_count,
                                "columns": [column.name for column in table.columns],
                            }
                            for table in record.tables
                        ],
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.trace_writer.append(event)
        return record

    def list_uploads(self, session_id: str) -> list[UploadedFileRecord]:
        self.get(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json FROM workflow_uploads
                WHERE session_id = ? ORDER BY created_at
                """,
                (session_id,),
            ).fetchall()
        return [UploadedFileRecord.model_validate_json(row["record_json"]) for row in rows]

    def list_plan_snapshots(self, session_id: str) -> list[dict[str, Any]]:
        self.get(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_id, snapshot_hash, plan_json, approved, created_at
                FROM workflow_plan_snapshots WHERE session_id = ? ORDER BY created_at
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                "snapshot_id": row["snapshot_id"],
                "snapshot_hash": row["snapshot_hash"],
                "plan": json.loads(row["plan_json"]),
                "approved": bool(row["approved"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def commit_graph_transition(self, plan: GraphTransitionPlan) -> WorkflowCommandResponse:
        session_id = plan.meta.session_id
        events: list[TraceEvent] = []
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                prior = connection.execute(
                    """
                    SELECT response_json FROM workflow_commands
                    WHERE session_id = ? AND idempotency_key = ?
                    """,
                    (session_id, plan.meta.idempotency_key),
                ).fetchone()
                if prior is not None:
                    connection.rollback()
                    response = WorkflowCommandResponse.model_validate_json(prior["response_json"])
                    return response.model_copy(update={"idempotent_replay": True})

                row = connection.execute(
                    "SELECT * FROM workflow_sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    raise WorkflowSessionNotFound(session_id)
                projection = self._projection_from_row(row, connection)
                if (
                    bool(row["archived"])
                    or projection.active_stage != plan.meta.expected_stage
                    or projection.current_snapshot_hash != plan.meta.expected_snapshot_hash
                ):
                    raise WorkflowConflict(
                        "Workflow session changed since it was loaded.", projection
                    )
                previous_document = WorkflowSessionDocument.model_validate_json(
                    row["document_json"]
                )
                previous_graph = self._graph_snapshot_from_connection(connection, session_id)
                previous_wire = _wire_document(previous_document)
                if _checksum(previous_wire) != plan.document_patch.base_document_checksum:
                    raise WorkflowConflict(
                        "Workflow document changed before the transition plan was committed.",
                        projection,
                    )
                wire = dict(previous_wire)
                for field in plan.document_patch.remove_fields:
                    wire.pop(field, None)
                wire.update(plan.document_patch.set_fields)
                result_document = WorkflowSessionDocument.model_validate(wire)
                result_snapshot_hash = _checksum(wire)
                connection.execute(
                    """
                    UPDATE workflow_sessions SET
                        title = ?, request = ?, status = ?, active_stage = ?,
                        reached_stages_json = ?, current_snapshot_hash = ?, document_json = ?,
                        updated_at = ?, archived = ?
                    WHERE session_id = ?
                    """,
                    (
                        result_document.title,
                        result_document.request,
                        result_document.status.value,
                        result_document.active_stage.value,
                        _canonical_json([stage.value for stage in result_document.reached_stages]),
                        result_snapshot_hash,
                        _canonical_json(wire),
                        result_document.updated_at.isoformat(),
                        int(result_document.archived),
                        session_id,
                    ),
                )
                self._sync_nodes(connection, session_id, result_document)
                self._sync_graph(connection, session_id, result_document)
                self._sync_plan_snapshots(connection, session_id, result_document)
                from macro_research_agent.workflow.graph.service import GraphService

                current_graph = self._graph_snapshot_from_connection(connection, session_id)
                GraphService.validate(current_graph)
                projection_facts = WorkflowProjectionService.derive(
                    current_graph,
                    fallback_status=result_document.status,
                    fallback_stage=result_document.active_stage,
                    fallback_reachable=result_document.reached_stages,
                )
                wire.update(
                    {
                        "status": projection_facts.status.value,
                        "activeStage": projection_facts.active_stage.value,
                        "reachedStages": [
                            stage.value for stage in projection_facts.reachable_stages
                        ],
                    }
                )
                result_document = WorkflowSessionDocument.model_validate(wire)
                result_snapshot_hash = _checksum(wire)
                connection.execute(
                    """
                    UPDATE workflow_sessions SET
                        status = ?, active_stage = ?, reached_stages_json = ?,
                        current_snapshot_hash = ?, document_json = ?
                    WHERE session_id = ?
                    """,
                    (
                        result_document.status.value,
                        result_document.active_stage.value,
                        _canonical_json([stage.value for stage in result_document.reached_stages]),
                        result_snapshot_hash,
                        _canonical_json(wire),
                        session_id,
                    ),
                )
                graph_transition = self._graph_transition_summary(previous_graph, current_graph)
                updated_row = connection.execute(
                    "SELECT * FROM workflow_sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                assert updated_row is not None
                previous_refs = set(filter(None, _snapshot_refs(previous_document).values()))
                result_refs = set(filter(None, _snapshot_refs(result_document).values()))
                previous_nodes = {
                    str(item.get("id")): str(item.get("status")) for item in previous_document.nodes
                }
                legacy_invalidated_nodes = [
                    str(item.get("id"))
                    for item in result_document.nodes
                    if item.get("status") == "stale"
                    and previous_nodes.get(str(item.get("id"))) != "stale"
                ]
                invalidated_nodes = sorted(
                    set(legacy_invalidated_nodes) | set(graph_transition.invalidated_node_ids)
                )
                previous_messages = previous_wire.get("planThread") or []
                result_messages = wire.get("planThread") or []
                added_plan_messages = result_messages[len(previous_messages) :]
                response = WorkflowCommandResponse(
                    session=result_document,
                    projection=self._projection_from_row(updated_row, connection),
                    created_snapshot_refs=sorted(result_refs - previous_refs),
                    invalidated_node_ids=invalidated_nodes,
                    outcome=f"Applied {plan.command.get('type', 'workflow command')}",
                    graph_transition=graph_transition,
                )
                connection.execute(
                    """
                    INSERT INTO workflow_commands(
                        session_id, idempotency_key, command_id, response_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        plan.meta.idempotency_key,
                        plan.meta.command_id,
                        response.model_dump_json(by_alias=True),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                command_type = str(plan.command.get("type") or "workflow_command")
                event_type = {
                    "start_clarification": "plan.clarification_started",
                    "request_plan_clarification": "plan.clarification_requested",
                    "submit_clarification": "plan.drafted",
                    "propose_plan_patch": "plan.patch_proposed",
                    "apply_plan_patch": "plan.patch_applied",
                    "reject_plan_patch": "plan.patch_rejected",
                    "save_plan": "plan.saved",
                    "confirm_geography": "plan.geography_confirmed",
                    "plan_next": "plan.approved",
                    "propose_data_assistance": "data.assistant_proposed",
                    "apply_data_assistance": "data.assistant_applied",
                    "reject_data_assistance": "data.assistant_rejected",
                    "propose_analysis_assistance": "analysis.assistant_proposed",
                    "apply_analysis_assistance": "analysis.assistant_applied",
                    "reject_analysis_assistance": "analysis.assistant_rejected",
                    "run_pipeline": "pipeline.executed",
                    "retry_output_generation": "output.generation_retried",
                    "add_pipeline_operation": "pipeline.operation_added",
                    "move_pipeline_operation": "pipeline.operation_moved",
                    "toggle_pipeline_operation": "pipeline.operation_toggled",
                    "delete_pipeline_operation": "pipeline.operation_deleted",
                    "undo_pipeline_edit": "pipeline.edit_undone",
                    "update_pipeline_target": "pipeline.target_updated",
                    "update_pipeline_parameters": "pipeline.parameters_updated",
                    "add_model_job": "model.job_added",
                    "update_model_input": "model.input_updated",
                    "update_model_specification": "model.specification_updated",
                    "delete_model_job": "model.job_deleted",
                    "start_pipeline_revision": "pipeline.revision_started",
                    "select_artifact": "artifact.selected",
                    "toggle_artifact_export": "artifact.export_selection_changed",
                    "request_output_review": "output.review_completed",
                    "propose_output_revision": "output.revision_proposed",
                    "apply_output_revision": "output.revision_applied",
                    "reject_output_revision": "output.revision_rejected",
                    "finalize_output": "artifact_set.frozen",
                }.get(command_type, "command.dispatched")
                events.append(
                    self._allocate_event(
                        connection,
                        session_id,
                        event_type,
                        Actor(plan.meta.actor),
                        {
                            "command_id": plan.meta.command_id,
                            "idempotency_key": plan.meta.idempotency_key,
                            "command_type": command_type,
                            "command": plan.command,
                            "expected_snapshot_hash": plan.meta.expected_snapshot_hash,
                            "result_snapshot_hash": result_snapshot_hash,
                            "result_document_checksum": _checksum(wire),
                            "transition_plan_checksum": _checksum(plan.model_dump(mode="json")),
                            "document_patch_fields": sorted(
                                set(plan.document_patch.set_fields)
                                | set(plan.document_patch.remove_fields)
                            ),
                            "graph_transition": graph_transition.model_dump(mode="json"),
                            "added_plan_messages": added_plan_messages,
                            "approved_plan_snapshot_id": wire.get("approvedPlanSnapshotId"),
                            "model_result_ids": (
                                ((wire.get("pipeline") or {}).get("bundle") or {}).get(
                                    "modelResultIds"
                                )
                                if command_type == "run_pipeline"
                                else None
                            ),
                            "code_artifact_ids": (
                                [
                                    item.get("id")
                                    for item in (wire.get("pipeline") or {}).get(
                                        "codeArtifacts", []
                                    )
                                ]
                                if command_type == "run_pipeline"
                                else None
                            ),
                            "output_artifact_ids": (
                                [
                                    item.get("id")
                                    for item in (wire.get("output") or {}).get("artifacts", [])
                                ]
                                if command_type
                                in {"run_pipeline", "retry_output_generation", "finalize_output"}
                                else None
                            ),
                            "artifact_set_id": (wire.get("output") or {}).get("artifactSetId"),
                            "manifest_artifact_id": (wire.get("output") or {}).get(
                                "manifestArtifactId"
                            ),
                        },
                    )
                )
                for receipt_payload in _capability_receipts(
                    plan.meta,
                    plan.command,
                    previous_document,
                    result_document,
                    current_graph,
                ):
                    events.append(
                        self._allocate_event(
                            connection,
                            session_id,
                            "capability.invocation_completed",
                            Actor(plan.meta.actor),
                            receipt_payload,
                        )
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        for event in events:
            self.trace_writer.append(event)
        return response

    def trace(self, session_id: str) -> list[TraceEvent]:
        self.get(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM workflow_trace_events
                WHERE session_id = ? ORDER BY sequence
                """,
                (session_id,),
            ).fetchall()
        return [TraceEvent.model_validate_json(row["event_json"]) for row in rows]

    def record_trace_event(
        self,
        session_id: str,
        event_type: str,
        actor: Actor,
        payload: dict[str, Any],
    ) -> TraceEvent:
        self.get(session_id)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                event = self._allocate_event(connection, session_id, event_type, actor, payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.trace_writer.append(event)
        return event

    def recover_traces(self) -> None:
        with self._connect() as connection:
            rows = connection.execute("SELECT session_id FROM workflow_sessions").fetchall()
        for row in rows:
            session_id = str(row["session_id"])
            self.trace_writer.recover(session_id, self.trace(session_id))
