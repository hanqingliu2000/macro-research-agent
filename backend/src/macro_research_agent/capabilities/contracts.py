from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

StageId = Literal["plan", "data", "transformation", "output", "agent"]


def _default_callers() -> list[Literal["user", "agent", "system"]]:
    return ["user", "agent"]


class CapabilityKind(str, Enum):
    CONNECTOR = "connector"
    FUNCTION = "function"
    MODEL = "model"
    RENDERER = "renderer"
    REVIEWER = "reviewer"


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    PLANNED = "planned"
    DISABLED = "disabled"


class InvocationMode(str, Enum):
    DIRECT = "direct"
    STAGE_COMMAND = "stage_command"
    USER_ACTION = "user_action"


class ApprovalPolicy(str, Enum):
    NONE = "none"
    RESEARCH_PLAN = "research_plan"
    PIPELINE_EXECUTION = "pipeline_execution"
    FINAL_OUTPUTS = "final_outputs"


class DataAccessPolicy(str, Enum):
    NONE = "none"
    GRANT_READ = "grant_read"
    SNAPSHOT_READ = "snapshot_read"
    ARTIFACT_READ = "artifact_read"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    retryable_error_codes: list[str] = Field(default_factory=list)


class CapabilityDescriptor(BaseModel):
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    kind: CapabilityKind
    stages: list[StageId] = Field(min_length=1)
    availability: CapabilityAvailability
    invocation_mode: InvocationMode
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    approval_policy: ApprovalPolicy = ApprovalPolicy.NONE
    data_access_policy: DataAccessPolicy = DataAccessPolicy.NONE
    permitted_provider_profiles: list[str] = Field(default_factory=lambda: ["*"])
    allowed_callers: list[Literal["user", "agent", "system"]] = Field(
        default_factory=_default_callers
    )
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    handler_ref: str | None = None
    unavailable_reason: str | None = None
    code_package_version: str = "0.1.0"

    @model_validator(mode="after")
    def validate_availability(self) -> CapabilityDescriptor:
        if self.availability == CapabilityAvailability.PLANNED:
            if self.handler_ref is not None:
                raise ValueError("planned capabilities cannot expose a handler")
            if not self.unavailable_reason:
                raise ValueError("planned capabilities require an unavailable reason")
        elif self.availability == CapabilityAvailability.AVAILABLE and not self.handler_ref:
            raise ValueError("available capabilities require a handler reference")
        return self


class CapabilityInvocationIntent(BaseModel):
    invocation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    stage: StageId
    target_snapshot_hash: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    purpose: str = Field(min_length=1)
    arguments: dict[str, Any]
    input_refs: list[str] = Field(default_factory=list)
    expected_output_role: str = Field(min_length=1)
    checkpoint_ref: str | None = None
    provider_profile: str = "deterministic-local"
    actor: Literal["user", "agent", "system"] = "agent"
    skill_id: str | None = None
    skill_version: str | None = None

    @model_validator(mode="after")
    def skill_version_requires_skill(self) -> CapabilityInvocationIntent:
        if self.skill_version and not self.skill_id:
            raise ValueError("skill_version requires skill_id")
        return self


class CapabilityInvocationResult(BaseModel):
    invocation_id: str
    capability_id: str
    capability_version: str
    status: Literal["completed", "failed", "blocked"]
    output: dict[str, Any] | None = None
    result_refs: list[str] = Field(default_factory=list)
    argument_checksum: str
    latency_ms: float = Field(ge=0)
    attempt: int = Field(default=1, ge=1)
    error_code: str | None = None
