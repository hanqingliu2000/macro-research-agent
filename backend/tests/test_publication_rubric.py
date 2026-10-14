from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
from macro_research_agent.workflow.output_review import ChartSpec, stable_hash
from macro_research_agent.workflow.output_workspace import _chart_frame, _svg_chart
from macro_research_agent.workflow.publication_guidelines import PUBLICATION_GUIDELINE
from macro_research_agent.workflow.publication_rubric import (
    ACADEMIC_VISUAL_RUBRIC,
    ACADEMIC_VISUAL_RUBRIC_HASH,
)


def test_placeholder_has_stable_identity_and_documented_rules() -> None:
    rubric = ACADEMIC_VISUAL_RUBRIC
    assert stable_hash(rubric.model_dump(mode="json")) == ACADEMIC_VISUAL_RUBRIC_HASH
    assert PUBLICATION_GUIDELINE.visual_rubric == rubric
    document = (
        Path(__file__).resolve().parents[2] / "guidelines" / f"{rubric.version}.md"
    ).read_text()
    assert all(rule.rule_id in document for rule in rubric.rules)
    assert rubric.status == "placeholder"
    assert {key for key, _ in rubric.sources} == {"NATURE", "MRA"}


def test_missing_periods_break_paths_and_source_notes_wrap_without_losing_text() -> None:
    source = "Source: " + "long provider description and vintage " * 10
    rows = pd.DataFrame(
        {
            "period": ["2020", "2021", "2022", "2023", "2024"],
            "entity_code": ["CHN"] * 5,
            "indicator_code": ["CPI"] * 5,
            "value": [1.0, 2.0, None, 4.0, 5.0],
        }
    )
    chart = _chart_frame(rows)
    assert list(chart["period"]) == list(rows["period"])
    assert pd.isna(chart.loc[2, "CHN"])
    spec = ChartSpec(
        title="Historical CPI",
        unit="Percent",
        source_note=source,
        x_field="period",
        y_fields=["CHN"],
        alt_text="China CPI with a missing 2022 value.",
        guideline_version="publication-v1",
        data_hash="sha256:test",
    )
    root = ET.fromstring(_svg_chart(chart, spec))
    ns = {"s": "http://www.w3.org/2000/svg"}
    paths = root.findall("s:polyline", ns)
    assert len(paths) == 2
    assert all(len(path.attrib["points"].split()) == 2 for path in paths)
    metadata = root.find("s:metadata", ns)
    assert metadata is not None and metadata.text
    coordinates = json.loads(metadata.text)
    points = [point for path in paths for point in path.attrib["points"].split()]
    for point, value in zip(points, [1, 2, 4, 5], strict=True):
        y = float(point.split(",")[1])
        expected = coordinates["top"] + coordinates["plot_height"] * (
            coordinates["maximum"] - value
        ) / (coordinates["maximum"] - coordinates["minimum"])
        assert abs(y - expected) <= coordinates["coordinate_rounding_pixels"]
    notes = [node for node in root.findall("s:text", ns) if node.attrib.get("font-size") == "11"]
    assert len(notes) > 1
    assert " ".join(node.text or "" for node in notes) == f"Unit: Percent · {source.strip()}"
    assert all(0 < float(node.attrib["y"]) < spec.height for node in notes)


def test_isolated_observation_has_visible_marker() -> None:
    spec = ChartSpec(
        title="One observed value",
        unit="Index",
        source_note="Source: fixture",
        x_field="period",
        y_fields=["CHN"],
        alt_text="Only 2021 is observed.",
        guideline_version="publication-v1",
        data_hash="sha256:test",
    )
    chart = pd.DataFrame({"period": ["2020", "2021", "2022"], "CHN": [None, 2, None]})
    root = ET.fromstring(_svg_chart(chart, spec))
    assert len(root.findall("{http://www.w3.org/2000/svg}circle")) == 1
    assert not root.findall("{http://www.w3.org/2000/svg}polyline")
