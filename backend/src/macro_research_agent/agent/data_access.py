from __future__ import annotations

import io
import json
import math
from numbers import Integral, Real
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.agent.contracts import identifier
from macro_research_agent.agent.repository import AgentError, AgentRepository, checksum
from macro_research_agent.research_core.data_access import (
    DataClassification,
    ModelDataAccessError,
    ModelDataAccessGrant,
    ModelDataAggregate,
    ModelDataAggregateResult,
    ModelDataFilter,
    ModelDataPage,
    ModelDatasetContext,
    ResearchStage,
)


def frame_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads(frame.to_json(orient="records", date_format="iso"))
    # Pandas JSON defaults to ten decimal places. Preserve snapshot numeric scalars
    # using Python's round-trip representation, while retaining existing date/null handling.
    for encoded, original in zip(result, frame.to_dict(orient="records"), strict=True):
        for column, value in original.items():
            if isinstance(value, bool):
                encoded[column] = value
            elif isinstance(value, Integral):
                encoded[column] = int(value)
            elif isinstance(value, Real):
                encoded[column] = float(value) if math.isfinite(value) else None
    return result


def write_snapshot(
    repository: AgentRepository,
    session_id: str,
    run_id: str,
    frame: pd.DataFrame,
    *,
    classification: DataClassification = "public",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stream = io.BytesIO()
    frame.to_parquet(stream, index=False)
    ref = repository.put_blob(
        session_id,
        run_id,
        "dataset",
        stream.getvalue(),
        {
            "classification": classification,
            "row_count": len(frame),
            "columns": [str(column) for column in frame.columns],
            "provenance": provenance or {},
        },
    )
    repository.event(
        session_id,
        run_id,
        "dataset.snapshotted",
        {
            "snapshot_ref": ref["id"],
            "hash": ref["hash"],
            "row_count": len(frame),
            "classification": classification,
            "provenance": provenance or {},
        },
    )
    return ref


def read_snapshot(
    repository: AgentRepository, session_id: str, run_id: str, snapshot_ref: str
) -> pd.DataFrame:
    blobs = {blob["id"]: blob for blob in repository.blobs(session_id, run_id)}
    blob = blobs.get(snapshot_ref)
    if not blob or blob["kind"] != "dataset":
        raise AgentError("Snapshot is not owned by this Agent run.", "ownership_violation")
    return pd.read_parquet(
        io.BytesIO(repository.read_blob(session_id, run_id, snapshot_ref, blob["hash"]))
    )


class AgentModelDataAccess:
    def __init__(
        self,
        repository: AgentRepository,
        session_id: str,
        run_id: str,
        *,
        enabled: bool = True,
        remote_user_data_allowed: bool = True,
        remote_licensed_data_allowed: bool = False,
    ) -> None:
        self.repository, self.session_id, self.run_id = repository, session_id, run_id
        self.enabled = enabled
        self.remote_user_data_allowed = remote_user_data_allowed
        self.remote_licensed_data_allowed = remote_licensed_data_allowed
        self.grants: dict[str, ModelDataAccessGrant] = {}

    def context(
        self,
        snapshot_ref: str,
        stage: ResearchStage,
        *,
        provider: str,
        model: str,
        remote: bool = True,
    ) -> ModelDatasetContext:
        if not self.enabled:
            raise ModelDataAccessError("AI data access is disabled.")
        ref = next(
            (
                blob
                for blob in self.repository.blobs(self.session_id, self.run_id)
                if blob["id"] == snapshot_ref and blob["kind"] == "dataset"
            ),
            None,
        )
        if ref is None:
            raise ModelDataAccessError("Unknown Agent snapshot.")
        classification: DataClassification = ref["classification"]
        run = self.repository.get_run(self.session_id, self.run_id)
        if remote and run.authorizations:
            permissions = run.authorizations[-1].provider_permissions
            if provider not in {
                permissions.get("research_roles"),
                permissions.get("reviewer"),
            } or not permissions.get("remote_" + classification, False):
                raise ModelDataAccessError(
                    "Remote disclosure exceeds this run's immutable authorization."
                )
        if remote and (
            (classification == "licensed" and not self.remote_licensed_data_allowed)
            or (classification == "user_supplied" and not self.remote_user_data_allowed)
        ):
            raise ModelDataAccessError("Remote disclosure is not authorized for these data.")
        grant = ModelDataAccessGrant(
            mode="agent",
            run_id=self.run_id,
            access_id=identifier("grant"),
            session_id=self.session_id,
            stage=stage,
            source_kind="snapshot",
            source_ref=snapshot_ref,
            content_hash=ref["hash"],
            classification=classification,
            provider_profile=provider,
            model_id=model,
            columns=ref["columns"],
            row_count=ref["row_count"],
            page_size=200,
            page_count=math.ceil(ref["row_count"] / 200),
            remote_disclosure_allowed=remote,
        )
        self.grants[grant.access_id] = grant
        self.repository.event(
            self.session_id, self.run_id, "ai.grant_issued", grant.model_dump(mode="json")
        )
        return ModelDatasetContext(grant=grant)

    def _frame(
        self, access_id: str, session_id: str, stage: ResearchStage
    ) -> tuple[ModelDataAccessGrant, pd.DataFrame]:
        grant = self.grants.get(access_id)
        if (
            grant is None
            or grant.session_id != session_id
            or session_id != self.session_id
            or grant.stage != stage
            or grant.run_id != self.run_id
            or grant.mode != "agent"
        ):
            raise ModelDataAccessError("Agent grant ownership/stage mismatch.")
        content = self.repository.read_blob(
            session_id, self.run_id, grant.source_ref, grant.content_hash
        )
        return grant, pd.read_parquet(io.BytesIO(content))

    def _page(
        self,
        grant: ModelDataAccessGrant,
        frame: pd.DataFrame,
        offset: int,
        limit: int | None,
        operation: str,
        specification: Any = None,
    ) -> ModelDataPage:
        requested = limit if limit is not None else grant.page_size
        if not 1 <= requested <= 500 or offset < 0:
            raise ModelDataAccessError("Read is outside the bounded page range.")
        rows = frame_rows(frame.iloc[offset : offset + requested])
        page = ModelDataPage(
            access_id=grant.access_id,
            offset=offset,
            limit=requested,
            rows=rows,
            page_hash=checksum(rows),
        )
        self.repository.event(
            self.session_id,
            self.run_id,
            "ai.data_accessed",
            {
                "mode": "agent",
                "operation": operation,
                "grant_id": grant.access_id,
                "source_ref": grant.source_ref,
                "source_hash": grant.content_hash,
                "provider": grant.provider_profile,
                "model": grant.model_id,
                "classification": grant.classification,
                "columns": grant.columns,
                "offset": offset,
                "limit": requested,
                "row_count": len(rows),
                "page_hash": page.page_hash,
                "specification": specification,
            },
        )
        return page

    def read_page(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        grant, frame = self._frame(access_id, session_id, stage)
        return self._page(grant, frame, offset, limit, "read_rows")

    def read_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        return self.read_page(
            access_id, session_id=session_id, stage=stage, offset=offset, limit=limit
        )

    def filter_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        filters: list[ModelDataFilter],
        offset: int = 0,
        limit: int | None = None,
    ) -> ModelDataPage:
        grant, frame = self._frame(access_id, session_id, stage)
        for selection in filters:
            if selection.column not in grant.columns:
                raise ModelDataAccessError("Filter column is not granted.")
            series = frame[selection.column]
            if selection.operator == "eq":
                frame = frame[series == selection.value]
            elif selection.operator == "in":
                if not isinstance(selection.value, list) or len(selection.value) > 100:
                    raise ModelDataAccessError("Filter values exceed their bound.")
                frame = frame[series.isin(selection.value)]
            elif selection.operator == "gte":
                frame = frame[series >= selection.value]
            else:
                frame = frame[series <= selection.value]
        return self._page(
            grant,
            frame,
            offset,
            limit,
            "filter_rows",
            [selection.model_dump() for selection in filters],
        )

    def aggregate_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: ResearchStage,
        specification: ModelDataAggregate,
    ) -> ModelDataAggregateResult:
        grant, frame = self._frame(access_id, session_id, stage)
        if set([*specification.group_by, specification.column]) - set(grant.columns):
            raise ModelDataAccessError("Aggregate columns are not granted.")
        if specification.group_by:
            result = (
                frame.groupby(specification.group_by, dropna=False)[specification.column]
                .agg(specification.function)
                .reset_index()
            )
        else:
            result = pd.DataFrame(
                {specification.column: [frame[specification.column].agg(specification.function)]}
            )
        rows = frame_rows(result)
        digest = checksum(rows)
        self.repository.event(
            self.session_id,
            self.run_id,
            "ai.data_accessed",
            {
                "operation": "aggregate_rows",
                "grant_id": grant.access_id,
                "source_ref": grant.source_ref,
                "source_hash": grant.content_hash,
                "specification": specification.model_dump(),
                "row_count": len(rows),
                "page_hash": digest,
            },
        )
        return ModelDataAggregateResult(access_id=access_id, rows=rows, result_hash=digest)
