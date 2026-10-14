"""Build a reviewable Transformation draft from an approved research Plan."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from macro_research_agent.workflow.model_workspace import SUPPORTED_MODELS
from macro_research_agent.workflow.pipeline_workspace import (
    SUPPORTED_TRANSFORMATIONS,
    TRANSFORMATION_LABELS,
)


class PlanPipelineDraftError(ValueError):
    """Raised when an approved Plan cannot produce a safe reviewable draft."""


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def default_transformation_parameters(kind: str) -> dict[str, Any]:
    if kind in {"lag", "lead", "difference", "period_growth"}:
        return {"periods": 1}
    if kind == "rolling_mean":
        return {"window": 4, "minimumPeriods": 1}
    if kind == "rebase_index":
        return {"basePeriod": "first", "baseValue": 100}
    if kind == "unit_conversion":
        return {
            "sourceUnit": "percent",
            "targetUnit": "basis points",
            "factor": 100,
            "offset": 0,
        }
    if kind == "frequency_conversion":
        return {
            "method": "mean",
            "targetFrequency": "annual",
            "calendar": "calendar",
            "fiscalYearEndMonth": 12,
            "incompletePeriod": "keep",
        }
    if kind == "group_aggregation":
        return {
            "method": "mean",
            "groupCode": "AGGREGATE",
            "coverageThreshold": 0.85,
        }
    return {}


def default_model_parameters(kind: str) -> dict[str, Any]:
    return {
        "missing": "drop",
        "addConstant": True,
        "covariance": "nonrobust",
        "maxLags": 1,
        **({"regression": "c", "autolag": "AIC"} if kind == "adf" else {}),
        **(
            {
                "orderP": 1,
                "orderD": 0,
                "orderQ": 0,
                "seasonalP": 0,
                "seasonalD": 0,
                "seasonalQ": 0,
                "seasonalPeriod": 0,
                "trend": "c",
                "forecastSteps": 4,
                "confidenceLevel": 0.95,
                "enforceStationarity": True,
                "enforceInvertibility": True,
            }
            if kind in {"arima", "sarimax"}
            else {}
        ),
        **(
            {
                "lagSelection": "fixed",
                "trend": "c",
                "includeIrf": False,
                "irfPeriods": 12,
                "impulseVariables": [],
                "orthogonalized": True,
                "confidenceLevel": 0.95,
                "forecastSteps": 0,
            }
            if kind == "var"
            else {}
        ),
    }


def _intent_variables(intent: dict[str, Any], available: list[str]) -> list[dict[str, Any]]:
    available_set = set(available)
    variables = sorted(
        [dict(item) for item in intent.get("variables") or []],
        key=lambda item: int(item.get("order") or 0),
    )
    missing = [
        str(item.get("indicatorCode"))
        for item in variables
        if str(item.get("indicatorCode")) not in available_set
    ]
    if missing:
        raise PlanPipelineDraftError(
            "Plan model variables are absent from the approved dataset: "
            + ", ".join(dict.fromkeys(missing))
        )
    return variables


def planned_forecast_contract(
    plan: dict[str, Any], observed_indicators: Iterable[object]
) -> dict[str, Any] | None:
    """Return the targets/periods promised by executable Plan forecast intents."""

    indicators = _ordered_indicators(plan, observed_indicators)
    targets: list[str] = []
    for intent in plan.get("modelIntents") or []:
        kind = str(intent.get("capabilityId") or intent.get("id") or "")
        if not intent.get("enabled", True) or kind not in {"arima", "sarimax", "var"}:
            continue
        horizon = dict(intent.get("forecastHorizon") or {})
        if not horizon:
            continue
        variables = _intent_variables(intent, indicators)
        target_roles = {"system"} if kind == "var" else {"dependent"}
        targets.extend(
            str(item["indicatorCode"]) for item in variables if item.get("role") in target_roles
        )
    ordered_targets = list(dict.fromkeys(targets))
    steps = max(
        (
            int((intent.get("forecastHorizon") or {}).get("steps") or 0)
            for intent in plan.get("modelIntents") or []
        ),
        default=0,
    )
    if not steps or not ordered_targets:
        return None
    return {"steps": steps, "targets": ordered_targets}


def _ordered_indicators(plan: dict[str, Any], observed: Iterable[object]) -> list[str]:
    observed_codes = list(
        dict.fromkeys(str(value).strip().upper() for value in observed if str(value).strip())
    )
    observed_set = set(observed_codes)
    requested = [
        str(code).strip().upper()
        for source in plan.get("dataSources") or []
        if source.get("enabled", True)
        for code in source.get("indicators") or []
        if str(code).strip()
    ]
    ordered = [code for code in dict.fromkeys(requested) if code in observed_set]
    return [*ordered, *(code for code in observed_codes if code not in ordered)]


def _is_time_window_summary(label: str) -> bool:
    return bool(
        re.search(
            r"\b(?:sub[- ]?period|time[- ]?window|pre\s*(?:/|and|versus|vs\.?)\s*post|"
            r"period averaging|period averages?)\b",
            label,
            flags=re.IGNORECASE,
        )
    )


def _reviewed_group_aggregation(plan: dict[str, Any]) -> tuple[list[str], dict[str, Any]] | None:
    for resolution in plan.get("geographyResolutions") or []:
        members = list(
            dict.fromkeys(
                str(code).strip().upper()
                for code in resolution.get("memberCodes") or []
                if str(code).strip()
            )
        )
        policy = resolution.get("aggregation")
        if (
            resolution.get("kind") != "country_group"
            or not resolution.get("confirmed")
            or len(members) < 2
            or not isinstance(policy, dict)
        ):
            continue
        method = {
            "simple_mean": "mean",
            "mean": "mean",
            "sum": "sum",
            "weighted_mean": "weighted_mean",
        }.get(str(policy.get("method") or ""))
        if method is None:
            continue
        parameters: dict[str, Any] = {
            "method": method,
            "groupCode": str(resolution.get("label") or resolution.get("id") or "AGGREGATE")
            .strip()
            .upper()
            .replace(" ", "_"),
            "coverageThreshold": float(policy.get("coverageThreshold", 0.85)),
            "missingPolicy": str(policy.get("missingPolicy") or "available_members"),
            "membershipPolicy": str(policy.get("membershipPolicy") or "period_specific"),
        }
        if method == "weighted_mean":
            weight_indicator = str(policy.get("weightIndicator") or "").strip()
            if not weight_indicator:
                continue
            parameters["weightField"] = weight_indicator
            parameters["weightSource"] = str(policy.get("weightSource") or "")
        return members, parameters
    return None


def validate_plan_pipeline_draft(draft: dict[str, Any]) -> None:
    """Validate the generated chain before it is exposed as a reviewable draft."""

    prior_outputs: set[str] = set()
    operation_ids: set[str] = set()
    for operation in draft.get("operations") or []:
        operation_id = str(operation.get("id") or "")
        kind = str(operation.get("kind") or "")
        input_ref = str(operation.get("inputRef") or "")
        output_ref = str(operation.get("outputRef") or "")
        target = dict(operation.get("target") or {})
        if not operation_id or operation_id in operation_ids:
            raise PlanPipelineDraftError("Generated operation IDs must be non-empty and unique.")
        if kind not in SUPPORTED_TRANSFORMATIONS:
            raise PlanPipelineDraftError("Generated operation is not registered.")
        if input_ref != "active_dataset" and input_ref not in prior_outputs:
            raise PlanPipelineDraftError(
                "Generated operation does not reference an upstream input."
            )
        if target.get("inputRef") != input_ref or target.get("fields") != ["value"]:
            raise PlanPipelineDraftError(
                "Generated operation target is inconsistent with its input."
            )
        if kind == "group_aggregation":
            if len(target.get("entities") or []) < 2:
                raise PlanPipelineDraftError(
                    "Generated group aggregation requires reviewed member entities."
                )
            parameters = dict(operation.get("parameters") or {})
            if parameters.get("method") not in {"mean", "sum", "weighted_mean"}:
                raise PlanPipelineDraftError(
                    "Generated group aggregation requires a reviewed aggregation policy."
                )
        if not output_ref or output_ref in prior_outputs or output_ref == "active_dataset":
            raise PlanPipelineDraftError("Generated operation output refs must be unique.")
        operation_ids.add(operation_id)
        prior_outputs.add(output_ref)
    allowed_inputs = {"active_dataset", *prior_outputs}
    for model in draft.get("models") or []:
        if str(model.get("kind") or "") not in SUPPORTED_MODELS:
            raise PlanPipelineDraftError("Generated model is not registered.")
        if str(model.get("inputRef") or "") not in allowed_inputs:
            raise PlanPipelineDraftError("Generated model does not reference a pipeline input.")


def build_plan_pipeline_draft(
    plan: dict[str, Any],
    observed_indicators: Iterable[object],
    *,
    plan_snapshot_id: str,
) -> dict[str, Any]:
    """Translate enabled Plan intents without crossing the Run approval gate."""

    indicators = _ordered_indicators(plan, observed_indicators)
    operations: list[dict[str, Any]] = []
    input_ref = "active_dataset"
    for intent in plan.get("transformationIntents") or []:
        kind = str(intent.get("id") or "")
        if not intent.get("enabled", True) or kind not in SUPPORTED_TRANSFORMATIONS:
            continue
        label = str(intent.get("label") or TRANSFORMATION_LABELS[kind])
        group_aggregation = None
        if kind == "group_aggregation":
            if _is_time_window_summary(label):
                continue
            group_aggregation = _reviewed_group_aggregation(plan)
            if group_aggregation is None:
                continue
        operation_id = _identifier("pipeline-operation")
        output_ref = f"step:{operation_id}"
        target_entities, parameters = (
            group_aggregation
            if group_aggregation is not None
            else ([], default_transformation_parameters(kind))
        )
        operations.append(
            {
                "id": operation_id,
                "kind": kind,
                "label": label,
                "enabled": True,
                "target": {
                    "inputRef": input_ref,
                    "indicators": indicators,
                    "entities": target_entities,
                    "fields": ["value"],
                },
                "parameters": parameters,
                "inputRef": input_ref,
                "outputRef": output_ref,
                "status": "not_run",
                "origin": "approved_plan",
            }
        )
        input_ref = output_ref

    models: list[dict[str, Any]] = []
    for intent in plan.get("modelIntents") or []:
        kind = str(intent.get("capabilityId") or intent.get("id") or "")
        if not intent.get("enabled", True) or kind not in SUPPORTED_MODELS:
            continue
        label = str(intent.get("purpose") or intent.get("label") or f"{kind.upper()} model")
        variables_spec = _intent_variables(intent, indicators)
        by_role: dict[str, list[str]] = {}
        for variable in variables_spec:
            by_role.setdefault(str(variable["role"]), []).append(str(variable["indicatorCode"]))
        targets: list[str | None] = (
            [*by_role.get("dependent", [])] if kind in {"adf", "arima"} else [None]
        )
        for target in targets:
            variables = (
                by_role.get("system", [])
                if kind == "var"
                else by_role.get("descriptive", [])
                if kind in {"descriptive", "correlation"}
                else []
            )
            dependent = [target] if target else by_role.get("dependent", [])
            independent = (
                by_role.get("independent", [])
                if kind == "ols"
                else by_role.get("exogenous", [])
                if kind == "sarimax"
                else []
            )
            parameters = default_model_parameters(kind)
            horizon = dict(intent.get("forecastHorizon") or {})
            if horizon:
                parameters["forecastSteps"] = int(horizon["steps"])
                parameters["confidenceLevel"] = float(horizon.get("confidenceLevel", 0.95))
            models.append(
                {
                    "id": _identifier("model-job"),
                    "kind": kind,
                    "label": f"{label} [{target}]" if target is not None else label,
                    "inputRef": input_ref,
                    "variables": variables,
                    "dependentVariables": dependent,
                    "independentVariables": independent,
                    "parameters": parameters,
                    "status": "not_run",
                    "origin": "approved_plan",
                }
            )

    draft = {
        "operations": operations,
        "models": models,
        "runStatus": "editing",
        "bundleHistory": [],
        "editHistory": [],
        "draftSource": "approved_plan",
        "sourcePlanSnapshotId": plan_snapshot_id,
    }
    validate_plan_pipeline_draft(draft)
    return draft
