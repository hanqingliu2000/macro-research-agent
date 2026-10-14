from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CodeWorkspaceError(ValueError):
    pass


class CodeArtifactRecord(BaseModel):
    id: str
    session_id: str
    bundle_id: str
    language: str
    filename: str
    media_type: str
    checksum: str
    specification_hash: str
    relative_path: str
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _stata_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,24}", value):
        value = "s_" + hashlib.sha256(value.encode()).hexdigest()[:18]
    return f"value{value}"


def _stata_literal(value: object) -> str:
    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.:%/(),= -]+", text):
        raise CodeWorkspaceError(f"Stata generation cannot safely quote value: {text}.")
    return f'"{text}"'


def _stata_condition(target: dict[str, Any]) -> str:
    clauses: list[str] = []
    mappings = (("indicators", "indicator_code"), ("entities", "entity_code"))
    for key, column in mappings:
        values = [str(item) for item in target.get(key) or []]
        if values:
            clauses.append(
                "(" + " | ".join(f"{column} == {_stata_literal(value)}" for value in values) + ")"
            )
    if target.get("periodStart"):
        clauses.append(f"period >= {_stata_literal(target['periodStart'])}")
    if target.get("periodEnd"):
        clauses.append(f"period <= {_stata_literal(target['periodEnd'])}")
    if target.get("frequency"):
        clauses.append(f"frequency == {_stata_literal(target['frequency'])}")
    return " & ".join(clauses) or "1"


def _stata_operation(operation: dict[str, Any], index: int) -> list[str]:
    kind = str(operation["kind"])
    if kind not in {
        "lag",
        "lead",
        "difference",
        "period_growth",
        "yoy_growth",
        "log",
        "unit_conversion",
    }:
        raise CodeWorkspaceError(f"Stata translation is not registered for {kind}.")
    condition = _stata_condition(dict(operation.get("target") or {}))
    source = f"__source_{index}"
    lines = ["sort entity_code indicator_code frequency period", f"clonevar {source} = value"]
    if kind == "unit_conversion":
        parameters = dict(operation.get("parameters") or {})
        source_unit = _stata_literal(parameters["sourceUnit"])
        target_unit = _stata_literal(parameters["targetUnit"])
        factor = float(parameters.get("factor", 1))
        unit_offset = float(parameters.get("offset", 0))
        lines.append(f"assert lower(strtrim(unit)) == lower({source_unit}) if {condition}")
        lines.append(f"replace value = {source} * {factor} + {unit_offset} if {condition}")
        lines.append(f"replace unit = {target_unit} if {condition}")
    elif kind == "log":
        lines.append(f"replace value = ln({source}) if {condition}")
    elif kind == "yoy_growth":
        shifts = (("annual", 1), ("quarterly", 4), ("monthly", 12))
        for frequency, periods in shifts:
            lines.append(
                "by entity_code indicator_code frequency: replace value = "
                f"({source} / {source}[_n-{periods}] - 1) * 100 "
                f'if ({condition}) & frequency == "{frequency}"'
            )
    else:
        periods = int((operation.get("parameters") or {}).get("periods", 1))
        offset = f"_n+{periods}" if kind == "lead" else f"_n-{periods}"
        if kind in {"lag", "lead"}:
            expression = f"{source}[{offset}]"
        elif kind == "difference":
            expression = f"{source} - {source}[{offset}]"
        else:
            expression = f"({source} / {source}[{offset}] - 1) * 100"
        lines.append(
            f"by entity_code indicator_code frequency: replace value = {expression} if {condition}"
        )
        if kind == "difference" and (operation.get("parameters") or {}).get("outputUnit"):
            output_unit = _stata_literal((operation.get("parameters") or {})["outputUnit"])
            lines.append(f"replace unit = {output_unit} if {condition}")
    lines.append(f"drop {source}")
    return lines


