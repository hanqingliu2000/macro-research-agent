from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from macro_research_agent.agent.contracts import AgentNodeV1, AgentRunV1, identifier, utc_now
from macro_research_agent.agent.repository import AgentBudgetExceeded, AgentError, AgentRepository


class AgentStopped(RuntimeError):
    def __init__(self, message: str, code: str = "run_stopped") -> None:
        super().__init__(message)
        self.code = code


class AgentGraphService:
    def __init__(self, repository: AgentRepository) -> None:
        self.repository = repository

    def claim(
        self, session_id: str, run_id: str, kind: str, inputs: list[str]
    ) -> tuple[AgentNodeV1, bool]:
        selected: list[AgentNodeV1] = []
        reused = []

        def apply(run: AgentRunV1) -> dict[str, Any]:
            read_only = kind.startswith("explain:")
            if not read_only and run.status not in {"requested", "clarifying", "queued", "running"}:
                raise AgentStopped("The run is not executable.", "run_stopped")
            if run.pause_requested and not read_only:
                raise AgentStopped("Pause requested.", "pause_requested")
            if kind != "clarification" and not read_only and not run.authorizations:
                raise AgentError(
                    "Agent execution requires a user run authorization.", "unauthorized"
                )
            node = next(
                (
                    node
                    for node in reversed(run.nodes)
                    if node.kind == kind and node.input_refs == inputs and node.status != "stale"
                ),
                None,
            )
            if node and node.status == "completed":
                selected.append(node)
                reused.append(True)
                return {"node_id": node.node_id, "reused": True}
            if node and node.status == "running":
                raise AgentStopped("Task already owns an execution lease.", "task_leased")
            if (
                sum(other.status == "running" for other in run.nodes)
                >= run.ledger.limits.concurrency
            ):
                raise AgentStopped("Per-run task concurrency limit reached.", "concurrency_limit")
            if node and len(node.attempt_ids) >= 3:
                raise AgentStopped("Task attempt limit reached.", "task_attempt_limit")
            if node is None:
                count = run.ledger.used.get("nodes", 0)
                if count >= run.ledger.limits.nodes:
                    raise AgentBudgetExceeded("Task node budget exhausted.", "budget_exhausted")
                parents = [
                    item.node_id
                    for item in run.nodes
                    if item.status == "completed"
                    and set([*item.output_refs, *item.produced_refs]).intersection(inputs)
                ]
                if run.task_plan and not kind.startswith("route:"):
                    from macro_research_agent.agent.repository import checksum

                    route_hash = checksum(run.task_plan.model_dump(mode="json"))
                    parents.extend(
                        item.node_id
                        for item in run.nodes
                        if item.status == "completed"
                        and route_hash in item.produced_refs
                        and item.node_id not in parents
                    )
                node = AgentNodeV1(kind=kind, input_refs=inputs, depends_on=parents)
                run.nodes.append(node)
                run.ledger.used["nodes"] = count + 1
            node.status = "running"
            node.epoch = run.epoch
            node.active_attempt_id = identifier("attempt")
            node.attempt_ids.append(node.active_attempt_id)
            node.lease_until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
            if not read_only:
                run.status = "clarifying" if kind == "clarification" else "running"
                run.phase = kind.split(":")[0]
                self._clock(run)
                run.data["active_clock"] = utc_now()
            selected.append(node)
            reused.append(False)
            return {
                "node_id": node.node_id,
                "attempt_id": node.active_attempt_id,
                "inputs": inputs,
                "lease_until": node.lease_until,
                "epoch": run.epoch,
            }

        self.repository.mutate(session_id, run_id, "task.started", apply)
        return selected[0], reused[0]

    def finish(
        self,
        session_id: str,
        run_id: str,
        node: AgentNodeV1,
        outputs: list[str],
        *,
        error: dict[str, Any] | None = None,
        produced_refs: list[str] | None = None,
    ) -> bool:
        accepted = []

        def apply(run: AgentRunV1) -> dict[str, Any]:
            current = next(item for item in run.nodes if item.node_id == node.node_id)
            allowed = (
                run.epoch == node.epoch
                and current.active_attempt_id == node.active_attempt_id
                and current.status == "running"
                and run.status != "cancelled"
                and current.lease_until is not None
                and datetime.fromisoformat(current.lease_until) > datetime.now(timezone.utc)
            )
            accepted.append(allowed)
            if not allowed:
                if (
                    current.status == "running"
                    and current.active_attempt_id == node.active_attempt_id
                    and run.epoch == node.epoch
                ):
                    current.status = "failed"
                    current.lease_until = None
                    current.completed_at = utc_now()
                    if not any(other.status == "running" for other in run.nodes):
                        run.data.pop("active_clock", None)
                return {
                    "node_id": node.node_id,
                    "attempt_id": node.active_attempt_id,
                    "late_result": True,
                    "output_refs": outputs,
                }
            self._clock(run)
            current.status = "failed" if error else "completed"
            current.output_refs = [] if error else outputs
            current.produced_refs = [] if error else list(produced_refs or [])
            current.completed_at = utc_now()
            current.lease_until = None
            if run.pause_requested and not node.kind.startswith("explain:"):
                run.status = "paused"
            if not any(other.status == "running" for other in run.nodes):
                run.data.pop("active_clock", None)
            return {
                "node_id": node.node_id,
                "attempt_id": node.active_attempt_id,
                "output_refs": outputs,
                "error": error,
            }

        self.repository.mutate(
            session_id, run_id, "task.failed" if error else "task.completed", apply
        )
        return accepted[0]

    def invalidate_descendants(self, run: AgentRunV1, roots: set[str]) -> list[str]:
        affected = set(roots)
        while True:
            descendants = {
                node.node_id for node in run.nodes if set(node.depends_on).intersection(affected)
            }
            expanded = affected | descendants
            if expanded == affected:
                break
            affected = expanded
        for node in run.nodes:
            if node.node_id in affected:
                node.status = "stale"
        return sorted(affected)

    @staticmethod
    def _clock(run: AgentRunV1) -> None:
        since = run.data.get("active_clock")
        if since:
            elapsed = max(
                0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(since)).total_seconds()
            )
            run.ledger.used["active_seconds"] = run.ledger.used.get("active_seconds", 0) + min(
                60, elapsed
            )
            run.data["active_clock"] = utc_now()

    def heartbeat(self, session_id: str, run_id: str) -> None:
        def apply(run: AgentRunV1) -> dict[str, Any]:
            if run.status not in {"running", "clarifying"}:
                return {"idle": True}
            self._clock(run)
            if run.ledger.used.get("active_seconds", 0) >= run.ledger.limits.active_seconds:
                run.status = "budget_exhausted"
                run.epoch += 1
                for active in run.nodes:
                    if active.status == "running":
                        active.status = "cancelled"
                        active.lease_until = None
                run.data.pop("active_clock", None)
                return {"active_time_exhausted": True}
            for node in run.nodes:
                if node.status == "running":
                    node.lease_until = (
                        datetime.now(timezone.utc) + timedelta(seconds=60)
                    ).isoformat()
            return {"active_seconds": run.ledger.used.get("active_seconds", 0)}

        self.repository.mutate(session_id, run_id, "task.heartbeat", apply)

    def ensure_current(self, session_id: str, run_id: str) -> None:
        run = self.repository.get_run(session_id, run_id)
        if any(node.status == "running" and node.kind.startswith("explain:") for node in run.nodes):
            return
        if run.status not in {"running", "clarifying", "queued"}:
            raise AgentStopped("Execution stopped by run state.", "run_stopped")
        if run.ledger.used.get("active_seconds", 0) >= run.ledger.limits.active_seconds:
            raise AgentBudgetExceeded("Active time budget exhausted.", "budget_exhausted")
