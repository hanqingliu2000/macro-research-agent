from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Protocol, TypeVar, cast

from pydantic import BaseModel, Field

from macro_research_agent.workflow.model_data_access import ModelDataPage, ModelDatasetContext
from macro_research_agent.workflow.schemas import (
    AggregationSpecification,
    CapabilityIntent,
    ClarificationBatch,
    ClarificationQuestion,
    DataSourceIntent,
    DeliverableSelection,
    Frequency,
    GeographyResolution,
    ModelIntentV2,
    ModelVariable,
    PlanDraft,
    PlannedCapabilityInvocation,
    PlanPatch,
    PlanPatchChanges,
    ResearchPeriod,
)
from macro_research_agent.workflow.states import WorkflowStage

StructuredPlanningOutput = TypeVar("StructuredPlanningOutput", bound=BaseModel)


class PlanningDataAccessPort(Protocol):
    def read_page(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage: ...


class WorkflowPlanningContext(BaseModel):
    research_request: str
    reference_date: str | None = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    clarification_questions: list[dict[str, Any]] = Field(default_factory=list)
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    current_plan: PlanDraft | None = None
    available_connector_ids: list[str]
    available_transformation_ids: list[str] = Field(default_factory=list)
    available_model_ids: list[str] = Field(default_factory=list)
    available_deliverable_ids: list[str] = Field(default_factory=list)
    capability_catalog: list[dict[str, Any]] = Field(default_factory=list)
    source_knowledge_catalog_version: str | None = None
    source_knowledge_catalog_sha256: str | None = None
    source_knowledge: list[dict[str, Any]] = Field(default_factory=list)
    uploaded_schema_summaries: list[dict[str, Any]] = Field(default_factory=list)
    uploaded_data_contexts: list[ModelDatasetContext] = Field(default_factory=list)


class WorkflowPlanningProvider(ABC):
    remote_data_disclosure: bool = True
    provider_profile: str = "unconfigured"
    model_id: str = "unconfigured"

    @abstractmethod
    async def clarification_batch(
        self,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> ClarificationBatch:
        raise NotImplementedError

    @abstractmethod
    async def draft_plan(
        self,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> PlanDraft:
        raise NotImplementedError

    @abstractmethod
    async def propose_patch(
        self,
        request: str,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> PlanPatch:
        raise NotImplementedError


# Product-facing port name used by the Phase 1E architecture documents.
PlanningAssistantPort = WorkflowPlanningProvider


def validate_structured_output(
    model: type[StructuredPlanningOutput], payload: dict[str, Any]
) -> StructuredPlanningOutput:
    return model.model_validate(payload)


def openai_structured_request(
    *, model: str, instructions: str, input_text: str, output_model: type[BaseModel]
) -> dict[str, Any]:
    """Build, but never send, a Responses API structured-output request."""

    def strict_schema(value: Any) -> Any:
        if isinstance(value, list):
            return [strict_schema(item) for item in value]
        if not isinstance(value, dict):
            return value
        normalized = {key: strict_schema(item) for key, item in value.items() if key != "default"}
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["additionalProperties"] = False
            normalized["required"] = list(properties)
        return normalized

    return {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": output_model.__name__,
                "strict": True,
                "schema": strict_schema(output_model.model_json_schema()),
            }
        },
    }


class DeterministicPlanningProvider(WorkflowPlanningProvider):
    """Offline provider for contract acceptance before live model integration."""

    remote_data_disclosure = False
    provider_profile = "deterministic-local"
    model_id = "deterministic-planning-v1"

    async def clarification_batch(
        self,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> ClarificationBatch:
        period_options = ["2015-2024 annual", "2019-2024 quarterly", "2019-2024 monthly"]
        period_match = re.search(
            r"\b(19|20)\d{2}\s*[-–—/]\s*((?:19|20)\d{2})\b", context.research_request
        )
        lowered = context.research_request.lower()
        requested_frequency = next(
            (value for value in ("monthly", "quarterly", "annual") if value in lowered),
            None,
        )
        if period_match and requested_frequency:
            requested_period = (
                f"{period_match.group(0)[:4]}-{period_match.group(2)} {requested_frequency}"
            )
            period_options = list(dict.fromkeys([requested_period, *period_options]))
        return ClarificationBatch(
            questions=[
                ClarificationQuestion(
                    question_id="geography_scope",
                    prompt="Which economies or country group should the research cover?",
                    options=["Use the economies in my request", "G7", "Euro area"],
                ),
                ClarificationQuestion(
                    question_id="period_frequency",
                    prompt="Which default time frame and frequency should be used?",
                    options=period_options,
                ),
            ]
        )

    async def draft_plan(
        self,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> PlanDraft:
        period_answer = context.clarification_answers.get("period_frequency", "2015-2024 annual")
        frequency = (
            "monthly"
            if "monthly" in period_answer
            else "quarterly"
            if "quarterly" in period_answer
            else "annual"
        )
        bounds = period_answer.split()[0].split("-")
        start, end = (bounds[0], bounds[1]) if len(bounds) == 2 else ("2015", "2024")
        if frequency == "monthly":
            start, end = f"{start}-01", f"{end}-12"
        elif frequency == "quarterly":
            start, end = f"{start}-Q1", f"{end}-Q4"
        geography = context.clarification_answers.get(
            "geography_scope", "Use the economies in my request"
        )
        group = geography in {"G7", "Euro area"}
        g7 = ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"]
        euro = [
            "AUT",
            "BEL",
            "HRV",
            "CYP",
            "EST",
            "FIN",
            "FRA",
            "DEU",
            "GRC",
            "IRL",
            "ITA",
            "LVA",
            "LTU",
            "LUX",
            "MLT",
            "NLD",
            "PRT",
            "SVK",
            "SVN",
            "ESP",
        ]
        request_lower = context.research_request.lower()
        requested_countries = [
            code
            for code, aliases in [
                ("CHN", ("china", "中国")),
                ("USA", ("united states", "u.s.", " usa")),
                ("JPN", ("japan",)),
                ("GBR", ("united kingdom", "britain", " uk")),
                ("CAN", ("canada",)),
                ("FRA", ("france",)),
                ("DEU", ("germany",)),
                ("ITA", ("italy",)),
            ]
            if any(alias in request_lower for alias in aliases)
        ]
        request_is_euro_area = "euro area" in request_lower or "eurozone" in request_lower
        members = (
            g7
            if geography == "G7"
            else euro
            if geography == "Euro area" or request_is_euro_area
            else requested_countries or ["USA"]
        )
        group = group or request_is_euro_area
        geography_label = "Euro area" if request_is_euro_area else geography
        geography_resolutions = (
            [
                GeographyResolution(
                    resolution_id="geo-primary",
                    label=geography_label,
                    kind="country_group",
                    member_codes=members,
                    membership_source="MRA controlled geography registry v1",
                    effective_period=f"{start}/{end}",
                    confirmed=False,
                    aggregation=AggregationSpecification(
                        method="simple_mean",
                        missing_data_policy="available_members",
                        coverage_threshold=0.8,
                        membership_policy="period_specific",
                    ),
                )
            ]
            if group
            else [
                GeographyResolution(
                    resolution_id="geo-primary" if index == 0 else f"geo-request-{index + 1}",
                    label=code,
                    kind="country",
                    member_codes=[code],
                    membership_source="MRA controlled geography registry v1",
                    effective_period=f"{start}/{end}",
                    confirmed=False,
                )
                for index, code in enumerate(members)
            ]
        )
        uploaded = bool(context.uploaded_schema_summaries)
        uploaded_indicators = list(
            dict.fromkeys(
                str(row.get("indicator_code") or row.get("indicator") or "").strip().upper()
                for dataset in context.uploaded_data_contexts
                for row in (dataset.initial_page.rows if dataset.initial_page else [])
                if str(row.get("indicator_code") or row.get("indicator") or "").strip()
            )
        )
        planned_indicators = uploaded_indicators or ["value" if uploaded else "research_indicator"]
        plan = PlanDraft(
            objective=context.research_request,
            geography_intent=geography,
            period=ResearchPeriod(start=start, end=end, frequency=cast(Frequency, frequency)),
            geography_resolutions=geography_resolutions,
            data_sources=[
                DataSourceIntent(
                    connector_id="local_file" if uploaded else "imf_data",
                    dataset="uploaded_file" if uploaded else "International Financial Statistics",
                    indicators=planned_indicators,
                    query_intent=(
                        "Use the reviewed uploaded values through their data-access grant."
                        if uploaded
                        else "Retrieve the requested macroeconomic indicators."
                    ),
                )
            ],
            transformation_intents=[
                CapabilityIntent(capability_id="yoy_growth", label="Year-on-year growth")
            ],
            model_intents=[
                ModelIntentV2(
                    capability_id="descriptive",
                    purpose="Summarize the requested indicator.",
                    variables=[
                        ModelVariable(
                            indicator_code=planned_indicators[0],
                            role="descriptive",
                            order=1,
                        )
                    ],
                )
            ],
            deliverables=DeliverableSelection(
                research_report=(
                    "report" in request_lower
                    or "brief" in request_lower
                    or "报告" in context.research_request
                )
            ),
            assumptions=[
                "AI may inspect actual session data through read-only, snapshot-bound "
                "access grants."
            ],
            unresolved_items=[
                "Confirm the geography resolution and aggregation semantics.",
                *(
                    []
                    if uploaded
                    else [
                        "IMF Data is planned but unavailable; attach a local file or enable an "
                        "executable connector."
                    ]
                ),
            ],
        )
        desired = {
            "connector.local_file" if uploaded else "connector.imf_data": (
                WorkflowStage.DATA,
                "Acquire the reviewed research data.",
            ),
            "transformation.apply": (
                WorkflowStage.TRANSFORMATION,
                "Apply the reviewed transformation specification.",
            ),
            "model.descriptive": (
                WorkflowStage.TRANSFORMATION,
                "Run reviewed descriptive analysis.",
            ),
            "artifact.chart.render": (
                WorkflowStage.OUTPUT,
                "Render requested charts.",
            ),
            "artifact.table.render": (
                WorkflowStage.OUTPUT,
                "Render requested tables.",
            ),
            "output.review.structural": (
                WorkflowStage.OUTPUT,
                "Review output structure against publication rules.",
            ),
            "output.review.visual": (
                WorkflowStage.OUTPUT,
                "Review chart and table visual quality.",
            ),
        }
        catalog = {str(item.get("capability_id")): item for item in context.capability_catalog}
        plan.capability_invocations = [
            PlannedCapabilityInvocation(
                capability_id=capability_id,
                capability_version=str(catalog.get(capability_id, {}).get("version") or "1.0.0"),
                stage=stage,
                purpose=purpose,
                availability=cast(
                    Any,
                    catalog.get(capability_id, {}).get("availability") or "planned",
                ),
                approval_gate=(
                    catalog.get(capability_id, {}).get("approval_policy")
                    if catalog.get(capability_id, {}).get("approval_policy") != "none"
                    else None
                ),
            )
            for capability_id, (stage, purpose) in desired.items()
        ]
        return plan

    async def propose_patch(
        self,
        request: str,
        context: WorkflowPlanningContext,
        data_access: PlanningDataAccessPort | None = None,
    ) -> PlanPatch:
        if context.current_plan is None:
            raise ValueError("A current Plan is required before proposing a patch.")
        lowered = request.lower()
        if "report" in lowered:
            changes = PlanPatchChanges(
                deliverables=context.current_plan.deliverables.model_copy(
                    update={"research_report": True}
                )
            )
            summary = "Enable the Research Report deliverable."
            affected: list[WorkflowStage] = [WorkflowStage.OUTPUT]
        elif "2010" in lowered or "period" in lowered or "start" in lowered:
            changes = PlanPatchChanges(
                period=context.current_plan.period.model_copy(update={"start": "2010"})
            )
            summary = "Extend the research period start to 2010."
            affected = [WorkflowStage.DATA, WorkflowStage.TRANSFORMATION, WorkflowStage.OUTPUT]
        else:
            changes = PlanPatchChanges(
                objective=f"{context.current_plan.objective} {request}".strip(),
                assumptions=[*context.current_plan.assumptions, request],
            )
            summary = "Add the requested scope adjustment to the objective."
            affected = [WorkflowStage.DATA, WorkflowStage.TRANSFORMATION, WorkflowStage.OUTPUT]
        return PlanPatch(
            target_snapshot_hash="pending-server-snapshot",
            summary=summary,
            changes=changes,
            affected_stages=affected,
        )