def _stata_model(job: dict[str, Any], ref_name: str, index: int) -> list[str]:
    kind = str(job["kind"])
    if kind == "var":
        raise CodeWorkspaceError(
            "Stata VAR/IRF generation is not yet registered because panel/time declaration, "
            "shock ordering and IRF persistence require an explicit reviewed mapping."
        )
    if kind in {"arima", "sarimax"}:
        raise CodeWorkspaceError(
            "Stata ARIMA/SARIMAX generation is not yet registered because panel/time declaration "
            "and future-exogenous-data semantics require an explicit reviewed mapping."
        )
    if kind == "adf":
        raise CodeWorkspaceError(
            "Stata ADF generation is not yet registered because panel/time declaration "
            "semantics require an explicit reviewed mapping."
        )
    parameters = dict(job.get("parameters") or {})
    if kind == "ols" and parameters.get("covariance", "nonrobust") == "HAC":
        raise CodeWorkspaceError(
            "Stata HAC is unavailable because the reviewed runtime blocks kernels "
            "by entity/frequency."
        )
    variables = list(job.get("variables") or [])
    if kind == "ols":
        variables = [*job.get("dependentVariables", []), *job.get("independentVariables", [])]
    if kind == "descriptive" and not variables:
        raise CodeWorkspaceError(
            "Stata descriptive generation requires explicit indicator selection."
        )
    names = [_stata_name(str(value)) for value in variables]
    lines = [
        f"use `{ref_name}', clear",
        "keep if "
        + " | ".join(f"indicator_code == {_stata_literal(variable)}" for variable in variables),
    ]
    if job.get("entityCodes"):
        lines.append(
            "keep if "
            + " | ".join(f"entity_code == {_stata_literal(code)}" for code in job["entityCodes"])
        )
    if job.get("sampleWindow"):
        window = job["sampleWindow"]
        lines.append(f"keep if period >= {_stata_literal(window['start'])}")
        if window["end"] != "latest":
            lines.append(f"keep if period <= {_stata_literal(window['end'])}")
    for variable in variables:
        safe_code = _stata_name(str(variable))[5:]
        if safe_code != variable:
            lines.append(
                f"replace indicator_code = {_stata_literal(safe_code)} "
                f"if indicator_code == {_stata_literal(variable)}"
            )
    lines.append("reshape wide value, i(entity_code frequency period) j(indicator_code) string")
    rowmiss = f"__rowmiss_{index}"
    lines.extend(
        [
            f"egen {rowmiss} = rowmiss({' '.join(names)})",
            f"keep if {rowmiss} == 0",
            f"drop {rowmiss}",
        ]
    )
    if kind == "descriptive":
        lines.append(f"summarize {' '.join(names)}, detail")
    elif kind == "correlation":
        lines.append(f"correlate {' '.join(names)}")
    else:
        dependent = _stata_name(str(job["dependentVariables"][0]))
        independent = " ".join(_stata_name(str(value)) for value in job["independentVariables"])
        covariance = parameters.get("covariance", "nonrobust")
        suffix = ", vce(robust)" if covariance == "HC1" else ""
        lines.append(f"regress {dependent} {independent}{suffix}")
    return lines


