from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ModelKind(str, Enum):
    DESCRIPTIVE = "descriptive"
    CORRELATION = "correlation"
    OLS = "ols"
    ADF = "adf"
    ARIMA = "arima"
    SARIMAX = "sarimax"
    VAR = "var"


class ModelSpecification(BaseModel):
    kind: ModelKind
    dependent_variables: list[str] = Field(default_factory=list)
    independent_variables: list[str] = Field(default_factory=list)
    options: dict[str, str | int | float | bool | list[int]] = Field(default_factory=dict)
    use_hac_errors: bool = False
    hac_max_lags: int | None = None
