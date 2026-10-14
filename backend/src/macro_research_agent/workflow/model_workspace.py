from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import warnings as python_warnings
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from pydantic import BaseModel, Field
from statsmodels.tools.sm_exceptions import ConvergenceWarning  # type: ignore[import-untyped]
from statsmodels.tsa.api import VAR  # type: ignore[import-untyped]
from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore[import-untyped]
from statsmodels.tsa.stattools import adfuller  # type: ignore[import-untyped]

from macro_research_agent.workflow.data_workspace import DataWorkspaceManager

SUPPORTED_MODELS = {"descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"}


class ModelWorkspaceError(ValueError):
    pass


class ModelResultRecord(BaseModel):
    id: str
    session_id: str
    job_id: str
    kind: str
    input_snapshot_id: str
    input_snapshot_hash: str
    specification_hash: str
    result_hash: str
    sample: dict[str, int]
    result: dict[str, Any]
    diagnostics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value).encode()).hexdigest()}"


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


class ModelWorkspaceManager:
    def __init__(self, database_path: Any, data_manager: DataWorkspaceManager) -> None:
        self.database_path = database_path
        self.data_manager = data_manager
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_model_results (
                    session_id TEXT NOT NULL,
                    result_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, result_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def validate_job(job: dict[str, Any]) -> None:
        kind = str(job.get("kind") or "")
        if kind not in SUPPORTED_MODELS:
            raise ModelWorkspaceError("Model kind is not registered for Phase 1D-2.")
        variables = job.get("variables") or []
        dependent = job.get("dependentVariables") or []
        independent = job.get("independentVariables") or []
        if not all(isinstance(items, list) for items in (variables, dependent, independent)):
            raise ModelWorkspaceError("Model variables must be code lists.")
        if not all(
            isinstance(value, str) and value.strip()
            for items in (variables, dependent, independent)
            for value in items
        ):
            raise ModelWorkspaceError("Model variable codes must be non-empty strings.")
        for items in (variables, dependent, independent):
            normalized = [value.strip().upper() for value in items]
            if len(normalized) != len(set(normalized)):
                raise ModelWorkspaceError("Model variable code lists cannot contain duplicates.")
        if kind == "correlation" and len(variables) < 2:
            raise ModelWorkspaceError("Correlation requires at least two indicator codes.")
        if kind == "adf" and len(variables) != 1:
            raise ModelWorkspaceError("ADF requires exactly one indicator code.")
        if kind == "var" and len(variables) < 2:
            raise ModelWorkspaceError("VAR requires at least two indicator codes.")
        if kind == "var" and (dependent or independent):
            raise ModelWorkspaceError("VAR uses the ordered indicator list, not regression roles.")
        if kind in {"arima", "sarimax"} and len(dependent) != 1:
            raise ModelWorkspaceError(f"{kind.upper()} requires exactly one dependent indicator.")
        if kind == "arima" and independent:
            raise ModelWorkspaceError("ARIMA does not accept exogenous indicators; use SARIMAX.")
        if kind == "ols" and (len(dependent) != 1 or not independent):
            raise ModelWorkspaceError(
                "OLS requires one dependent indicator and at least one independent indicator."
            )
        parameters = job.get("parameters") or {}
        if parameters.get("missing", "drop") != "drop":
            raise ModelWorkspaceError("Phase 1D-2 models support listwise missing-value drop only.")
        if kind == "ols" and dependent[0].strip().upper() in {
            value.strip().upper() for value in independent
        }:
            raise ModelWorkspaceError("The dependent indicator cannot also be independent.")
        covariance = str(parameters.get("covariance", "nonrobust"))
        if covariance not in {"nonrobust", "HC1", "HAC"}:
            raise ModelWorkspaceError("OLS covariance must be nonrobust, HC1 or HAC.")
        if covariance == "HAC":
            try:
                max_lags = int(parameters.get("maxLags", 1))
            except (TypeError, ValueError) as error:
                raise ModelWorkspaceError("HAC max lags must be a positive integer.") from error
            if max_lags < 1:
                raise ModelWorkspaceError("HAC max lags must be a positive integer.")
        if kind == "adf":
            regression = str(parameters.get("regression", "c"))
            if regression not in {"c", "ct", "ctt", "n"}:
                raise ModelWorkspaceError("ADF regression must be c, ct, ctt or n.")
            autolag = str(parameters.get("autolag", "AIC"))
            if autolag not in {"AIC", "BIC", "t-stat", "none"}:
                raise ModelWorkspaceError("ADF autolag must be AIC, BIC, t-stat or none.")
            try:
                max_lags = int(parameters.get("maxLags", 1))
            except (TypeError, ValueError) as error:
                raise ModelWorkspaceError("ADF max lags must be a non-negative integer.") from error
            if max_lags < 0:
                raise ModelWorkspaceError("ADF max lags must be a non-negative integer.")
        if kind in {"arima", "sarimax"}:
            bounds = {
                "orderP": (0, 5),
                "orderD": (0, 2),
                "orderQ": (0, 5),
                "seasonalP": (0, 5),
                "seasonalD": (0, 2),
                "seasonalQ": (0, 5),
                "seasonalPeriod": (0, 24),
                "forecastSteps": (1, 60),
            }
            parsed: dict[str, int] = {}
            for key, (minimum, maximum) in bounds.items():
                try:
                    value = int(parameters.get(key, 0 if key != "forecastSteps" else 4))
                except (TypeError, ValueError) as error:
                    raise ModelWorkspaceError(f"{key} must be an integer.") from error
                if not minimum <= value <= maximum:
                    raise ModelWorkspaceError(f"{key} must be between {minimum} and {maximum}.")
                parsed[key] = value
            seasonal_terms = (parsed["seasonalP"], parsed["seasonalD"], parsed["seasonalQ"])
            seasonal_period = parsed["seasonalPeriod"]
            if kind == "arima" and (any(seasonal_terms) or seasonal_period):
                raise ModelWorkspaceError("ARIMA seasonal terms must be zero; use SARIMAX.")
            if kind == "sarimax" and any(seasonal_terms) and seasonal_period < 2:
                raise ModelWorkspaceError(
                    "SARIMAX seasonal period must be at least 2 when seasonal terms are used."
                )
            if seasonal_period == 1:
                raise ModelWorkspaceError("seasonalPeriod must be zero or at least 2.")
            trend = str(parameters.get("trend", "n"))
            if trend not in {"n", "c", "t", "ct"}:
                raise ModelWorkspaceError("ARIMA/SARIMAX trend must be n, c, t or ct.")
            try:
                confidence_level = float(parameters.get("confidenceLevel", 0.95))
            except (TypeError, ValueError) as error:
                raise ModelWorkspaceError("confidenceLevel must be numeric.") from error
            if not 0.5 <= confidence_level <= 0.99:
                raise ModelWorkspaceError("confidenceLevel must be between 0.5 and 0.99.")
            for key in ("enforceStationarity", "enforceInvertibility"):
                if key in parameters and not isinstance(parameters[key], bool):
                    raise ModelWorkspaceError(f"{key} must be true or false.")
        if kind == "var":
            try:
                max_lags = int(parameters.get("maxLags", 1))
                irf_periods = int(parameters.get("irfPeriods", 12))
                forecast_steps = int(parameters.get("forecastSteps", 0))
                confidence_level = float(parameters.get("confidenceLevel", 0.95))
            except (TypeError, ValueError) as error:
                raise ModelWorkspaceError(
                    "VAR lag, forecast, IRF period and confidence values are invalid."
                ) from error
            if not 1 <= max_lags <= 12:
                raise ModelWorkspaceError("VAR maxLags must be between 1 and 12.")
            if not 1 <= irf_periods <= 40:
                raise ModelWorkspaceError("VAR irfPeriods must be between 1 and 40.")
            if not 0 <= forecast_steps <= 60:
                raise ModelWorkspaceError("VAR forecastSteps must be between 0 and 60.")
            if not 0.5 <= confidence_level <= 0.99:
                raise ModelWorkspaceError("VAR confidenceLevel must be between 0.5 and 0.99.")
            lag_selection = str(parameters.get("lagSelection", "fixed"))
            if lag_selection not in {"fixed", "aic", "bic", "hqic", "fpe"}:
                raise ModelWorkspaceError("VAR lagSelection must be fixed, aic, bic, hqic or fpe.")
            trend = str(parameters.get("trend", "c"))
            if trend not in {"n", "c", "ct", "ctt"}:
                raise ModelWorkspaceError("VAR trend must be n, c, ct or ctt.")
            for key in ("includeIrf", "orthogonalized"):
                if key in parameters and not isinstance(parameters[key], bool):
                    raise ModelWorkspaceError(f"{key} must be true or false.")
            impulses = parameters.get("impulseVariables") or []
            if not isinstance(impulses, list) or not all(
                isinstance(value, str) and value.strip() for value in impulses
            ):
                raise ModelWorkspaceError("VAR impulseVariables must be an indicator-code list.")
            normalized_variables = [value.strip().upper() for value in variables]
            normalized_impulses = [value.strip().upper() for value in impulses]
            if len(normalized_impulses) != len(set(normalized_impulses)):
                raise ModelWorkspaceError("VAR impulseVariables cannot contain duplicates.")
            if any(value not in normalized_variables for value in normalized_impulses):
                raise ModelWorkspaceError("VAR impulses must be selected model indicators.")

    @staticmethod
    def specification_hash(job: dict[str, Any]) -> str:
        return _hash(
            {
                "kind": str(job.get("kind") or ""),
                "inputRef": job.get("inputRef"),
                "variables": job.get("variables") or [],
                "dependentVariables": job.get("dependentVariables") or [],
                "independentVariables": job.get("independentVariables") or [],
                "parameters": job.get("parameters") or {},
            }
        )

    def find_compatible(
        self, session_id: str, snapshot_id: str, job: dict[str, Any]
    ) -> ModelResultRecord | None:
        snapshot = self.data_manager.get_snapshot(session_id, snapshot_id)
        specification_hash = self.specification_hash(job)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json FROM workflow_model_results
                WHERE session_id = ? ORDER BY rowid DESC
                """,
                (session_id,),
            ).fetchall()
        for row in rows:
            record = ModelResultRecord.model_validate_json(row["record_json"])
            if (
                record.job_id == str(job.get("id"))
                and record.input_snapshot_hash == snapshot.snapshot_hash
                and record.specification_hash == specification_hash
            ):
                return record
        return None

    @staticmethod
    def _wide(frame: pd.DataFrame) -> pd.DataFrame:
        ordered = frame.sort_values(["entity_code", "frequency", "period"], kind="stable")
        wide = ordered.pivot(
            index=["entity_code", "frequency", "period"],
            columns="indicator_code",
            values="value",
        )
        wide.columns = [str(value).strip().upper() for value in wide.columns]
        return wide.apply(pd.to_numeric, errors="coerce")

    @staticmethod
    def _require_columns(wide: pd.DataFrame, variables: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in variables]
        missing = [value for value in normalized if value not in wide.columns]
        if missing:
            raise ModelWorkspaceError("Input snapshot is missing indicators: " + ", ".join(missing))
        return normalized

    @staticmethod
    def _descriptive(wide: pd.DataFrame, variables: list[str]) -> tuple[dict[str, Any], int, int]:
        selected = ModelWorkspaceManager._require_columns(
            wide, variables or [str(column) for column in wide.columns]
        )
        if not selected:
            raise ModelWorkspaceError("Descriptive statistics require at least one indicator.")
        table: list[dict[str, Any]] = []
        for variable in selected:
            values = wide[variable].dropna()
            table.append(
                {
                    "variable": variable,
                    "count": int(values.count()),
                    "missing": int(wide[variable].isna().sum()),
                    "mean": values.mean(),
                    "std": values.std(ddof=1),
                    "min": values.min(),
                    "p25": values.quantile(0.25),
                    "median": values.median(),
                    "p75": values.quantile(0.75),
                    "max": values.max(),
                }
            )
        return {"statistics": table}, len(wide), int(wide[selected].isna().any(axis=1).sum())

    @staticmethod
    def _correlation(wide: pd.DataFrame, variables: list[str]) -> tuple[dict[str, Any], int, int]:
        selected = ModelWorkspaceManager._require_columns(wide, variables)
        complete = wide[selected].dropna()
        if len(complete) < 2:
            raise ModelWorkspaceError("Correlation requires at least two complete observations.")
        matrix = complete.corr()
        return (
            {
                "variables": selected,
                "matrix": [
                    {"variable": row, **{column: matrix.loc[row, column] for column in selected}}
                    for row in selected
                ],
            },
            len(complete),
            len(wide) - len(complete),
        )

    @staticmethod
    def _ols(wide: pd.DataFrame, job: dict[str, Any]) -> tuple[dict[str, Any], int, int, list[str]]:
        dependent = ModelWorkspaceManager._require_columns(wide, job["dependentVariables"])[0]
        independent = ModelWorkspaceManager._require_columns(wide, job["independentVariables"])
        columns = [dependent, *independent]
        complete = wide[columns].dropna()
        add_constant = bool((job.get("parameters") or {}).get("addConstant", True))
        x = complete[independent].to_numpy(dtype=float)
        names = list(independent)
        if add_constant:
            x = np.column_stack([np.ones(len(x)), x])
            names.insert(0, "const")
        y = complete[dependent].to_numpy(dtype=float)
        n, k = x.shape
        if n <= k:
            raise ModelWorkspaceError("OLS requires more complete observations than coefficients.")
        if np.linalg.matrix_rank(x) < k:
            raise ModelWorkspaceError("OLS design matrix is rank deficient.")
        xtx_inverse = np.linalg.inv(x.T @ x)
        coefficients = xtx_inverse @ x.T @ y
        residuals = y - x @ coefficients
        dof = n - k
        covariance_kind = str((job.get("parameters") or {}).get("covariance", "nonrobust"))
        warnings: list[str] = []
        if covariance_kind == "nonrobust":
            covariance = float(residuals @ residuals / dof) * xtx_inverse
        elif covariance_kind == "HC1":
            meat = x.T @ ((residuals**2)[:, None] * x)
            covariance = (n / dof) * xtx_inverse @ meat @ xtx_inverse
        else:
            max_lags = int((job.get("parameters") or {}).get("maxLags", 1))
            meat = x.T @ ((residuals**2)[:, None] * x)
            positions = pd.DataFrame({"position": np.arange(n)}, index=complete.index)
            for _, block in positions.groupby(level=[0, 1], sort=False):
                indices = block["position"].to_numpy(dtype=int)
                for lag in range(1, min(max_lags, len(indices) - 1) + 1):
                    weight = 1 - lag / (max_lags + 1)
                    current = indices[lag:]
                    prior = indices[:-lag]
                    gamma = x[current].T @ (
                        (residuals[current] * residuals[prior])[:, None] * x[prior]
                    )
                    meat += weight * (gamma + gamma.T)
            covariance = (n / dof) * xtx_inverse @ meat @ xtx_inverse
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
        t_statistics = np.divide(
            coefficients,
            standard_errors,
            out=np.full_like(coefficients, np.nan),
            where=standard_errors > 0,
        )
        total = float(((y - y.mean()) ** 2).sum())
        residual_sum = float(residuals @ residuals)
        r_squared = 1 - residual_sum / total if total > 0 else None
        adjusted = 1 - (1 - r_squared) * (n - 1) / dof if r_squared is not None else None
        return (
            {
                "dependentVariable": dependent,
                "covariance": covariance_kind,
                "coefficients": [
                    {
                        "term": name,
                        "estimate": coefficients[index],
                        "standardError": standard_errors[index],
                        "tStatistic": t_statistics[index],
                    }
                    for index, name in enumerate(names)
                ],
                "fit": {
                    "observations": n,
                    "parameters": k,
                    "degreesOfFreedom": dof,
                    "rSquared": r_squared,
                    "adjustedRSquared": adjusted,
                    "rmse": np.sqrt(residual_sum / dof),
                },
            },
            n,
            len(wide) - n,
            warnings,
        )

    @staticmethod
    def _adf(wide: pd.DataFrame, job: dict[str, Any]) -> tuple[dict[str, Any], int, int, list[str]]:
        variable = ModelWorkspaceManager._require_columns(wide, list(job["variables"]))[0]
        parameters = dict(job.get("parameters") or {})
        regression = str(parameters.get("regression", "c"))
        autolag_value = str(parameters.get("autolag", "AIC"))
        autolag = None if autolag_value == "none" else autolag_value
        max_lags = int(parameters.get("maxLags", 1))
        groups: list[dict[str, Any]] = []
        warnings: list[str] = []
        observations = 0
        dropped = 0
        for (entity_code, frequency), group in wide.groupby(level=[0, 1], sort=False):
            series = group[variable].dropna().astype(float)
            observations += len(series)
            dropped += len(group) - len(series)
            try:
                values = adfuller(
                    series.to_numpy(),
                    maxlag=max_lags,
                    regression=regression,
                    autolag=autolag,
                )
            except ValueError as error:
                raise ModelWorkspaceError(
                    f"ADF could not evaluate {entity_code}/{frequency}: {error}"
                ) from error
            statistic, p_value, used_lag, nobs, critical_values = values[:5]
            information_criterion = values[5] if len(values) > 5 else None
            stationary = bool(float(p_value) < 0.05)
            group_label = f"{entity_code}/{frequency}"
            if not stationary:
                warnings.append(f"ADF did not reject a unit root at 5% for {group_label}.")
            groups.append(
                {
                    "entityCode": str(entity_code),
                    "frequency": str(frequency),
                    "statistic": float(statistic),
                    "pValue": float(p_value),
                    "usedLag": int(used_lag),
                    "observations": int(nobs),
                    "criticalValues": {
                        str(level): float(value) for level, value in dict(critical_values).items()
                    },
                    "informationCriterion": (
                        float(information_criterion) if information_criterion is not None else None
                    ),
                    "rejectUnitRootAt5Percent": stationary,
                }
            )
        if not groups:
            raise ModelWorkspaceError("ADF requires at least one non-empty entity series.")
        return (
            {
                "variable": variable,
                "regression": regression,
                "autolag": autolag_value,
                "nullHypothesis": "The series has a unit root.",
                "groups": groups,
            },
            observations,
            dropped,
            warnings,
        )

    @staticmethod
    def _future_periods(last_period: str, frequency: str, steps: int) -> list[str]:
        aliases = {"annual": "Y", "quarterly": "Q", "monthly": "M"}
        alias = aliases.get(frequency)
        if alias is None:
            raise ModelWorkspaceError(f"Forecast frequency is not supported: {frequency}.")
        try:
            current = pd.Period(last_period, freq=alias)
        except ValueError as error:
            raise ModelWorkspaceError(
                f"Forecast period {last_period!r} is invalid for {frequency} data."
            ) from error
        return [str(current + step) for step in range(1, steps + 1)]

    @staticmethod
    def _arima_family(
        wide: pd.DataFrame, job: dict[str, Any]
    ) -> tuple[dict[str, Any], int, int, list[str]]:
        kind = str(job["kind"])
        dependent = ModelWorkspaceManager._require_columns(wide, list(job["dependentVariables"]))[0]
        independent = ModelWorkspaceManager._require_columns(
            wide, list(job.get("independentVariables") or [])
        )
        parameters = dict(job.get("parameters") or {})
        order = tuple(int(parameters.get(key, 0)) for key in ("orderP", "orderD", "orderQ"))
        seasonal_order = tuple(
            int(parameters.get(key, 0))
            for key in ("seasonalP", "seasonalD", "seasonalQ", "seasonalPeriod")
        )
        trend = str(parameters.get("trend", "n"))
        forecast_steps = int(parameters.get("forecastSteps", 4))
        confidence_level = float(parameters.get("confidenceLevel", 0.95))
        enforce_stationarity = bool(parameters.get("enforceStationarity", True))
        enforce_invertibility = bool(parameters.get("enforceInvertibility", True))
        group_results: list[dict[str, Any]] = []
        forecasts: list[dict[str, Any]] = []
        warnings: list[str] = []
        observations = 0
        dropped = 0

        for (entity_code, frequency), group in wide.groupby(level=[0, 1], sort=False):
            target = group[dependent]
            observed_positions = np.flatnonzero(target.notna().to_numpy())
            if not len(observed_positions):
                raise ModelWorkspaceError(
                    f"{kind.upper()} has no observed target for {entity_code}/{frequency}."
                )
            last_observed_position = int(observed_positions[-1])
            columns = [dependent, *independent]
            historical = group.iloc[: last_observed_position + 1][columns]
            complete = historical.dropna()
            group_dropped = len(historical) - len(complete)
            if len(complete) < 8:
                raise ModelWorkspaceError(
                    f"{kind.upper()} requires at least 8 complete observations for "
                    f"{entity_code}/{frequency}."
                )
            if group_dropped:
                warnings.append(
                    f"{kind.upper()} dropped {group_dropped} incomplete time points for "
                    f"{entity_code}/{frequency}; review temporal continuity."
                )
            future_exog: pd.DataFrame | None = None
            if independent:
                future_block = group.iloc[
                    last_observed_position + 1 : last_observed_position + 1 + forecast_steps
                ][independent]
                if len(future_block) != forecast_steps or future_block.isna().any(axis=None):
                    raise ModelWorkspaceError(
                        f"SARIMAX requires {forecast_steps} complete future exogenous rows for "
                        f"{entity_code}/{frequency}."
                    )
                future_exog = future_block.astype(float)
                forecast_periods = [
                    str(value) for value in future_block.index.get_level_values("period")
                ]
            else:
                last_period = str(group.index[last_observed_position][2])
                forecast_periods = ModelWorkspaceManager._future_periods(
                    last_period, str(frequency), forecast_steps
                )
            try:
                model = SARIMAX(
                    complete[dependent].to_numpy(dtype=float),
                    exog=complete[independent].to_numpy(dtype=float) if independent else None,
                    order=order,
                    seasonal_order=seasonal_order,
                    trend=trend,
                    enforce_stationarity=enforce_stationarity,
                    enforce_invertibility=enforce_invertibility,
                )
                with python_warnings.catch_warnings(record=True) as fit_warnings:
                    python_warnings.simplefilter("always", ConvergenceWarning)
                    fitted = model.fit(disp=False)
                prediction = fitted.get_forecast(
                    steps=forecast_steps,
                    exog=future_exog.to_numpy(dtype=float) if future_exog is not None else None,
                )
            except (ValueError, np.linalg.LinAlgError) as error:
                raise ModelWorkspaceError(
                    f"{kind.upper()} could not evaluate {entity_code}/{frequency}: {error}"
                ) from error
            converged = bool(fitted.mle_retvals.get("converged", True))
            if not converged or fit_warnings:
                warnings.append(
                    f"{kind.upper()} optimization reported a convergence warning for "
                    f"{entity_code}/{frequency}."
                )
            intervals = np.asarray(prediction.conf_int(alpha=1 - confidence_level), dtype=float)
            means = np.asarray(prediction.predicted_mean, dtype=float)
            for index, period in enumerate(forecast_periods):
                forecasts.append(
                    {
                        "entityCode": str(entity_code),
                        "frequency": str(frequency),
                        "period": period,
                        "step": index + 1,
                        "variable": dependent,
                        "mean": means[index],
                        "lower": intervals[index, 0],
                        "upper": intervals[index, 1],
                    }
                )
            group_results.append(
                {
                    "entityCode": str(entity_code),
                    "frequency": str(frequency),
                    "observations": len(complete),
                    "aic": fitted.aic,
                    "bic": fitted.bic,
                    "hqic": fitted.hqic,
                    "logLikelihood": fitted.llf,
                    "converged": converged,
                    "parameters": {
                        str(name): value
                        for name, value in zip(fitted.param_names, fitted.params, strict=True)
                    },
                }
            )
            observations += len(complete)
            dropped += group_dropped
        if not group_results:
            raise ModelWorkspaceError(f"{kind.upper()} requires at least one non-empty series.")
        return (
            {
                "dependentVariable": dependent,
                "independentVariables": independent,
                "order": list(order),
                "seasonalOrder": list(seasonal_order),
                "trend": trend,
                "forecastSteps": forecast_steps,
                "confidenceLevel": confidence_level,
                "groups": group_results,
                "forecasts": forecasts,
            },
            observations,
            dropped,
            warnings,
        )

    @staticmethod
    def _var(wide: pd.DataFrame, job: dict[str, Any]) -> tuple[dict[str, Any], int, int, list[str]]:
        variables = ModelWorkspaceManager._require_columns(wide, list(job["variables"]))
        parameters = dict(job.get("parameters") or {})
        max_lags = int(parameters.get("maxLags", 1))
        lag_selection = str(parameters.get("lagSelection", "fixed"))
        trend = str(parameters.get("trend", "c"))
        include_irf = bool(parameters.get("includeIrf", False))
        irf_periods = int(parameters.get("irfPeriods", 12))
        orthogonalized = bool(parameters.get("orthogonalized", True))
        confidence_level = float(parameters.get("confidenceLevel", 0.95))
        forecast_steps = int(parameters.get("forecastSteps", 0))
        impulses = [
            str(value).strip().upper() for value in parameters.get("impulseVariables") or variables
        ]
        groups: list[dict[str, Any]] = []
        coefficients: list[dict[str, Any]] = []
        impulse_responses: list[dict[str, Any]] = []
        forecasts: list[dict[str, Any]] = []
        warnings: list[str] = []
        observations = 0
        dropped = 0

        for (entity_code, frequency), group in wide.groupby(level=[0, 1], sort=False):
            selected = group[variables]
            complete_indexed = selected.dropna()
            complete = complete_indexed.reset_index(drop=True)
            group_dropped = len(selected) - len(complete)
            if len(complete) <= max_lags + len(variables) + 1:
                raise ModelWorkspaceError(
                    f"VAR has too few complete observations for {entity_code}/{frequency}."
                )
            if group_dropped:
                warnings.append(
                    f"VAR dropped {group_dropped} incomplete time points for "
                    f"{entity_code}/{frequency}; review temporal continuity."
                )
            try:
                fitted = VAR(complete).fit(
                    maxlags=max_lags,
                    ic=None if lag_selection == "fixed" else lag_selection,
                    trend=trend,
                )
            except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as error:
                raise ModelWorkspaceError(
                    f"VAR could not evaluate {entity_code}/{frequency}: {error}"
                ) from error
            stable = bool(fitted.is_stable(verbose=False))
            if not stable:
                warnings.append(
                    f"VAR is unstable for {entity_code}/{frequency}; interpret IRFs cautiously."
                )
            groups.append(
                {
                    "entityCode": str(entity_code),
                    "frequency": str(frequency),
                    "observations": int(fitted.nobs),
                    "lagOrder": int(fitted.k_ar),
                    "aic": fitted.aic,
                    "bic": fitted.bic,
                    "hqic": fitted.hqic,
                    "fpe": fitted.fpe,
                    "logLikelihood": fitted.llf,
                    "stable": stable,
                }
            )
            for term in fitted.params.index:
                for equation in fitted.params.columns:
                    coefficients.append(
                        {
                            "entityCode": str(entity_code),
                            "frequency": str(frequency),
                            "equation": str(equation),
                            "term": str(term),
                            "estimate": fitted.params.loc[term, equation],
                            "standardError": fitted.stderr.loc[term, equation],
                            "tStatistic": fitted.tvalues.loc[term, equation],
                            "pValue": fitted.pvalues.loc[term, equation],
                        }
                    )
            if forecast_steps:
                if fitted.k_ar < 1:
                    raise ModelWorkspaceError(
                        f"VAR forecasting requires a selected lag order of at least 1 for "
                        f"{entity_code}/{frequency}."
                    )
                last_period = str(complete_indexed.index[-1][2])
                forecast_periods = ModelWorkspaceManager._future_periods(
                    last_period, str(frequency), forecast_steps
                )
                try:
                    means, lowers, uppers = fitted.forecast_interval(
                        complete.to_numpy(dtype=float)[-fitted.k_ar :],
                        steps=forecast_steps,
                        alpha=1 - confidence_level,
                    )
                except (ValueError, np.linalg.LinAlgError) as error:
                    raise ModelWorkspaceError(
                        f"VAR could not forecast {entity_code}/{frequency}: {error}"
                    ) from error
                for step_index, period in enumerate(forecast_periods):
                    for variable_index, forecast_variable in enumerate(variables):
                        forecasts.append(
                            {
                                "entityCode": str(entity_code),
                                "frequency": str(frequency),
                                "period": period,
                                "step": step_index + 1,
                                "variable": forecast_variable,
                                "mean": means[step_index, variable_index],
                                "lower": lowers[step_index, variable_index],
                                "upper": uppers[step_index, variable_index],
                            }
                        )
            if include_irf:
                if fitted.k_ar < 1:
                    raise ModelWorkspaceError(
                        f"VAR IRF requires a selected lag order of at least 1 for "
                        f"{entity_code}/{frequency}."
                    )
                analysis = fitted.irf(irf_periods)
                values = analysis.orth_irfs if orthogonalized else analysis.irfs
                standard_errors = analysis.stderr(orth=orthogonalized)
                quantile = NormalDist().inv_cdf((1 + confidence_level) / 2)
                for impulse in impulses:
                    impulse_index = variables.index(impulse)
                    for response_index, response in enumerate(variables):
                        for irf_step in range(irf_periods + 1):
                            estimate = values[irf_step, response_index, impulse_index]
                            standard_error = standard_errors[
                                irf_step, response_index, impulse_index
                            ]
                            impulse_responses.append(
                                {
                                    "entityCode": str(entity_code),
                                    "frequency": str(frequency),
                                    "impulse": impulse,
                                    "response": response,
                                    "period": irf_step,
                                    "estimate": estimate,
                                    "lower": estimate - quantile * standard_error,
                                    "upper": estimate + quantile * standard_error,
                                }
                            )
            observations += len(complete)
            dropped += group_dropped
        if not groups:
            raise ModelWorkspaceError("VAR requires at least one non-empty entity series.")
        return (
            {
                "variables": variables,
                "lagSelection": lag_selection,
                "maxLags": max_lags,
                "trend": trend,
                "includeIrf": include_irf,
                "irfPeriods": irf_periods if include_irf else None,
                "orthogonalized": orthogonalized if include_irf else None,
                "confidenceLevel": confidence_level if include_irf or forecast_steps else None,
                "forecastSteps": forecast_steps,
                "forecasts": forecasts,
                "groups": groups,
                "coefficients": coefficients,
                "impulseResponses": impulse_responses,
            },
            observations,
            dropped,
            warnings,
        )

    def execute(
        self,
        session_id: str,
        snapshot_id: str,
        job: dict[str, Any],
        *,
        persist: bool = True,
    ) -> ModelResultRecord:
        snapshot = self.data_manager.get_snapshot(session_id, snapshot_id)
        result, sample, warnings = evaluate_typed_model_frame(
            self.data_manager.frame(snapshot), job
        )
        kind = str(job["kind"])
        record = ModelResultRecord(
            id=f"model-result-{uuid4().hex}",
            session_id=session_id,
            job_id=str(job["id"]),
            kind=kind,
            input_snapshot_id=snapshot_id,
            input_snapshot_hash=snapshot.snapshot_hash,
            specification_hash=self.specification_hash(job),
            result_hash=_hash(result),
            sample=sample,
            result=result,
            diagnostics=["Typed model validation passed.", "Input snapshot hash recorded."],
            warnings=warnings,
            created_at=datetime.now(timezone.utc),
        )
        if persist:
            self.persist([record])
        return record

    def persist(self, records: list[ModelResultRecord]) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO workflow_model_results(session_id, result_id, record_json)
                VALUES (?, ?, ?)
                """,
                [(record.session_id, record.id, record.model_dump_json()) for record in records],
            )


