from __future__ import annotations

import hashlib
import json
import math
import threading
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.research_core.data_access import (
    DataClassification as DataClassification,
)
from macro_research_agent.research_core.data_access import (
    DataSourceKind as DataSourceKind,
)
from macro_research_agent.research_core.data_access import (
    ModelDataAccessError as ModelDataAccessError,
)
from macro_research_agent.research_core.data_access import (
    ModelDataAccessGrant as ModelDataAccessGrant,
)
from macro_research_agent.research_core.data_access import (
    ModelDataAccessPort as ModelDataAccessPort,
)
from macro_research_agent.research_core.data_access import (
    ModelDataAggregate as ModelDataAggregate,
)
from macro_research_agent.research_core.data_access import (
    ModelDataAggregateResult as ModelDataAggregateResult,
)
from macro_research_agent.research_core.data_access import (
    ModelDataFilter as ModelDataFilter,
)
from macro_research_agent.research_core.data_access import (
    ModelDataOperation as ModelDataOperation,
)
from macro_research_agent.research_core.data_access import (
    ModelDataPage as ModelDataPage,
)
from macro_research_agent.research_core.data_access import (
    ModelDatasetContext as ModelDatasetContext,
)
from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.data_workspace import DataWorkspaceError, DataWorkspaceManager
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.states import WorkflowStage
from macro_research_agent.workflow.uploads import UploadedFileRecord


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _wire_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    return [{str(key): value for key, value in row.items()} for row in records]


