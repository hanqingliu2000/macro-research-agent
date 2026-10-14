from __future__ import annotations

from copy import deepcopy

import pytest
from macro_research_agent.workflow.planning_service import plan_from_wire, plan_to_wire
from macro_research_agent.workflow.schemas import ModelIntentV2, ResearchPeriod
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("frequency", "start", "end"),
    [
        ("annual", "2020", "2024"),
        ("annual", "2020", "latest"),
        ("monthly", "2020-01", "2024-12"),
        ("monthly", "2020-01", "latest"),
        ("quarterly", "2020-Q1", "2024-Q4"),
        ("quarterly", "2020-Q1", "latest"),
    ],
)
def test_research_period_accepts_only_frequency_aligned_values(
    frequency: str, start: str, end: str
) -> None:
    period = ResearchPeriod.model_validate({"frequency": frequency, "start": start, "end": end})
    assert period.end == end


@pytest.mark.parametrize(
    ("frequency", "start", "end"),
    [
        ("annual", "2020-01", "2024"),
        ("monthly", "2020", "2024"),
        ("quarterly", "2020-Q0", "2024-Q4"),
        ("annual", "latest", "latest"),
        ("annual", "2025", "2024"),
    ],
)
def test_research_period_rejects_mixed_invalid_or_reversed_values(
    frequency: str, start: str, end: str
) -> None:
    with pytest.raises(ValidationError):
        ResearchPeriod.model_validate({"frequency": frequency, "start": start, "end": end})


@pytest.mark.parametrize(
    ("capability_id", "roles"),
    [
        ("var", ["system", "system"]),
        ("descriptive", ["descriptive"]),
        ("correlation", ["descriptive", "descriptive"]),
        ("ols", ["dependent", "independent"]),
        ("adf", ["dependent"]),
        ("arima", ["dependent", "dependent"]),
        ("sarimax", ["dependent", "exogenous"]),
    ],
)
def test_model_intent_v2_accepts_registered_role_contracts(
    capability_id: str, roles: list[str]
) -> None:
    intent = ModelIntentV2.model_validate(
        {
            "capability_id": capability_id,
            "purpose": "Contract test",
            "variables": [
                {"indicator_code": f"S{index}", "role": role, "order": index}
                for index, role in enumerate(roles, start=1)
            ],
            "forecast_horizon": (
                {"steps": 6, "unit": "periods", "confidence_level": 0.9}
                if capability_id in {"var", "arima", "sarimax"}
                else None
            ),
        }
    )
    assert intent.target_indicators == [f"S{index}" for index in range(1, len(roles) + 1)]


@pytest.mark.parametrize(
    ("capability_id", "roles"),
    [
        ("var", ["system"]),
        ("descriptive", ["dependent"]),
        ("correlation", ["descriptive", "independent"]),
        ("ols", ["dependent", "dependent"]),
        ("adf", ["descriptive"]),
        ("arima", ["dependent", "independent"]),
        ("sarimax", ["dependent"]),
    ],
)
def test_model_intent_v2_rejects_incompatible_roles(capability_id: str, roles: list[str]) -> None:
    with pytest.raises(ValidationError, match="invalid variable roles"):
        ModelIntentV2.model_validate(
            {
                "capability_id": capability_id,
                "purpose": "Invalid contract",
                "variables": [
                    {"indicator_code": f"S{index}", "role": role, "order": index}
                    for index, role in enumerate(roles, start=1)
                ],
            }
        )


def test_plan_wire_round_trip_derives_compatibility_targets_from_variables() -> None:
    wire = {
        "objective": "Explain inflation using policy rates.",
        "geographyIntent": "China",
        "period": {"start": "2020-01", "end": "latest", "frequency": "monthly"},
        "geographyResolutions": [
            {
                "id": "geo-chn",
                "label": "China",
                "kind": "country",
                "memberCodes": ["CHN"],
                "membershipSource": "registry",
                "effectivePeriod": "2020-01/latest",
                "confirmed": False,
            }
        ],
        "dataSources": [
            {
                "id": "source-1",
                "connectorId": "local_file",
                "provider": "Local file",
                "dataset": "macro",
                "indicators": ["CPI", "RATE"],
                "queryIntent": "Read reviewed data.",
                "enabled": True,
            }
        ],
        "transformationIntents": [],
        "modelIntents": [
            {
                "capabilityId": "ols",
                "id": "ols",
                "purpose": "Estimate association.",
                "label": "Legacy label",
                "enabled": True,
                "variables": [
                    {"indicatorCode": "CPI", "role": "dependent", "order": 1},
                    {"indicatorCode": "RATE", "role": "independent", "order": 2},
                ],
                "targetIndicators": ["RATE", "CPI"],
            }
        ],
        "capabilityInvocations": [],
        "deliverables": {},
        "assumptions": [],
        "warnings": [],
        "unresolvedItems": [],
    }

    plan = plan_from_wire(deepcopy(wire))
    output = plan_to_wire(plan)

    assert output["modelIntents"][0]["targetIndicators"] == ["CPI", "RATE"]
    assert output["modelIntents"][0]["variables"][1]["role"] == "independent"


def test_plan_rejects_model_indicator_outside_enabled_sources() -> None:
    wire = {
        "objective": "Describe CPI.",
        "geographyIntent": "China",
        "period": {"start": "2020", "end": "2024", "frequency": "annual"},
        "geographyResolutions": [],
        "dataSources": [
            {
                "connectorId": "local_file",
                "dataset": "macro",
                "indicators": ["CPI"],
                "queryIntent": "Read reviewed data.",
                "enabled": True,
            }
        ],
        "transformationIntents": [],
        "modelIntents": [
            {
                "capabilityId": "descriptive",
                "purpose": "Describe an invented variable.",
                "enabled": True,
                "variables": [{"indicatorCode": "INVENTED", "role": "descriptive", "order": 1}],
            }
        ],
        "capabilityInvocations": [],
        "deliverables": {},
    }

    with pytest.raises(ValidationError, match="enabled data sources"):
        plan_from_wire(wire)
