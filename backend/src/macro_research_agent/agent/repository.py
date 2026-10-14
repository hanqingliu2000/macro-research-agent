"""Agent-owned transactional graph, budgets, audit and content-addressed files."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import subprocess
import sys
import threading
import zipfile
from collections.abc import Callable
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from macro_research_agent.agent.contracts import (
    AgentCommandV1,
    AgentRunV1,
    AgentTraceEventV1,
    identifier,
    utc_now,
)
from macro_research_agent.trace.writer import redact_trace_value


class AgentError(ValueError):
    def __init__(self, message: str, code: str = "agent_error") -> None:
        super().__init__(message)
        self.code = code


class AgentConflict(AgentError):
    pass


class AgentBudgetExceeded(RuntimeError):
    def __init__(self, message: str, code: str = "budget_exhausted") -> None:
        super().__init__(message)
        self.code = code


def checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


class AgentRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / "agent.sqlite3"
        self.lock = threading.RLock()
        self.build_info = self._build_info()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                    current_run_id TEXT, next_sequence INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT NOT NULL, sequence INTEGER NOT NULL, run_id TEXT NOT NULL,
                    document TEXT NOT NULL, PRIMARY KEY(session_id,sequence));
                CREATE TABLE IF NOT EXISTS commands (
                    run_id TEXT NOT NULL, key TEXT NOT NULL, command_hash TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(run_id,key));
                CREATE TABLE IF NOT EXISTS blobs (
                    blob_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
                    kind TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL,
                    metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    status TEXT NOT NULL, document TEXT NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _build_info() -> dict[str, Any]:
        versions = {}
        for name in (
            "macro-research-agent",
            "pandas",
            "statsmodels",
            "pydantic",
            "httpx",
            "fastapi",
        ):
            try:
                versions[name] = version(name)
            except PackageNotFoundError:
                versions[name] = "source-checkout"
        package = Path(__file__).resolve().parents[1]
        hashes = {
            str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in (
                package / "agent",
                package / "research_core",
                package / "workflow",
                package / "connectors",
                package / "reproduction",
            )
            for path in folder.glob("*.py")
        }
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=package.parents[2],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            commit = "unavailable"
        return {
            "application_commit": commit,
            "python": sys.version,
            "dependencies": versions,
            "implementation_hash": checksum(hashes),
            "source_hashes": hashes,
        }

    @staticmethod
    def valid_id(value: str, kind: str) -> None:
        if not re.fullmatch(rf"agent-{kind}-[a-f0-9]{{32}}", value):
            raise AgentError(f"Invalid Agent {kind} identity.", "invalid_identity")

    def get_run(self, session_id: str, run_id: str) -> AgentRunV1:
        self.valid_id(session_id, "session")
        self.valid_id(run_id, "run")
        with self.connect() as db:
            row = db.execute(
                "SELECT document FROM runs WHERE run_id=? AND session_id=?", (run_id, session_id)
            ).fetchone()
        if row is None:
            raise AgentError("Agent run was not found.", "not_found")
        return AgentRunV1.model_validate_json(row[0])

    def current_run(self, session_id: str) -> AgentRunV1:
        self.valid_id(session_id, "session")
        with self.connect() as db:
            row = db.execute(
                "SELECT current_run_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise AgentError("Agent session was not found.", "not_found")
        return self.get_run(session_id, row[0])

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def list_runs(self, session_id: str | None = None) -> list[AgentRunV1]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT document FROM runs" + (" WHERE session_id=?" if session_id else ""),
                (session_id,) if session_id else (),
            ).fetchall()
        return [AgentRunV1.model_validate_json(row[0]) for row in rows]

    def replay_command(
        self, session_id: str, run_id: str, key: str, command_hash: str
    ) -> AgentRunV1 | None:
        self.get_run(session_id, run_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT command_hash,response FROM commands WHERE run_id=? AND key=?", (run_id, key)
            ).fetchone()
        if row:
            if row[0] != command_hash:
                raise AgentConflict("Idempotency key belongs to another command.", "key_conflict")
            return AgentRunV1.model_validate_json(row[1])
        return None

    def create(
        self, request: str, *, session_id: str | None = None, parent_run_id: str | None = None
    ) -> AgentRunV1:
        session_id = session_id or identifier("session")
        self.valid_id(session_id, "session")
        run = AgentRunV1(session_id=session_id, request=request, parent_run_id=parent_run_id)
        run.data["environment"] = self.build_info
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT current_run_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if existing:
                current = self.get_run(session_id, existing[0])
                if current.status not in {"completed", "cancelled", "failed", "budget_exhausted"}:
                    raise AgentConflict("Only one Agent run may be active.", "run_active")
                if not parent_run_id:
                    raise AgentConflict(
                        "Existing sessions require an explicitly linked new run.", "parent_required"
                    )
            if parent_run_id:
                parent = self.get_run(session_id, parent_run_id)
                if parent.status not in {"completed", "cancelled", "failed", "budget_exhausted"}:
                    raise AgentConflict("Only one Agent run may be active.", "run_active")
            db.execute(
                "INSERT OR IGNORE INTO sessions(session_id,title,created_at) VALUES(?,?,?)",
                (session_id, request[:100], utc_now()),
            )
            db.execute(
                "INSERT INTO runs VALUES(?,?,?)", (run.run_id, session_id, run.model_dump_json())
            )
            db.execute(
                "UPDATE sessions SET current_run_id=? WHERE session_id=?", (run.run_id, session_id)
            )
            self._event(db, run, "run.created", "user", {"request": request})
        self.materialize(session_id)
        return run

    def new_run_command(
        self, session_id: str, parent_id: str, command: AgentCommandV1
    ) -> AgentRunV1:
        request = str(command.arguments.get("request") or "").strip()
        if not request:
            raise AgentError("A new research request is required.", "invalid_request")
        digest = checksum(command.model_dump(exclude={"expected_version"}))
        self.get_run(session_id, parent_id)
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cached = db.execute(
                "SELECT command_hash,response FROM commands WHERE run_id=? AND key=?",
                (parent_id, command.idempotency_key),
            ).fetchone()
            if cached:
                if cached[0] != digest:
                    raise AgentConflict(
                        "Idempotency key belongs to another command.", "key_conflict"
                    )
                return AgentRunV1.model_validate_json(cached[1])
            parent = AgentRunV1.model_validate_json(
                db.execute("SELECT document FROM runs WHERE run_id=?", (parent_id,)).fetchone()[0]
            )
            if parent.version != command.expected_version:
                raise AgentConflict("Parent run changed.", "version_conflict")
            if parent.status not in {"completed", "cancelled", "failed", "budget_exhausted"}:
                raise AgentConflict("Stop the active run first.", "run_active")
            current_id = db.execute(
                "SELECT current_run_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()[0]
            current = AgentRunV1.model_validate_json(
                db.execute("SELECT document FROM runs WHERE run_id=?", (current_id,)).fetchone()[0]
            )
            if current.run_id != parent_id and current.status not in {
                "completed",
                "cancelled",
                "failed",
                "budget_exhausted",
            }:
                raise AgentConflict("Only one run may be active.", "run_active")
            child = AgentRunV1(session_id=session_id, request=request, parent_run_id=parent_id)
            child.data["environment"] = self.build_info
            db.execute(
                "INSERT INTO runs VALUES(?,?,?)",
                (child.run_id, session_id, child.model_dump_json()),
            )
            db.execute(
                "UPDATE sessions SET current_run_id=? WHERE session_id=?",
                (child.run_id, session_id),
            )
            self._event(
                db,
                child,
                "run.created",
                "user",
                {
                    "parent_run_id": parent_id,
                    "command_id": command.command_id,
                    "request": request,
                    "environment": self.build_info,
                },
            )
            db.execute(
                "INSERT INTO commands VALUES(?,?,?,?)",
                (parent_id, command.idempotency_key, digest, child.model_dump_json()),
            )
        self.materialize(session_id)
        return child

    def _event(
        self,
        db: sqlite3.Connection,
        run: AgentRunV1,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> AgentTraceEventV1:
        sequence = db.execute(
            "SELECT next_sequence FROM sessions WHERE session_id=?", (run.session_id,)
        ).fetchone()[0]
        db.execute(
            "UPDATE sessions SET next_sequence=next_sequence+1 WHERE session_id=?",
            (run.session_id,),
        )
        node = next(
            (node for node in run.nodes if node.node_id == payload.get("node_id")), None
        ) or next((node for node in reversed(run.nodes) if node.status == "running"), None)
        event = AgentTraceEventV1(
            sequence=sequence,
            session_id=run.session_id,
            run_id=run.run_id,
            trace_id=run.trace_id,
            span_id=str(payload.get("span_id") or identifier("span")),
            parent_span_id=payload.get("parent_span_id")
            or (node.active_attempt_id if node else None),
            task_id=payload.get("task_id") or (node.kind if node else None),
            node_id=payload.get("node_id") or (node.node_id if node else None),
            attempt_id=payload.get("attempt_id") or (node.active_attempt_id if node else None),
            command_id=payload.get("command_id"),
            event_type=event_type,
            actor=actor,
            level="error" if "failed" in event_type or "rejected" in event_type else "info",
            payload=redact_trace_value({"execution_version": run.epoch, **payload}),
        )
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?)",
            (run.session_id, sequence, run.run_id, event.model_dump_json()),
        )
        if event.attempt_id and event_type == "task.started" and node and not payload.get("reused"):
            db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?)",
                (
                    event.attempt_id,
                    run.run_id,
                    node.node_id,
                    "running",
                    json.dumps(
                        {
                            "attempt_id": event.attempt_id,
                            "node_id": node.node_id,
                            "task": node.kind,
                            "started_at": event.occurred_at,
                            "input_refs": node.input_refs,
                            "epoch": run.epoch,
                            "first_sequence": sequence,
                        }
                    ),
                ),
            )
        if event.attempt_id and event_type in {"task.completed", "task.failed"}:
            row = db.execute(
                "SELECT document FROM attempts WHERE attempt_id=?", (event.attempt_id,)
            ).fetchone()
            if row:
                document = json.loads(row[0])
                document.update(
                    {
                        "finished_at": event.occurred_at,
                        "last_sequence": sequence,
                        "output_refs": payload.get("output_refs", []),
                        "error": event.payload.get("error"),
                        "late_result": bool(payload.get("late_result")),
                    }
                )
                status = (
                    "late_result"
                    if payload.get("late_result")
                    else "failed"
                    if event_type == "task.failed"
                    else "completed"
                )
                db.execute(
                    "UPDATE attempts SET status=?,document=? WHERE attempt_id=?",
                    (status, json.dumps(document), event.attempt_id),
                )
        return event

    @staticmethod
    def _validate_graph(before: AgentRunV1, after: AgentRunV1) -> None:
        if before.run_id != after.run_id or before.session_id != after.session_id:
            raise AgentError("Run ownership is immutable.", "graph_invariant")
        for old_auth, new_auth in zip(before.authorizations, after.authorizations, strict=False):
            if old_auth != new_auth:
                raise AgentError("Authorization versions are immutable.", "graph_invariant")
        if len(after.authorizations) < len(before.authorizations):
            raise AgentError("Authorization history cannot be deleted.", "graph_invariant")
        if before.status == "completed" and (
            before.status != after.status
            or before.task_plan != after.task_plan
            or before.analysis != after.analysis
            or before.output != after.output
            or before.authorizations != after.authorizations
        ):
            raise AgentError("Frozen scientific results cannot be changed.", "run_read_only")
        nodes = {node.node_id: node for node in after.nodes}
        if len(nodes) != len(after.nodes):
            raise AgentError("Duplicate graph nodes.", "graph_invariant")
        for old in before.nodes:
            new = nodes.get(old.node_id)
            if new is None or (
                old.status == "completed"
                and (
                    old.input_refs != new.input_refs
                    or old.output_refs != new.output_refs
                    or old.produced_refs != new.produced_refs
                )
            ):
                raise AgentError("Completed node references are immutable.", "graph_invariant")
        for name, value in before.ledger.used.items():
            if after.ledger.used.get(name, 0) < value:
                raise AgentError("Consumed budgets cannot be reset.", "budget_invariant")
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node_id: str) -> None:
            if node_id in visiting or node_id not in nodes:
                raise AgentError("Graph cycle or dangling dependency.", "graph_invariant")
            if node_id in visited:
                return
            visiting.add(node_id)
            for parent in nodes[node_id].depends_on:
                walk(parent)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in nodes:
            walk(node_id)

    def mutate(
        self,
        session_id: str,
        run_id: str,
        event_type: str,
        change: Callable[[AgentRunV1], dict[str, Any] | None],
        *,
        actor: str = "system",
        expected_version: int | None = None,
        key: str | None = None,
        command_hash: str = "",
    ) -> AgentRunV1:
        self.valid_id(session_id, "session")
        self.valid_id(run_id, "run")
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if key:
                replay = db.execute(
                    "SELECT command_hash,response FROM commands WHERE run_id=? AND key=?",
                    (run_id, key),
                ).fetchone()
                if replay:
                    if replay[0] != command_hash:
                        raise AgentConflict(
                            "Idempotency key belongs to another command.", "key_conflict"
                        )
                    return AgentRunV1.model_validate_json(replay[1])
            row = db.execute(
                "SELECT document FROM runs WHERE run_id=? AND session_id=?", (run_id, session_id)
            ).fetchone()
            if row is None:
                raise AgentError("Agent run was not found.", "not_found")
            run = AgentRunV1.model_validate_json(row[0])
            if expected_version is not None and expected_version != run.version:
                raise AgentConflict(
                    "The run changed; reload its current version.", "version_conflict"
                )
            before = deepcopy(run)
            payload = change(run) or {}
            if run.ledger != before.ledger and run.ledger.version <= before.ledger.version:
                run.ledger.version = before.ledger.version + 1
            self._validate_graph(before, run)
            run.version += 1
            run.updated_at = utc_now()
            payload = {
                "before_status": before.status,
                "after_status": run.status,
                "before_phase": before.phase,
                "after_phase": run.phase,
                **payload,
            }
            db.execute("UPDATE runs SET document=? WHERE run_id=?", (run.model_dump_json(), run_id))
            self._event(db, run, event_type, actor, payload)
            if key:
                db.execute(
                    "INSERT INTO commands VALUES(?,?,?,?)",
                    (run_id, key, command_hash, run.model_dump_json()),
                )
        self.materialize(session_id)
        return run

    def event(
        self, session_id: str, run_id: str, kind: str, payload: dict[str, Any], actor: str = "agent"
    ) -> None:
        self.mutate(session_id, run_id, kind, lambda run: payload, actor=actor)

    def reserve(self, session_id: str, run_id: str, costs: dict[str, float]) -> str:
        reservation_id = identifier("reservation")

        def apply(run: AgentRunV1) -> dict[str, Any]:
            limits = run.ledger.limits.model_dump()
            for name, value in costs.items():
                if value < 0 or name not in limits:
                    raise AgentError("Invalid budget reservation.", "budget_invalid")
                pending = sum(item.get(name, 0) for item in run.ledger.reservations.values())
                if run.ledger.used.get(name, 0) + pending + value > limits[name]:
                    raise AgentBudgetExceeded(
                        f"Agent budget exhausted: {name}.", "budget_exhausted"
                    )
            run.ledger.reservations[reservation_id] = costs
            return {"reservation_id": reservation_id, "costs": costs}

        self.mutate(session_id, run_id, "budget.reserved", apply)
        return reservation_id

    def settle(
        self,
        session_id: str,
        run_id: str,
        reservation_id: str,
        actual: dict[str, float],
        *,
        unknown: list[str] | None = None,
    ) -> None:
        def apply(run: AgentRunV1) -> dict[str, Any]:
            reservation = run.ledger.reservations.get(reservation_id)
            if reservation is None:
                return {"reservation_id": reservation_id, "replay": True}
            if any(value < 0 for value in actual.values()):
                raise AgentError("Actual use cannot be negative.", "budget_invalid")
            for name in reservation:
                if name not in (unknown or []):
                    run.ledger.used[name] = run.ledger.used.get(name, 0) + actual.get(
                        name, reservation[name]
                    )
            retained = {
                name: value for name, value in reservation.items() if name in (unknown or [])
            }
            if retained:
                run.ledger.reservations[reservation_id] = retained
            else:
                run.ledger.reservations.pop(reservation_id)
            return {"reservation_id": reservation_id, "actual": actual, "unknown": unknown or []}

        self.mutate(session_id, run_id, "budget.settled", apply)

    def put_blob(
        self,
        session_id: str,
        run_id: str,
        kind: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.get_run(session_id, run_id)
        digest = hashlib.sha256(content).hexdigest()
        blob_id = identifier("blob")
        directory = self.root / "sessions" / session_id / run_id / "blobs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / digest
        if not path.exists():
            temporary = directory / f".{blob_id}.pending"
            temporary.write_bytes(content)
            temporary.replace(path)
        result = {"id": blob_id, "kind": kind, "hash": "sha256:" + digest, **(metadata or {})}
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO blobs VALUES(?,?,?,?,?,?,?)",
                (
                    blob_id,
                    session_id,
                    run_id,
                    kind,
                    str(path.relative_to(self.root)),
                    result["hash"],
                    json.dumps(result),
                ),
            )
        return result

    def payload(
        self, session_id: str, run_id: str, value: Any, kind: str = "diagnostic"
    ) -> dict[str, Any]:
        safe = redact_trace_value(value)
        return self.put_blob(
            session_id, run_id, kind, json.dumps(safe, ensure_ascii=False).encode()
        )

    def blobs(self, session_id: str, run_id: str) -> list[dict[str, Any]]:
        self.get_run(session_id, run_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT metadata FROM blobs WHERE session_id=? AND run_id=?", (session_id, run_id)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_blob(
        self, session_id: str, run_id: str, blob_id: str, expected_hash: str | None = None
    ) -> bytes:
        self.get_run(session_id, run_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM blobs WHERE blob_id=? AND session_id=? AND run_id=?",
                (blob_id, session_id, run_id),
            ).fetchone()
        if row is None:
            raise AgentError("Agent payload was not found.", "not_found")
        path = (self.root / row["path"]).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise AgentError("Payload ownership failed.", "ownership_violation")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise AgentError("Diagnostic evidence is missing.", "evidence_missing") from error
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if digest != row["hash"] or (expected_hash and expected_hash != digest):
            raise AgentError("Payload checksum failed.", "evidence_corrupt")
        return bytes(content)

    def events(
        self,
        session_id: str,
        run_id: str | None = None,
        *,
        after: int = 0,
        limit: int = 200,
        event_type: str | None = None,
        role: str | None = None,
        task_id: str | None = None,
        attempt_id: str | None = None,
        error_code: str | None = None,
    ) -> list[dict[str, Any]]:
        self.current_run(session_id)
        clauses, arguments = ["session_id=?", "sequence>?"], [session_id, after]
        if run_id:
            self.get_run(session_id, run_id)
            clauses.append("run_id=?")
            arguments.append(run_id)
        query = "SELECT document FROM events WHERE " + " AND ".join(clauses) + " ORDER BY sequence"
        with self.connect() as db:
            rows = db.execute(query, arguments).fetchall()
        events = [json.loads(row[0]) for row in rows]
        if event_type:
            events = [event for event in events if event_type in event["event_type"]]
        if role:
            events = [event for event in events if event["payload"].get("role") == role]
        if task_id:
            events = [event for event in events if task_id in str(event["task_id"])]
        if attempt_id:
            events = [event for event in events if event["attempt_id"] == attempt_id]
        if error_code:
            events = [event for event in events if error_code in json.dumps(event["payload"])]
        return events[: min(max(1, limit), 1000)]

    def materialize(self, session_id: str) -> None:
        # SQL is authoritative; a torn JSONL projection is safely reconstructed in full.
        path = self.root / "sessions" / session_id / "trace.jsonl"
        try:
            with self.lock, self.connect() as db:
                rows = db.execute(
                    "SELECT document FROM events WHERE session_id=? ORDER BY sequence",
                    (session_id,),
                ).fetchall()
                path.parent.mkdir(parents=True, exist_ok=True)
                pending = path.with_suffix(".pending")
                pending.write_text("".join(row[0] + "\n" for row in rows), encoding="utf-8")
                pending.replace(path)
        except OSError:
            # No durable event is lost. Recovery runs from SQL on startup/on next write.
            return

    def recover(self) -> None:
        for run in self.list_runs():
            if run.status in {"running", "queued"} or any(
                node.status == "running" for node in run.nodes
            ):

                def pause(current: AgentRunV1) -> dict[str, Any]:
                    if current.status not in {"completed", "cancelled"}:
                        current.status = "paused"
                    current.epoch += 1
                    current.data.pop("active_clock", None)
                    for node in current.nodes:
                        if node.status == "running":
                            node.status = "failed"
                            node.lease_until = None
                    return {"reason": "process_restart", "counters_preserved": True}

                self.mutate(run.session_id, run.run_id, "run.recovered", pause)
            self.materialize(run.session_id)

    def diagnostics(self, session_id: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(session_id, run_id)
        issues = []
        blobs = self.blobs(session_id, run_id)
        for blob in blobs:
            try:
                self.read_blob(session_id, run_id, blob["id"], blob["hash"])
            except AgentError as error:
                issues.append({"blob_id": blob["id"], "code": error.code})
        with self.connect() as db:
            events = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT document FROM events WHERE session_id=? AND run_id=? ORDER BY sequence",
                    (session_id, run_id),
                )
            ]
            attempts = [
                dict(json.loads(row["document"]), status=row["status"])
                for row in db.execute(
                    "SELECT document,status FROM attempts WHERE run_id=?", (run_id,)
                )
            ]
        known_blobs = {item["id"] for item in blobs}

        def referenced(value: Any) -> set[str]:
            if isinstance(value, str):
                return {value} if value.startswith("agent-blob-") else set()
            if isinstance(value, dict):
                return set().union(*(referenced(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(referenced(item) for item in value))
            return set()

        for missing in referenced(run.model_dump()) - known_blobs:
            issues.append({"blob_id": missing, "code": "broken_reference"})
        for attempt in attempts:
            if attempt["status"] == "running" and not any(
                node.status == "running" and node.active_attempt_id == attempt["attempt_id"]
                for node in run.nodes
            ):
                issues.append({"attempt_id": attempt["attempt_id"], "code": "incomplete_attempt"})
        model_events = [
            e for e in events if e["event_type"] in {"ai.request_completed", "ai.request_failed"}
        ]
        tool_events = [e for e in events if e["event_type"].startswith("connector.")]
        return {
            "run": run.model_dump(mode="json"),
            "events": events,
            "payloads": blobs,
            "attempts": attempts,
            "integrity_issues": issues,
            "metrics": {
                "events": len(events),
                "errors": sum(e["level"] == "error" for e in events),
                "budget": run.ledger.model_dump(mode="json"),
                "model_latency_ms": sum(e["payload"].get("latency_ms", 0) for e in model_events),
                "format_repairs": sum("contract_rejected" in e["event_type"] for e in events),
                "tool_failures": sum(e["level"] == "error" for e in tool_events),
                "no_progress_stops": sum(
                    (e["payload"].get("error") or {}).get("code") == "no_progress" for e in events
                ),
                "review_rounds": run.ledger.used.get("formal_reviews", 0),
            },
        }

    def attempt(self, session_id: str, run_id: str, attempt_id: str) -> dict[str, Any]:
        diagnostics = self.diagnostics(session_id, run_id)
        found = next(
            (item for item in diagnostics["attempts"] if item["attempt_id"] == attempt_id), None
        )
        if found is None:
            raise AgentError("Attempt was not found in this run.", "not_found")
        return {
            "attempt": found,
            "events": [e for e in diagnostics["events"] if e["attempt_id"] == attempt_id],
            "payloads": diagnostics["payloads"],
        }

    def debug_bundle(self, session_id: str, run_id: str) -> bytes:
        diagnostics = self.diagnostics(session_id, run_id)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("diagnostics.json", json.dumps(diagnostics, ensure_ascii=False))
            for blob in diagnostics["payloads"]:
                if blob["kind"] in {"diagnostic", "model_request", "model_response", "error"}:
                    try:
                        package.writestr(
                            f"payloads/{blob['id']}.json",
                            self.read_blob(session_id, run_id, blob["id"]),
                        )
                    except AgentError:
                        continue
        return stream.getvalue()
