from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from macro_research_agent.capabilities.contracts import (
    ApprovalPolicy,
    CapabilityAvailability,
    CapabilityDescriptor,
    CapabilityKind,
    DataAccessPolicy,
    InvocationMode,
    RetryPolicy,
    StageId,
)
from macro_research_agent.capabilities.registry import CapabilityRegistry


class GeographyResolveArguments(BaseModel):
    intent: str = Field(min_length=1)


class GeographyResolveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geography_id: str
    canonical_label: str
    kind: str
    aliases: list[str]
    members: list[dict[str, str | None]]
    source: str
    registry_version: str
    result_refs: list[str]


class AggregationArguments(BaseModel):
    input_snapshot_ref: str
    method: Literal["simple_mean", "weighted_mean"]
    member_codes: list[str] = Field(min_length=1)
    weight_field: str | None = None
    missing_data_policy: str
    coverage_threshold: float = Field(ge=0, le=1)


class LocalFileArguments(BaseModel):
    upload_id: str


class ImfDataArguments(BaseModel):
    dataset: Literal["CPI", "WEO"]
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[str] = Field(min_length=1, max_length=20)
    frequency: Literal["M", "Q", "A"]
    start_period: str
    end_period: str

    @model_validator(mode="after")
    def validate_dataset_contract(self) -> ImfDataArguments:
        if self.dataset == "WEO" and self.frequency != "A":
            raise ValueError("WEO supports annual frequency only")
        return self


class WorldBankArguments(BaseModel):
    dataset: Literal["WDI"] = "WDI"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[str] = Field(min_length=1, max_length=20)
    frequency: Literal["A"] = "A"
    start_period: str
    end_period: str


class OecdArguments(BaseModel):
    dataset: Literal["CLI"] = "CLI"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["LI"]] = Field(min_length=1, max_length=1)
    frequency: Literal["M"] = "M"
    start_period: str
    end_period: str


class EurostatArguments(BaseModel):
    dataset: Literal["HICP_INDEX"] = "HICP_INDEX"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["TOTAL"]] = Field(min_length=1, max_length=1)
    frequency: Literal["M"] = "M"
    start_period: str
    end_period: str


class AdbArguments(BaseModel):
    dataset: Literal["NATIONAL_ACCOUNTS"] = "NATIONAL_ACCOUNTS"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["NGDP_XDC", "NGDPVA_XDC"]] = Field(min_length=1, max_length=2)
    frequency: Literal["A"] = "A"
    start_period: str
    end_period: str


class EcbArguments(BaseModel):
    dataset: Literal["EXCHANGE_RATES"] = "EXCHANGE_RATES"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["EUR_REFERENCE_RATE"]] = Field(min_length=1, max_length=1)
    frequency: Literal["M"] = "M"
    start_period: str
    end_period: str


class BisArguments(BaseModel):
    dataset: Literal["POLICY_RATES"] = "POLICY_RATES"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["POLICY_RATE"]] = Field(min_length=1, max_length=1)
    frequency: Literal["M"] = "M"
    start_period: str
    end_period: str


class UnSdgArguments(BaseModel):
    dataset: Literal["SDG_INDICATORS"] = "SDG_INDICATORS"
    countries: list[str] = Field(min_length=1, max_length=20)
    indicators: list[Literal["NY_GDP_PCAP"]] = Field(min_length=1, max_length=1)
    frequency: Literal["A"] = "A"
    start_period: str
    end_period: str


class DataPreparationArguments(BaseModel):
    operation: Literal[
        "filter_missing",
        "keep_columns",
        "drop_columns",
        "rename_columns",
        "map_codes",
        "cast_types",
        "missing_value_rule",
        "deduplicate",
        "sort",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)


class TransformationArguments(BaseModel):
    operation: Literal[
        "lag",
        "lead",
        "difference",
        "yoy_growth",
        "period_growth",
        "log",
        "rebase_index",
        "unit_conversion",
        "frequency_conversion",
        "rolling_mean",
        "group_aggregation",
    ]
    input_ref: str
    target: dict[str, Any]
    parameters: dict[str, Any] = Field(default_factory=dict)


