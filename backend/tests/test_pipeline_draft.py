import pytest
from macro_research_agent.workflow.pipeline_draft import (
    PlanPipelineDraftError,
    build_plan_pipeline_draft,
    planned_forecast_contract,
    validate_plan_pipeline_draft,
)


def test_approved_plan_intents_become_a_reviewable_pipeline_draft() -> None:
    draft = build_plan_pipeline_draft(
        {
            "dataSources": [
                {
                    "enabled": True,
                    "indicators": ["GGXWDG_NGDP", "GGXWDG"],
                }
            ],
            "transformationIntents": [
                {"id": "yoy_growth", "label": "Year-on-year growth", "enabled": True},
                {"id": "log", "label": "Natural logarithm", "enabled": False},
            ],
            "modelIntents": [
                {
                    "capabilityId": "descriptive",
                    "purpose": "Descriptive statistics",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": "GGXWDG_NGDP", "role": "descriptive", "order": 1},
                        {"indicatorCode": "GGXWDG", "role": "descriptive", "order": 2},
                    ],
                },
                {
                    "capabilityId": "ols",
                    "purpose": "OLS relationship",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": "GGXWDG_NGDP", "role": "dependent", "order": 1},
                        {"indicatorCode": "GGXWDG", "role": "independent", "order": 2},
                    ],
                },
            ],
        },
        ["GGXWDG", "GGXWDG_NGDP"],
        plan_snapshot_id="plan-approved-1",
    )

    assert draft["draftSource"] == "approved_plan"
    assert draft["sourcePlanSnapshotId"] == "plan-approved-1"
    assert [item["kind"] for item in draft["operations"]] == ["yoy_growth"]
    operation = draft["operations"][0]
    assert operation["target"]["indicators"] == ["GGXWDG_NGDP", "GGXWDG"]
    assert operation["status"] == "not_run"
    assert [item["kind"] for item in draft["models"]] == ["descriptive", "ols"]
    assert draft["models"][0]["variables"] == ["GGXWDG_NGDP", "GGXWDG"]
    assert draft["models"][1]["dependentVariables"] == ["GGXWDG_NGDP"]
    assert draft["models"][1]["independentVariables"] == ["GGXWDG"]
    assert all(item["inputRef"] == operation["outputRef"] for item in draft["models"])


def test_plan_with_no_enabled_analysis_keeps_an_explicit_empty_draft() -> None:
    draft = build_plan_pipeline_draft(
        {
            "dataSources": [],
            "transformationIntents": [],
            "modelIntents": [],
        },
        ["CPI"],
        plan_snapshot_id="plan-approved-2",
    )

    assert draft["operations"] == []
    assert draft["models"] == []
    assert draft["runStatus"] == "editing"


def test_two_year_multiseries_forecast_compiles_to_exact_executable_jobs() -> None:
    indicators = ["NGDP_RPCH", "GGXWDG_NGDP", "NE.CON.PRVT.KD.ZG", "NE.CON.PRVT.ZS"]
    draft = build_plan_pipeline_draft(
        {
            "objective": (
                "Project growth, consumption and debt together over a two-year forecast horizon."
            ),
            "period": {"start": "2000", "end": "2024", "frequency": "annual"},
            "dataSources": [{"enabled": True, "indicators": indicators}],
            "transformationIntents": [],
            "modelIntents": [
                {
                    "capabilityId": "arima",
                    "purpose": (
                        "Univariate baseline forecasts of growth, consumption and debt ratio"
                    ),
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": code, "role": "dependent", "order": index + 1}
                        for index, code in enumerate(indicators)
                    ],
                    "forecastHorizon": {
                        "steps": 2,
                        "unit": "periods",
                        "confidenceLevel": 0.9,
                    },
                },
                {
                    "capabilityId": "sarimax",
                    "purpose": "Multivariate forecast of growth with consumption and debt inputs",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": indicators[0], "role": "dependent", "order": 1},
                        *[
                            {"indicatorCode": code, "role": "exogenous", "order": index + 2}
                            for index, code in enumerate(indicators[1:])
                        ],
                    ],
                    "forecastHorizon": {
                        "steps": 2,
                        "unit": "periods",
                        "confidenceLevel": 0.9,
                    },
                },
            ],
        },
        indicators,
        plan_snapshot_id="plan-forecast-1",
    )

    arima_jobs = [item for item in draft["models"] if item["kind"] == "arima"]
    sarimax_jobs = [item for item in draft["models"] if item["kind"] == "sarimax"]
    assert [item["dependentVariables"][0] for item in arima_jobs] == indicators
    assert all(item["parameters"]["forecastSteps"] == 2 for item in arima_jobs)
    assert len(sarimax_jobs) == 1
    assert sarimax_jobs[0]["dependentVariables"] == [indicators[0]]
    assert sarimax_jobs[0]["independentVariables"] == indicators[1:]
    assert sarimax_jobs[0]["parameters"]["forecastSteps"] == 2


