from pathlib import Path

from macro_research_agent.workflow.artifact_comparison import compare_artifacts


def test_csv_comparison_reports_value_and_row_changes_without_values(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    current = tmp_path / "current.csv"
    baseline.write_text("period,value\n2023,2.0\n2024,2.5\n", encoding="utf-8")
    current.write_text("period,value\n2023,2.0\n2024,2.8\n2025,3.0\n", encoding="utf-8")

    report = compare_artifacts(
        baseline_artifact_id="artifact-old",
        current_artifact_id="artifact-new",
        baseline_format="csv",
        current_format="csv",
        baseline_hash="sha256:old",
        current_hash="sha256:new",
        baseline_path=baseline,
        current_path=current,
        baseline_specification={"title": "Results", "data_hash": "sha256:data-old"},
        current_specification={"title": "Updated results", "data_hash": "sha256:data-new"},
    )

    assert report.status == "data_changed"
    assert report.value_comparison.status == "changed"
    assert report.value_comparison.added_row_count == 2
    assert report.value_comparison.removed_row_count == 1
    assert [item.field for item in report.specification_changes] == ["data_hash", "title"]
    assert "2.8" not in report.model_dump_json()


def test_specification_data_hash_distinguishes_presentation_only_change(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.svg"
    current = tmp_path / "current.svg"
    baseline.write_text("<svg><title>Old</title></svg>", encoding="utf-8")
    current.write_text("<svg><title>New</title></svg>", encoding="utf-8")

    report = compare_artifacts(
        baseline_artifact_id="artifact-old",
        current_artifact_id="artifact-new",
        baseline_format="svg",
        current_format="svg",
        baseline_hash="sha256:old",
        current_hash="sha256:new",
        baseline_path=baseline,
        current_path=current,
        baseline_specification={"title": "Old", "data_hash": "sha256:data"},
        current_specification={"title": "New", "data_hash": "sha256:data"},
    )

    assert report.status == "presentation_changed"
    assert report.value_comparison.status == "unchanged"
    assert report.hash_changed is True
