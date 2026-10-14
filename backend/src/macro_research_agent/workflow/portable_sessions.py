from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.api_schemas import StoredWorkflowSession
from macro_research_agent.workflow.repository import (
    SQLiteWorkflowRepository,
)
from macro_research_agent.workflow.states import SessionState

PORTABLE_SESSION_SCHEMA_VERSION = "mra-portable-session-v1"
MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000

_TABLES = (
    "workflow_sessions",
    "workflow_nodes",
    "workflow_commands",
    "workflow_trace_events",
    "workflow_uploads",
    "workflow_plan_snapshots",
    "workflow_graph_nodes",
    "workflow_graph_edges",
    "workflow_graph_attempts",
    "workflow_graph_checkpoints",
    "workflow_graph_active_pointers",
    "workflow_dataset_snapshots",
    "workflow_data_operations",
    "workflow_roundtrip_packages",
    "workflow_roundtrip_imports",
    "workflow_pipeline_runs",
    "workflow_model_results",
    "workflow_code_artifacts",
    "workflow_output_artifacts",
)


class PortableSessionError(ValueError):
    pass


class ArchiveFile(BaseModel):
    path: str
    size: int = Field(ge=0)
    checksum: str


class PortableSessionManifest(BaseModel):
    schema_version: Literal["mra-portable-session-v1"] = "mra-portable-session-v1"
    source_session_id: str
    source_status: str
    exported_at: datetime
    database_checksum: str
    files: list[ArchiveFile]


class ForkSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)


