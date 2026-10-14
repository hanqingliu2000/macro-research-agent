from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from macro_research_agent.models.specs import ModelSpecification
from macro_research_agent.workflow.output_review import ArtifactPatch, OutputReviewReport
from macro_research_agent.workflow.states import ApprovalGate, SessionState, WorkflowStage

Frequency = Literal["monthly", "quarterly", "annual"]
LogicalRole = Literal[
    "series_id",
    "entity_code",
    "indicator_code",
    "frequency",
    "period",
    "value",
    "attribute",
    "ignore",
]
ParameterValue = str | int | float | bool | list[str] | list[int]


class CommandMeta(BaseModel):
    command_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    expected_stage: WorkflowStage
    expected_snapshot_hash: str = Field(min_length=1)
    actor: Literal["user", "agent"]
    requested_at: datetime


class StrictPlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClarificationQuestion(StrictPlanningModel):
    question_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)


class ClarificationBatch(StrictPlanningModel):
    questions: list[ClarificationQuestion] = Field(min_length=1, max_length=6)
    answered: dict[str, str] = Field(default_factory=dict)


class WorkflowNodeRecord(BaseModel):
    node_id: str
    node_kind: Literal[
        "research_request",
        "clarification_batch",
        "research_plan",
        "geography_resolution",
        "data_acquisition",
        "data_merge",
        "data_preparation",
        "external_round_trip",
        "transformation_pipeline",
        "model_execution",
        "stage_handoff",
        "output_generation",
        "output_revision",
        "reproduction_manifest",
    ]
    status: Literal[
        "pending",
        "ready",
        "in_progress",
        "waiting_for_review",
        "approved",
        "completed",
        "stale",
        "failed",
        "cancelled",
    ]
    attempt: int = Field(default=1, ge=1)
    parent_node_ids: list[str] = Field(default_factory=list)
    input_snapshot_refs: list[str] = Field(default_factory=list)
    output_snapshot_ref: str | None = None
    required_checkpoint: ApprovalGate | None = None
    stale_reason: str | None = None
    supersedes_node_id: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowSessionProjection(BaseModel):
    session_id: str
    status: SessionState
    active_stage: WorkflowStage
    reachable_stages: list[WorkflowStage]
    current_snapshot_hash: str
    nodes: list[WorkflowNodeRecord]


class WorkflowCommandResult(BaseModel):
    projection: WorkflowSessionProjection
    created_snapshot_refs: list[str] = Field(default_factory=list)
    invalidated_node_ids: list[str] = Field(default_factory=list)
    outcome: str


class ResearchPeriod(StrictPlanningModel):
    start: str
    end: str
    frequency: Frequency

    @model_validator(mode="after")
    def validate_frequency_periods(self) -> ResearchPeriod:
        patterns = {
            "annual": r"^\d{4}$",
            "monthly": r"^\d{4}-(?:0[1-9]|1[0-2])$",
            "quarterly": r"^\d{4}-Q[1-4]$",
        }
        pattern = patterns[self.frequency]
        if not re.fullmatch(pattern, self.start):
            raise ValueError(f"period.start must match {self.frequency} frequency")
        if self.end != "latest" and not re.fullmatch(pattern, self.end):
            raise ValueError(f"period.end must match {self.frequency} frequency or latest")
        if self.end != "latest" and self.start > self.end:
            raise ValueError("period.start must not be after period.end")
        return self


class AggregationSpecification(StrictPlanningModel):
    method: Literal["sum", "simple_mean", "weighted_mean"]
    weight_indicator: str | None = None
    weight_source: str | None = None
    missing_data_policy: Literal["available_members", "balanced_members"]
    coverage_threshold: float = Field(ge=0, le=1)
    membership_policy: Literal["period_specific", "fixed_snapshot"]

    @model_validator(mode="after")
    def require_weight_for_weighted_mean(self) -> AggregationSpecification:
        if self.method == "weighted_mean" and not (self.weight_indicator and self.weight_source):
            raise ValueError("weighted_mean requires a weight indicator and source")
        return self


class GeographyResolution(StrictPlanningModel):
    resolution_id: str
    label: str
    kind: Literal["country", "country_group"]
    member_codes: list[str] = Field(min_length=1)
    membership_source: str
    effective_period: str
    confirmed: bool = False
    aggregation: AggregationSpecification | None = None


class DataSourceIntent(StrictPlanningModel):
    connector_id: str
    dataset: str
    indicators: list[str] = Field(min_length=1)
    query_intent: str


class CapabilityIntent(StrictPlanningModel):
    capability_id: str
    label: str
    enabled: bool = True
    target_indicators: list[str] = Field(default_factory=list)


class ForecastHorizon(StrictPlanningModel):
    steps: int = Field(ge=1, le=240)
    unit: Literal["periods"] = "periods"
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1)