class ModelArguments(BaseModel):
    input_ref: str
    specification: dict[str, Any] = Field(default_factory=dict)


class DescriptiveModelArguments(ModelArguments):
    kind: Literal["descriptive"] = "descriptive"


class CorrelationModelArguments(ModelArguments):
    kind: Literal["correlation"] = "correlation"


class OlsModelArguments(ModelArguments):
    kind: Literal["ols"] = "ols"


class AdfModelArguments(ModelArguments):
    kind: Literal["adf"] = "adf"


class ArimaModelArguments(ModelArguments):
    kind: Literal["arima"] = "arima"


class SarimaxModelArguments(ModelArguments):
    kind: Literal["sarimax"] = "sarimax"


class VarModelArguments(ModelArguments):
    kind: Literal["var"] = "var"


class RenderArguments(BaseModel):
    bundle_id: str
    deliverables: dict[str, bool]
    guideline_version: str = "publication-v1"


class CodeGenerationArguments(BaseModel):
    bundle_id: str
    languages: list[Literal["python", "stata_do"]] = Field(min_length=1)


class ManifestArguments(BaseModel):
    artifact_set_id: str
    selected_artifact_ids: list[str] = Field(min_length=1)


class OutputReviewArguments(BaseModel):
    artifact_set_id: str
    artifact_set_hash: str
    selected_artifact_ids: list[str] = Field(min_length=1)
    guideline_version: str


class ArtifactRegenerationArguments(BaseModel):
    artifact_id: str
    patch: dict[str, str] = Field(min_length=1)


class ReportRevisionArguments(BaseModel):
    artifact_id: str
    directive_id: str
    target_section_ids: list[str] = Field(min_length=1)
    target_artifact_hash: str


class ReportGenerationArguments(BaseModel):
    bundle_id: str
    guideline_version: str
    citation_refs: list[str] = Field(default_factory=list)


class PlannedArguments(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)


class GenericResult(BaseModel):
    result_refs: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


def _descriptor(
    capability_id: str,
    display_name: str,
    description: str,
    kind: CapabilityKind,
    stages: list[StageId],
    input_model: type[BaseModel],
    *,
    output_model: type[BaseModel] = GenericResult,
    availability: CapabilityAvailability = CapabilityAvailability.AVAILABLE,
    invocation_mode: InvocationMode = InvocationMode.STAGE_COMMAND,
    approval_policy: ApprovalPolicy = ApprovalPolicy.NONE,
    data_access_policy: DataAccessPolicy = DataAccessPolicy.NONE,
    handler_ref: str | None,
    unavailable_reason: str | None = None,
    allowed_callers: list[Literal["user", "agent", "system"]] | None = None,
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        version="1.0.0",
        display_name=display_name,
        description=description,
        kind=kind,
        stages=stages,
        availability=availability,
        invocation_mode=invocation_mode,
        input_schema=input_model.model_json_schema(),
        output_schema=output_model.model_json_schema(),
        approval_policy=approval_policy,
        data_access_policy=data_access_policy,
        handler_ref=handler_ref,
        unavailable_reason=unavailable_reason,
        allowed_callers=allowed_callers or ["user", "agent"],
        retry_policy=RetryPolicy(max_attempts=1, timeout_seconds=120),
    )


