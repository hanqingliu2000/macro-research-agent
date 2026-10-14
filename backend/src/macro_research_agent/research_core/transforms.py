from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

CANONICAL_COLUMNS = ["series_id", "entity_code", "indicator_code", "frequency", "period", "value"]

SUPPORTED_TRANSFORMATIONS = {
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
}

TRANSFORMATION_LABELS = {
    "lag": "Lag",
    "lead": "Lead",
    "difference": "First difference",
    "yoy_growth": "Year-on-year growth",
    "period_growth": "Period-on-period growth",
    "log": "Natural logarithm",
    "rebase_index": "Rebase index",
    "unit_conversion": "Unit conversion",
    "frequency_conversion": "Frequency conversion",
    "rolling_mean": "Rolling mean",
    "group_aggregation": "Group aggregation",
}

FREQUENCY_ALIASES = {
    "a": "annual",
    "annual": "annual",
    "q": "quarterly",
    "quarterly": "quarterly",
    "m": "monthly",
    "monthly": "monthly",
}


class PipelineWorkspaceError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _frequency(value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized not in FREQUENCY_ALIASES:
        raise PipelineWorkspaceError(f"Unsupported frequency value: {value}.")
    return FREQUENCY_ALIASES[normalized]


def _positive_int(parameters: dict[str, Any], key: str, default: int) -> int:
    value = parameters.get(key, default)
    if isinstance(value, bool):
        raise PipelineWorkspaceError(f"{key} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise PipelineWorkspaceError(f"{key} must be a positive integer.") from error
    if parsed < 1 or parsed != float(value):
        raise PipelineWorkspaceError(f"{key} must be a positive integer.")
    return parsed


def _finite_float(parameters: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(parameters.get(key, default))
    except (TypeError, ValueError) as error:
        raise PipelineWorkspaceError(f"{key} must be a finite number.") from error
    if not np.isfinite(value):
        raise PipelineWorkspaceError(f"{key} must be a finite number.")
    return value


def _specification_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


class FrameTransformEngine:
    def validate_operation(
        self,
        operation: dict[str, Any],
        prior_output_refs: set[str],
    ) -> None:
        kind = str(operation.get("kind") or "")
        if kind not in SUPPORTED_TRANSFORMATIONS:
            raise PipelineWorkspaceError("Transformation is not registered for Phase 1D-1.")
        input_ref = str(operation.get("inputRef") or "")
        if input_ref != "active_dataset" and input_ref not in prior_output_refs:
            raise PipelineWorkspaceError(
                "A transformation may only read the active dataset or an upstream output."
            )
        raw_target = operation.get("target") or {}
        raw_parameters = operation.get("parameters") or {}
        if not isinstance(raw_target, dict) or not isinstance(raw_parameters, dict):
            raise PipelineWorkspaceError("Target and parameters must be structured objects.")
        target = dict(raw_target)
        for name in ("indicators", "entities", "fields"):
            value = target.get(name) or []
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise PipelineWorkspaceError(f"Target {name} must be a list of codes.")
        if str(target.get("inputRef") or input_ref) != input_ref:
            raise PipelineWorkspaceError("Target input and operation input must match.")
        fields = list(target.get("fields") or ["value"])
        if fields != ["value"]:
            raise PipelineWorkspaceError("Phase 1D-1 transformations target the value field only.")
        parameters = dict(raw_parameters)
        if kind in {"lag", "lead", "difference", "period_growth"}:
            _positive_int(parameters, "periods", 1)
            if (
                kind == "difference"
                and "outputUnit" in parameters
                and not str(parameters.get("outputUnit") or "").strip()
            ):
                raise PipelineWorkspaceError("Difference outputUnit cannot be empty.")
        elif kind == "rolling_mean":
            window = _positive_int(parameters, "window", 4)
            minimum = _positive_int(parameters, "minimumPeriods", 1)
            if minimum > window:
                raise PipelineWorkspaceError("minimumPeriods cannot exceed the rolling window.")
        elif kind == "rebase_index":
            base_value = _finite_float(parameters, "baseValue", 100)
            if base_value <= 0:
                raise PipelineWorkspaceError("baseValue must be a positive finite number.")
        elif kind == "unit_conversion":
            source_unit = str(parameters.get("sourceUnit") or "").strip()
            target_unit = str(parameters.get("targetUnit") or "").strip()
            if not source_unit or not target_unit:
                raise PipelineWorkspaceError("Unit conversion requires sourceUnit and targetUnit.")
            factor = _finite_float(parameters, "factor", 1)
            _finite_float(parameters, "offset", 0)
            if factor == 0:
                raise PipelineWorkspaceError("Unit conversion factor cannot be zero.")
        elif kind == "frequency_conversion":
            target_frequency = _frequency(parameters.get("targetFrequency", "annual"))
            if target_frequency not in {"annual", "quarterly"}:
                raise PipelineWorkspaceError(
                    "Frequency conversion currently supports quarterly or annual outputs."
                )
            if parameters.get("method", "mean") not in {"mean", "sum", "end"}:
                raise PipelineWorkspaceError("Frequency method must be mean, sum or end.")
            if parameters.get("calendar", "calendar") not in {"calendar", "fiscal"}:
                raise PipelineWorkspaceError("Calendar must be calendar or fiscal.")
            fiscal_year_end = _positive_int(parameters, "fiscalYearEndMonth", 12)
            if fiscal_year_end > 12:
                raise PipelineWorkspaceError("fiscalYearEndMonth must be between 1 and 12.")
            if parameters.get("incompletePeriod", "keep") not in {"keep", "drop", "error"}:
                raise PipelineWorkspaceError("incompletePeriod must be keep, drop or error.")
        elif kind == "group_aggregation":
            if not target.get("entities"):
                raise PipelineWorkspaceError("Group aggregation requires reviewed member entities.")
            if parameters.get("method", "mean") not in {"mean", "sum", "weighted_mean"}:
                raise PipelineWorkspaceError(
                    "Group aggregation method must be mean, sum or weighted_mean."
                )
            if parameters.get("method") == "weighted_mean" and not parameters.get("weightField"):
                raise PipelineWorkspaceError(
                    "Weighted aggregation requires an explicit weightField."
                )
            threshold = _finite_float(parameters, "coverageThreshold", 0.85)
            if not 0 < threshold <= 1:
                raise PipelineWorkspaceError("coverageThreshold must be within (0, 1].")

    def validate_pipeline(self, operations: list[dict[str, Any]]) -> None:
        prior_output_refs: set[str] = set()
        operation_ids: set[str] = set()
        output_refs: set[str] = set()
        for operation in operations:
            operation_id = str(operation.get("id") or "")
            output_ref = str(operation.get("outputRef") or "")
            if not operation_id or operation_id in operation_ids:
                raise PipelineWorkspaceError("Pipeline operation IDs must be non-empty and unique.")
            if not output_ref or output_ref in output_refs or output_ref == "active_dataset":
                raise PipelineWorkspaceError("Pipeline output refs must be non-empty and unique.")
            self.validate_operation(operation, prior_output_refs)
            operation_ids.add(operation_id)
            output_refs.add(output_ref)
            prior_output_refs.add(output_ref)

    def _selection_mask(self, frame: pd.DataFrame, target: dict[str, Any]) -> pd.Series:
        mask = pd.Series(True, index=frame.index)
        indicators = {str(item).strip().upper() for item in target.get("indicators") or []}
        entities = {str(item).strip().upper() for item in target.get("entities") or []}
        if indicators:
            mask &= frame["indicator_code"].astype(str).str.upper().isin(indicators)
        if entities:
            mask &= frame["entity_code"].astype(str).str.upper().isin(entities)
        if target.get("periodStart"):
            mask &= frame["period"].astype(str) >= str(target["periodStart"])
        if target.get("periodEnd"):
            mask &= frame["period"].astype(str) <= str(target["periodEnd"])
        if target.get("frequency"):
            wanted = _frequency(target["frequency"])
            mask &= frame["frequency"].map(_frequency) == wanted
        return mask

    @staticmethod
    def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(
            ["entity_code", "indicator_code", "frequency", "period"],
            kind="stable",
        )

    @staticmethod
    def _shift_values(selected: pd.DataFrame, periods: int) -> pd.Series:
        keys = ["entity_code", "indicator_code", "frequency"]
        return selected.groupby(keys, sort=False, dropna=False)["value"].shift(periods)

    def _frequency_period(
        self,
        period: object,
        source_frequency: str,
        target_frequency: str,
        calendar: str,
        fiscal_year_end_month: int,
    ) -> str:
        value = str(period)
        try:
            year = int(value[:4])
        except ValueError as error:
            raise PipelineWorkspaceError(f"Period {value!r} has no valid year.") from error
        if source_frequency == "quarterly":
            normalized = value.upper().replace("_", "-")
            if "Q" not in normalized:
                raise PipelineWorkspaceError(f"Quarterly period {value!r} has no quarter.")
            quarter = int(normalized.split("Q", maxsplit=1)[1])
            if not 1 <= quarter <= 4:
                raise PipelineWorkspaceError(f"Quarterly period {value!r} is invalid.")
            return str(year) if target_frequency == "annual" else f"{year}-Q{quarter}"
        digits = "".join(character for character in value[4:] if character.isdigit())
        if not digits:
            raise PipelineWorkspaceError("Monthly periods must include a month number.")
        month = int(digits[:2])
        if not 1 <= month <= 12:
            raise PipelineWorkspaceError("Monthly period contains an invalid month.")
        if calendar == "fiscal":
            fiscal_year = year + (1 if month > fiscal_year_end_month else 0)
            fiscal_month = (month - fiscal_year_end_month - 1) % 12 + 1
            year = fiscal_year
            month = fiscal_month
        if target_frequency == "annual":
            return str(year)
        return f"{year}-Q{((month - 1) // 3) + 1}"

    def transform_frame(
        self,
        frame: pd.DataFrame,
        operation: dict[str, Any],
    ) -> pd.DataFrame:
        self.validate_operation(operation, {str(operation.get("inputRef") or "")})
        kind = str(operation["kind"])
        target = dict(operation.get("target") or {})
        parameters = dict(operation.get("parameters") or {})
        mask = self._selection_mask(frame, target)
        if not mask.any():
            raise PipelineWorkspaceError(f"{TRANSFORMATION_LABELS[kind]} selected no rows.")
        selected = self._ordered(frame.loc[mask].copy())
        selected["value"] = pd.to_numeric(selected["value"], errors="coerce")

        if kind in {"lag", "lead", "difference", "period_growth", "yoy_growth"}:
            periods = _positive_int(parameters, "periods", 1)
            if kind == "yoy_growth":
                shifted = pd.Series(index=selected.index, dtype=float)
                for frequency, group in selected.groupby("frequency", sort=False):
                    annual_periods = {"annual": 1, "quarterly": 4, "monthly": 12}[
                        _frequency(frequency)
                    ]
                    shifted.loc[group.index] = self._shift_values(group, annual_periods)
            else:
                direction = -periods if kind == "lead" else periods
                shifted = self._shift_values(selected, direction)
            if kind in {"lag", "lead"}:
                selected["value"] = shifted
            elif kind == "difference":
                selected["value"] = selected["value"] - shifted
                if parameters.get("outputUnit"):
                    selected["unit"] = str(parameters["outputUnit"]).strip()
            else:
                selected["value"] = (selected["value"] / shifted - 1) * 100
                selected["unit"] = "Percent"
                if "indicator_name" in selected:
                    selected["indicator_name"] = (
                        selected["indicator_name"].fillna(selected["indicator_code"]).astype(str)
                        + f" ({TRANSFORMATION_LABELS[kind]}, %)"
                    )
        elif kind == "log":
            if (selected["value"].dropna() <= 0).any():
                raise PipelineWorkspaceError("Natural logarithm requires strictly positive values.")
            selected["value"] = np.log(selected["value"])
        elif kind == "rebase_index":
            base_period = str(parameters.get("basePeriod", "first"))
            base_value = float(parameters.get("baseValue", 100))
            keys = ["entity_code", "indicator_code", "frequency"]
            for indices in selected.groupby(keys, sort=False).groups.values():
                group = selected.loc[indices]
                eligible = group[group["value"].notna()]
                requested = group.loc[group["period"].astype(str) == base_period, "value"].dropna()
                base = (
                    eligible.iloc[0]["value"]
                    if base_period == "first" and not eligible.empty
                    else requested.iloc[0]
                    if not requested.empty
                    else np.nan
                )
                if pd.isna(base) or float(base) == 0:
                    raise PipelineWorkspaceError(
                        f"No non-zero base observation exists for period {base_period}."
                    )
                selected.loc[indices, "value"] = (
                    selected.loc[indices, "value"] / float(base) * base_value
                )
        elif kind == "unit_conversion":
            if "unit" not in selected.columns:
                raise PipelineWorkspaceError(
                    "Unit conversion requires a unit attribute in the selected data."
                )
            source_unit = str(parameters["sourceUnit"]).strip()
            target_unit = str(parameters["targetUnit"]).strip()
            actual_units = {
                str(value).strip().casefold() for value in selected["unit"].dropna().unique()
            }
            if actual_units != {source_unit.casefold()}:
                raise PipelineWorkspaceError(
                    "Selected rows must all match the reviewed sourceUnit."
                )
            factor = float(parameters.get("factor", 1))
            offset = float(parameters.get("offset", 0))
            selected["value"] = selected["value"] * factor + offset
            selected["unit"] = target_unit
        elif kind == "rolling_mean":
            window = _positive_int(parameters, "window", 4)
            minimum = _positive_int(parameters, "minimumPeriods", 1)
            keys = ["entity_code", "indicator_code", "frequency"]
            selected["value"] = selected.groupby(keys, sort=False, dropna=False)["value"].transform(
                lambda values: values.rolling(window, min_periods=minimum).mean()
            )
        elif kind == "frequency_conversion":
            target_frequency = _frequency(parameters.get("targetFrequency", "annual"))
            method = str(parameters.get("method", "mean"))
            calendar = str(parameters.get("calendar", "calendar"))
            fiscal_year_end_month = int(parameters.get("fiscalYearEndMonth", 12))
            incomplete_policy = str(parameters.get("incompletePeriod", "keep"))
            source_ranks = {"monthly": 3, "quarterly": 2, "annual": 1}
            source_frequencies = {_frequency(value) for value in selected["frequency"].unique()}
            if len(source_frequencies) != 1:
                raise PipelineWorkspaceError(
                    "Frequency conversion requires one reviewed source frequency per operation."
                )
            source_frequency = next(iter(source_frequencies))
            if any(
                source_ranks[_frequency(value)] <= source_ranks[target_frequency]
                for value in selected["frequency"].unique()
            ):
                raise PipelineWorkspaceError(
                    "Frequency conversion cannot upsample or keep frequency."
                )
            selected["period"] = selected["period"].map(
                lambda value: self._frequency_period(
                    value,
                    source_frequency,
                    target_frequency,
                    calendar,
                    fiscal_year_end_month,
                )
            )
            selected["frequency"] = target_frequency
            keys = ["entity_code", "indicator_code", "frequency", "period"]
            expected = {
                ("monthly", "quarterly"): 3,
                ("monthly", "annual"): 12,
                ("quarterly", "annual"): 4,
            }[(source_frequency, target_frequency)]
            counts = selected.groupby(keys, sort=False, dropna=False)["value"].size()
            coverage = counts / expected
            incomplete_keys = set(counts[counts < expected].index)
            if incomplete_keys and incomplete_policy == "error":
                raise PipelineWorkspaceError(
                    f"Frequency conversion found {len(incomplete_keys)} incomplete target periods."
                )
            if incomplete_keys and incomplete_policy == "drop":
                index = pd.MultiIndex.from_frame(selected[keys])
                selected = selected.loc[~index.isin(incomplete_keys)].copy()
            attribute_columns = [
                column
                for column in selected.columns
                if column not in {*CANONICAL_COLUMNS, "value", "series_id"}
            ]
            if selected.empty:
                selected = pd.DataFrame(columns=[*keys, "value", *attribute_columns])
                selected["frequency_coverage"] = pd.Series(dtype=float)
            else:
                grouped = selected.groupby(keys, as_index=False, sort=False, dropna=False)
                if method == "mean":
                    selected = grouped["value"].mean()
                elif method == "sum":
                    selected = grouped["value"].sum(min_count=1)
                else:
                    selected = grouped["value"].last()
                selected_index = pd.MultiIndex.from_frame(selected[keys])
                selected["frequency_coverage"] = selected_index.map(coverage).astype(float)
                for column in attribute_columns:
                    attributes = grouped[column].agg(
                        lambda values: (
                            values.dropna().iloc[0] if values.dropna().nunique() == 1 else None
                        )
                    )
                    selected[column] = attributes[column].to_numpy()
            selected["calendar"] = (
                f"fiscal-year-ending-{fiscal_year_end_month:02d}"
                if calendar == "fiscal"
                else "calendar"
            )
            selected.insert(
                0,
                "series_id",
                selected["indicator_code"].astype(str) + ":" + selected["entity_code"].astype(str),
            )
        elif kind == "group_aggregation":
            members = {str(item).strip().upper() for item in target.get("entities") or []}
            method = str(parameters.get("method", "mean"))
            group_code = str(parameters.get("groupCode", "AGGREGATE")).strip().upper()
            threshold = float(parameters.get("coverageThreshold", 0.85))
            keys = ["indicator_code", "frequency", "period"]
            grouped_rows: list[dict[str, Any]] = []
            for key, group in selected.groupby(keys, sort=False, dropna=False):
                observed = group[group["value"].notna()]
                coverage = len(observed["entity_code"].unique()) / len(members)
                if coverage < threshold:
                    value = np.nan
                elif method == "sum":
                    value = observed["value"].sum(min_count=1)
                elif method == "weighted_mean":
                    weight_field = str(parameters["weightField"])
                    if weight_field not in observed:
                        raise PipelineWorkspaceError(
                            f"Weight field {weight_field} is not present in the input schema."
                        )
                    weights = pd.to_numeric(observed[weight_field], errors="coerce")
                    valid = observed["value"].notna() & weights.notna() & (weights > 0)
                    if not valid.any():
                        value = np.nan
                    else:
                        value = np.average(observed.loc[valid, "value"], weights=weights[valid])
                else:
                    value = observed["value"].mean()
                indicator, frequency, period = key
                grouped_rows.append(
                    {
                        "series_id": f"{indicator}:{group_code}",
                        "entity_code": group_code,
                        "indicator_code": indicator,
                        "frequency": frequency,
                        "period": period,
                        "value": value,
                        "aggregation_coverage": coverage,
                    }
                )
            selected = pd.DataFrame(grouped_rows)

        if kind not in {"frequency_conversion", "group_aggregation"}:
            output = frame.copy()
            output["value"] = pd.to_numeric(output["value"], errors="coerce").astype(float)
            output.loc[selected.index, "value"] = selected["value"]
            if kind == "unit_conversion" or (kind == "difference" and parameters.get("outputUnit")):
                output.loc[selected.index, "unit"] = selected["unit"]
        else:
            output = pd.concat([frame.loc[~mask].copy(), selected], ignore_index=True, sort=False)
        output["value"] = pd.to_numeric(output["value"], errors="coerce")
        ordered = [
            *CANONICAL_COLUMNS,
            *[column for column in output.columns if column not in CANONICAL_COLUMNS],
        ]
        return self._ordered(output[ordered]).reset_index(drop=True)