class ModelVariable(StrictPlanningModel):
    indicator_code: str = Field(min_length=1)
    role: Literal["system", "descriptive", "dependent", "independent", "exogenous"]
    order: int = Field(ge=1)


class ModelIntentV2(StrictPlanningModel):
    capability_id: str = Field(min_length=1)
    enabled: bool = True
    purpose: str = Field(min_length=1)
    variables: list[ModelVariable] = Field(min_length=1)
    forecast_horizon: ForecastHorizon | None = None

    @property
    def target_indicators(self) -> list[str]:
        return [
            item.indicator_code
            for item in sorted(self.variables, key=lambda variable: variable.order)
        ]

    @model_validator(mode="after")
    def validate_model_roles(self) -> ModelIntentV2:
        if not self.enabled:
            return self
        ordered = sorted(self.variables, key=lambda item: item.order)
        if [item.order for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("model variables must use unique contiguous order values from 1")
        if len({item.indicator_code for item in ordered}) != len(ordered):
            raise ValueError("model variables must use unique indicator codes")
        roles: dict[str, list[ModelVariable]] = {}
        for item in ordered:
            roles.setdefault(item.role, []).append(item)
        kind = self.capability_id
        valid = True
        if kind == "var":
            valid = len(roles.get("system", [])) >= 2 and len(roles) == 1
        elif kind in {"descriptive", "correlation"}:
            valid = len(roles.get("descriptive", [])) >= 1 and len(roles) == 1
        elif kind == "ols":
            valid = (
                len(roles.get("dependent", [])) == 1
                and len(roles.get("independent", [])) >= 1
                and set(roles) == {"dependent", "independent"}
            )
        elif kind in {"adf", "arima"}:
            valid = len(roles.get("dependent", [])) >= 1 and len(roles) == 1
        elif kind == "sarimax":
            valid = (
                len(roles.get("dependent", [])) == 1
                and len(roles.get("exogenous", [])) >= 1
                and set(roles) == {"dependent", "exogenous"}
            )
        if not valid:
            raise ValueError(f"invalid variable roles for {kind}")
        if self.forecast_horizon is not None and kind not in {"arima", "sarimax", "var"}:
            raise ValueError("forecast_horizon is allowed only for forecasting models")
        return self


class PlannedCapabilityInvocation(StrictPlanningModel):
    capability_id: str = Field(min_length=1)
    capability_version: str = Field(min_length=1)
    stage: WorkflowStage
    purpose: str = Field(min_length=1)
    availability: Literal["available", "planned", "disabled"]
    approval_gate: ApprovalGate | None = None


class DeliverableSelection(StrictPlanningModel):
    charts: bool = True
    tables: bool = True
    clean_data: bool = True
    python: bool = True
    stata: bool = True
    research_report: bool = False


class PlanDraft(StrictPlanningModel):
    objective: str
    geography_intent: str
    period: ResearchPeriod
    geography_resolutions: list[GeographyResolution]
    data_sources: list[DataSourceIntent]
    transformation_intents: list[CapabilityIntent] = Field(default_factory=list)
    model_intents: list[ModelIntentV2] = Field(default_factory=list)
    capability_invocations: list[PlannedCapabilityInvocation] = Field(default_factory=list)
    deliverables: DeliverableSelection
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_model_variables_from_enabled_sources(self) -> PlanDraft:
        indicators = {code for source in self.data_sources for code in source.indicators}
        missing = [
            variable.indicator_code
            for intent in self.model_intents
            if intent.enabled
            for variable in intent.variables
            if variable.indicator_code not in indicators
        ]
        if missing:
            raise ValueError(
                "model variables must use indicators from enabled data sources: "
                + ", ".join(dict.fromkeys(missing))
            )
        return self


class TitledPlanDraft(PlanDraft):
    session_title: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"\S",
        description="Short research title based on this Plan, in the user's language; no markup.",
    )


class PlanPatchChanges(StrictPlanningModel):
    objective: str | None = None
    geography_intent: str | None = None
    period: ResearchPeriod | None = None
    geography_resolutions: list[GeographyResolution] | None = None
    data_sources: list[DataSourceIntent] | None = None
    transformation_intents: list[CapabilityIntent] | None = None
    model_intents: list[ModelIntentV2] | None = None
    capability_invocations: list[PlannedCapabilityInvocation] | None = None
    deliverables: DeliverableSelection | None = None
    assumptions: list[str] | None = None
    warnings: list[str] | None = None
    unresolved_items: list[str] | None = None


class PlanPatch(StrictPlanningModel):
    target_snapshot_hash: str
    summary: str
    changes: PlanPatchChanges
    affected_stages: list[WorkflowStage]


