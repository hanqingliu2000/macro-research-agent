import pandas as pd
import pytest
from macro_research_agent.research_core.cleaning import CleaningPolicyError, clean_statistical_frame


def series(count=21):
    return pd.DataFrame(
        {
            "entity_code": ["USA"] * count,
            "indicator_code": ["CPI"] * count,
            "frequency": ["annual"] * count,
            "period": [str(2000 + i) for i in range(count)],
            "value": [float(i) for i in range(count)],
            "unit": [None] * count,
        }
    )


def test_statistical_policy_preserves_metadata_and_validation_truth():
    frame = series()
    unchanged, receipt = clean_statistical_frame(frame, "complete_cases")
    assert len(unchanged) == 21 and receipt["changed_count"] == 0
    frame.loc[10, "value"] = None
    filled, receipt = clean_statistical_frame(frame, "interpolate")
    assert filled.loc[10, "value"] == 10 and receipt["changed_count"] == 1
    assert frame.loc[10, "value"] != frame.loc[10, "value"]  # Original remains missing.
    protected, receipt = clean_statistical_frame(frame, "interpolate", "2009")
    assert pd.isna(protected.loc[10, "value"]) and receipt["changed_count"] == 0
    frame.loc[11, "value"] = None
    with pytest.raises(CleaningPolicyError):
        clean_statistical_frame(frame, "complete_cases")


def test_winsorization_is_bounded_and_insufficient_samples_stop():
    frame = series(100)
    transformed, receipt = clean_statistical_frame(frame, "winsorize")
    assert (
        receipt["changed_count"] == 2
        and transformed["observation_origin"].eq("winsorized").sum() == 2
    )
    with pytest.raises(CleaningPolicyError, match="100"):
        clean_statistical_frame(series(99), "winsorize")
    with pytest.raises(CleaningPolicyError):
        clean_statistical_frame(
            series(15).assign(value=lambda df: df.value.where(df.index != 5)), "interpolate"
        )


def test_absent_periods_cannot_be_treated_as_a_single_period_gap():
    frame = series(22).drop(index=9).reset_index(drop=True)
    frame.loc[9, "value"] = None
    result, receipt = clean_statistical_frame(frame, "interpolate")
    assert receipt["changed_count"] == 0 and pd.isna(result.loc[9, "value"])


def test_required_indicator_missingness_and_typed_forecast_holdout():
    from macro_research_agent.agent.contracts import AgentAnalysisTaskV1
    from macro_research_agent.agent.providers import model_job
    from macro_research_agent.research_core.numerics import evaluate_typed_model_frame

    unused = series().assign(indicator_code="UNUSED", value=float("nan"))
    prepared, receipt = clean_statistical_frame(
        pd.concat([series(), unused], ignore_index=True),
        "complete_cases",
        required_indicators={"CPI"},
    )
    assert len(prepared) == 42 and receipt["changed_count"] == 0
    frame = series(30).assign(series_id="USA.CPI", value=lambda df: df.value + 100)
    task = AgentAnalysisTaskV1(
        task_id="forecast",
        model="arima",
        variables=["CPI"],
        dependent_variables=["CPI"],
        purpose="Predict",
        parameters={"forecastSteps": 2},
    )
    job = model_job(task)
    job["validationStart"] = "2026"
    result, sample, _ = evaluate_typed_model_frame(frame, job)
    validation = result["validation"]
    assert (
        validation["policy"] == "fixed-mae-rmse-v1"
        and validation["trainingSample"]["observations"] == 26
    )
    assert {row["period"] for row in validation["comparisons"]} == {"2026", "2027"}
    assert {row["period"] for row in result["forecasts"]} == {"2030", "2031"}
    assert sample["observations"] == 30 and validation["rmse"] >= 0