def default_capability_registry(*, codex_local_visual_review: bool = False) -> CapabilityRegistry:
    descriptors = [
        _descriptor(
            "geography.resolve",
            "Resolve controlled geography",
            "Resolve a country or group through the versioned local geography registry.",
            CapabilityKind.FUNCTION,
            ["plan", "agent"],
            GeographyResolveArguments,
            output_model=GeographyResolveOutput,
            invocation_mode=InvocationMode.DIRECT,
            handler_ref="direct:geography.resolve",
        ),
        _descriptor(
            "aggregation.apply",
            "Apply controlled aggregation",
            "Aggregate reviewed member observations with explicit weighting and coverage rules.",
            CapabilityKind.FUNCTION,
            ["data", "transformation", "agent"],
            AggregationArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.pipeline:group_aggregation",
        ),
        _descriptor(
            "connector.local_file",
            "Local file intake",
            "Inspect and normalize a user-selected CSV, JSON or XLSX file.",
            CapabilityKind.CONNECTOR,
            ["plan", "data", "agent"],
            LocalFileArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.upload:local_file",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.imf_data",
            "IMF Data Portal",
            "Registered public SDMX datasets with explicit countries, indicators "
            "and bounded periods.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            ImfDataArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:imf_data",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.world_bank",
            "World Bank Indicators",
            "World Development Indicators source 2 with explicit economies, indicators and years.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            WorldBankArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:world_bank",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.oecd",
            "OECD Composite Leading Indicators",
            "Pinned OECD CLI 4.1 monthly harmonised index with explicit reference areas and dates.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            OecdArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:oecd",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.eurostat",
            "Eurostat HICP index",
            "Monthly all-items HICP index, 2025=100, with reviewed ISO3-to-geo mapping.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            EurostatArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:eurostat",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.adb",
            "ADB Key Indicators national accounts",
            "Annual DF_NA GDP/value-added series for reviewed ADB economy mappings, 2000–2024.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            AdbArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:adb",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.ecb",
            "ECB euro reference exchange rates",
            "Monthly average spot reference rates quoted as foreign currency per euro.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            EcbArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:ecb",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.bis",
            "BIS central bank policy rates",
            "Monthly end-of-period central bank policy rates from pinned flow WS_CBPOL 1.0.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            BisArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:bis",
            allowed_callers=["user"],
        ),
        _descriptor(
            "connector.un_sdg",
            "UN SDG real GDP per capita growth",
            "Annual SDG 8.1.1 observations with release and disaggregation metadata preserved.",
            CapabilityKind.CONNECTOR,
            ["plan", "data"],
            UnSdgArguments,
            invocation_mode=InvocationMode.USER_ACTION,
            approval_policy=ApprovalPolicy.RESEARCH_PLAN,
            handler_ref="workflow.data:un_sdg",
            allowed_callers=["user"],
        ),
        _descriptor(
            "data.prepare",
            "Prepare active data",
            "Apply one allowlisted snapshot-producing Data preparation operation.",
            CapabilityKind.FUNCTION,
            ["data", "agent"],
            DataPreparationArguments,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.data:apply_data_operation",
        ),
        _descriptor(
            "transformation.apply",
            "Apply typed transformation",
            "Execute one reviewed transformation through the typed pipeline runner.",
            CapabilityKind.FUNCTION,
            ["transformation", "agent"],
            TransformationArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.pipeline:run_operation",
        ),
        _descriptor(
            "code.generate",
            "Generate reproduction code",
            "Generate Python and supported Stata code from the reviewed typed specification.",
            CapabilityKind.FUNCTION,
            ["transformation", "output", "agent"],
            CodeGenerationArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            handler_ref="workflow.code:generate",
        ),
        _descriptor(
            "artifact.chart.render",
            "Render chart artifacts",
            "Render deterministic publication-v1 SVG and native Excel chart artifacts.",
            CapabilityKind.RENDERER,
            ["output", "agent"],
            RenderArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:render_chart",
        ),
        _descriptor(
            "artifact.table.render",
            "Render table artifacts",
            "Render deterministic CSV and XLSX analytical tables.",
            CapabilityKind.RENDERER,
            ["output", "agent"],
            RenderArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:render_table",
        ),
        _descriptor(
            "artifact.report.generate",
            "Generate Research Report",
            "Generate a governed report from approved summaries, diagnostics and source refs.",
            CapabilityKind.RENDERER,
            ["output", "agent"],
            ReportGenerationArguments,
            approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:render_report",
        ),
        _descriptor(
            "output.review.structural",
            "Structural output review",
            "Run rule-addressed checks, including hash-bound SVG coordinate/tick calculation "
            "receipts, over the current ArtifactSet. Native receipts are not AI approval.",
            CapabilityKind.REVIEWER,
            ["output", "agent"],
            OutputReviewArguments,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:review_structural",
        ),
        _descriptor(
            "output.review.visual",
            "Visual output review",
            "Review direct fixed-size artifact renders locally or through an authorized provider.",
            CapabilityKind.REVIEWER,
            ["output", "agent"],
            OutputReviewArguments,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:review_visual",
        ),
        _descriptor(
            "output.review.semantic_report",
            "Semantic Research Report review",
            "Review report claims against approved hash-bound data and model results.",
            CapabilityKind.REVIEWER,
            ["output", "agent"],
            OutputReviewArguments,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:review_semantic_report",
        ),
        _descriptor(
            "artifact.regenerate",
            "Selective artifact regeneration",
            "Regenerate one artifact from an approved typed specification patch.",
            CapabilityKind.FUNCTION,
            ["output", "agent"],
            ArtifactRegenerationArguments,
            handler_ref="workflow.output:regenerate",
        ),
        _descriptor(
            "artifact.report.revise",
            "Revise approved report sections",
            "Rewrite only sections named by a user-approved Report Reviewer directive.",
            CapabilityKind.FUNCTION,
            ["output", "agent"],
            ReportRevisionArguments,
            data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
            handler_ref="workflow.output:revise_report_sections",
            allowed_callers=["user"],
        ),
        _descriptor(
            "manifest.freeze",
            "Freeze reproduction manifest",
            "Create the final manifest for the selected immutable artifact set.",
            CapabilityKind.FUNCTION,
            ["output"],
            ManifestArguments,
            approval_policy=ApprovalPolicy.FINAL_OUTPUTS,
            handler_ref="workflow.output:finalize_manifest",
            allowed_callers=["user"],
        ),
    ]
    for model_id, display_name, input_model in (
        ("descriptive", "Descriptive statistics", DescriptiveModelArguments),
        ("correlation", "Correlation model", CorrelationModelArguments),
        ("ols", "OLS model", OlsModelArguments),
        ("adf", "ADF unit-root test", AdfModelArguments),
        ("arima", "ARIMA forecast model", ArimaModelArguments),
        ("sarimax", "SARIMAX forecast model", SarimaxModelArguments),
        ("var", "VAR and impulse-response model", VarModelArguments),
    ):
        descriptors.append(
            _descriptor(
                f"model.{model_id}",
                display_name,
                f"Run a reviewed {model_id} specification on an approved input.",
                CapabilityKind.MODEL,
                ["transformation", "agent"],
                input_model,
                approval_policy=ApprovalPolicy.PIPELINE_EXECUTION,
                data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
                handler_ref=f"workflow.model:{model_id}",
            )
        )
    if codex_local_visual_review:
        descriptors.append(
            _descriptor(
                "output.review.remote_visual",
                "Codex-local multimodal output review",
                "Review checksum-bound direct renders through the locally authenticated Codex "
                "runtime. Project-specific visual rules remain missing.",
                CapabilityKind.REVIEWER,
                ["output", "agent"],
                OutputReviewArguments,
                data_access_policy=DataAccessPolicy.SNAPSHOT_READ,
                invocation_mode=InvocationMode.STAGE_COMMAND,
                handler_ref="workflow.output:review_codex_local",
            )
        )
    planned: list[tuple[str, str, CapabilityKind, list[StageId], str]] = []
    if not codex_local_visual_review:
        planned.append(
            (
                "output.review.remote_visual",
                "Remote multimodal output review",
                CapabilityKind.REVIEWER,
                ["output", "agent"],
                "No authorized multimodal Output reviewer is configured.",
            )
        )
    descriptors.extend(
        _descriptor(
            capability_id,
            display_name,
            reason,
            kind,
            stages,
            PlannedArguments,
            availability=CapabilityAvailability.PLANNED,
            invocation_mode=InvocationMode.STAGE_COMMAND,
            handler_ref=None,
            unavailable_reason=reason,
        )
        for capability_id, display_name, kind, stages, reason in planned
    )
    return CapabilityRegistry(descriptors)