def test_joint_var_uses_explicit_ordered_targets_not_descriptive_only_indicator() -> None:
    indicators = ["NE.GDI.FTOT.ZS", "NE.CON.PRVT.ZS", "NY.GDP.MKTP.KD.ZG"]
    draft = build_plan_pipeline_draft(
        {
            "objective": "Forecast the two expenditure shares over a two-year forecast horizon.",
            "period": {"start": "2000", "end": "2024", "frequency": "annual"},
            "dataSources": [{"enabled": True, "indicators": indicators}],
            "transformationIntents": [],
            "modelIntents": [
                {
                    "capabilityId": "var",
                    "purpose": "Joint two-share VAR forecast",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": "NE.CON.PRVT.ZS", "role": "system", "order": 1},
                        {"indicatorCode": "NE.GDI.FTOT.ZS", "role": "system", "order": 2},
                    ],
                    "forecastHorizon": {
                        "steps": 2,
                        "unit": "periods",
                        "confidenceLevel": 0.95,
                    },
                },
                {
                    "capabilityId": "descriptive",
                    "purpose": "Describe GDP growth as context",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": "NY.GDP.MKTP.KD.ZG", "role": "descriptive", "order": 1}
                    ],
                },
            ],
        },
        indicators,
        plan_snapshot_id="plan-china-wdi-contract",
    )

    var_job = next(item for item in draft["models"] if item["kind"] == "var")
    descriptive = next(item for item in draft["models"] if item["kind"] == "descriptive")
    assert var_job["variables"] == ["NE.CON.PRVT.ZS", "NE.GDI.FTOT.ZS"]
    assert var_job["parameters"]["forecastSteps"] == 2
    assert descriptive["variables"] == ["NY.GDP.MKTP.KD.ZG"]


def test_compiler_never_infers_forecast_horizon_or_variables_from_prose() -> None:
    plan = {
        "objective": "Forecast CPI for the next 24 months.",
        "dataSources": [{"enabled": True, "indicators": ["CPI"]}],
        "transformationIntents": [],
        "modelIntents": [
            {
                "capabilityId": "arima",
                "purpose": "Two-year projection",
                "enabled": True,
                "variables": [{"indicatorCode": "CPI", "role": "dependent", "order": 1}],
            }
        ],
    }
    draft = build_plan_pipeline_draft(
        plan,
        ["CPI"],
        plan_snapshot_id="plan-no-prose-inference",
    )

    assert draft["models"][0]["dependentVariables"] == ["CPI"]
    assert draft["models"][0]["parameters"]["forecastSteps"] == 4
    assert planned_forecast_contract(plan, ["CPI"]) is None


