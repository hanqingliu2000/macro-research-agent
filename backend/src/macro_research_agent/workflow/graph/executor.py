from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock

from pydantic import BaseModel, Field

from macro_research_agent.workflow.graph.contracts import NodeAttempt, ResearchNode
from macro_research_agent.workflow.graph.service import GraphService

NodeHandler = Callable[[ResearchNode, NodeAttempt], list[str]]


class NodeExecutionRecord(BaseModel):
    node_id: str
    attempt_id: str
    status: str
    output_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None


class NodeExecutionReport(BaseModel):
    session_id: str
    claimed: int
    completed: int
    failed: int
    records: list[NodeExecutionRecord]


class NodeExecutor:
    """Bounded local scheduler over GraphService readiness and attempt primitives."""

    def __init__(
        self,
        graph_service: GraphService,
        handlers: dict[str, NodeHandler] | None = None,
        *,
        max_concurrency: int = 4,
        max_nodes_per_run: int = 100,
    ) -> None:
        if max_concurrency < 1 or max_concurrency > 32:
            raise ValueError("Node executor concurrency must be between 1 and 32.")
        if max_nodes_per_run < 1:
            raise ValueError("Node executor run bound must be positive.")
        self.graph_service = graph_service
        self.handlers = handlers or {}
        self.max_concurrency = max_concurrency
        self.max_nodes_per_run = max_nodes_per_run
        self._run_lock = Lock()

    def register(self, capability_id: str, handler: NodeHandler) -> None:
        if capability_id in self.handlers:
            raise ValueError(f"Node handler is already registered: {capability_id}")
        self.handlers[capability_id] = handler

    def run_ready(self, session_id: str) -> NodeExecutionReport:
        records: list[NodeExecutionRecord] = []
        with self._run_lock:
            while len(records) < self.max_nodes_per_run:
                snapshot = self.graph_service.snapshot(session_id)
                ready = [
                    node
                    for node in snapshot.nodes
                    if self.graph_service.is_ready(snapshot, node)
                ]
                if not ready:
                    break
                batch = ready[
                    : min(
                        self.max_concurrency,
                        self.max_nodes_per_run - len(records),
                    )
                ]
                claimed: list[tuple[ResearchNode, NodeAttempt]] = []
                for node in batch:
                    claimed.append(
                        (
                            node,
                            self.graph_service.claim(
                                session_id,
                                node.node_id,
                                f"executor:{node.node_id}:{node.attempt}",
                                datetime.now(timezone.utc),
                            ),
                        )
                    )
                with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
                    futures = {
                        pool.submit(self._execute_claimed, node, attempt): (node, attempt)
                        for node, attempt in claimed
                    }
                    for future in as_completed(futures):
                        records.append(future.result())
        records.sort(key=lambda item: (item.node_id, item.attempt_id))
        return NodeExecutionReport(
            session_id=session_id,
            claimed=len(records),
            completed=sum(item.status == "completed" for item in records),
            failed=sum(item.status == "failed" for item in records),
            records=records,
        )

    def _execute_claimed(
        self, node: ResearchNode, attempt: NodeAttempt
    ) -> NodeExecutionRecord:
        handler_key = node.capability_id or node.kind.value
        handler = self.handlers.get(handler_key)
        if handler is None:
            error_code = "handler_unavailable"
            self.graph_service.fail(
                node.session_id,
                attempt.attempt_id,
                error_code,
                datetime.now(timezone.utc),
            )
            return NodeExecutionRecord(
                node_id=node.node_id,
                attempt_id=attempt.attempt_id,
                status="failed",
                error_code=error_code,
            )
        try:
            output_refs = handler(node, attempt)
            self.graph_service.complete(
                node.session_id,
                attempt.attempt_id,
                output_refs,
                datetime.now(timezone.utc),
            )
            return NodeExecutionRecord(
                node_id=node.node_id,
                attempt_id=attempt.attempt_id,
                status="completed",
                output_refs=output_refs,
            )
        except Exception as exc:
            error_code = f"handler_failed:{type(exc).__name__}"
            self.graph_service.fail(
                node.session_id,
                attempt.attempt_id,
                error_code,
                datetime.now(timezone.utc),
            )
            return NodeExecutionRecord(
                node_id=node.node_id,
                attempt_id=attempt.attempt_id,
                status="failed",
                error_code=error_code,
            )
