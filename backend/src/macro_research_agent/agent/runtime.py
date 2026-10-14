from __future__ import annotations

import asyncio
import json
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.agent.acquisition import (
    acquire_public,
    canonical_indicator,
    connector_query,
    local_frame,
    normalize_local,
)
from macro_research_agent.agent.contracts import (
    AgentCommandV1,
    AgentInterventionV1,
    AgentRunEnvelopeV1,
    AgentRunV1,
    AgentTaskPlanV1,
    identifier,
    utc_now,
)
from macro_research_agent.agent.data_access import (
    AgentModelDataAccess,
    read_snapshot,
    write_snapshot,
)
from macro_research_agent.agent.delivery import AgentDelivery
from macro_research_agent.agent.graph import AgentGraphService, AgentStopped
from macro_research_agent.agent.providers import (
    AgentAssessment,
    AgentExplanation,
    DeepSeekAgentProvider,
    model_job,
    plan_scope,
    validate_route,
)
from macro_research_agent.agent.recovery import EVIDENCE_STOP_CODES, RETRY_CODES, recovery_advice
from macro_research_agent.agent.repository import (
    AgentBudgetExceeded,
    AgentError,
    AgentRepository,
    checksum,
)
from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.config import Settings
from macro_research_agent.connectors.registry import connector_catalog
from macro_research_agent.knowledge.planning_source_index import PlanningSourceIndex
from macro_research_agent.research_core.cleaning import clean_statistical_frame
from macro_research_agent.research_core.data_access import ResearchStage
from macro_research_agent.research_core.delivery_evidence import report_result_facts
from macro_research_agent.research_core.numerics import (
    CANONICAL_KEYS,
    SUPPORTED_MODELS,
    evaluate_typed_model_frame,
    validate_model_job,
)
from macro_research_agent.research_core.presentation_evidence import PRESENTATION_PREREQUISITE_RULES
from macro_research_agent.research_core.transforms import (
    SUPPORTED_TRANSFORMATIONS,
    FrameTransformEngine,
)


