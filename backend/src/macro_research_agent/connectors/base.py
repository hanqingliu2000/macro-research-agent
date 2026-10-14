from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from macro_research_agent.data.schemas import NormalizedDataset


class AuthenticationMode(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    USER_CREDENTIALS = "user_credentials"
    LICENSED_LOCAL = "licensed_local"


class ConnectorCapability(BaseModel):
    connector_id: str
    display_name: str
    authentication: AuthenticationMode
    supports_discovery: bool = True
    supports_observations: bool = True
    provider_hosts: tuple[str, ...] = ()
    availability: Literal["available", "planned", "disabled"] = "available"
    unavailable_reason: str | None = None


class DataQuery(BaseModel):
    dataset: str
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    start_period: str | None = None
    end_period: str | None = None
    frequency: str | None = None
    options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SourceProvenance(BaseModel):
    connector_id: str
    connector_version: str
    provider: str
    dataset: str
    source_identifier: str
    retrieved_at: datetime
    request_parameters: dict[str, Any]
    raw_sha256: str
    normalized_sha256: str
    attribution: str | None = None


class FetchResult(BaseModel):
    dataset: NormalizedDataset
    provenance: SourceProvenance
    warnings: list[str] = Field(default_factory=list)


class DataConnector(ABC):
    @property
    @abstractmethod
    def capability(self) -> ConnectorCapability:
        raise NotImplementedError

    @abstractmethod
    async def discover(self, term: str) -> list[dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, query: DataQuery) -> FetchResult:
        raise NotImplementedError
