from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.workflow.data_workspace import CANONICAL_COLUMNS
from macro_research_agent.workflow.model_workspace import evaluate_typed_model_frame
from macro_research_agent.workflow.pipeline_workspace import execute_typed_pipeline_frame


class ReproductionError(ValueError):
    pass


def _read_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, sheet_name="Data")
    else:
        raise ReproductionError("Input must be canonical CSV, Parquet or XLSX Data sheet.")
    missing = set(CANONICAL_COLUMNS) - set(frame.columns)
    if missing:
        raise ReproductionError("Input is missing canonical columns: " + ", ".join(sorted(missing)))
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def run_reviewed_analysis(
    input_path: str | Path,
    output_directory: str | Path,
    specification: dict[str, Any],
) -> dict[str, Any]:
    """Run the exact reviewed typed specifications and write deterministic outputs."""
    source = Path(input_path)
    output_root = Path(output_directory)
    output_root.mkdir(parents=True, exist_ok=True)
    source_frame = _read_frame(source)
    if specification.get("statisticalCleaning"):
        from macro_research_agent.research_core.cleaning import clean_statistical_frame

        policy = specification["statisticalCleaning"]
        source_frame, _ = clean_statistical_frame(
            source_frame,
            policy["strategy"],
            policy.get("validation_start"),
            required_indicators=set(policy["required_indicators"])
            if policy.get("required_indicators") is not None
            else None,
        )
    refs = execute_typed_pipeline_frame(source_frame, specification["operations"])
    final_ref = str(specification["finalOutputRef"])
    final_frame = refs[final_ref]
    final_path = output_root / "analytical_data.parquet"
    final_frame.to_parquet(final_path, index=False)
    model_results: list[dict[str, Any]] = []
    for job in specification["models"]:
        input_ref = str(job["inputRef"])
        result, sample, warnings = evaluate_typed_model_frame(refs[input_ref], job)
        model_results.append(
            {
                "jobId": job["id"],
                "kind": job["kind"],
                "inputRef": input_ref,
                "sample": sample,
                "result": result,
                "warnings": warnings,
            }
        )
    model_path = output_root / "model_results.json"
    model_path.write_text(
        json.dumps(model_results, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "analyticalData": str(final_path),
        "modelResults": str(model_path),
        "operationCount": len(
            [item for item in specification["operations"] if item.get("enabled", True)]
        ),
        "modelCount": len(model_results),
    }
