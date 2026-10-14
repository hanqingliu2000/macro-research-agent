from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


class CleaningPolicyError(ValueError):
    pass


def clean_statistical_frame(
    frame: pd.DataFrame,
    strategy: str,
    validation_start: str | None = None,
    *,
    required_indicators: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if strategy not in {"none", "complete_cases", "interpolate", "winsorize"}:
        raise CleaningPolicyError("Statistical strategy is not registered.")
    output = frame.copy().sort_values(["entity_code", "indicator_code", "frequency", "period"])
    output["value"] = pd.to_numeric(output["value"], errors="coerce")
    output["observation_origin"] = np.where(output["value"].isna(), "missing", "observed")
    changes: list[dict[str, Any]] = []
    for _, indices in output.groupby(
        ["entity_code", "indicator_code", "frequency"], dropna=False
    ).groups.items():
        group = output.loc[indices]
        if (
            strategy == "complete_cases"
            and required_indicators is not None
            and str(group.iloc[0]["indicator_code"]) not in required_indicators
        ):
            continue
        if validation_start:
            group = group[group["period"].astype(str) < validation_start]
        if group.empty:
            continue
        original = group["value"]
        if strategy == "none":
            continue
        if strategy == "complete_cases":
            affected = list(original[original.isna()].index)
            if len(affected) / len(group) > 0.05:
                raise CleaningPolicyError("Complete-case exclusion exceeds 5% of a series.")
            output = output.drop(index=affected)
        elif strategy == "interpolate":
            if original.isna().sum() == 0:
                continue
            if original.notna().sum() < 20:
                raise CleaningPolicyError("Interpolation needs 20 actual training observations.")
            missing = original.isna()
            long_gap = missing & (
                missing.shift(1, fill_value=False) | missing.shift(-1, fill_value=False)
            )
            eligible = missing & ~long_gap
            frequency = {"annual": "Y", "quarterly": "Q", "monthly": "M"}[
                str(group.iloc[0]["frequency"])
            ]
            ordinals = pd.Series(
                pd.PeriodIndex(group["period"], freq=frequency).asi8, index=group.index
            )
            eligible &= (ordinals - ordinals.shift(1) == 1) & (ordinals.shift(-1) - ordinals == 1)
            filled = original.interpolate(method="linear", limit_area="inside")
            affected = list(original[eligible & filled.notna()].index)
            if len(affected) / len(group) > 0.05:
                raise CleaningPolicyError("Interpolation exceeds 5% of a series.")
            output.loc[affected, "value"] = filled.loc[affected]
            output.loc[affected, "observation_origin"] = "imputed"
        else:
            observed = original.dropna()
            if len(observed) < 100:
                raise CleaningPolicyError("Winsorization needs 100 actual training observations.")
            low, high = observed.quantile([0.01, 0.99])
            clipped = original.clip(low, high)
            affected = list(original[original.notna() & (original != clipped)].index)
            if len(affected) / len(group) > 0.05:
                raise CleaningPolicyError("Winsorization exceeds 5% of a series.")
            output.loc[affected, "value"] = clipped.loc[affected]
            output.loc[affected, "observation_origin"] = "winsorized"
        changes.extend(
            {
                "row_index": int(index),
                "entity": str(frame.loc[index, "entity_code"]),
                "indicator": str(frame.loc[index, "indicator_code"]),
                "period": str(frame.loc[index, "period"]),
            }
            for index in affected
        )
    return output.reset_index(drop=True), {
        "policy": "statistical-cleaning-v1",
        "strategy": strategy,
        "input_rows": len(frame),
        "output_rows": len(output),
        "changed_count": len(changes),
        "changed_share": len(changes) / len(frame) if len(frame) else 0,
        "required_indicators": sorted(required_indicators)
        if required_indicators is not None
        else None,
        "changed_positions": changes,
        "validation_start": validation_start,
        "baseline_preserved": True,
        "quantiles": [0.01, 0.99] if strategy == "winsorize" else [],
    }
