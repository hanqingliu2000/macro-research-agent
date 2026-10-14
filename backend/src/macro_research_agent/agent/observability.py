from __future__ import annotations

import json
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from macro_research_agent.agent.contracts import AgentRunV1
from macro_research_agent.agent.graph import AgentGraphService, AgentStopped
from macro_research_agent.agent.repository import AgentError, AgentRepository, checksum
from macro_research_agent.research_core.authoring import (
    CodexCommandResult,
    SubprocessCodexCommandRunner,
)
from macro_research_agent.trace.writer import redact_trace_value


class AgentAuditAdapter:
    def __init__(self, repository: AgentRepository, session_id: str, run_id: str) -> None:
        self.repository = repository
        self.session_id = session_id
        self.run_id = run_id

    def record_trace_event(
        self, session_id: str, event_type: str, actor: Any, payload: dict[str, Any]
    ) -> None:
        if session_id != self.session_id:
            raise AgentError("Audit ownership mismatch.", "ownership_violation")
        self.repository.event(
            session_id, self.run_id, event_type, payload, actor=str(getattr(actor, "value", actor))
        )


class AgentContextCapture:
    def __init__(self, repository: AgentRepository, session_id: str, run_id: str) -> None:
        self.repo, self.session_id, self.run_id = repository, session_id, run_id

    def capture(self, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key in {"rows", "dataset_rows", "underlying_rows"} and isinstance(item, list):
                    # Read evidence is separate from ordinary trace and bundles.
                    ref = self.repo.put_blob(
                        self.session_id,
                        self.run_id,
                        "context_data",
                        json.dumps(item, ensure_ascii=False).encode(),
                    )
                    result[key] = {"data_context_ref": ref["id"], "hash": ref["hash"]}
                else:
                    result[key] = self.capture(item)
            return result
        if isinstance(value, list):
            return [self.capture(item) for item in value]
        if isinstance(value, str):
            # Adapters serialize a context then may append a repair instruction.
            try:
                parsed, end = json.JSONDecoder().raw_decode(value)
                if isinstance(parsed, (dict, list)):
                    serialization = {"ensure_ascii": False, "separators": [",", ":"]}
                    for ascii_mode in (False, True):
                        for separators in ((",", ":"), (", ", ": ")):
                            if (
                                json.dumps(parsed, ensure_ascii=ascii_mode, separators=separators)
                                == value[:end]
                            ):
                                serialization = {
                                    "ensure_ascii": ascii_mode,
                                    "separators": list(separators),
                                }
                    return {
                        "serialized_json": self.capture(parsed),
                        "serialization": serialization,
                        "suffix": value[end:],
                        "original_text_hash": checksum(value),
                    }
            except (ValueError, TypeError):
                pass
        return value

    def reconstruct(self, value: Any) -> Any:
        if isinstance(value, dict):
            if "data_context_ref" in value:
                return json.loads(
                    self.repo.read_blob(
                        self.session_id, self.run_id, value["data_context_ref"], value["hash"]
                    )
                )
            if "serialized_json" in value:
                return (
                    json.dumps(
                        self.reconstruct(value["serialized_json"]),
                        ensure_ascii=value.get("serialization", {}).get("ensure_ascii", False),
                        separators=tuple(
                            value.get("serialization", {}).get("separators", [",", ":"])
                        ),
                    )
                    + value["suffix"]
                )
            return {key: self.reconstruct(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.reconstruct(item) for item in value]
        return value


class AgentAuditedHttpClient(httpx.Client):
    def record_contract_rejection(self, issues: list[dict[str, Any]], attempt: int) -> None:
        ref = self.repo.payload(
            self.session_id, self.run_id, {"issues": issues, "attempt": attempt}
        )
        self.repo.event(
            self.session_id,
            self.run_id,
            "ai.contract_rejected",
            {"role": self.role, "attempt": attempt, "details_ref": ref["id"]},
        )

    def __init__(
        self,
        repository: AgentRepository,
        session_id: str,
        run_id: str,
        role: str,
        *,
        timeout: float = 180,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(timeout=timeout, transport=transport)
        self.repo, self.session_id, self.run_id, self.role = repository, session_id, run_id, role
        self.capture = AgentContextCapture(repository, session_id, run_id)
        self.graph = AgentGraphService(repository)
        self.counts: dict[str, int] = {}

    def post(self, url: httpx.URL | str, **kwargs: Any) -> httpx.Response:
        self.graph.ensure_current(self.session_id, self.run_id)
        run = self.repo.get_run(self.session_id, self.run_id)
        node = next((node for node in reversed(run.nodes) if node.status == "running"), None)
        if node is None:
            raise AgentStopped("Model calls require a claimed task.", "task_not_claimed")
        task = node.node_id
        task_key = str(task) + ":" + self.role
        # Both transport retries and schema repair share one physical-call limit per role/task.
        count = node.physical_calls.get(self.role, 0)
        self.counts[task_key] = count
        if count >= 3:
            raise AgentStopped("Model task physical-call limit reached.", "task_attempt_limit")
        body = redact_trace_value(kwargs.get("json", {}))
        kwargs["json"] = body
        if self.role == "report_author":
            body["thinking"] = {"type": "enabled"}
        token_upper = len(json.dumps(body, ensure_ascii=False).encode()) + int(
            body.get("max_tokens", 12000)
        )
        for transport_attempt in range(3 - count):
            self.graph.ensure_current(self.session_id, self.run_id)
            request_ref = self.repo.payload(
                self.session_id, self.run_id, self.capture.capture(body), "model_request"
            )
            reservation = self.repo.reserve(
                self.session_id, self.run_id, {"model_calls": 1, "tokens": token_upper}
            )
            span_id = reservation
            self.counts[task_key] = self.counts.get(task_key, 0) + 1
            started = time.perf_counter()

            def record_call(
                current: AgentRunV1,
                captured_ref: str = request_ref["id"],
                captured_span: str = span_id,
            ) -> dict[str, Any]:
                active = next(n for n in current.nodes if n.node_id == task)
                if active.status != "running" or active.epoch != current.epoch:
                    raise AgentStopped(
                        "The task was cancelled or superseded before dispatch.", "late_result"
                    )
                consumed = active.physical_calls.get(self.role, 0)
                if consumed >= 3:
                    raise AgentStopped("Model task call limit reached.", "task_attempt_limit")
                active.physical_calls[self.role] = consumed + 1
                return {
                    "role": self.role,
                    "provider": "deepseek",
                    "model": body.get("model"),
                    "request_ref": captured_ref,
                    "request_hash": checksum(body),
                    "span_id": captured_span,
                    "reservation_id": captured_span,
                    "physical_attempt": self.counts[task_key],
                }

            self.repo.mutate(
                self.session_id, self.run_id, "ai.request_started", record_call, actor="agent"
            )
            try:
                response = super().post(url, **kwargs)
                try:
                    wire = response.json()
                except ValueError:
                    wire = {"content": response.text}
                response_ref = self.repo.payload(
                    self.session_id, self.run_id, wire, "model_response"
                )
                usage = wire.get("usage") or {} if isinstance(wire, dict) else {}
                tokens = usage.get("total_tokens")
                known_rejection = response.status_code in {400, 401, 403, 404, 422, 429}
                self.repo.settle(
                    self.session_id,
                    self.run_id,
                    reservation,
                    {"model_calls": 1, "tokens": tokens or 0},
                    unknown=[] if tokens is not None or known_rejection else ["tokens"],
                )
                self.repo.event(
                    self.session_id,
                    self.run_id,
                    "ai.request_completed" if response.is_success else "ai.request_failed",
                    {
                        "role": self.role,
                        "span_id": span_id,
                        "response_ref": response_ref["id"],
                        "usage": usage,
                        "http_status": response.status_code,
                        "provider_request_id": response.headers.get("x-request-id"),
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    },
                )
                retryable = response.status_code == 429 or response.status_code in {
                    500,
                    502,
                    503,
                    504,
                }
                if retryable and self.counts[task_key] < 3:
                    delay = min(
                        60, float(response.headers.get("retry-after", transport_attempt + 1))
                    )
                    self.repo.event(
                        self.session_id,
                        self.run_id,
                        "ai.retry_scheduled",
                        {"role": self.role, "delay_seconds": delay},
                    )
                    time.sleep(delay)
                    continue
                return response
            except httpx.TransportError:
                self.repo.settle(
                    self.session_id,
                    self.run_id,
                    reservation,
                    {"model_calls": 1},
                    unknown=["tokens"],
                )
                ref = self.repo.payload(
                    self.session_id, self.run_id, {"stack": traceback.format_exc()}, "error"
                )
                self.repo.event(
                    self.session_id,
                    self.run_id,
                    "ai.transport_failed",
                    {"span_id": span_id, "error_ref": ref["id"]},
                )
                if self.counts[task_key] >= 3:
                    raise
                time.sleep(transport_attempt + 1)
        raise AgentError("Model retry limit exhausted.", "provider_unavailable")


class AgentAuditedCodexRunner(SubprocessCodexCommandRunner):
    def __init__(self, repository: AgentRepository, session_id: str, run_id: str) -> None:
        self.repo, self.session_id, self.run_id = repository, session_id, run_id

    def run(
        self,
        command: Sequence[str],
        *,
        prompt: str,
        timeout_seconds: float,
        environment: dict[str, str],
    ) -> CodexCommandResult:
        AgentGraphService(self.repo).ensure_current(self.session_id, self.run_id)
        run = self.repo.get_run(self.session_id, self.run_id)
        active = next((node for node in reversed(run.nodes) if node.status == "running"), None)
        if active is None:
            raise AgentStopped("Review calls require a claimed task.", "task_not_claimed")

        def claim_review_call(current: AgentRunV1) -> dict[str, Any]:
            node = next(node for node in current.nodes if node.node_id == active.node_id)
            count = node.physical_calls.get("codex-local", 0)
            if count >= 3 or node.status != "running" or node.epoch != current.epoch:
                raise AgentStopped("Review task physical-call limit reached.", "task_attempt_limit")
            node.physical_calls["codex-local"] = count + 1
            return {"role": "reviewer", "provider": "codex-local", "physical_attempt": count + 1}

        self.repo.mutate(
            self.session_id, self.run_id, "ai.codex_attempt_reserved", claim_review_call
        )
        # Reserve complete context plus bounded local review usage when CLI reports no usage.
        reservation = self.repo.reserve(
            self.session_id, self.run_id, {"model_calls": 1, "tokens": 60000}
        )
        contexts: dict[str, Any] = {}
        if "--cd" in command:
            directory = Path(command[list(command).index("--cd") + 1])
            if directory.resolve().is_relative_to(self.repo.root.resolve()):
                for path in directory.glob("*context*.json"):
                    try:
                        contexts[path.name] = AgentContextCapture(
                            self.repo, self.session_id, self.run_id
                        ).capture(json.loads(path.read_text(encoding="utf-8")))
                    except ValueError:
                        contexts[path.name] = {"integrity_error": "invalid_context_json"}
        request_ref = self.repo.payload(
            self.session_id,
            self.run_id,
            {"command": list(command), "prompt": prompt, "contexts": contexts},
            "model_request",
        )
        self.repo.event(
            self.session_id,
            self.run_id,
            "ai.codex_started",
            {"request_ref": request_ref["id"], "span_id": reservation},
        )
        started = time.perf_counter()
        try:
            result = super().run(
                command, prompt=prompt, timeout_seconds=timeout_seconds, environment=environment
            )
            final_message = ""
            if "--output-last-message" in command:
                path = Path(command[list(command).index("--output-last-message") + 1])
                if path.resolve().is_relative_to(self.repo.root.resolve()) and path.exists():
                    final_message = path.read_text(encoding="utf-8")
            # CLI progress can contain private reasoning; retain only its final response/errors.
            ref = self.repo.payload(
                self.session_id,
                self.run_id,
                {
                    "returncode": result.returncode,
                    "content": final_message,
                    "errors": [
                        line for line in result.stderr.splitlines() if line.startswith("ERROR")
                    ],
                },
                "model_response",
            )
            self.repo.event(
                self.session_id,
                self.run_id,
                "ai.codex_completed",
                {
                    "response_ref": ref["id"],
                    "returncode": result.returncode,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "span_id": reservation,
                },
            )
            return result
        finally:
            self.repo.settle(
                self.session_id, self.run_id, reservation, {"model_calls": 1}, unknown=["tokens"]
            )