class WorkflowModelDataAccessService:
    """Issues auditable, snapshot-bound grants without exposing arbitrary files or SQL."""

    def __init__(
        self,
        repository: WorkflowRepository,
        data_manager: DataWorkspaceManager,
        *,
        enabled: bool = True,
        page_size: int = 200,
        remote_user_data_allowed: bool = True,
        remote_licensed_data_allowed: bool = False,
    ) -> None:
        if page_size < 1 or page_size > 500:
            raise ValueError("AI data page size must be between 1 and 500.")
        self.repository = repository
        self.data_manager = data_manager
        self.enabled = enabled
        self.page_size = page_size
        self.remote_user_data_allowed = remote_user_data_allowed
        self.remote_licensed_data_allowed = remote_licensed_data_allowed
        self._lock = threading.RLock()
        self._grants: dict[str, ModelDataAccessGrant] = {}

    def contexts_for_uploads(
        self,
        session_id: str,
        stage: WorkflowStage,
        *,
        for_remote_provider: bool = True,
        provider_profile: str = "unspecified",
        model_id: str = "unspecified",
    ) -> list[ModelDatasetContext]:
        if not self.enabled:
            return []
        return [
            self.context_for_upload(
                record,
                stage,
                for_remote_provider=for_remote_provider,
                provider_profile=provider_profile,
                model_id=model_id,
            )
            for record in self.repository.list_uploads(session_id)
        ]

    def context_for_upload(
        self,
        record: UploadedFileRecord,
        stage: WorkflowStage,
        *,
        for_remote_provider: bool = True,
        provider_profile: str = "unspecified",
        model_id: str = "unspecified",
    ) -> ModelDatasetContext:
        if not self.enabled:
            raise ModelDataAccessError("AI data access is disabled for this runtime.")
        frame = self.data_manager.read_upload_frame(record)
        grant = self._register(
            session_id=record.session_id,
            stage=stage,
            source_kind="upload",
            source_ref=record.upload_id,
            content_hash=record.checksum,
            classification="user_supplied",
            provider_profile=provider_profile,
            model_id=model_id,
            frame=frame,
        )
        if for_remote_provider:
            self.require_remote_disclosure(grant.access_id, record.session_id, stage)
        return ModelDatasetContext(
            grant=grant,
            initial_page=self.read_page(
                grant.access_id,
                session_id=record.session_id,
                stage=stage,
                offset=0,
            ),
        )

    def context_for_snapshot(
        self,
        session_id: str,
        snapshot_id: str,
        stage: WorkflowStage,
        *,
        classification: DataClassification = "public",
        for_remote_provider: bool = True,
        provider_profile: str = "unspecified",
        model_id: str = "unspecified",
    ) -> ModelDatasetContext:
        if not self.enabled:
            raise ModelDataAccessError("AI data access is disabled for this runtime.")
        snapshot = self.data_manager.get_snapshot(session_id, snapshot_id)
        frame = self.data_manager.frame(snapshot)
        grant = self._register(
            session_id=session_id,
            stage=stage,
            source_kind="snapshot",
            source_ref=snapshot.snapshot_id,
            content_hash=snapshot.snapshot_hash,
            classification=classification,
            provider_profile=provider_profile,
            model_id=model_id,
            frame=frame,
        )
        if for_remote_provider:
            self.require_remote_disclosure(grant.access_id, session_id, stage)
        return ModelDatasetContext(
            grant=grant,
            initial_page=self.read_page(
                grant.access_id,
                session_id=session_id,
                stage=stage,
                offset=0,
            ),
        )

    def require_remote_disclosure(
        self, access_id: str, session_id: str, stage: WorkflowStage
    ) -> ModelDataAccessGrant:
        """Fail closed before any values are placed in a remote provider request."""

        grant = self._grant(access_id, session_id, stage)
        if not grant.remote_disclosure_allowed:
            raise ModelDataAccessError(
                f"Remote model access is not authorized for {grant.classification} data."
            )
        return grant

    def read_page(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        grant = self._grant(access_id, session_id, stage)
        requested_limit = limit or grant.page_size
        if offset < 0 or requested_limit < 1 or requested_limit > 500:
            raise ModelDataAccessError("Model data page is outside the allowed range.")
        frame = self._frame_for_grant(grant).iloc[offset : offset + requested_limit]
        rows = _wire_rows(frame)
        page = ModelDataPage(
            access_id=grant.access_id,
            offset=offset,
            limit=requested_limit,
            rows=rows,
            page_hash=_hash({"access_id": grant.access_id, "offset": offset, "rows": rows}),
        )
        self.repository.record_trace_event(
            grant.session_id,
            "ai.data_accessed",
            Actor.AGENT,
            {
                "policy_version": "model-data-access-v1",
                "access_id": grant.access_id,
                "provider_profile": grant.provider_profile,
                "model_id": grant.model_id,
                "stage": grant.stage.value,
                "source_kind": grant.source_kind,
                "source_ref": grant.source_ref,
                "content_hash": grant.content_hash,
                "classification": grant.classification,
                "columns": grant.columns,
                "offset": offset,
                "limit": requested_limit,
                "returned_row_count": len(rows),
                "page_hash": page.page_hash,
                "remote_disclosure_allowed": grant.remote_disclosure_allowed,
            },
        )
        return page

    def read_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        """Registered report-model row read; kept as an explicit API over pagination."""

        return self.read_page(
            access_id,
            session_id=session_id,
            stage=stage,
            offset=offset,
            limit=limit,
        )

    def filter_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        filters: list[ModelDataFilter],
        offset: int = 0,
        limit: int | None = None,
    ) -> ModelDataPage:
        grant = self._grant(access_id, session_id, stage)
        frame = self._frame_for_grant(grant)
        for item in filters:
            if item.column not in grant.columns:
                raise ModelDataAccessError("Model data filter references an unavailable column.")
            series = frame[item.column]
            if item.operator == "eq":
                frame = frame[series == item.value]
            elif item.operator == "in":
                if not isinstance(item.value, list):
                    raise ModelDataAccessError("The in filter requires a bounded value list.")
                frame = frame[series.isin(item.value[:100])]
            elif item.operator == "gte":
                frame = frame[series >= item.value]
            else:
                frame = frame[series <= item.value]
        requested_limit = limit or grant.page_size
        if offset < 0 or requested_limit < 1 or requested_limit > 500:
            raise ModelDataAccessError("Model data page is outside the allowed range.")
        rows = _wire_rows(frame.iloc[offset : offset + requested_limit])
        filter_wire = [item.model_dump(mode="json") for item in filters]
        page = ModelDataPage(
            access_id=access_id,
            offset=offset,
            limit=requested_limit,
            rows=rows,
            page_hash=_hash({"access_id": access_id, "filters": filter_wire, "rows": rows}),
        )
        self._record_derived_access(grant, "filter_rows", page.page_hash, len(rows), filter_wire)
        return page

    def aggregate_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        specification: ModelDataAggregate,
    ) -> ModelDataAggregateResult:
        grant = self._grant(access_id, session_id, stage)
        requested = [*specification.group_by, specification.column]
        if any(column not in grant.columns for column in requested):
            raise ModelDataAccessError("Model data aggregation references an unavailable column.")
        frame = self._frame_for_grant(grant)
        if specification.function == "count":
            if specification.group_by:
                result = (
                    frame.groupby(specification.group_by, dropna=False)
                    .size()
                    .reset_index(name="value")
                )
            else:
                result = pd.DataFrame([{"value": int(frame[specification.column].count())}])
        else:
            numeric = pd.to_numeric(frame[specification.column], errors="coerce")
            frame = frame.assign(**{specification.column: numeric})
            if specification.group_by:
                result = (
                    frame.groupby(specification.group_by, dropna=False)[specification.column]
                    .agg(specification.function)
                    .reset_index(name="value")
                )
            else:
                result = pd.DataFrame(
                    [{"value": getattr(frame[specification.column], specification.function)()}]
                )
        rows = _wire_rows(result)
        spec_wire = specification.model_dump(mode="json")
        result_hash = _hash({"access_id": access_id, "specification": spec_wire, "rows": rows})
        self._record_derived_access(grant, "aggregate_rows", result_hash, len(rows), spec_wire)
        return ModelDataAggregateResult(access_id=access_id, rows=rows, result_hash=result_hash)

    def _record_derived_access(
        self,
        grant: ModelDataAccessGrant,
        operation: ModelDataOperation,
        result_hash: str,
        row_count: int,
        specification: Any,
    ) -> None:
        self.repository.record_trace_event(
            grant.session_id,
            "ai.data_accessed",
            Actor.AGENT,
            {
                "policy_version": "model-data-access-v1",
                "access_id": grant.access_id,
                "provider_profile": grant.provider_profile,
                "model_id": grant.model_id,
                "stage": grant.stage.value,
                "source_kind": grant.source_kind,
                "source_ref": grant.source_ref,
                "content_hash": grant.content_hash,
                "classification": grant.classification,
                "operation": operation,
                "specification": specification,
                "returned_row_count": row_count,
                "result_hash": result_hash,
                "remote_disclosure_allowed": grant.remote_disclosure_allowed,
            },
        )

    def _grant(self, access_id: str, session_id: str, stage: WorkflowStage) -> ModelDataAccessGrant:
        with self._lock:
            grant = self._grants.get(access_id)
        if grant is None:
            raise ModelDataAccessError("Unknown or expired model data access grant.")
        if grant.session_id != session_id or grant.stage != stage:
            raise ModelDataAccessError("Model data access grant is outside its session or stage.")
        return grant

    def _register(
        self,
        *,
        session_id: str,
        stage: WorkflowStage,
        source_kind: DataSourceKind,
        source_ref: str,
        content_hash: str,
        classification: DataClassification,
        provider_profile: str,
        model_id: str,
        frame: pd.DataFrame,
    ) -> ModelDataAccessGrant:
        if classification == "licensed":
            disclosure_allowed = self.remote_licensed_data_allowed
        else:
            disclosure_allowed = self.remote_user_data_allowed
        access_id = (
            "data-access-"
            + hashlib.sha256(
                f"{session_id}|{stage.value}|{source_kind}|{source_ref}|{content_hash}".encode()
            ).hexdigest()[:24]
        )
        grant = ModelDataAccessGrant(
            access_id=access_id,
            session_id=session_id,
            stage=stage,
            source_kind=source_kind,
            source_ref=source_ref,
            content_hash=content_hash,
            classification=classification,
            provider_profile=provider_profile,
            model_id=model_id,
            columns=[str(column) for column in frame.columns],
            row_count=len(frame),
            page_size=self.page_size,
            page_count=math.ceil(len(frame) / self.page_size) if len(frame) else 0,
            remote_disclosure_allowed=disclosure_allowed,
        )
        with self._lock:
            self._grants[access_id] = grant
        return grant

    def _frame_for_grant(self, grant: ModelDataAccessGrant) -> pd.DataFrame:
        if grant.source_kind == "upload":
            record = next(
                (
                    item
                    for item in self.repository.list_uploads(grant.session_id)
                    if item.upload_id == grant.source_ref and item.checksum == grant.content_hash
                ),
                None,
            )
            if record is None:
                raise ModelDataAccessError("The granted upload is no longer current or available.")
            try:
                return self.data_manager.read_upload_frame(record)
            except DataWorkspaceError as exc:
                raise ModelDataAccessError(str(exc)) from exc
        snapshot = self.data_manager.get_snapshot(grant.session_id, grant.source_ref)
        if snapshot.snapshot_hash != grant.content_hash:
            raise ModelDataAccessError("The granted dataset snapshot hash no longer matches.")
        return self.data_manager.frame(snapshot)
