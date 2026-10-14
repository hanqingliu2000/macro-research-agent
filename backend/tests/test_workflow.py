import pytest
from macro_research_agent.workflow.schemas import (
    AggregationSpecification,
    ApprovedPlanSnapshot,
    DataSourceIntent,
    DeliverableSelection,
    GeographyResolution,
    PlanDraft,
    ResearchPeriod,
)
from macro_research_agent.workflow.states import SessionState, ensure_transition
from pydantic import ValidationError


def test_plan_approval_can_enter_acquisition() -> None:
    ensure_transition(SessionState.PLAN_REVIEW, SessionState.ACQUIRING)


def test_acquisition_cannot_skip_data_review() -> None:
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        ensure_transition(SessionState.ACQUIRING, SessionState.PIPELINE_EDITING)


def test_completed_work_is_an_immutable_audit_record() -> None:
    with pytest.raises(ValueError, match="completed -> data_review"):
        ensure_transition(SessionState.COMPLETED, SessionState.DATA_REVIEW)


def test_weighted_aggregation_requires_a_registered_weight_source() -> None:
    with pytest.raises(ValidationError, match="weight indicator and source"):
        AggregationSpecification(
            method="weighted_mean",
            weight_indicator="NGDP",
            missing_data_policy="available_members",
            coverage_threshold=0.8,
            membership_policy="period_specific",
        )


def test_approved_plan_rejects_an_unconfirmed_country_group() -> None:
    plan = PlanDraft(
        objective="Compare inflation paths.",
        geography_intent="Euro area",
        period=ResearchPeriod(start="2015-01", end="2025-12", frequency="monthly"),
        geography_resolutions=[
            GeographyResolution(
                resolution_id="ea",
                label="Euro area",
                kind="country_group",
                member_codes=["DEU", "FRA"],
                membership_source="registered-geography-resolver",
                effective_period="period-specific",
                confirmed=False,
                aggregation=AggregationSpecification(
                    method="weighted_mean",
                    weight_indicator="NGDP",
                    weight_source="imf_weo",
                    missing_data_policy="available_members",
                    coverage_threshold=0.8,
                    membership_policy="period_specific",
                ),
            )
        ],
        data_sources=[
            DataSourceIntent(
                connector_id="imf_data",
                dataset="CPI",
                indicators=["PCPI_IX"],
                query_intent="Acquire member-country CPI observations.",
            )
        ],
        deliverables=DeliverableSelection(research_report=True),
    )

    with pytest.raises(ValidationError, match="must be confirmed"):
        ApprovedPlanSnapshot(
            snapshot_id="plan-1",
            snapshot_hash="sha256:abc",
            approved_at="2026-08-24T12:00:00Z",
            plan=plan,
        )
