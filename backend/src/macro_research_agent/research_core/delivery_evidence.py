"""Read-only, hash-bound calculation receipts, not an AI reviewer or approval."""

from __future__ import annotations

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.research_core.numerics import chart_frame, svg_chart
from macro_research_agent.workflow.output_review import ChartSpec


def digest(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
    )


def chart_geometry_receipt(
    *,
    artifact_id: str,
    artifact_hash: str,
    dataset_hash: str,
    specification: dict[str, Any],
    svg: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare current SVG with the registered rendering selection and exact tick math.

    Do not accept SVG metadata as its own authority. Rebuild the expected selection from
    authorized rows and the typed spec, then compare metadata, tick labels and data marks.
    Receipt failure/unverifiability never becomes a fabricated successful inspection.
    """
    binding = {
        "artifactId": artifact_id,
        "artifactHash": artifact_hash,
        "datasetHash": dataset_hash,
        "specificationHash": digest(specification),
    }
    checks: list[dict[str, Any]] = []
    ticks: list[dict[str, Any]] = []

    def add(rule: str, status: str, **facts: Any) -> None:
        checks.append({"checkId": f"{artifact_id}:{rule}", "rule": rule, "status": status, **facts})

    try:
        if "sha256:" + hashlib.sha256(svg.encode()).hexdigest() != artifact_hash:
            raise ValueError("artifact_hash_mismatch")
        if len(svg) > 500_000 or len(rows) > 2000 or "<!DOCTYPE" in svg.upper():
            raise ValueError("inspection_input_outside_budget")
        spec = ChartSpec.model_validate(specification)
        if spec.data_hash != dataset_hash:
            raise ValueError("dataset_binding_mismatch")
        frame = chart_frame(pd.DataFrame(rows), spec.indicator_code, spec.source_unit)
        if frame.empty or set(spec.y_fields) - set(frame.columns):
            raise ValueError("selection_unverifiable")
        frame = frame[["period", *spec.y_fields]]
        expected = ET.fromstring(svg_chart(frame, spec))
        actual = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}

        def metadata(root: ET.Element) -> dict[str, Any]:
            element = root.find('s:metadata[@id="coordinate-system"]', ns)
            if element is None or not element.text:
                raise ValueError("coordinate_metadata_missing")
            return dict(json.loads(element.text))

        authoritative = metadata(expected)
        observed = metadata(actual)
        add(
            "coordinate_metadata",
            "pass" if authoritative == observed else "fail",
            expected=authoritative,
            observed=observed,
        )

        def axis_ticks(root: ET.Element) -> list[ET.Element]:
            return [
                e
                for e in root.findall("s:text", ns)
                if e.get("text-anchor") == "end" and e.get("x") == str(authoritative["left"] - 8)
            ]

        wanted, rendered = axis_ticks(expected), axis_ticks(actual)
        valid = len(wanted) == len(rendered) == 5
        for index, tick in enumerate(rendered):
            baseline = float(tick.attrib["y"])
            gridline = baseline - authoritative["tick_text_baseline_offset"]
            value = authoritative["maximum"] - (
                (gridline - authoritative["top"])
                / authoritative["plot_height"]
                * (authoritative["maximum"] - authoritative["minimum"])
            )
            matched = (
                index < len(wanted)
                and tick.text == wanted[index].text
                and math.isclose(baseline, float(wanted[index].attrib["y"]), abs_tol=0.11)
            )
            valid = valid and matched
            ticks.append(
                {
                    "textBaselineY": baseline,
                    "gridlineY": gridline,
                    "expectedValue": value,
                    "renderedLabel": tick.text,
                    "matches": matched,
                }
            )
        add(
            "axis_ticks",
            "pass" if valid else "fail",
            ticks=ticks,
            formula="maximum - (gridlineY - top) / plot_height * (maximum - minimum)",
        )

        def marks(root: ET.Element) -> list[tuple[str, dict[str, str]]]:
            return [
                (e.tag, dict(e.attrib))
                for e in root.iter()
                if e.tag.endswith(("}polyline", "}circle", "}rect"))
            ]

        add(
            "series_coordinates",
            "pass" if marks(actual) == marks(expected) else "fail",
            expectedMarkCount=len(marks(expected)),
            observedMarkCount=len(marks(actual)),
        )
    except (ValueError, KeyError, TypeError, ET.ParseError) as error:
        add("inspection_unverifiable", "unverifiable", reason=str(error))
    receipt = {
        "schemaVersion": "chart-geometry-receipt-v1",
        **binding,
        "checks": checks,
        "approval": False,
        "scope": "numeric SVG structure only; not pixel/semantic review",
    }
    return {**receipt, "receiptHash": digest(receipt)}


def report_result_facts(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project existing typed results, not new comparisons/tests inferred from prose."""
    return [
        {
            "resultRef": r["id"],
            "recordHash": digest(r),
            "kind": r.get("kind"),
            "entity": r.get("entity"),
            "window": r.get("window"),
            "sample": r.get("sample"),
            "perVariableStatistics": r.get("result", {}).get("statistics", []),
            "observedSeriesRef": {"resultRef": r["id"], "path": "$.result.observedSeries"},
            "endpointComparisons": r.get("result", {}).get("endpointComparisons", []),
            "boundary": "Use these quantities only; counts are per model/variable/window. "
            "Endpoint comparisons use two boundary observations, not the phase sample.",
        }
        for r in results
    ]
