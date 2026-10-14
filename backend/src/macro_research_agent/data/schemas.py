from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Observation(BaseModel):
    provider: str
    dataset: str
    series_id: str
    entity_code: str | None = None
    entity_name: str | None = None
    indicator_code: str | None = None
    indicator_name: str | None = None
    frequency: str | None = None
    period: str
    value: float | None
    unit: str | None = None
    scale: str | None = None
    status: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class NormalizedDataset(BaseModel):
    observations: list[Observation]
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