class AgentRuntime:
    def __init__(
        self,
        repository: AgentRepository,
        settings: Settings,
        registry: CapabilityRegistry,
        source_index: PlanningSourceIndex,
        *,
        autorun: bool = True,
    ) -> None:
        self.repo, self.settings, self.registry = repository, settings, registry
        self.graph = AgentGraphService(repository)
        self.provider: Any = DeepSeekAgentProvider(repository, settings, registry, source_index)
        self.autorun = autorun
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-run")
        self.futures: dict[str, Future[None]] = {}
        self.lock = threading.RLock()
        self.closed = False
        self.delivery_ports: dict[str, Any] = {}
        self.repo.recover()

    def close(self) -> None:
        self.closed = True
        for run in self.repo.list_runs():
            if run.status in {"running", "queued"}:
                self.repo.mutate(
                    run.session_id,
                    run.run_id,
                    "run.shutdown_paused",
                    lambda r: setattr(r, "pause_requested", True),
                )
        self.pool.shutdown(wait=False, cancel_futures=True)

    def schedule(self, run: AgentRunV1) -> None:
        if not self.autorun or self.closed:
            return
        with self.lock:
            active = self.futures.get(run.run_id)
            if active is None or active.done():
                self.futures[run.run_id] = self.pool.submit(
                    self.execute, run.session_id, run.run_id
                )

                def continue_queued(_: Future[None]) -> None:
                    if not self.closed:
                        latest = self.repo.get_run(run.session_id, run.run_id)
                        if latest.status == "queued":
                            self.schedule(latest)

                self.futures[run.run_id].add_done_callback(continue_queued)

    def create(self, request: str, *, defer_clarification: bool = False) -> AgentRunV1:
        if not request.strip():
            raise AgentError("Research request cannot be empty.", "invalid_request")
        run = self.repo.create(request.strip())
        if defer_clarification:
            run = self.repo.mutate(
                run.session_id,
                run.run_id,
                "inputs.pending",
                lambda current: current.data.update({"inputs_pending": True}),
            )
        else:
            self.schedule(run)
        return run

    def upload(self, run: AgentRunV1, name: str, content: bytes) -> AgentRunV1:
        if run.status != "requested" or not run.data.get("inputs_pending"):
            raise AgentError("Attach inputs before clarification starts.", "inputs_locked")
        if len(content) > self.settings.max_upload_mb * 1024 * 1024:
            raise AgentError("Attachment exceeds the configured size limit.", "upload_too_large")
        frame = local_frame(name, content)
        ref = self.repo.put_blob(
            run.session_id,
            run.run_id,
            "upload",
            content,
            {"name": name, "classification": "user_supplied"},
        )
        snapshot = write_snapshot(
            self.repo,
            run.session_id,
            run.run_id,
            frame,
            classification="user_supplied",
            provenance={"upload": ref["id"]},
        )
        return self.repo.mutate(
            run.session_id,
            run.run_id,
            "attachment.inspected",
            lambda current: current.attachments.append(
                {**ref, "snapshot_ref": snapshot["id"], "row_count": len(frame)}
            ),
            actor="user",
        )

    def command(self, session_id: str, run_id: str, command: AgentCommandV1) -> AgentRunV1:
        arguments = command.arguments
        command_hash = checksum(command.model_dump(exclude={"expected_version"}))
        replay = self.repo.replay_command(session_id, run_id, command.idempotency_key, command_hash)
        if replay:
            return replay
        if command.type == "new_run":
            child = self.repo.new_run_command(session_id, run_id, command)
            self.schedule(child)
            return child
        manifest_ref = None
        if command.type == "finalize":
            snapshot = self.repo.get_run(session_id, run_id)
            self._validate_finish(snapshot, arguments)
            for artifact in snapshot.output["candidate"]["artifacts"]:
                self.repo.read_blob(session_id, run_id, artifact["id"], artifact["hash"])
            manifest_ref = self.repo.payload(
                session_id,
                run_id,
                {
                    "schema_version": "agent-reproduction-manifest-v1",
                    "run_id": run_id,
                    "request": snapshot.request,
                    "authorizations": [a.model_dump(mode="json") for a in snapshot.authorizations],
                    "task_plan": snapshot.task_plan.model_dump(mode="json")
                    if snapshot.task_plan
                    else None,
                    "snapshots": snapshot.data,
                    "analysis": snapshot.analysis,
                    "artifacts": snapshot.output["candidate"]["artifacts"],
                    "artifact_set_hash": snapshot.output["candidate"]["artifact_set_hash"],
                    "self_checks": snapshot.output["candidate"]["self_checks"],
                    "review": snapshot.output["candidate"]["review"],
                    "budget": snapshot.ledger.model_dump(mode="json"),
                    "finalized_by": "user",
                    "finalized_at": utc_now(),
                },
                "manifest",
            )

        def apply(run: AgentRunV1) -> dict[str, Any]:
            kind = command.type
            if run.status in {"completed", "cancelled"} and kind not in {"message", "new_run"}:
                raise AgentError(
                    "Finished runs are immutable; start a linked run.", "run_read_only"
                )
            if kind == "start":
                if run.status != "requested":
                    raise AgentError("Inputs were already submitted.", "invalid_state")
                run.data.pop("inputs_pending", None)
            elif kind == "answer_clarification":
                if run.status != "clarifying" or run.clarification is None:
                    raise AgentError("No clarification batch is awaiting answers.", "invalid_state")
                answers = arguments.get("answers")
                required = {q.question_id for q in run.clarification.questions}
                if (
                    not isinstance(answers, dict)
                    or set(answers) != required
                    or not all(
                        isinstance(value, str) and value.strip() for value in answers.values()
                    )
                ):
                    raise AgentError(
                        "Answer every question with an option or custom text.", "invalid_answers"
                    )
                run.answers.update(answers)
                run.authorizations.append(
                    AgentRunEnvelopeV1(
                        request=run.request,
                        answers=run.answers,
                        allowed_connectors=[
                            key
                            for key, value in connector_catalog().items()
                            if value.availability == "available"
                        ],
                        allowed_models=sorted(SUPPORTED_MODELS),
                        allowed_transforms=sorted(SUPPORTED_TRANSFORMATIONS),
                        budget_limits=run.ledger.limits.model_copy(deep=True),
                        provider_permissions={
                            "research_roles": "deepseek-development",
                            "reviewer": "codex-local",
                            "remote_public": self.settings.ai_data_access_enabled,
                            "remote_user_supplied": self.settings.ai_remote_user_data_allowed,
                            "remote_licensed": self.settings.ai_remote_licensed_data_allowed,
                        },
                    )
                )
                run.status = "queued"
                run.messages.append(
                    {
                        "id": identifier("message"),
                        "role": "user",
                        "body": " · ".join(answers.values()),
                        "created_at": utc_now(),
                    }
                )
            elif kind == "pause":
                if run.status not in {"queued", "running", "clarifying"}:
                    raise AgentError("This run is not active.", "invalid_state")
                run.pause_requested = True
                if not any(node.status == "running" for node in run.nodes):
                    run.status = "paused"
            elif kind == "cancel":
                run.status = "cancelled"
                run.epoch += 1
                for node in run.nodes:
                    if node.status in {"pending", "running"}:
                        node.status = "cancelled"
                run.data.pop("active_clock", None)
            elif kind == "resume":
                self._reject_missing_evidence_retry(run)
                if run.status not in {"paused", "failed"}:
                    raise AgentError("Resume requires a paused/failed run.", "invalid_state")
                if (run.error or {}).get("code") == "task_attempt_limit":
                    raise AgentError(
                        "This task exhausted its three calls. Start a linked new run; "
                        "existing results and diagnostics remain available.",
                        "task_attempt_limit",
                    )
                self._reject_exhausted_delivery_retry(run)
                if (run.error or {}).get("code") in RETRY_CODES:
                    raise AgentError(
                        "Follow the recovery advice and use the explicit retry action.",
                        "provider_action_required",
                    )
                run.status = "queued" if run.authorizations else "requested"
                run.pause_requested = False
                run.error = None
            elif kind == "retry_failed_task":
                advice = recovery_advice(run)
                if (
                    run.status not in {"waiting_for_user", "failed", "paused"}
                    or not advice
                    or not advice["can_retry"]
                ):
                    raise AgentError(
                        "This step cannot be retried within its current limits. "
                        "Follow the recovery advice.",
                        "retry_not_available",
                    )
                if (
                    advice["requires_provider_confirmation"]
                    and arguments.get("confirm_provider_ready") is not True
                ):
                    raise AgentError(
                        "Confirm restored provider credit/access/configuration before retrying.",
                        "provider_action_required",
                    )
                if (
                    advice["code"] == "provider_credentials_missing"
                    and not self.settings.deepseek_api_key
                ):
                    raise AgentError(
                        "The configured DeepSeek key is still missing. Update configuration "
                        "and restart before retrying.",
                        "provider_credentials_missing",
                    )
                # Transport/format recovery is not a new research decision. Preserve
                # answers and task inputs so retries share the same physical-call ceiling.
                run.status = "queued" if run.authorizations else "requested"
                run.pause_requested = False
                run.error = None
                run.intervention = None
            elif kind == "extend_budget":
                updates = arguments.get("limits", {})
                limits = run.ledger.limits.model_dump()
                if not isinstance(updates, dict) or any(
                    key not in limits or value < limits[key] for key, value in updates.items()
                ):
                    raise AgentError("Budget limits may only increase.", "invalid_budget")
                run.ledger.limits = type(run.ledger.limits).model_validate({**limits, **updates})
                run.ledger.version += 1
                if run.authorizations:
                    previous = run.authorizations[-1]
                    run.authorizations.append(
                        previous.model_copy(
                            update={
                                "envelope_id": identifier("authorization"),
                                "version": previous.version + 1,
                                "budget_limits": run.ledger.limits.model_copy(deep=True),
                                "created_at": utc_now(),
                            }
                        )
                    )
                if run.status == "budget_exhausted":
                    run.status = "paused"
            elif kind == "retry_review":
                self._reject_missing_evidence_retry(run)
                candidate = run.output.get("candidate", {})
                if run.status not in {
                    "waiting_for_user",
                    "budget_exhausted",
                    "paused",
                    "awaiting_final_confirmation",
                } or not candidate.get("review"):
                    raise AgentError("A finished current review is required.", "invalid_state")
                if arguments.get("artifact_set_hash") != candidate["artifact_set_hash"]:
                    raise AgentError("Review retry targets a stale delivery.", "stale_artifacts")
                if run.ledger.used.get("formal_reviews", 0) >= run.ledger.limits.formal_reviews:
                    raise AgentBudgetExceeded("Formal review rounds are exhausted.")
                candidate.setdefault("review_history", []).append(candidate["review"])
                candidate["review"] = None
                run.status = "queued"
                run.error = None
                run.intervention = None
            elif kind == "resolve_intervention":
                self._reject_missing_evidence_retry(run)
                if run.status != "waiting_for_user" or run.intervention is None:
                    raise AgentError("No intervention is awaiting input.", "invalid_state")
                if (run.error or {}).get("code") == "task_attempt_limit":
                    raise AgentError(
                        "This historical task exhausted its calls. Cancel it and start a "
                        "linked new run; an answer cannot reset the attempt limit.",
                        "task_attempt_limit",
                    )
                self._reject_exhausted_delivery_retry(run)
                advice = recovery_advice(run)
                if advice and advice["code"] in RETRY_CODES - {"provider_unavailable"}:
                    raise AgentError(
                        "Call/contract failures use explicit retry, not a research-scope answer.",
                        "provider_action_required",
                    )
                answer = arguments.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    raise AgentError("A concrete response is required.", "invalid_answer")
                run.answers[f"intervention_{run.intervention.intervention_id}"] = answer
                if arguments.get("allow_scope_change") is True and run.authorizations:
                    previous = run.authorizations[-1]
                    run.authorizations.append(
                        previous.model_copy(
                            update={
                                "envelope_id": identifier("authorization"),
                                "version": previous.version + 1,
                                "scope": {},
                                "plan_hash": None,
                                "answers": dict(run.answers),
                                "created_at": utc_now(),
                            }
                        )
                    )
                    run.task_plan = None
                    run.epoch += 1
                    if run.output.get("candidate"):
                        run.output.setdefault("history", []).append(run.output.pop("candidate"))
                    for node in run.nodes:
                        if node.kind != "clarification":
                            node.status = "stale"
                run.intervention = None
                run.error = None
                run.status = "queued" if run.authorizations else "requested"
                if arguments.get("allow_scope_change") is True or run.task_plan is None:
                    run.data["route_revision_requested"] = True
            elif kind == "finalize":
                self._validate_finish(run, arguments)
                run.output["manifest"] = manifest_ref
                run.status = "completed"
                for artifact in run.output["candidate"]["artifacts"]:
                    artifact["status"] = "frozen"
            elif kind == "message":
                text = arguments.get("message")
                if not isinstance(text, str) or not text.strip():
                    raise AgentError("Message cannot be empty.", "invalid_message")
                if any(node.status == "running" for node in run.nodes):
                    raise AgentError(
                        "Pause active execution before asking for an explanation.", "task_leased"
                    )
                run.messages.append(
                    {
                        "id": command.command_id,
                        "role": "user",
                        "body": text,
                        "created_at": utc_now(),
                    }
                )
            elif kind == "new_run":
                if run.status not in {"completed", "cancelled", "failed", "budget_exhausted"}:
                    raise AgentError(
                        "Finish or stop the current run before starting another.", "run_active"
                    )
            return {"command_id": command.command_id, "command": command.model_dump(mode="json")}

        current = self.repo.mutate(
            session_id,
            run_id,
            f"command.{command.type}",
            apply,
            actor="user",
            expected_version=command.expected_version,
            key=command.idempotency_key,
            command_hash=command_hash,
        )
        if command.type in {
            "start",
            "answer_clarification",
            "resume",
            "retry_review",
            "retry_failed_task",
            "resolve_intervention",
            "new_run",
        }:
            self.schedule(current)
        if command.type == "message" and self.autorun:
            self.pool.submit(self.explain, session_id, run_id, command.command_id)
        return current

    def explain(self, session_id: str, run_id: str, message_id: str) -> None:
        """A read-only model answer; it cannot replan or unfreeze scientific results."""
        run = self.repo.get_run(session_id, run_id)
        try:

            def answer() -> dict[str, Any]:
                evidence = {
                    "request": run.request,
                    "answers": run.answers,
                    "plan": run.task_plan.model_dump(mode="json") if run.task_plan else None,
                    "results": run.analysis.get("results", []),
                    "report": run.output.get("candidate", {}).get("drafts", {}),
                    "messages": run.messages[-8:],
                    "error": run.error,
                }
                known_refs = {blob["id"] for blob in self.repo.blobs(session_id, run_id)}
                known_refs.update(item["id"] for item in run.analysis.get("results", []))

                def validate(reply: AgentExplanation) -> None:
                    if set(reply.evidence_refs) - known_refs:
                        raise ValueError("Explanation references unknown evidence.")

                reply = self.provider.call(
                    run,
                    "research_explainer",
                    "Explain existing research only. Do not execute new research, data edits, "
                    "budget changes or final approval. For new research questions direct the user "
                    "to a linked new run. Cite supplied result IDs for numerical claims.",
                    evidence,
                    AgentExplanation,
                    validate,
                )
                return dict(reply.model_dump(mode="json"))

            response = self.step(
                session_id, run_id, "explain:" + message_id, [checksum(run.messages[-8:])], answer
            )
            body = response["body"]
        except Exception as error:
            body = (
                "The explanation could not be generated: "
                + str(error)
                + ". Existing research is unchanged."
            )
        self.repo.mutate(
            session_id,
            run_id,
            "explanation.ready",
            lambda current: current.messages.append(
                {
                    "id": identifier("message"),
                    "role": "agent",
                    "body": body,
                    "created_at": utc_now(),
                    "reply_to": message_id,
                }
            ),
        )

    @staticmethod
    def _reject_missing_evidence_retry(run: AgentRunV1) -> None:
        error = run.error or {}
        if error.get("code") in EVIDENCE_STOP_CODES:
            raise AgentError(
                "Missing upstream/presentation evidence must be repaired before a new "
                "authorized run; an answer or retry cannot substitute that evidence.",
                str(error["code"]),
            )

    @staticmethod
    def _reject_exhausted_delivery_retry(run: AgentRunV1) -> None:
        error = run.error or {}
        capped = (
            run.ledger.used.get("output_candidates", 0) >= run.ledger.limits.output_candidates
            or run.ledger.used.get("formal_reviews", 0) >= run.ledger.limits.formal_reviews
        )
        delivery_stop = error.get("code") in {"no_progress", "delivery_round_limit"} or (
            error.get("code") == "budget_exhausted"
            and "Output candidate limit" in str(error.get("message", ""))
        )
        if capped and delivery_stop:
            raise AgentError(
                "Delivery rounds are exhausted. Preserve this run and start a linked new run; "
                "execution budget or an answer cannot reset the delivery ceiling.",
                "delivery_round_limit",
            )

    @staticmethod
    def _validate_finish(run: AgentRunV1, arguments: dict[str, Any]) -> None:
        if run.status != "awaiting_final_confirmation":
            raise AgentError(
                "Review-approved results are required before finalization.", "finish_blocked"
            )
        candidate = run.output.get("candidate", {})
        report = candidate.get("review") or {}
        if report.get("status") == "fail" or report.get(
            "target_artifact_set_hash"
        ) != candidate.get("artifact_set_hash"):
            raise AgentError("Current artifact hashes are not approved.", "finish_blocked")
        if (
            run.task_plan
            and run.task_plan.plan.deliverables.research_report
            and report.get("semantic_report_status") != "pass"
        ):
            raise AgentError("Research Report requires semantic approval.", "finish_blocked")
        checks = candidate.get("self_checks", [])
        if (
            len(checks) != 2
            or {check["round"] for check in checks} != {1, 2}
            or any(
                check["status"] != "pass"
                or check["artifact_set_hash"] != candidate["artifact_set_hash"]
                for check in checks
            )
        ):
            raise AgentError("Author self-checks did not pass.", "finish_blocked")
        if any(
            finding["severity"] == "fail"
            or finding.get("blocking")
            or finding["rule_id"] not in {"VISUAL-RUBRIC-PLACEHOLDER"}
            for finding in report.get("findings", [])
        ):
            raise AgentError("Substantive findings must be corrected.", "finish_blocked")
        if report.get("findings") and not arguments.get("accept_warnings"):
            raise AgentError(
                "Acknowledge the publication-placeholder scope advisory.", "warning_ack_required"
            )

    def step(
        self,
        session_id: str,
        run_id: str,
        kind: str,
        inputs: list[str],
        action: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        node, reused = self.graph.claim(session_id, run_id, kind, inputs)
        if reused:
            result: dict[str, Any] = json.loads(
                self.repo.read_blob(session_id, run_id, node.output_refs[0])
            )
            return result
        try:
            result = action()
            payload = self.repo.payload(session_id, run_id, result, "task_result")

            def produced(value: Any) -> set[str]:
                refs: set[str] = set()
                if isinstance(value, dict):
                    if isinstance(value.get("id"), str) and value["id"].startswith(
                        ("agent-blob-", "agent-result-")
                    ):
                        refs.add(value["id"])
                        if isinstance(value.get("hash"), str):
                            refs.add(value["hash"])
                    if isinstance(value.get("artifact_set_hash"), str):
                        refs.add(value["artifact_set_hash"])
                    if isinstance(value.get("proposed_route"), dict):
                        refs.add(checksum(value["proposed_route"]))
                    for key in ("snapshot", "artifact", "render", "artifacts", "renders"):
                        item = value.get(key)
                        if isinstance(item, dict) and "id" not in item:
                            for inner in item.values():
                                refs.update(produced(inner))
                        else:
                            refs.update(produced(item))
                if isinstance(value, list):
                    for item in value:
                        refs.update(produced(item))
                return refs

            if not self.graph.finish(
                session_id,
                run_id,
                node,
                [payload["id"]],
                produced_refs=sorted({checksum(result), *produced(result)}),
            ):
                raise AgentStopped(
                    "Task completed after its execution epoch changed.", "late_result"
                )
            return result
        except Exception as error:
            payload = self.repo.payload(
                session_id,
                run_id,
                {
                    "stack": traceback.format_exc(),
                    "code": getattr(error, "code", "execution_error"),
                    "message": str(error),
                },
                "error",
            )
            self.graph.finish(
                session_id,
                run_id,
                node,
                [],
                error={
                    "code": getattr(error, "code", "execution_error"),
                    "details_ref": payload["id"],
                },
            )
            raise

    def counted_step(
        self,
        session_id: str,
        run_id: str,
        kind: str,
        inputs: list[str],
        costs: dict[str, float],
        action: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        def counted_action() -> dict[str, Any]:
            reservation = self.repo.reserve(session_id, run_id, costs)
            try:
                return action()
            finally:
                self.repo.settle(session_id, run_id, reservation, costs)

        return self.step(session_id, run_id, kind, inputs, counted_action)

    def execute(self, session_id: str, run_id: str) -> None:
        done = threading.Event()

        def heartbeats() -> None:
            while not done.wait(10):
                self.graph.heartbeat(session_id, run_id)

        heart = threading.Thread(target=heartbeats, daemon=True)
        heart.start()

        def step(
            kind: str, inputs: list[str], action: Callable[[], dict[str, Any]]
        ) -> dict[str, Any]:
            return self.step(session_id, run_id, kind, inputs, action)

        delivery = AgentDelivery(
            self.repo, self.settings, step, session_id, run_id, **self.delivery_ports
        )
        try:
            run = self.repo.get_run(session_id, run_id)
            if not run.authorizations:
                if run.clarification is not None:
                    return
                contexts = {}
                planning_access = AgentModelDataAccess(
                    self.repo,
                    session_id,
                    run_id,
                    enabled=self.settings.ai_data_access_enabled,
                    remote_user_data_allowed=self.settings.ai_remote_user_data_allowed,
                    remote_licensed_data_allowed=self.settings.ai_remote_licensed_data_allowed,
                )
                for attachment in run.attachments:
                    frame = read_snapshot(self.repo, session_id, run_id, attachment["snapshot_ref"])
                    if len(frame) > self.settings.planning_max_data_rows:
                        raise AgentError(
                            "Complete attachment exceeds the planning context budget.",
                            "context_budget",
                        )
                    context = planning_access.context(
                        attachment["snapshot_ref"],
                        ResearchStage.PLAN,
                        provider="deepseek-development",
                        model=self.settings.deepseek_model,
                    )
                    rows = []
                    for offset in range(0, context.grant.row_count, context.grant.page_size):
                        rows.extend(
                            planning_access.read_page(
                                context.grant.access_id,
                                session_id=session_id,
                                stage=ResearchStage.PLAN,
                                offset=offset,
                            ).rows
                        )
                    contexts[attachment["name"]] = {
                        "rows": rows,
                        "grant": context.grant.model_dump(mode="json"),
                    }
                result = self.counted_step(
                    session_id,
                    run_id,
                    "clarification",
                    [checksum(run.request), checksum(run.attachments)],
                    {"clarification_batches": 1},
                    lambda: self.provider.clarify(run, contexts).model_dump(mode="json"),
                )

                def save_clarification(current: AgentRunV1) -> None:
                    from macro_research_agent.research_core.planning import ClarificationBatch

                    current.clarification = ClarificationBatch.model_validate(result)
                    current.status = "clarifying"

                self.repo.mutate(session_id, run_id, "clarification.ready", save_clarification)
                return
            self._research(session_id, run_id, step, delivery)
        except Exception as error:
            ref = self.repo.payload(
                session_id,
                run_id,
                {"stack": traceback.format_exc(), "message": str(error)},
                "error",
            )

            def stop(run: AgentRunV1, captured_error: Exception = error) -> dict[str, Any]:
                if run.status in {"cancelled", "completed", "paused", "budget_exhausted"}:
                    return {"ignored_terminal_error": True}
                if isinstance(captured_error, AgentBudgetExceeded):
                    run.status = "budget_exhausted"
                elif getattr(captured_error, "code", "") in EVIDENCE_STOP_CODES or (
                    isinstance(captured_error, AgentStopped)
                    and captured_error.code == "task_attempt_limit"
                ):
                    run.status = "failed"
                    run.intervention = None
                elif (
                    isinstance(captured_error, AgentStopped)
                    and captured_error.code == "pause_requested"
                ):
                    run.status = "paused"
                else:
                    run.status = "waiting_for_user"
                    run.intervention = AgentInterventionV1(
                        reason=getattr(captured_error, "code", "execution_error"),
                        message=str(captured_error),
                        options=[
                            "Retry within remaining budget",
                            "Revise the research constraints",
                        ],
                        details_ref=ref["id"],
                    )
                run.error = {
                    "code": getattr(captured_error, "code", "execution_error"),
                    "message": str(captured_error),
                    "details_ref": ref["id"],
                }
                run.data.pop("active_clock", None)
                return {"error": run.error}

            self.repo.mutate(session_id, run_id, "run.stopped", stop)
        finally:
            done.set()
            delivery.close()

    def _research(self, session_id: str, run_id: str, step: Any, delivery: AgentDelivery) -> None:
        run = self.repo.get_run(session_id, run_id)
        if run.task_plan is None or run.data.pop("route_revision_requested", False):
            route_version = len(run.route_history) + 1
            result = self.counted_step(
                session_id,
                run_id,
                f"route:{route_version}",
                [run.authorizations[-1].envelope_id, checksum(run.answers)],
                {"routes": 1},
                lambda: self.provider.route(run).model_dump(mode="json"),
            )
            parsed_route = AgentTaskPlanV1.model_validate(result)
            validate_route(parsed_route, run, self.registry)
            if parsed_route.plan.unresolved_items:
                raise AgentError(
                    "; ".join(parsed_route.plan.unresolved_items), "handoff_incomplete"
                )

            def save_route(current: AgentRunV1) -> None:
                previous = current.authorizations[-1]
                if not previous.scope:
                    current.authorizations.append(
                        previous.model_copy(
                            update={
                                "envelope_id": identifier("authorization"),
                                "version": previous.version + 1,
                                "scope": plan_scope(parsed_route),
                                "plan_hash": checksum(result),
                            }
                        )
                    )
                current.task_plan = parsed_route
                current.route_history.append(
                    {"version": route_version, "hash": checksum(result), "route": result}
                )
                current.data.pop("route_revision_requested", None)

            self.repo.mutate(session_id, run_id, "route.accepted", save_route)
        run = self.repo.get_run(session_id, run_id)
        route = run.task_plan
        if route is None:
            raise AgentError("No task route.", "route_missing")
        sources = []
        for source in route.plan.data_sources:
            if source.connector_id == "local_file":
                for attachment in run.attachments:
                    sources.append(
                        step(
                            f"acquire_local:{attachment['id']}",
                            [attachment["id"]],
                            lambda attachment=attachment: normalize_local(
                                self.repo, run, attachment
                            ),
                        )
                    )
            else:
                query = connector_query(run, source)
                sources.append(
                    step(
                        f"acquire:{source.connector_id}:{source.dataset}",
                        [checksum(query.model_dump())],
                        lambda source=source, query=query: asyncio.run(
                            acquire_public(self.repo, run, source.connector_id, query)
                        ),
                    )
                )

        def merge() -> dict[str, Any]:
            frames = [
                read_snapshot(self.repo, session_id, run_id, source["snapshot"]["id"])
                for source in sources
            ]
            if not frames:
                raise AgentError("No data source completed.", "coverage_missing")
            frame = pd.concat(frames, ignore_index=True)
            if frame.duplicated(CANONICAL_KEYS).any():
                raise AgentError(
                    "Sources overlap on canonical identities; an explicit mapping is needed.",
                    "merge_conflict",
                )
            values = pd.to_numeric(frame["value"], errors="coerce")
            if (~np.isfinite(values[values.notna()])).any():
                raise AgentError(
                    "Non-finite observation values require correction.", "data_contract"
                )
            ref = write_snapshot(
                self.repo,
                session_id,
                run_id,
                frame,
                classification="user_supplied"
                if any(
                    source["snapshot"]["classification"] == "user_supplied" for source in sources
                )
                else "public",
                provenance={"sources": [s["snapshot"]["id"] for s in sources]},
            )
            return {"snapshot": ref}

        merged = step("merge", [source["snapshot"]["id"] for source in sources], merge)
        raw_ref = merged["snapshot"]["id"]
        frame = read_snapshot(self.repo, session_id, run_id, raw_ref)
        data_access = AgentModelDataAccess(
            self.repo,
            session_id,
            run_id,
            enabled=self.settings.ai_data_access_enabled,
            remote_user_data_allowed=self.settings.ai_remote_user_data_allowed,
            remote_licensed_data_allowed=self.settings.ai_remote_licensed_data_allowed,
        )

        def diagnose() -> dict[str, Any]:
            context = data_access.context(
                raw_ref,
                ResearchStage.DATA,
                provider="deepseek-development",
                model=self.settings.deepseek_model,
            )
            if context.grant.row_count > self.settings.report_author_max_data_rows:
                raise AgentError("Full Data AI context exceeds its row budget.", "context_budget")
            rows = []
            for offset in range(0, context.grant.row_count, context.grant.page_size):
                rows.extend(
                    data_access.read_page(
                        context.grant.access_id,
                        session_id=session_id,
                        stage=ResearchStage.DATA,
                        offset=offset,
                    ).rows
                )
            assessment = self.provider.call(
                run,
                "data_steward",
                "Diagnose the complete acquired rows. Missingness concerns value only, not null "
                "unit/name/status metadata. Use only none/complete_cases/interpolate/winsorize. "
                "Missing exclusions max 5%; interpolation isolated interior gaps, >=20 actual "
                "observations and <=5%; winsorize fixed 1%/99% with >=100 observations and <=5%. "
                "Keep meaningful macro extremes unless a valid registered strategy is justified. "
                "Do not claim source unavailability from discovery metadata. Choose none when "
                "data are usable. proposed_route=null unless an upstream change is essential.",
                {
                    "route": route.model_dump(mode="json"),
                    "acquisition_checks": route.acquisition_checks,
                    "source_metadata_receipts": [
                        source.get("metadata_receipt", {}) for source in sources
                    ],
                    "rows": rows,
                    "missing_value_share": float(frame["value"].isna().mean()),
                },
                AgentAssessment,
            )
            return dict(assessment.model_dump(mode="json"))

        assessment = step("data_assessment", [raw_ref, checksum(route.model_dump())], diagnose)
        if route.acquisition_checks:
            self.repo.mutate(
                session_id,
                run_id,
                "acquisition.checks_observed",
                lambda current: current.data.update(
                    {
                        "acquisition_checks": {
                            "requests": route.acquisition_checks,
                            "state": "assessed_against_acquired_evidence",
                            "assessment_ref": next(
                                n.output_refs[0]
                                for n in reversed(current.nodes)
                                if n.kind == "data_assessment" and n.status == "completed"
                            ),
                            "source_snapshot_refs": [s["snapshot"]["id"] for s in sources],
                        },
                    }
                ),
            )
        if assessment["status"] == "requires_user":
            raise AgentError(assessment["summary"], "data_quality_intervention")
        strategy = assessment.get("cleaning", route.cleaning)

        def prepare() -> dict[str, Any]:
            has_forecast = any(
                intent.enabled and intent.forecast_horizon for intent in route.plan.model_intents
            )
            if has_forecast and strategy != "none" and route.validation_start is None:
                raise AgentError(
                    "Forecast cleaning requires an explicit protected validation window.",
                    "training_split_required",
                )
            required = {
                canonical_indicator(run, variable)
                for task in route.analyses
                for variable in task.variables
            }
            cleaned, receipt = clean_statistical_frame(
                frame, strategy, route.validation_start, required_indicators=required
            )
            ref = write_snapshot(
                self.repo,
                session_id,
                run_id,
                cleaned,
                classification=merged["snapshot"]["classification"],
                provenance={"input": raw_ref, "cleaning": receipt},
            )
            return {"snapshot": ref, "receipt": receipt}

        prepared = step("prepare", [raw_ref, checksum([strategy, route.validation_start])], prepare)
        self.repo.mutate(
            session_id,
            run_id,
            "data.ready",
            lambda current: current.data.update(
                {
                    "sources": sources,
                    "raw_snapshot": raw_ref,
                    "prepared_snapshot": prepared["snapshot"]["id"],
                    "cleaning": prepared["receipt"],
                }
            ),
        )
        run = self.repo.get_run(session_id, run_id)
        analysis_signature = checksum(
            {
                "snapshot": prepared["snapshot"]["id"],
                "analyses": [task.model_dump(mode="json") for task in route.analyses],
                "transforms": [task.model_dump(mode="json") for task in route.transformations],
            }
        )

        def register_candidate(current: AgentRunV1) -> dict[str, Any]:
            fingerprints = current.analysis.setdefault("candidate_fingerprints", [])
            if analysis_signature in fingerprints:
                return {"reused": True, "signature": analysis_signature}
            cost = 2 if current.data.get("cleaning", {}).get("changed_count", 0) else 1
            used = current.ledger.used.get("analysis_candidates", 0)
            if used + cost > current.ledger.limits.analysis_candidates:
                raise AgentBudgetExceeded("Analysis candidate budget exhausted.")
            current.ledger.used["analysis_candidates"] = used + cost
            fingerprints.append(analysis_signature)
            return {"signature": analysis_signature, "cost": cost}

        self.repo.mutate(session_id, run_id, "analysis.candidate_registered", register_candidate)
        results, model_jobs, operations = self._analyze(
            run, route, raw_ref, prepared["snapshot"]["id"], step
        )
        final_ref = self.repo.get_run(session_id, run_id).analysis["final_snapshot"]
        self.repo.mutate(
            session_id,
            run_id,
            "analysis.ready",
            lambda current: current.analysis.update(
                {"results": results, "model_jobs": model_jobs, "operations": operations}
            ),
        )
        run = self.repo.get_run(session_id, run_id)

        def assess_analysis() -> dict[str, Any]:
            context = data_access.context(
                final_ref,
                ResearchStage.TRANSFORMATION,
                provider="deepseek-development",
                model=self.settings.deepseek_model,
            )
            rows = []
            if context.grant.row_count > self.settings.report_author_max_data_rows:
                raise AgentError(
                    "Complete analysis context exceeds its row budget.", "context_budget"
                )
            for offset in range(0, context.grant.row_count, context.grant.page_size):
                rows.extend(
                    data_access.read_page(
                        context.grant.access_id,
                        session_id=session_id,
                        stage=ResearchStage.TRANSFORMATION,
                        offset=offset,
                    ).rows
                )
            parsed = self.provider.call(
                run,
                "analyst",
                "Check the actual typed results against the research question, sample windows and "
                "forecast horizon. Compare variants without selecting favorable p-values. "
                "Registered descriptive outputs include observedSeries and endpointComparisons. "
                "Ordered rows also support report writing; do not refit merely for report/table "
                "presentation. Do not introduce unregistered output/statistics parameters. "
                "Do not call missing metadata missing observations. Return pass when scope is "
                "covered and limitations can be disclosed. Propose a scope-preserving route only "
                "for concrete missing analysis or numerical/diagnostic failures; never execute it.",
                {
                    "request": run.request,
                    "route": route.model_dump(mode="json"),
                    "rows": rows,
                    "results": results,
                    "cleaning": run.data.get("cleaning"),
                },
                AgentAssessment,
                lambda response: (
                    validate_route(response.proposed_route, run, self.registry)
                    if response.proposed_route
                    else None
                ),
            )
            return dict(parsed.model_dump(mode="json"))

        analysis_assessment = step(
            "analysis_assessment",
            [
                final_ref,
                checksum(results),
                checksum(route.model_dump(mode="json")),
                "analyst-contract-v2",
            ],
            assess_analysis,
        )
        self.repo.mutate(
            session_id,
            run_id,
            "analysis.assessed",
            lambda current: current.analysis.update({"assessment": analysis_assessment}),
        )
        if analysis_assessment["status"] == "requires_user":
            raise AgentError(analysis_assessment["summary"], "analysis_intervention")
        if analysis_assessment.get("proposed_route"):
            updated_route = AgentTaskPlanV1.model_validate(analysis_assessment["proposed_route"])
            validate_route(updated_route, run, self.registry)
            reservation = self.repo.reserve(session_id, run_id, {"routes": 1})

            def replan(current: AgentRunV1) -> None:
                current.task_plan = updated_route
                current.route_history.append(
                    {
                        "version": len(current.route_history) + 1,
                        "hash": checksum(analysis_assessment["proposed_route"]),
                        "route": analysis_assessment["proposed_route"],
                    }
                )

            self.repo.mutate(session_id, run_id, "route.revised_from_analysis", replan)
            self.repo.settle(session_id, run_id, reservation, {"routes": 1})
            self._research(session_id, run_id, step, delivery)
            return
        self._deliver(run, final_ref, results, step, delivery)

    def _analyze(
        self, run: AgentRunV1, route: AgentTaskPlanV1, raw_ref: str, prepared_ref: str, step: Any
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        session_id, run_id = run.session_id, run.run_id
        operations = []
        selected_ref = prepared_ref
        baseline_ref = raw_ref
        input_ref = "active_dataset"
        for operation in route.transformations:
            compiled = {
                "id": operation.task_id,
                "kind": operation.operation,
                "enabled": True,
                "inputRef": input_ref,
                "outputRef": f"step:{operation.task_id}",
                "target": {
                    "inputRef": input_ref,
                    "fields": ["value"],
                    "indicators": [canonical_indicator(run, code) for code in operation.indicators],
                    "entities": [],
                    "periodStart": None,
                    "periodEnd": None,
                    "frequency": None,
                },
                "parameters": operation.parameters,
            }
            operations.append(compiled)

            def transform(snapshot: str, compiled: dict[str, Any] = compiled) -> dict[str, Any]:
                frame = read_snapshot(self.repo, session_id, run_id, snapshot)
                transformed = FrameTransformEngine().transform_frame(frame, compiled)
                ref = write_snapshot(
                    self.repo,
                    session_id,
                    run_id,
                    transformed,
                    provenance={"input": snapshot, "operation": compiled},
                    classification=next(
                        blob["classification"]
                        for blob in self.repo.blobs(session_id, run_id)
                        if blob["id"] == snapshot
                    ),
                )
                return {"snapshot": ref}

            selected = step(
                f"transform:{operation.task_id}",
                [selected_ref, checksum(compiled)],
                lambda current_ref=selected_ref, transform_action=transform: transform_action(
                    current_ref
                ),
            )
            selected_ref = selected["snapshot"]["id"]
            if run.data.get("cleaning", {}).get("changed_count", 0):
                baseline = step(
                    f"baseline_transform:{operation.task_id}",
                    [baseline_ref, checksum(compiled)],
                    lambda current_ref=baseline_ref, transform_action=transform: transform_action(
                        current_ref
                    ),
                )
                baseline_ref = baseline["snapshot"]["id"]
            input_ref = str(compiled["outputRef"])
        results, jobs = [], []
        variants = [("selected", selected_ref)]
        if run.data.get("cleaning", {}).get("changed_count", 0):
            variants.insert(0, ("raw_baseline", baseline_ref))
        for variant, snapshot in variants:
            frame = read_snapshot(self.repo, session_id, run_id, snapshot)
            for task in route.analyses:
                for entity in sorted(frame["entity_code"].dropna().unique()):
                    job = model_job(task, input_ref)
                    for field in ("variables", "dependentVariables", "independentVariables"):
                        job[field] = [canonical_indicator(run, code) for code in job[field]]
                    job["entityCodes"] = [str(entity)]
                    if task.sample_window:
                        job["sampleWindow"] = task.sample_window.model_dump()
                    if (
                        route.validation_start
                        and task.model in {"arima", "var", "sarimax"}
                        and job["parameters"].get("forecastSteps", 0) > 0
                    ):
                        job["validationStart"] = route.validation_start
                    validate_model_job(job)

                    def fit(
                        job: dict[str, Any] = job,
                        snapshot: str = snapshot,
                        variant: str = variant,
                        entity: Any = entity,
                        task: Any = task,
                    ) -> dict[str, Any]:
                        fit_cost = 2 if job.get("validationStart") else 1
                        reservation = self.repo.reserve(
                            session_id, run_id, {"model_fits": fit_cost}
                        )
                        try:
                            result, sample, warnings = evaluate_typed_model_frame(
                                read_snapshot(self.repo, session_id, run_id, snapshot), job
                            )
                            return {
                                "id": identifier("result"),
                                "jobId": task.task_id,
                                "kind": task.model,
                                "purpose": task.purpose,
                                "entity": str(entity),
                                "variant": variant,
                                "window": task.sample_window.model_dump()
                                if task.sample_window
                                else route.plan.period.model_dump(),
                                "sample": sample,
                                "result": result,
                                "warnings": warnings,
                                "resultHash": checksum(result),
                                "inputSnapshotRef": snapshot,
                                "specificationHash": checksum(job),
                            }
                        finally:
                            self.repo.settle(
                                session_id, run_id, reservation, {"model_fits": fit_cost}
                            )

                    result = step(
                        f"model:{variant}:{task.task_id}:{entity}", [snapshot, checksum(job)], fit
                    )
                    results.append(result)
                    if variant == "selected":
                        jobs.append(job)
        self.repo.mutate(
            session_id,
            run_id,
            "analysis.snapshot_ready",
            lambda current: current.analysis.update(
                {"final_snapshot": selected_ref, "raw_transformed_snapshot": baseline_ref}
            ),
        )
        return results, jobs, operations

    def _deliver(
        self,
        run: AgentRunV1,
        final_ref: str,
        results: list[dict[str, Any]],
        step: Any,
        delivery: AgentDelivery,
    ) -> None:
        from macro_research_agent.agent.providers import AgentOutputCorrection

        session_id, run_id = run.session_id, run.run_id
        current = self.repo.get_run(session_id, run_id)
        candidate: dict[str, Any] = current.output.get("candidate") or {}
        if not candidate:
            number = int(current.ledger.used.get("output_candidates", 0)) + 1

            def generate() -> dict[str, Any]:
                reservation = self.repo.reserve(session_id, run_id, {"output_candidates": 1})
                try:
                    return delivery.generate(current, final_ref, results, number)
                finally:
                    self.repo.settle(session_id, run_id, reservation, {"output_candidates": 1})

            candidate = step(f"output:{number}", [final_ref, checksum(results)], generate)
            self.repo.mutate(
                session_id,
                run_id,
                "output.generated",
                lambda r: r.output.update({"candidate": candidate}),
            )
        while True:
            current = self.repo.get_run(session_id, run_id)
            if (
                candidate.get("review")
                and candidate["review"].get("validation_protocol") != "artifact-references-v2"
            ):
                candidate.setdefault("review_history", []).append(candidate["review"])
                candidate["review"] = None
                self._save_candidate(
                    session_id, run_id, "output.review_protocol_updated", candidate
                )
            preflight = delivery.preflight(current, candidate, final_ref)
            self.repo.event(session_id, run_id, "output.preflight", {"findings": preflight})
            issues = [
                item for item in preflight if item["severity"] == "fail" or item.get("blocking")
            ]
            for item in issues:
                if item.get("rule_id") in PRESENTATION_PREREQUISITE_RULES:
                    item["requires_upstream_stage"] = True
                    item["rule_id"] = "PRESENTATION-HANDOFF-INCOMPLETE"
                elif item.get("rule_id") == "DATA-VALUE-001":
                    item["requires_upstream_stage"] = True
            if not issues:
                handoff_number = int(current.ledger.used.get("formal_reviews", 0)) + 1
                if candidate.get("review"):
                    handoff_number = int(candidate["review"]["iteration"])
                candidate["self_checks"] = delivery.self_checks(
                    candidate, final_ref, handoff_number
                )
                self._save_candidate(session_id, run_id, "output.self_checks", candidate)
                issues = []
                for check in candidate["self_checks"]:
                    if check["status"] == "pass":
                        continue
                    if check.get("findings"):
                        issues.extend(
                            {
                                "rule_id": "AUTHOR-SELF-" + finding["category"],
                                "artifact_ids": [finding["artifact_id"]],
                                "evidence_refs": finding["evidence_refs"],
                                "message": finding["message"],
                            }
                            for finding in check["findings"]
                        )
                    else:
                        issues.extend(
                            {"rule_id": "AUTHOR-SELF-CHECK", "message": issue}
                            for issue in check["issues"]
                        )
            if not issues:
                existing = candidate.get("review")
                iteration = int(current.ledger.used.get("formal_reviews", 0)) + 1
                if existing is None:

                    def review_action(
                        current: AgentRunV1 = current,
                        candidate: dict[str, Any] = candidate,
                        iteration: int = iteration,
                    ) -> dict[str, Any]:
                        reservation = self.repo.reserve(session_id, run_id, {"formal_reviews": 1})
                        try:
                            return delivery.review(
                                current, candidate, final_ref, results, iteration
                            )
                        finally:
                            self.repo.settle(session_id, run_id, reservation, {"formal_reviews": 1})

                    candidate["review"] = step(
                        f"review:{candidate['candidate']}:{iteration}:references-v2",
                        [candidate["artifact_set_hash"]],
                        review_action,
                    )
                    self._save_candidate(session_id, run_id, "output.reviewed", candidate)
                report = candidate["review"]
                issues = [
                    finding
                    for finding in report["findings"]
                    if finding["rule_id"] != "VISUAL-RUBRIC-PLACEHOLDER"
                ]
                if (
                    not issues
                    and current.task_plan
                    and current.task_plan.plan.deliverables.research_report
                    and report["semantic_report_status"] != "pass"
                ):
                    issues = [
                        {
                            "rule_id": "REPORT-SEMANTIC",
                            "message": "Semantic approval is required.",
                        }
                    ]
            if not issues:

                def ready(current: AgentRunV1) -> None:
                    current.status = "awaiting_final_confirmation"
                    current.messages.append(
                        {
                            "id": identifier("message"),
                            "role": "agent",
                            "body": "Review AI approved this package. Please confirm delivery.",
                            "created_at": utc_now(),
                        }
                    )

                self.repo.mutate(session_id, run_id, "output.ready_for_user", ready)
                return
            if any(item.get("requires_upstream_stage") for item in issues) or (
                (candidate.get("review") or {}).get("semantic_report_status")
                == "requires_upstream_stage"
            ):
                finding_ref = self.repo.payload(session_id, run_id, issues)["id"]
                self.repo.event(
                    session_id,
                    run_id,
                    "output.upstream_required",
                    {
                        "findings_ref": finding_ref,
                        "artifact_set_hash": candidate["artifact_set_hash"],
                        "reason": "Missing evidence is not repairable by output rewriting.",
                    },
                )
                code = (
                    "presentation_handoff_incomplete"
                    if any(
                        item.get("rule_id") == "PRESENTATION-HANDOFF-INCOMPLETE" for item in issues
                    )
                    else "requires_upstream_stage"
                )
                raise AgentError(
                    "Review requires missing upstream or presentation evidence. Inspect the "
                    "recorded findings and repair that evidence; no Output Editor retry was used.",
                    code,
                )
            signature = checksum(sorted(str(item.get("rule_id") or "QUALITY") for item in issues))

            finding_ref = self.repo.payload(session_id, run_id, issues)["id"]

            def progress(
                current: AgentRunV1,
                signature: str = signature,
                candidate: dict[str, Any] = candidate,
                finding_ref: str = finding_ref,
            ) -> dict[str, Any]:
                current.no_progress = (
                    current.no_progress + 1 if current.last_failure_signature == signature else 0
                )
                current.last_failure_signature = signature
                current.output.setdefault("history", []).append(candidate)
                return {
                    "signature": signature,
                    "no_progress": current.no_progress,
                    "finding_ref": finding_ref,
                }

            current = self.repo.mutate(session_id, run_id, "output.correction_needed", progress)
            if current.no_progress >= 2:
                raise AgentError(
                    "Two successive corrections did not improve the same blockers.", "no_progress"
                )
            if (
                current.ledger.used.get("output_candidates", 0)
                >= current.ledger.limits.output_candidates
            ):
                raise AgentBudgetExceeded("Output candidate limit reached.", "budget_exhausted")
            if (candidate.get("review") or {}).get("report_directives") and not any(
                item.get("requires_upstream_stage") for item in issues
            ):
                correction = {
                    "summary": "Apply reviewer-authorized report section revisions.",
                    "patches": candidate["review"].get("patches", []),
                }
            else:

                def propose(
                    current: AgentRunV1 = current,
                    candidate: dict[str, Any] = candidate,
                    issues: list[dict[str, Any]] = issues,
                ) -> dict[str, Any]:
                    parsed = self.provider.call(
                        current,
                        "output_editor",
                        "Coordinate corrections for all issues. Only chart/table presentation "
                        "fields are allowed: title, unit, source_note, number_format, alt_text, "
                        "column subset. Never change data/results/code/manifest or invent units. "
                        "Keep required outputs/rules. Report edits use reviewer directives. "
                        "Before formal review, report_directives may self-revise only current "
                        "report sections, preserving all their evidenceRefs. Never patch "
                        "report IDs via patches. Use immutable sourceNoteVerbatim. "
                        "For obsolete report artifact hashes set rebind_artifact_references=true; "
                        "the controller only rebinds verified past hashes to current same-named "
                        "artifacts. It cannot change data/model hashes or numeric claims. "
                        "For missing analysis/data propose a scope-preserving route. "
                        "Do not conceal upstream gaps through wording changes.",
                        {
                            "request": current.request,
                            "route": current.task_plan.model_dump(mode="json")
                            if current.task_plan
                            else {},
                            "issues": issues,
                            "confirmedDecisions": current.answers,
                            "geometryReceipts": [
                                json.loads(
                                    self.repo.read_blob(
                                        session_id,
                                        run_id,
                                        check["geometry_receipt_ref"],
                                        check["geometry_receipt_hash"],
                                    )
                                )
                                for check in candidate["self_checks"]
                                if check.get("geometry_receipt_ref")
                            ],
                            "reportResultFacts": report_result_facts(
                                current.analysis.get("results", [])
                            ),
                            "artifacts": candidate["artifacts"],
                            "editable_chart_table_ids": [
                                artifact["id"]
                                for artifact in candidate["artifacts"]
                                if artifact["format"] in {"svg", "csv", "xlsx"}
                            ],
                            "reportDrafts": candidate["drafts"],
                            "specifications": candidate["specifications"],
                            "sourceNoteVerbatim": "Source: "
                            + ", ".join(
                                str(item.get("provenance", {}).get("provider") or "User data")
                                for item in current.data.get("sources", [])
                            ),
                        },
                        AgentOutputCorrection,
                        lambda response: delivery.validate_correction(
                            current, candidate, response.model_dump(mode="json")
                        ),
                    )
                    return dict(parsed.model_dump(mode="json"))

                correction = step(
                    f"output_proposal:{candidate['candidate']}",
                    [candidate["artifact_set_hash"], signature],
                    propose,
                )
            if correction.get("proposed_route"):
                route = AgentTaskPlanV1.model_validate(correction["proposed_route"])
                validate_route(route, current, self.registry)
                reservation = self.repo.reserve(session_id, run_id, {"routes": 1})

                def replan(
                    updated: AgentRunV1,
                    route: AgentTaskPlanV1 = route,
                    correction: dict[str, Any] = correction,
                ) -> dict[str, Any]:
                    updated.task_plan = route
                    updated.route_history.append(
                        {
                            "version": len(updated.route_history) + 1,
                            "hash": checksum(correction["proposed_route"]),
                            "route": correction["proposed_route"],
                        }
                    )
                    updated.output.pop("candidate", None)
                    for node in updated.nodes:
                        if node.kind.split(":")[0] in {
                            "model",
                            "output",
                            "chart",
                            "report",
                            "author_check",
                            "review",
                            "output_revision",
                        }:
                            node.status = "stale"
                    updated.status = "queued"
                    return {
                        "reason": "requires_upstream_stage",
                        "route_hash": checksum(correction["proposed_route"]),
                    }

                self.repo.mutate(session_id, run_id, "route.revised_from_review", replan)
                self.repo.settle(session_id, run_id, reservation, {"routes": 1})
                self._research(session_id, run_id, step, delivery)
                return
            if (
                not correction.get("patches")
                and not (candidate.get("review") or {}).get("report_directives")
                and not correction.get("rebind_artifact_references")
                and not correction.get("report_directives")
            ):
                raise AgentError(
                    "No supported correction can resolve these findings.", "requires_upstream_stage"
                )
            number = int(current.ledger.used.get("output_candidates", 0)) + 1

            def revise(
                candidate: dict[str, Any] = candidate,
                correction: dict[str, Any] = correction,
                number: int = number,
                current: AgentRunV1 = current,
            ) -> dict[str, Any]:
                reservation = self.repo.reserve(session_id, run_id, {"output_candidates": 1})
                try:
                    return delivery.revise(current, candidate, final_ref, correction, number)
                finally:
                    self.repo.settle(session_id, run_id, reservation, {"output_candidates": 1})

            candidate = step(
                f"output_revision:{number}",
                [candidate["artifact_set_hash"], checksum(correction)],
                revise,
            )
            self._save_candidate(session_id, run_id, "output.revised", candidate)

    def _save_candidate(
        self, session_id: str, run_id: str, event_type: str, candidate: dict[str, Any]
    ) -> None:
        self.repo.mutate(
            session_id,
            run_id,
            event_type,
            lambda current: current.output.update({"candidate": candidate}),
        )
