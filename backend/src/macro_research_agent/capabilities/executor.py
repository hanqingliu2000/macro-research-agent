from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any, Literal

from pydantic import ValidationError

from macro_research_agent.capabilities.contracts import (
    ApprovalPolicy,
    CapabilityAvailability,
    CapabilityInvocationIntent,
    CapabilityInvocationResult,
    InvocationMode,
)
from macro_research_agent.capabilities.registry import (
    CapabilityRegistry,
    CapabilityRegistryError,
)
from macro_research_agent.skills.registry import SkillRegistry

CapabilityAuditWriter = Callable[[str, str, dict[str, Any]], None]
CheckpointValidator = Callable[[CapabilityInvocationIntent, ApprovalPolicy], bool]


class CapabilityExecutionError(ValueError):
    def __init__(self, message: str, code: str, result: CapabilityInvocationResult) -> None:
        super().__init__(message)
        self.code = code
        self.result = result


def _checksum(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


class CapabilityExecutor:
    """Executes only directly bound, available handlers and records a value-free receipt."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        audit_writer: CapabilityAuditWriter,
        skill_registry: SkillRegistry | None = None,
        checkpoint_validator: CheckpointValidator | None = None,
    ) -> None:
        self.registry = registry
        self.audit_writer = audit_writer
        self.skill_registry = skill_registry
        self.checkpoint_validator = checkpoint_validator

    def execute(self, intent: CapabilityInvocationIntent) -> CapabilityInvocationResult:
        started = time.perf_counter()
        argument_checksum = _checksum(intent.arguments)
        error_code: str | None = None
        output: dict[str, Any] | None = None
        result_refs: list[str] = []
        status: Literal["completed", "failed", "blocked"] = "failed"
        approval_policy = ApprovalPolicy.NONE
        try:
            descriptor = self.registry.resolve(
                intent.capability_id, intent.capability_version
            )
            approval_policy = descriptor.approval_policy
            if intent.skill_id is not None:
                if self.skill_registry is None or intent.skill_version is None:
                    error_code = "skill_not_registered"
                    raise CapabilityRegistryError("Runtime skill registry is unavailable.")
                skill = self.skill_registry.resolve(intent.skill_id, intent.skill_version)
                if skill.availability != CapabilityAvailability.AVAILABLE:
                    error_code = "skill_unavailable"
                    raise CapabilityRegistryError(
                        skill.unavailable_reason or "Runtime skill is unavailable."
                    )
                if intent.stage not in skill.stages:
                    error_code = "skill_stage_not_allowed"
                    raise CapabilityRegistryError(
                        "Runtime skill is not allowed in the requested stage."
                    )
                if not any(
                    step.capability_id == intent.capability_id
                    and step.capability_version == intent.capability_version
                    for step in skill.steps
                ):
                    error_code = "skill_capability_not_allowed"
                    raise CapabilityRegistryError(
                        "Capability is not declared by the requested runtime skill."
                    )
            if descriptor.availability != CapabilityAvailability.AVAILABLE:
                error_code = "capability_unavailable"
                raise CapabilityRegistryError(
                    descriptor.unavailable_reason or "Capability is not available."
                )
            if intent.stage not in descriptor.stages:
                error_code = "stage_not_allowed"
                raise CapabilityRegistryError("Capability is not allowed in the requested stage.")
            if intent.actor not in descriptor.allowed_callers:
                error_code = "caller_not_allowed"
                raise CapabilityRegistryError("Caller is not allowed to invoke this capability.")
            if "*" not in descriptor.permitted_provider_profiles and (
                intent.provider_profile not in descriptor.permitted_provider_profiles
            ):
                error_code = "provider_not_allowed"
                raise CapabilityRegistryError(
                    "Provider profile is not allowed for this capability."
                )
            if descriptor.approval_policy != ApprovalPolicy.NONE and not intent.checkpoint_ref:
                error_code = "checkpoint_required"
                raise CapabilityRegistryError("Capability requires an approval checkpoint.")
            if descriptor.approval_policy != ApprovalPolicy.NONE and (
                self.checkpoint_validator is None
                or not self.checkpoint_validator(intent, descriptor.approval_policy)
            ):
                error_code = "checkpoint_invalid"
                raise CapabilityRegistryError(
                    "Capability checkpoint is missing, stale or targets different inputs."
                )
            if descriptor.invocation_mode != InvocationMode.DIRECT:
                error_code = "typed_boundary_required"
                raise CapabilityRegistryError(
                    "Capability must execute through its typed stage or user-action boundary."
                )
            registered = self.registry.handler(
                intent.capability_id, intent.capability_version
            )
            arguments = registered.input_model.model_validate(intent.arguments)
            output = registered.output_model.model_validate(
                registered.handler(arguments)
            ).model_dump(mode="json")
            result_refs = [str(item) for item in output.get("result_refs", [])]
            status = "completed"
        except ValidationError as exc:
            error_code = "arguments_invalid"
            message = str(exc)
            status = "failed"
        except CapabilityRegistryError as exc:
            message = str(exc)
            status = "blocked"
            error_code = error_code or "capability_not_registered"
        except Exception as exc:
            message = str(exc)
            status = "failed"
            error_code = "handler_failed"

        result = CapabilityInvocationResult(
            invocation_id=intent.invocation_id,
            capability_id=intent.capability_id,
            capability_version=intent.capability_version,
            status=status,
            output=output,
            result_refs=result_refs,
            argument_checksum=argument_checksum,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=error_code,
        )
        self.audit_writer(
            intent.session_id,
            (
                "capability.invocation_completed"
                if status == "completed"
                else "capability.invocation_rejected"
            ),
            {
                "invocation_id": intent.invocation_id,
                "capability_id": intent.capability_id,
                "capability_version": intent.capability_version,
                "skill_id": intent.skill_id,
                "skill_version": intent.skill_version,
                "stage": intent.stage,
                "target_snapshot_hash": intent.target_snapshot_hash,
                "argument_checksum": argument_checksum,
                "input_refs": intent.input_refs,
                "result_refs": result_refs,
                "checkpoint_ref": intent.checkpoint_ref,
                "approval_policy": approval_policy.value,
                "provider_profile": intent.provider_profile,
                "actor": intent.actor,
                "attempt": result.attempt,
                "latency_ms": result.latency_ms,
                "status": status,
                "error_code": error_code,
            },
        )
        if status != "completed":
            raise CapabilityExecutionError(message, error_code or "capability_failed", result)
        return result
