from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from macro_research_agent.capabilities.contracts import (
    ApprovalPolicy,
    CapabilityAvailability,
    StageId,
)


class SkillFailurePolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    ALLOW_PARTIAL = "allow_partial"


class SkillStep(BaseModel):
    step_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    depends_on: list[str] = Field(default_factory=list)
    optional: bool = False


class RuntimeSkillManifest(BaseModel):
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    stages: list[StageId] = Field(min_length=1)
    availability: CapabilityAvailability
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    steps: list[SkillStep] = Field(min_length=1)
    approval_policy: ApprovalPolicy
    data_minimization: str = Field(min_length=1)
    failure_policy: SkillFailurePolicy = SkillFailurePolicy.FAIL_CLOSED
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def validate_steps_and_availability(self) -> RuntimeSkillManifest:
        step_ids = {step.step_id for step in self.steps}
        if len(step_ids) != len(self.steps):
            raise ValueError("runtime skill step IDs must be unique")
        if any(dependency not in step_ids for step in self.steps for dependency in step.depends_on):
            raise ValueError("runtime skill dependency references an unknown step")
        if self.availability != CapabilityAvailability.AVAILABLE and not self.unavailable_reason:
            raise ValueError("unavailable runtime skills require a reason")
        return self