def _checksum(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _replace_session_identity(value: Any, source_id: str, target_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(source_id, target_id)
    if isinstance(value, list):
        return [_replace_session_identity(item, source_id, target_id) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_session_identity(item, source_id, target_id)
            for key, item in value.items()
        }
    return value


class PortableSessionManager:
    def __init__(
        self,
        database_path: Path,
        workflow_root: Path,
        repository: SQLiteWorkflowRepository,
    ) -> None:
        self.database_path = database_path
        self.workflow_root = workflow_root
        self.repository = repository
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _database_payload(self, session_id: str) -> dict[str, Any]:
        self.repository.get(session_id)
        tables: dict[str, list[dict[str, Any]]] = {}
        with self._connect() as connection:
            existing = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in _TABLES:
                if table not in existing:
                    tables[table] = []
                    continue
                rows = connection.execute(
                    f"SELECT * FROM {table} WHERE session_id = ? ORDER BY rowid",  # noqa: S608
                    (session_id,),
                ).fetchall()
                tables[table] = [dict(row) for row in rows]
        return {"schemaVersion": PORTABLE_SESSION_SCHEMA_VERSION, "tables": tables}

    def export(self, session_id: str) -> tuple[bytes, PortableSessionManifest]:
        stored = self.repository.get(session_id)
        database_bytes = _json_bytes(self._database_payload(session_id))
        session_root = self.workflow_root / "sessions" / session_id
        files: list[ArchiveFile] = []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("database.json", database_bytes)
            if session_root.exists():
                for path in sorted(item for item in session_root.rglob("*") if item.is_file()):
                    relative = path.relative_to(session_root).as_posix()
                    if relative == "trace.jsonl":
                        continue
                    content = path.read_bytes()
                    archive_path = f"files/{relative}"
                    archive.writestr(archive_path, content)
                    files.append(
                        ArchiveFile(path=relative, size=len(content), checksum=_checksum(content))
                    )
            manifest = PortableSessionManifest(
                source_session_id=session_id,
                source_status=stored.session.status.value,
                exported_at=datetime.now(timezone.utc),
                database_checksum=_checksum(database_bytes),
                files=files,
            )
            archive.writestr("manifest.json", manifest.model_dump_json(by_alias=True))
        return buffer.getvalue(), manifest

    @staticmethod
    def _validate_member(name: str) -> PurePosixPath:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise PortableSessionError("Archive contains an unsafe path.")
        return path

    def _read_archive(
        self, content: bytes
    ) -> tuple[PortableSessionManifest, dict[str, Any], dict[str, bytes]]:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_FILES:
                    raise PortableSessionError("Archive contains too many files.")
                total_size = sum(item.file_size for item in members)
                if total_size > MAX_ARCHIVE_BYTES:
                    raise PortableSessionError("Archive expands beyond the allowed size.")
                names = {item.filename for item in members}
                if not {"manifest.json", "database.json"}.issubset(names):
                    raise PortableSessionError("Archive manifest or database payload is missing.")
                for name in names:
                    self._validate_member(name)
                manifest = PortableSessionManifest.model_validate_json(
                    archive.read("manifest.json")
                )
                database_bytes = archive.read("database.json")
                if _checksum(database_bytes) != manifest.database_checksum:
                    raise PortableSessionError("Archive database checksum does not match.")
                database = json.loads(database_bytes)
                if database.get("schemaVersion") != PORTABLE_SESSION_SCHEMA_VERSION:
                    raise PortableSessionError("Archive database schema is not supported.")
                files: dict[str, bytes] = {}
                expected = {item.path: item for item in manifest.files}
                if len(expected) != len(manifest.files):
                    raise PortableSessionError("Archive file manifest contains duplicate paths.")
                actual_paths = {
                    name.removeprefix("files/")
                    for name in names
                    if name.startswith("files/") and not name.endswith("/")
                }
                if actual_paths != set(expected):
                    raise PortableSessionError("Archive files do not match the manifest.")
                for relative, item in expected.items():
                    self._validate_member(relative)
                    payload = archive.read(f"files/{relative}")
                    if len(payload) != item.size or _checksum(payload) != item.checksum:
                        raise PortableSessionError(
                            f"Archive file checksum does not match: {relative}"
                        )
                    files[relative] = payload
                return manifest, database, files
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValidationError) as error:
            raise PortableSessionError(
                "Portable session archive could not be validated."
            ) from error

    def import_archive(self, content: bytes) -> StoredWorkflowSession:
        manifest, database, files = self._read_archive(content)
        return self._restore(manifest, database, files, relationship="import")

    def fork(self, source_session_id: str, title: str | None = None) -> StoredWorkflowSession:
        stored = self.repository.get(source_session_id)
        if stored.session.status != SessionState.COMPLETED:
            raise PortableSessionError("Only a completed Workflow session can be continued.")
        archive, _ = self.export(source_session_id)
        manifest, database, files = self._read_archive(archive)
        return self._restore(
            manifest,
            database,
            files,
            relationship="fork",
            title=title,
            reopen=True,
        )

    def _restore(
        self,
        manifest: PortableSessionManifest,
        database: dict[str, Any],
        files: dict[str, bytes],
        *,
        relationship: Literal["import", "fork"],
        title: str | None = None,
        reopen: bool = False,
    ) -> StoredWorkflowSession:
        source_id = manifest.source_session_id
        target_id = f"workflow-session-{uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        tables = database.get("tables")
        if not isinstance(tables, dict) or any(table not in tables for table in _TABLES):
            raise PortableSessionError("Archive database tables are incomplete.")
        transformed = _replace_session_identity(tables, source_id, target_id)
        session_rows = transformed.get("workflow_sessions") or []
        if len(session_rows) != 1:
            raise PortableSessionError("Archive must contain exactly one Workflow session.")
        session_row = session_rows[0]
        document = json.loads(session_row["document_json"])
        document["id"] = target_id
        document["updatedAt"] = now
        if title:
            document["title"] = title.strip()
        elif relationship == "fork":
            document["title"] = f"{document['title']} — continued"
        document["lineage"] = {
            "relationship": relationship,
            "sourceSessionId": source_id,
            "sourceStatus": manifest.source_status,
            "sourceArchiveChecksum": manifest.database_checksum,
            "createdAt": now,
        }
        if reopen:
            self._reopen_document(document)
            self._reopen_graph_records(transformed)
        session_row.update(
            {
                "session_id": target_id,
                "title": document["title"],
                "status": document["status"],
                "active_stage": document["activeStage"],
                "updated_at": now,
                "current_snapshot_hash": _checksum(_json_bytes(document)),
                "document_json": json.dumps(
                    document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                ),
            }
        )
        target_root = self.workflow_root / "sessions" / target_id
        staging_root = Path(tempfile.mkdtemp(prefix="mra-session-import-"))
        try:
            for relative, payload in files.items():
                path = staging_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for table in _TABLES:
                        expected_columns = {
                            str(item["name"])
                            for item in connection.execute(
                                f"PRAGMA table_info({table})"  # noqa: S608
                            ).fetchall()
                        }
                        for row in transformed[table]:
                            if set(row) != expected_columns:
                                raise PortableSessionError(
                                    f"Archive table shape does not match: {table}"
                                )
                            if row.get("session_id") != target_id:
                                raise PortableSessionError(
                                    f"Archive contains a cross-session row: {table}"
                                )
                            columns = list(row)
                            placeholders = ",".join("?" for _ in columns)
                            statement = (
                                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                            )
                            connection.execute(
                                statement,  # noqa: S608
                                tuple(row[column] for column in columns),
                            )
                    target_root.parent.mkdir(parents=True, exist_ok=True)
                    if target_root.exists():
                        raise PortableSessionError("Generated session destination already exists.")
                    shutil.move(str(staging_root), str(target_root))
                    connection.commit()
                except Exception:
                    connection.rollback()
                    if target_root.exists():
                        shutil.rmtree(target_root)
                    raise
            self.repository.record_trace_event(
                target_id,
                f"session.{relationship}ed",
                Actor.USER,
                {
                    "source_session_id": source_id,
                    "source_archive_checksum": manifest.database_checksum,
                },
            )
            return self.repository.get(target_id)
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root)

    @staticmethod
    def _reopen_document(document: dict[str, Any]) -> None:
        document["status"] = SessionState.OUTPUT_REVIEW.value
        document["activeStage"] = "output"
        document.setdefault("stageHealth", {})["output"] = "current"
        output = document.setdefault("output", {})
        output.pop("finalizedAt", None)
        output.pop("manifestArtifactId", None)
        output.pop("reviewReport", None)
        output.pop("pendingProposal", None)
        output["artifacts"] = [
            {**artifact, "status": "ready"}
            for artifact in output.get("artifacts", [])
            if artifact.get("kind") != "manifest"
        ]
        for node in document.get("nodes", []):
            if node.get("kind") in {
                "output_compliance_review",
                "visual_artifact_review",
                "semantic_report_review",
                "reproduction_manifest",
            }:
                node["status"] = "stale"
                node["staleReason"] = "A continued session requires a new review and Finish gate."

    @staticmethod
    def _reopen_graph_records(tables: dict[str, list[dict[str, Any]]]) -> None:
        for row in tables.get("workflow_nodes", []):
            payload = json.loads(row["document_json"])
            if payload.get("kind") in {
                "output_compliance_review",
                "visual_artifact_review",
                "semantic_report_review",
                "reproduction_manifest",
            }:
                row["status"] = "stale"
                payload["status"] = "stale"
                payload["staleReason"] = (
                    "A continued session requires a new review and Finish gate."
                )
                row["document_json"] = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        for row in tables.get("workflow_graph_nodes", []):
            payload = json.loads(row["document_json"])
            if payload.get("kind") in {
                "output_compliance_review",
                "visual_artifact_review",
                "semantic_report_review",
                "reproduction_manifest",
            }:
                payload["lifecycle"] = "stale"
                payload["stale_reason"] = (
                    "A continued session requires a new review and Finish gate."
                )
                row["document_json"] = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        final_checkpoint_ids = {
            str(payload["checkpoint_id"])
            for row in tables.get("workflow_graph_checkpoints", [])
            if (payload := json.loads(row["document_json"])).get("gate") == "final_outputs"
        }
        tables["workflow_graph_checkpoints"] = [
            row
            for row in tables.get("workflow_graph_checkpoints", [])
            if json.loads(row["document_json"]).get("gate") != "final_outputs"
        ]
        tables["workflow_graph_edges"] = [
            row
            for row in tables.get("workflow_graph_edges", [])
            if not (
                (payload := json.loads(row["document_json"])).get("kind") == "authorized_by"
                and payload.get("target_ref") in final_checkpoint_ids
            )
        ]
