from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ResearchStage(str, Enum):
    PLAN = "plan"
    DATA = "data"
    TRANSFORMATION = "transformation"
    OUTPUT = "output"


DataClassification = Literal["user_supplied", "public", "licensed"]
DataSourceKind = Literal["upload", "snapshot"]
ModelDataOperation = Literal["read_rows", "filter_rows", "aggregate_rows"]


def default_operations() -> list[ModelDataOperation]:
    return ["read_rows", "filter_rows", "aggregate_rows"]


class ModelDataAccessError(ValueError):
    pass


class ModelDataPage(BaseModel):
    access_id: str
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    rows: list[dict[str, Any]]
    page_hash: str


class ModelDataFilter(BaseModel):
    column: str = Field(min_length=1)
    operator: Literal["eq", "in", "gte", "lte"]
    value: Any


class ModelDataAggregate(BaseModel):
    group_by: list[str] = Field(default_factory=list, max_length=8)
    column: str = Field(min_length=1)
    function: Literal["count", "sum", "mean", "min", "max"]


class ModelDataAggregateResult(BaseModel):
    access_id: str
    rows: list[dict[str, Any]]
    result_hash: str


class ModelDataAccessGrant(BaseModel):
    mode: Literal["workflow", "agent"] = "workflow"
    run_id: str | None = None
    access_id: str
    session_id: str
    stage: ResearchStage
    source_kind: DataSourceKind
    source_ref: str
    content_hash: str
    classification: DataClassification
    provider_profile: str
    model_id: str
    columns: list[str]
    row_count: int = Field(ge=0)
    page_size: int = Field(ge=1, le=500)
    page_count: int = Field(ge=0)
    complete_value_access: bool = True
    remote_disclosure_allowed: bool
    allowed_operations: list[ModelDataOperation] = Field(default_factory=default_operations)


class ModelDatasetContext(BaseModel):
    grant: ModelDataAccessGrant
    initial_page: ModelDataPage | None = None


class ModelDataAccessPort(Protocol):
    def read_page(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage: ...
    def read_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage: ...
    def filter_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        filters: list[ModelDataFilter],
        offset: int = 0,
        limit: int | None = None,
    ) -> ModelDataPage: ...
    def aggregate_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        specification: ModelDataAggregate,
    ) -> ModelDataAggregateResult: ...


class ModelAuditPort(Protocol):
    def record_trace_event(
        self, session_id: str, event_type: str, actor: Any, payload: dict[str, Any]
    ) -> Any: ...