def evaluate_typed_model_frame(
    frame: pd.DataFrame,
    job: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    """Evaluate a reviewed model job without storage side effects."""
    ModelWorkspaceManager.validate_job(job)
    if job.get("sampleWindow"):
        from macro_research_agent.research_core.planning import ResearchPeriod

        window = ResearchPeriod.model_validate(job["sampleWindow"])
        frame = frame.loc[
            (frame["period"].astype(str) >= window.start)
            & (frame["period"].astype(str) <= window.end)
            & (frame["frequency"] == window.frequency)
        ]
    if job.get("entityCodes"):
        frame = frame.loc[frame["entity_code"].isin(job["entityCodes"])]
    wide = ModelWorkspaceManager._wide(frame)
    kind = str(job["kind"])
    warnings: list[str] = []
    if kind == "descriptive":
        result, observations, dropped = ModelWorkspaceManager._descriptive(
            wide, list(job.get("variables") or [])
        )
        # Registered descriptive output, not label/objective parsing: retain the exact
        # ordered observations and first/last observed endpoint difference in every scope.
        selected = frame[frame["indicator_code"].isin(job.get("variables") or [])].sort_values(
            ["entity_code", "indicator_code", "frequency", "period"]
        )
        fields = [
            field
            for field in (
                "entity_code",
                "indicator_code",
                "frequency",
                "period",
                "value",
                "unit",
                "status",
                "observation_origin",
            )
            if field in selected.columns
        ]
        result["observedSeries"] = selected[fields].to_dict(orient="records")
        endpoints = []
        for (entity, variable, frequency), group in selected.groupby(
            ["entity_code", "indicator_code", "frequency"]
        ):
            observed = group[pd.to_numeric(group["value"], errors="coerce").notna()]
            if observed.empty:
                continue
            first, last = observed.iloc[0], observed.iloc[-1]
            endpoints.append(
                {
                    "entityCode": str(entity),
                    "variable": str(variable),
                    "frequency": str(frequency),
                    "startPeriod": str(first["period"]),
                    "endPeriod": str(last["period"]),
                    "startValue": float(first["value"]),
                    "endValue": float(last["value"]),
                    "difference": float(last["value"]) - float(first["value"]),
                    "unit": first.get("unit"),
                    "operation": "last_observed_minus_first_observed",
                }
            )
        result["endpointComparisons"] = endpoints
    elif kind == "correlation":
        result, observations, dropped = ModelWorkspaceManager._correlation(
            wide, list(job.get("variables") or [])
        )
    elif kind == "ols":
        result, observations, dropped, warnings = ModelWorkspaceManager._ols(wide, job)
    elif kind == "adf":
        result, observations, dropped, warnings = ModelWorkspaceManager._adf(wide, job)
    elif kind in {"arima", "sarimax"}:
        result, observations, dropped, warnings = ModelWorkspaceManager._arima_family(wide, job)
    else:
        result, observations, dropped, warnings = ModelWorkspaceManager._var(wide, job)
    if job.get("validationStart"):
        boundary = str(job["validationStart"])
        training = frame[frame["period"].astype(str) < boundary]
        validation = frame[frame["period"].astype(str) >= boundary]
        if kind not in {"arima", "sarimax", "var"} or training.empty or validation.empty:
            raise ModelWorkspaceError(
                "Forecast validation needs non-empty isolated train/holdout scopes."
            )
        holdout_job = {
            key: value
            for key, value in job.items()
            if key not in {"validationStart", "sampleWindow"}
        }
        holdout_job["parameters"] = {
            **job["parameters"],
            "forecastSteps": min(
                int(job["parameters"].get("forecastSteps", 0)), validation["period"].nunique()
            ),
        }
        if holdout_job["parameters"]["forecastSteps"] < 1:
            raise ModelWorkspaceError("Forecast validation needs at least one forecast period.")
        holdout_frame = training
        if kind == "sarimax":
            # Exogenous holdout observations are known for retrospective validation;
            # target holdout values remain unavailable to the fitting routine.
            future_exogenous = validation.copy()
            future_exogenous.loc[
                future_exogenous["indicator_code"].isin(job["dependentVariables"]), "value"
            ] = np.nan
            holdout_frame = pd.concat([training, future_exogenous], ignore_index=True)
        holdout_result, holdout_sample, holdout_warnings = evaluate_typed_model_frame(
            holdout_frame, holdout_job
        )
        comparisons = []
        for forecast in holdout_result.get("forecasts", []):
            actual = validation[
                validation["entity_code"].astype(str).eq(str(forecast["entityCode"]))
                & validation["indicator_code"].astype(str).eq(str(forecast["variable"]))
                & validation["period"].astype(str).eq(str(forecast["period"]))
            ]
            if len(actual) == 1 and pd.notna(actual.iloc[0]["value"]):
                comparisons.append(
                    {
                        **forecast,
                        "actual": float(actual.iloc[0]["value"]),
                        "error": float(forecast["mean"]) - float(actual.iloc[0]["value"]),
                    }
                )
        if not comparisons:
            raise ModelWorkspaceError("Forecast holdout produced no aligned actual comparisons.")
        errors = np.array([item["error"] for item in comparisons], dtype=float)
        result["validation"] = {
            "policy": "fixed-mae-rmse-v1",
            "validationStart": boundary,
            "trainingSample": holdout_sample,
            "comparisons": comparisons,
            "mae": float(np.abs(errors).mean()),
            "rmse": float(np.sqrt((errors**2).mean())),
            "warnings": holdout_warnings,
            "trainingResultHash": _hash(holdout_result),
            "futureForecastsUseFullHistory": True,
        }
    return (
        _json_value(result),
        {"observations": observations, "dropped": dropped},
        warnings,
    )