def test_compiler_rejects_structured_variable_absent_from_dataset() -> None:
    with pytest.raises(PlanPipelineDraftError, match="absent from the approved dataset"):
        build_plan_pipeline_draft(
            {
                "dataSources": [{"enabled": True, "indicators": ["CPI"]}],
                "transformationIntents": [],
                "modelIntents": [
                    {
                        "capabilityId": "descriptive",
                        "purpose": "Describe a missing series",
                        "enabled": True,
                        "variables": [
                            {
                                "indicatorCode": "INVENTED",
                                "role": "descriptive",
                                "order": 1,
                            }
                        ],
                    }
                ],
            },
            ["CPI"],
            plan_snapshot_id="plan-missing-variable",
        )


def test_single_country_subperiod_average_is_not_group_aggregation() -> None:
    draft = build_plan_pipeline_draft(
        {
            "geographyResolutions": [
                {
                    "id": "geo-india",
                    "label": "India",
                    "kind": "country",
                    "memberCodes": ["IND"],
                    "confirmed": True,
                    "aggregation": None,
                }
            ],
            "dataSources": [
                {
                    "enabled": True,
                    "indicators": ["NE.CON.PRVT.ZS", "NE.GDI.TOTL.ZS"],
                }
            ],
            "transformationIntents": [
                {
                    "id": "group_aggregation",
                    "label": "Expenditure-share composition and sub-period averaging",
                    "enabled": True,
                }
            ],
            "modelIntents": [
                {
                    "capabilityId": "descriptive",
                    "purpose": "Pre/post comparison",
                    "enabled": True,
                    "variables": [
                        {"indicatorCode": "NE.CON.PRVT.ZS", "role": "descriptive", "order": 1},
                        {"indicatorCode": "NE.GDI.TOTL.ZS", "role": "descriptive", "order": 2},
                    ],
                }
            ],
        },
        ["NE.CON.PRVT.ZS", "NE.GDI.TOTL.ZS"],
        plan_snapshot_id="plan-india-subperiod",
    )

    assert draft["operations"] == []
    assert draft["models"][0]["kind"] == "descriptive"
    assert draft["models"][0]["inputRef"] == "active_dataset"


def test_confirmed_country_group_compiles_with_members_and_policy() -> None:
    draft = build_plan_pipeline_draft(
        {
            "geographyResolutions": [
                {
                    "id": "geo-pair",
                    "label": "Selected economies",
                    "kind": "country_group",
                    "memberCodes": ["IND", "CHN"],
                    "confirmed": True,
                    "aggregation": {
                        "method": "simple_mean",
                        "missingPolicy": "available_members",
                        "coverageThreshold": 0.8,
                        "membershipPolicy": "fixed_snapshot",
                    },
                }
            ],
            "dataSources": [{"enabled": True, "indicators": ["GDP"]}],
            "transformationIntents": [
                {
                    "id": "group_aggregation",
                    "label": "Aggregate selected economies",
                    "enabled": True,
                }
            ],
            "modelIntents": [],
        },
        ["GDP"],
        plan_snapshot_id="plan-reviewed-group",
    )

    operation = draft["operations"][0]
    assert operation["target"]["entities"] == ["IND", "CHN"]
    assert operation["parameters"] == {
        "method": "mean",
        "groupCode": "SELECTED_ECONOMIES",
        "coverageThreshold": 0.8,
        "missingPolicy": "available_members",
        "membershipPolicy": "fixed_snapshot",
    }


def test_generated_draft_validation_rejects_invalid_group_before_rendering() -> None:
    with pytest.raises(PlanPipelineDraftError, match="reviewed member entities"):
        validate_plan_pipeline_draft(
            {
                "operations": [
                    {
                        "id": "bad-group",
                        "kind": "group_aggregation",
                        "inputRef": "active_dataset",
                        "outputRef": "step:bad-group",
                        "target": {
                            "inputRef": "active_dataset",
                            "indicators": ["GDP"],
                            "entities": [],
                            "fields": ["value"],
                        },
                        "parameters": {"method": "mean"},
                    }
                ],
                "models": [],
            }
        )
