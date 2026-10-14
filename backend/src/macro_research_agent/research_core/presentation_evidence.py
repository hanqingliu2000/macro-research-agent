"""Owned presentation evidence for report roles, never an approval or data mutation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PresentationEvidenceError(Exception):
    code = "presentation_handoff_incomplete"


PRESENTATION_PREREQUISITE_RULES = {
    "PKG-HASH-001",
    "SPEC-BINDING-001",
    "REPORT-METADATA-001",
    "REPORT-CONTENT-001",
}


def specification_hash(value: dict[str, Any]) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def is_presentation_artifact(artifact: dict[str, Any]) -> bool:
    return (
        artifact.get("format") in {"svg", "csv", "xlsx"}
        and artifact.get("kind") != "reproduction_source"
    )


class PresentationEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal["presentation-evidence-v1"] = Field(
        default="presentation-evidence-v1", alias="schemaVersion"
    )
    artifact_id: str = Field(alias="artifactId", min_length=1)
    artifact_hash: str = Field(alias="artifactHash", min_length=1)
    specification_hash: str = Field(alias="specificationHash", min_length=1)
    data_hash: str = Field(alias="dataHash", min_length=1)
    format: Literal["svg", "csv", "xlsx"]
    specification: dict[str, Any]
    inspection_scope: Literal[
        "svg_content_and_specification",
        "csv_header_and_specification",
        "file_hash_and_specification",
    ] = Field(alias="inspectionScope")
    svg_content: str | None = Field(default=None, alias="svgContent", max_length=64000)
    csv_columns: list[str] | None = Field(default=None, alias="csvColumns")

    @model_validator(mode="after")
    def bindings(self) -> PresentationEvidenceV1:
        from macro_research_agent.workflow.output_review import ChartSpec, TableSpec

        (ChartSpec if self.format == "svg" else TableSpec).model_validate(self.specification)
        if specification_hash(self.specification) != self.specification_hash:
            raise ValueError("Presentation specification hash mismatch.")
        if self.specification.get("data_hash") != self.data_hash:
            raise ValueError("Presentation dataset hash mismatch.")
        if self.format == "svg":
            if self.svg_content is None or (
                "sha256:" + hashlib.sha256(self.svg_content.encode()).hexdigest()
                != self.artifact_hash
            ):
                raise ValueError("Presentation SVG content hash mismatch.")
            if self.inspection_scope != "svg_content_and_specification":
                raise ValueError("SVG inspection scope mismatch.")
        elif self.format == "csv":
            if self.csv_columns != self.specification.get("columns") or (
                self.inspection_scope != "csv_header_and_specification"
            ):
                raise ValueError("CSV header/specification inspection mismatch.")
        elif self.inspection_scope != "file_hash_and_specification":
            raise ValueError("Workbook inspection scope mismatch.")
        return self


def validate_presentation_coverage(
    artifacts: list[dict[str, Any]], evidence: list[PresentationEvidenceV1]
) -> None:
    selected = {str(a["id"]): a for a in artifacts if is_presentation_artifact(a)}
    if len(evidence) != len(selected) or {e.artifact_id for e in evidence} != set(selected):
        raise PresentationEvidenceError("Current chart/table inspection evidence is incomplete.")
    for item in evidence:
        # Recheck mutable nested specs/model_copy values at the provider boundary.
        try:
            PresentationEvidenceV1.model_validate(item.model_dump(mode="json", by_alias=True))
        except ValueError as error:
            raise PresentationEvidenceError(
                "Presentation inspection evidence was altered."
            ) from error
        current = selected[item.artifact_id]
        if item.artifact_hash != current.get("hash") or item.format != current.get("format"):
            raise PresentationEvidenceError("Presentation evidence targets an obsolete artifact.")


def build_presentation_evidence(
    artifacts: list[dict[str, Any]],
    specifications: dict[str, dict[str, Any]],
    read_owned: Callable[[str, str], bytes],
) -> list[PresentationEvidenceV1]:
    # Imported on invocation to avoid a reporting/output-spec model import cycle.
    from macro_research_agent.workflow.output_review import ChartSpec, TableSpec

    selected = [a for a in artifacts if is_presentation_artifact(a)]
    if len(selected) > 24 or len({a["id"] for a in selected}) != len(selected):
        raise PresentationEvidenceError("Presentation evidence exceeds its artifact budget.")
    result = []
    for artifact in selected:
        artifact_id, expected = str(artifact["id"]), str(artifact.get("hash") or "")
        try:
            spec = specifications[artifact_id]
            (ChartSpec if artifact["format"] == "svg" else TableSpec).model_validate(spec)
            content = read_owned(artifact_id, expected)
            if "sha256:" + hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("artifact_checksum_mismatch")
            svg, columns = None, None
            scope: Literal[
                "svg_content_and_specification",
                "csv_header_and_specification",
                "file_hash_and_specification",
            ] = "file_hash_and_specification"
            if artifact["format"] == "svg":
                if (
                    len(content) > 64000
                    or b"<!DOCTYPE" in content.upper()
                    or b"<!ENTITY" in content.upper()
                ):
                    raise ValueError("SVG exceeds inspection safety budget")
                svg = content.decode("utf-8")
                root = ET.fromstring(svg)
                if root.tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("Not a registered SVG")
                scope = "svg_content_and_specification"
            elif artifact["format"] == "csv":
                with io.TextIOWrapper(
                    io.BytesIO(content), encoding="utf-8-sig", newline=""
                ) as stream:
                    columns = next(csv.reader(stream))
                if sum(len(column) for column in columns) > 16000:
                    raise ValueError("CSV header exceeds inspection budget")
                if columns != spec["columns"]:
                    raise ValueError("CSV columns disagree with the bound specification")
                scope = "csv_header_and_specification"
            result.append(
                PresentationEvidenceV1(
                    artifactId=artifact_id,
                    artifactHash=expected,
                    specificationHash=specification_hash(spec),
                    dataHash=spec["data_hash"],
                    format=artifact["format"],
                    specification=spec,
                    inspectionScope=scope,
                    svgContent=svg,
                    csvColumns=columns,
                )
            )
        except Exception as error:
            raise PresentationEvidenceError(
                "A current chart/table artifact or specification could not be verified; "
                "repair its owned evidence before authoring or review."
            ) from error
    if len(json.dumps([e.model_dump(mode="json", by_alias=True) for e in result])) > 160000:
        raise PresentationEvidenceError("Presentation evidence exceeds its context budget.")
    validate_presentation_coverage(artifacts, result)
    return result
