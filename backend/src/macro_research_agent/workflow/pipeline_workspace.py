from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from macro_research_agent.research_core.transforms import FrameTransformEngine
from macro_research_agent.research_core.transforms import (
    PipelineWorkspaceError as PipelineWorkspaceError,
)
from macro_research_agent.workflow.data_workspace import (
    DatasetSnapshotRecord,
    DataWorkspaceManager,
)

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


class TransformationLineageRecord(BaseModel):
    operation_id: str
    operation: str
    input_ref: str
    output_ref: str
    input_snapshot_id: str
    input_snapshot_hash: str
    output_snapshot_id: str
    output_snapshot_hash: str
    specification_hash: str
    input_rows: int = Field(ge=0)
    output_rows: int = Field(ge=0)


class PipelineRunRecord(BaseModel):
    session_id: str
    bundle_id: str
    input_snapshot_id: str
    final_snapshot_id: str
    operation_snapshot_refs: dict[str, str]
    output_snapshot_refs: dict[str, str]
    operation_lineage: list[TransformationLineageRecord] = Field(default_factory=list)
    operation_ids: list[str]
    diagnostics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


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


class PipelineWorkspaceManager(FrameTransformEngine):
    def __init__(
        self,
        database_path: Path,
        data_manager: DataWorkspaceManager,
    ) -> None:
        self.database_path = database_path
        self.data_manager = data_manager
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_pipeline_runs (
                    session_id TEXT NOT NULL,
                    bundle_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, bundle_id),
                    FOREIGN KEY (session_id) REFERENCES workflow_sessions(session_id)
                )
                """
            )

    def execute_pipeline(
        self,
        session_id: str,
        input_snapshot_id: str,
        operations: list[dict[str, Any]],
    ) -> PipelineRunRecord:
        self.validate_pipeline(operations)
        input_snapshot = self.data_manager.get_snapshot(session_id, input_snapshot_id)
        refs: dict[str, DatasetSnapshotRecord] = {"active_dataset": input_snapshot}
        operation_snapshot_refs: dict[str, str] = {}
        operation_lineage: list[TransformationLineageRecord] = []
        warnings: list[str] = []
        operation_ids: list[str] = []
        for operation in operations:
            input_record = refs[str(operation["inputRef"])]
            if not operation.get("enabled", True):
                refs[str(operation["outputRef"])] = input_record
                continue
            output = self.transform_frame(self.data_manager.frame(input_record), operation)
            if (
                str(operation["kind"]) == "frequency_conversion"
                and "frequency_coverage" in output
                and (pd.to_numeric(output["frequency_coverage"], errors="coerce") < 1).any()
            ):
                warnings.append(
                    f"{operation['label']} retained incomplete target periods; "
                    "review frequency_coverage before using the output."
                )
            snapshot = self.data_manager.record_analytical_snapshot(
                session_id,
                output,
                label=f"{operation['label']} output",
                operation_id=str(operation["id"]),
                parent_snapshot_id=input_record.snapshot_id,
            )
            refs[str(operation["outputRef"])] = snapshot
            operation_snapshot_refs[str(operation["id"])] = snapshot.snapshot_id
            operation_lineage.append(
                TransformationLineageRecord(
                    operation_id=str(operation["id"]),
                    operation=str(operation["kind"]),
                    input_ref=str(operation["inputRef"]),
                    output_ref=str(operation["outputRef"]),
                    input_snapshot_id=input_record.snapshot_id,
                    input_snapshot_hash=input_record.snapshot_hash,
                    output_snapshot_id=snapshot.snapshot_id,
                    output_snapshot_hash=snapshot.snapshot_hash,
                    specification_hash=_specification_hash(
                        {
                            "kind": operation["kind"],
                            "enabled": operation.get("enabled", True),
                            "inputRef": operation["inputRef"],
                            "outputRef": operation["outputRef"],
                            "target": operation.get("target") or {},
                            "parameters": operation.get("parameters") or {},
                        }
                    ),
                    input_rows=input_record.row_count,
                    output_rows=snapshot.row_count,
                )
            )
            operation_ids.append(str(operation["id"]))
        enabled = [operation for operation in operations if operation.get("enabled", True)]
        final_ref = str(enabled[-1]["outputRef"]) if enabled else "active_dataset"
        final_snapshot = refs[final_ref]
        record = PipelineRunRecord(
            session_id=session_id,
            bundle_id=_identifier("analytical-bundle"),
            input_snapshot_id=input_snapshot_id,
            final_snapshot_id=final_snapshot.snapshot_id,
            operation_snapshot_refs=operation_snapshot_refs,
            output_snapshot_refs={key: value.snapshot_id for key, value in refs.items()},
            operation_lineage=operation_lineage,
            operation_ids=operation_ids,
            diagnostics=[
                "Typed pipeline validation passed.",
                f"Executed {len(operation_ids)} registered transformations.",
            ],
            warnings=warnings,
            created_at=_now(),
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_pipeline_runs(session_id, bundle_id, record_json)
                VALUES (?, ?, ?)
                """,
                (session_id, record.bundle_id, record.model_dump_json()),
            )
        return record

    def preview_pipeline(
        self,
        session_id: str,
        input_snapshot_id: str,
        operations: list[dict[str, Any]],
        operation_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if offset < 0 or limit < 1 or limit > 500:
            raise PipelineWorkspaceError("Preview offset/limit is outside the allowed range.")
        self.validate_pipeline(operations)
        input_record = self.data_manager.get_snapshot(session_id, input_snapshot_id)
        refs: dict[str, pd.DataFrame] = {"active_dataset": self.data_manager.frame(input_record)}
        selected_output = refs["active_dataset"]
        selected_id: str | None = None
        for operation in operations:
            input_frame = refs[str(operation["inputRef"])]
            output = (
                self.transform_frame(input_frame, operation)
                if operation.get("enabled", True)
                else input_frame.copy()
            )
            refs[str(operation["outputRef"])] = output
            selected_output = output
            selected_id = str(operation["id"])
            if operation_id == selected_id:
                break
        if operation_id and selected_id != operation_id:
            raise PipelineWorkspaceError("Unknown pipeline operation for preview.")
        safe = selected_output.iloc[offset : offset + limit].copy()
        safe = safe.astype(object).where(pd.notna(safe), None)
        return {
            "operation_id": selected_id,
            "offset": offset,
            "limit": limit,
            "total_rows": len(selected_output),
            "columns": [str(column) for column in selected_output.columns],
            "rows": [
                {str(key): value for key, value in row.items()} for row in safe.to_dict("records")
            ],
        }


def execute_typed_pipeline_frame(
    frame: pd.DataFrame,
    operations: list[dict[str, Any]],
) -> dict[str, pd.DataFrame]:
    """Execute reviewed operations in memory for generated-code reproduction."""
    runtime = FrameTransformEngine()
    runtime.validate_pipeline(operations)
    refs: dict[str, pd.DataFrame] = {"active_dataset": frame.copy()}
    for operation in operations:
        input_frame = refs[str(operation["inputRef"])]
        refs[str(operation["outputRef"])] = (
            runtime.transform_frame(input_frame, operation)
            if operation.get("enabled", True)
            else input_frame.copy()
        )
    return refs