class ApprovedPlanSnapshot(BaseModel):
    snapshot_id: str
    snapshot_hash: str
    approved_at: datetime
    plan: PlanDraft

    @model_validator(mode="after")
    def require_resolved_geographies(self) -> ApprovedPlanSnapshot:
        for geography in self.plan.geography_resolutions:
            if not geography.confirmed:
                raise ValueError("all geography resolutions must be confirmed")
            if geography.kind == "country_group" and geography.aggregation is None:
                raise ValueError("country groups require an aggregation specification")
        if self.plan.unresolved_items:
            raise ValueError("approved plans cannot contain unresolved items")
        return self


class DatasetColumn(BaseModel):
    name: str
    data_type: Literal["string", "number", "period"]
    logical_role: LogicalRole
    required: bool = False
    key: bool = False


class DatasetSchema(BaseModel):
    schema_id: str
    columns: list[DatasetColumn]
    unique_key: list[str]


class DatasetSnapshotReference(BaseModel):
    snapshot_id: str
    snapshot_hash: str
    schema_id: str
    source_kind: Literal["connector", "prepared", "external_round_trip", "analytical"]
    parent_snapshot_id: str | None = None


class SourceRunReference(BaseModel):
    run_id: str
    connector_id: str
    dataset: str
    query_hash: str
    provenance_ref: str
    status: Literal["ready", "running", "completed", "failed"]


class DataWorkspaceState(BaseModel):
    source_runs: list[SourceRunReference]
    snapshots: list[DatasetSnapshotReference]
    active_dataset: DatasetSnapshotReference
    dataset_schema: DatasetSchema
    quality_diagnostics: dict[str, str | int | float | bool]
    entity_mappings: dict[str, str] = Field(default_factory=dict)
    indicator_mappings: dict[str, str] = Field(default_factory=dict)
    preparation_operation_ids: list[str] = Field(default_factory=list)
    preview_ref: str


class RoundTripManifest(BaseModel):
    session_id: str
    snapshot_id: str
    schema_id: str
    workbook_checksum: str
    source_snapshot_id: str
    manifest_verified: bool
    formulas_materialized: bool


class ColumnMapping(BaseModel):
    source_column: str
    target_column: str | None = None
    logical_role: LogicalRole


class ApprovedDatasetRef(BaseModel):
    snapshot: DatasetSnapshotReference
    schema_hash: str
    preparation_recipe_ref: str
    round_trip_manifest: RoundTripManifest | None = None


TransformationKind = Literal[
    "lag",
    "lead",
    "difference",
    "yoy_growth",
    "period_growth",
    "log",
    "rebase_index",
    "unit_conversion",
    "deflate",
    "per_capita",
    "frequency_conversion",
    "merge",
    "rolling_mean",
    "seasonal_rule",
    "group_aggregation",
]


class TargetSelector(BaseModel):
    input_ref: str
    indicators: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    period_start: str | None = None
    period_end: str | None = None
    frequency: Frequency | None = None


class TransformationOperation(BaseModel):
    operation_id: str
    operation: TransformationKind
    input_ref: str
    target: TargetSelector
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)
    output_ref: str
    enabled: bool = True


class ModelJob(BaseModel):
    job_id: str
    input_ref: str
    specification: ModelSpecification


class TransformationLineage(BaseModel):
    operation_id: str
    operation: TransformationKind
    input_ref: str
    output_ref: str
    input_snapshot_id: str
    input_snapshot_hash: str
    output_snapshot_id: str
    output_snapshot_hash: str
    specification_hash: str
    input_rows: int = Field(ge=0)
    output_rows: int = Field(ge=0)


class AnalyticalBundle(BaseModel):
    bundle_id: str
    input_snapshot_id: str
    final_dataset_ref: str
    operation_lineage: list[TransformationLineage]
    model_result_refs: list[str]
    diagnostics: list[str]
    warnings: list[str]
    python_code_ref: str
    stata_code_ref: str | None = None


class ArtifactReference(BaseModel):
    artifact_id: str
    kind: Literal[
        "chart",
        "table",
        "research_report",
        "underlying_data",
        "python",
        "stata",
        "workbook",
        "manifest",
    ]
    media_type: str
    content_hash: str
    status: Literal["ready", "stale", "frozen"]


class OutputRevisionProposal(BaseModel):
    proposal_id: str
    request: str
    target_artifact_set_hash: str
    summary: str
    affected_artifact_ids: list[str]
    target_artifact_hashes: dict[str, str]
    patches: list[ArtifactPatch]


class ArtifactSet(BaseModel):
    artifact_set_id: str
    artifact_set_hash: str
    guideline_version: str
    artifacts: list[ArtifactReference]
    provenance_refs: list[str]
    limitations: list[str]
    reproduction_manifest_ref: str
    artifact_specifications: dict[str, dict[str, object]] = Field(default_factory=dict)
    output_review: OutputReviewReport | None = None
    frozen_at: datetime | None = None