class CodeWorkspaceManager:
    def __init__(self, database_path: Path, workflow_root: Path) -> None:
        self.database_path = database_path
        self.workflow_root = workflow_root
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_code_artifacts (
                    session_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, artifact_id),
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
    def specification(
        operations: list[dict[str, Any]],
        models: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reviewed_operations = [
            {
                "id": item["id"],
                "kind": item["kind"],
                "enabled": item.get("enabled", True),
                "target": item.get("target") or {},
                "parameters": item.get("parameters") or {},
                "inputRef": item["inputRef"],
                "outputRef": item["outputRef"],
            }
            for item in operations
        ]
        reviewed_models = [
            {
                "id": item["id"],
                "kind": item["kind"],
                "inputRef": item["inputRef"],
                "variables": item.get("variables") or [],
                "dependentVariables": item.get("dependentVariables") or [],
                "independentVariables": item.get("independentVariables") or [],
                "parameters": item.get("parameters") or {},
                **({"sampleWindow": item["sampleWindow"]} if item.get("sampleWindow") else {}),
                **({"entityCodes": item["entityCodes"]} if item.get("entityCodes") else {}),
                **(
                    {"validationStart": item["validationStart"]}
                    if item.get("validationStart")
                    else {}
                ),
            }
            for item in models
        ]
        enabled = [item for item in reviewed_operations if item.get("enabled", True)]
        return {
            "schemaVersion": "mra-reproduction-v1",
            "operations": reviewed_operations,
            "models": reviewed_models,
            "finalOutputRef": enabled[-1]["outputRef"] if enabled else "active_dataset",
        }

    @staticmethod
    def python_source(specification: dict[str, Any], specification_hash: str) -> str:
        payload = json.dumps(specification, ensure_ascii=False, indent=2, sort_keys=True)
        return f'''#!/usr/bin/env python3
"""Generated by Macro Research Agent from reviewed typed specifications.

Specification: {specification_hash}
This file does not execute arbitrary model-generated code.
"""
from __future__ import annotations

import argparse
import json

from macro_research_agent.reproduction.runtime import run_reviewed_analysis

SPECIFICATION = json.loads({payload!r})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Canonical CSV, Parquet, or XLSX workbook")
    parser.add_argument("output_directory", help="Directory for reproduced results")
    args = parser.parse_args()
    run_reviewed_analysis(args.input, args.output_directory, SPECIFICATION)


if __name__ == "__main__":
    main()
'''

    @staticmethod
    def stata_source(specification: dict[str, Any], specification_hash: str) -> str:
        lines = [
            "* Generated by Macro Research Agent from reviewed typed specifications.",
            f"* Specification: {specification_hash}",
            "version 18",
            "clear all",
            "set more off",
            "args input_path output_directory",
            'import delimited using "`input_path\'", clear varnames(1) stringcols(_all)',
            "destring value, replace force",
            "tempfile active_dataset",
            "save `active_dataset', replace",
        ]
        ref_names = {"active_dataset": "active_dataset"}
        for index, operation in enumerate(specification["operations"], start=1):
            input_name = ref_names[str(operation["inputRef"])]
            output_name = f"step_{index}"
            lines.extend([f"use `{input_name}', clear"])
            if operation.get("enabled", True):
                lines.extend(_stata_operation(operation, index))
            lines.extend([f"tempfile {output_name}", f"save `{output_name}', replace"])
            ref_names[str(operation["outputRef"])] = output_name
        final_name = ref_names[str(specification["finalOutputRef"])]
        lines.extend(
            [
                f"use `{final_name}', clear",
                'save "`output_directory\'/analytical_data.dta", replace',
                "capture log close _all",
                'log using "`output_directory\'/model_results.log", replace text',
            ]
        )
        for index, job in enumerate(specification["models"], start=1):
            ref_name = ref_names[str(job["inputRef"])]
            lines.extend(_stata_model(job, ref_name, index))
        lines.extend(["log close", "exit, clear", ""])
        return "\n".join(lines)

    def _record(
        self,
        session_id: str,
        bundle_id: str,
        language: str,
        suffix: str,
        media_type: str,
        source: str,
        specification_hash: str,
        warnings: list[str] | None = None,
    ) -> CodeArtifactRecord:
        artifact_id = f"code-{uuid4().hex}"
        filename = f"reproduce_research.{suffix}"
        relative_path = f"sessions/{session_id}/code/{artifact_id}/{filename}"
        path = self.workflow_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return CodeArtifactRecord(
            id=artifact_id,
            session_id=session_id,
            bundle_id=bundle_id,
            language=language,
            filename=filename,
            media_type=media_type,
            checksum=_hash_text(source),
            specification_hash=specification_hash,
            relative_path=relative_path,
            warnings=warnings or [],
            created_at=datetime.now(timezone.utc),
        )

    def generate(
        self,
        session_id: str,
        bundle_id: str,
        operations: list[dict[str, Any]],
        models: list[dict[str, Any]],
    ) -> tuple[list[CodeArtifactRecord], list[str]]:
        specification = self.specification(operations, models)
        specification_hash = _hash_text(_canonical(specification))
        artifacts = [
            self._record(
                session_id,
                bundle_id,
                "python",
                "py",
                "text/x-python",
                self.python_source(specification, specification_hash),
                specification_hash,
            )
        ]
        warnings: list[str] = []
        try:
            stata = self.stata_source(specification, specification_hash)
        except CodeWorkspaceError as error:
            warnings.append(str(error))
        else:
            artifacts.append(
                self._record(
                    session_id,
                    bundle_id,
                    "stata",
                    "do",
                    "text/plain",
                    stata,
                    specification_hash,
                )
            )
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO workflow_code_artifacts(session_id, artifact_id, record_json)
                VALUES (?, ?, ?)
                """,
                [(session_id, artifact.id, artifact.model_dump_json()) for artifact in artifacts],
            )
        return artifacts, warnings

    def get(self, session_id: str, artifact_id: str) -> tuple[CodeArtifactRecord, Path]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT record_json FROM workflow_code_artifacts
                WHERE session_id = ? AND artifact_id = ?
                """,
                (session_id, artifact_id),
            ).fetchone()
        if row is None:
            raise CodeWorkspaceError("Code artifact was not found for this Workflow session.")
        record = CodeArtifactRecord.model_validate_json(row["record_json"])
        path = self.workflow_root / record.relative_path
        if not path.is_file() or _hash_text(path.read_text(encoding="utf-8")) != record.checksum:
            raise CodeWorkspaceError("Code artifact file is missing or failed checksum validation.")
        return record, path

    def content(self, session_id: str, artifact_id: str) -> dict[str, Any]:
        record, path = self.get(session_id, artifact_id)
        return {
            **record.model_dump(mode="json"),
            "content": path.read_text(encoding="utf-8"),
        }
