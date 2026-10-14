from __future__ import annotations

from pydantic import BaseModel, Field

from macro_research_agent.capabilities.contracts import (
    ApprovalPolicy,
    CapabilityAvailability,
)
from macro_research_agent.capabilities.registry import CapabilityRegistry
from macro_research_agent.skills.contracts import RuntimeSkillManifest, SkillStep
from macro_research_agent.skills.registry import SkillRegistry


class SkillInput(BaseModel):
    objective: str
    input_refs: list[str] = Field(default_factory=list)


class SkillOutput(BaseModel):
    result_refs: list[str] = Field(default_factory=list)
    proposal_refs: list[str] = Field(default_factory=list)


def default_skill_registry(capabilities: CapabilityRegistry) -> SkillRegistry:
    registry = SkillRegistry(capabilities)
    manifests = [
        RuntimeSkillManifest(
            skill_id="workflow.plan.resolve_scope",
            version="1.0.0",
            display_name="Resolve research scope",
            description="Resolve controlled geography before a human approves the Plan.",
            stages=["plan"],
            availability=CapabilityAvailability.AVAILABLE,
            input_schema=SkillInput.model_json_schema(),
            output_schema=SkillOutput.model_json_schema(),
            steps=[
                SkillStep(
                    step_id="resolve-geography",
                    capability_id="geography.resolve",
                    capability_version="1.0.0",
                )
            ],
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            data_minimization="Only the geography intent is passed to the local registry.",
        ),
        RuntimeSkillManifest(
            skill_id="workflow.data.prepare",
            version="1.0.0",
            display_name="Prepare reviewed data",
            description="Apply selected typed preparation operations to the active snapshot.",
            stages=["data"],
            availability=CapabilityAvailability.AVAILABLE,
            input_schema=SkillInput.model_json_schema(),
            output_schema=SkillOutput.model_json_schema(),
            steps=[
                SkillStep(
                    step_id="prepare",
                    capability_id="data.prepare",
                    capability_version="1.0.0",
                )
            ],
            approval_policy=ApprovalPolicy.NONE,
            data_minimization=(
                "Operations receive only the active snapshot ref and typed parameters."
            ),
        ),
        RuntimeSkillManifest(
            skill_id="workflow.analysis.run",
            version="1.0.0",
            display_name="Run reviewed analysis",
            description="Execute the reviewed transformation chain and model specifications.",
            stages=["transformation"],
            availability=CapabilityAvailability.AVAILABLE,
            input_schema=SkillInput.model_json_schema(),
            output_schema=SkillOutput.model_json_schema(),
            steps=[
                SkillStep(
                    step_id="transform",
                    capability_id="transformation.apply",
                    capability_version="1.0.0",
                ),
                SkillStep(
                    step_id="descriptive-model",
                    capability_id="model.descriptive",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="correlation-model",
                    capability_id="model.correlation",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="ols-model",
                    capability_id="model.ols",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="adf-model",
                    capability_id="model.adf",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="arima-model",
                    capability_id="model.arima",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="sarimax-model",
                    capability_id="model.sarimax",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="var-model",
                    capability_id="model.var",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                    optional=True,
                ),
                SkillStep(
                    step_id="code",
                    capability_id="code.generate",
                    capability_version="1.0.0",
                    depends_on=["transform"],
                ),
            ],
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_minimization="Handlers read only checkpoint-bound approved snapshot refs.",
        ),
        RuntimeSkillManifest(
            skill_id="workflow.output.publish",
            version="1.0.0",
            display_name="Publish governed outputs",
            description="Render reviewed artifacts and freeze a human-selected manifest.",
            stages=["output"],
            availability=CapabilityAvailability.AVAILABLE,
            input_schema=SkillInput.model_json_schema(),
            output_schema=SkillOutput.model_json_schema(),
            steps=[
                SkillStep(
                    step_id="chart",
                    capability_id="artifact.chart.render",
                    capability_version="1.0.0",
                    optional=True,
                ),
                SkillStep(
                    step_id="table",
                    capability_id="artifact.table.render",
                    capability_version="1.0.0",
                    optional=True,
                ),
                SkillStep(
                    step_id="report",
                    capability_id="artifact.report.generate",
                    capability_version="1.0.0",
                    optional=True,
                ),
                SkillStep(
                    step_id="freeze",
                    capability_id="manifest.freeze",
                    capability_version="1.0.0",
                    depends_on=["chart", "table", "report"],
                ),
            ],
            approval_policy=ApprovalPolicy.FINAL_OUTPUTS,
            data_minimization=(
                "Renderers receive approved bundle refs; manifest receives artifact hashes."
            ),
        ),
        RuntimeSkillManifest(
            skill_id="workflow.output.review",
            version="1.0.0",
            display_name="Review output compliance",
            description=(
                "Run structural, visual and semantic report review before final publication "
                "approval."
            ),
            stages=["output"],
            availability=CapabilityAvailability.AVAILABLE,
            input_schema=SkillInput.model_json_schema(),
            output_schema=SkillOutput.model_json_schema(),
            steps=[
                SkillStep(
                    step_id="structural-review",
                    capability_id="output.review.structural",
                    capability_version="1.0.0",
                ),
                SkillStep(
                    step_id="visual-review",
                    capability_id="output.review.visual",
                    capability_version="1.0.0",
                    depends_on=["structural-review"],
                ),
                SkillStep(
                    step_id="semantic-report-review",
                    capability_id="output.review.semantic_report",
                    capability_version="1.0.0",
                    depends_on=["structural-review"],
                    optional=True,
                ),
                SkillStep(
                    step_id="selective-regeneration",
                    capability_id="artifact.regenerate",
                    capability_version="1.0.0",
                    depends_on=["visual-review"],
                    optional=True,
                ),
                SkillStep(
                    step_id="report-revision",
                    capability_id="artifact.report.revise",
                    capability_version="1.0.0",
                    depends_on=["semantic-report-review"],
                    optional=True,
                ),
            ],
            approval_policy=ApprovalPolicy.FINAL_OUTPUTS,
            data_minimization=(
                "Only authorized artifact renders, report evidence, specs and underlying "
                "hash-bound values."
            ),
        ),
    ]
    for manifest in manifests:
        registry.register(manifest)
    return registry
