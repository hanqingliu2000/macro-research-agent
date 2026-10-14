from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from macro_research_agent.knowledge.planning_source_index import (
    PlanningSourceIndex,
    PlanningSourceIndexBuilder,
    default_planning_source_index,
)
from macro_research_agent.knowledge.source_index import (
    ProviderSourceSnapshot,
    SourceCodelist,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
    SourceIndexRepository,
)


def test_lite_index_content_deduplicates_provider_indicator_sets(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    output_path = tmp_path / "lite.sqlite3"
    repository = SourceIndexRepository(source_path)
    values = [
        SourceDimensionValue(
            code="GGXWDG_NGDP",
            label="Gross debt, General government, Percent of GDP",
        ),
        SourceDimensionValue(code="PCPI", label="Consumer price index"),
    ]
    snapshot = ProviderSourceSnapshot(
        provider_id="imf_data",
        provider_name="International Monetary Fund",
        catalog_url="https://data.imf.org/",
        snapshot_version="test",
        retrieved_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        coverage_status="complete",
        source_sha256="a" * 64,
        datasets=[
            SourceDataset(
                dataset_id="WEO",
                title="World Economic Outlook",
                description=(
                    "DescriptionOnlySentinel contact catalog-contact@example.invalid "
                    "<p>Long-form provider prose is not planning identity.</p>"
                ),
                executable=True,
                coverage_status="complete",
                dimensions=[
                    SourceDimension(
                        dimension_id="INDICATOR",
                        label="Indicator",
                        role="indicator",
                        codelist_agency_id="IMF",
                        codelist_id="CL_WEO_INDICATOR",
                        codelist_version="1",
                    )
                ],
            ),
            SourceDataset(
                dataset_id="WEO_ARCHIVE",
                title="World Economic Outlook archive",
                executable=False,
                coverage_status="complete",
                dimensions=[
                    SourceDimension(
                        dimension_id="INDICATOR",
                        label="Indicator",
                        role="indicator",
                        codelist_agency_id="IMF",
                        codelist_id="CL_WEO_ARCHIVE_INDICATOR",
                        codelist_version="1",
                    )
                ],
            ),
        ],
    )
    repository.replace_provider_with_codelists(
        snapshot,
        [
            SourceCodelist(
                agency_id="IMF",
                codelist_id="CL_WEO_INDICATOR",
                version="1",
                label="WEO indicators",
                values=values,
            ),
            SourceCodelist(
                agency_id="IMF",
                codelist_id="CL_WEO_ARCHIVE_INDICATOR",
                version="1",
                label="WEO archive indicators",
                values=values,
            ),
        ],
    )
    repository.close()

    summary = PlanningSourceIndexBuilder().build(source_path, output_path)
    connection = sqlite3.connect(output_path)
    set_total = connection.execute("SELECT COUNT(*) FROM indicator_sets").fetchone()[0]
    link_total = connection.execute(
        "SELECT COUNT(*) FROM dataset_indicator_sets"
    ).fetchone()[0]
    assert connection.execute(
        "SELECT COUNT(*) FROM datasets WHERE description IS NOT NULL"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM dataset_fts WHERE dataset_fts MATCH ?",
        ('"DescriptionOnlySentinel"',),
    ).fetchone()[0] == 0
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    assert metadata["projection_policy_version"] == "facts-only-v1"
    assert metadata["catalog_version"] == (
        f"source-index-lite-v1:facts-only-v1:{summary['snapshot_digest'][:12]}"
    )
    assert connection.execute(
        "SELECT snapshot_version, source_sha256 FROM providers"
    ).fetchone() == ("test", "a" * 64)
    connection.close()
    generated_bytes = output_path.read_bytes()
    assert b"DescriptionOnlySentinel" not in generated_bytes
    assert b"catalog-contact@example.invalid" not in generated_bytes
    assert b"Long-form provider prose" not in generated_bytes
    index = PlanningSourceIndex(output_path)
    matches = index.for_planning(
        "China general government gross debt", ["imf_data"]
    )

    assert summary["indicator_concept_total"] == 2
    assert set_total == 1
    assert link_total == 2
    assert matches[0]["dataset"] == "WEO"
    assert matches[0]["matched_indicators"][0]["code"] == "GGXWDG_NGDP"
    assert index.for_planning("DescriptionOnlySentinel", ["imf_data"]) == []
    index.close()


def test_committed_lite_index_is_bounded_and_contains_all_providers() -> None:
    index = default_planning_source_index()
    metadata = {
        str(item[0]): str(item[1])
        for item in index.connection.execute("SELECT key, value FROM metadata")
    }
    matches = index.for_planning(
        "Investigate China's inflation in the last 36 months and project 6 months",
        ["imf_data", "world_bank", "oecd", "eurostat", "adb", "ecb", "bis", "un_sdg"],
    )
    payload = json.dumps(matches, ensure_ascii=False, separators=(",", ":"))

    assert metadata["provider_total"] == "8"
    assert metadata["dataset_total"] == "10832"
    assert metadata["indicator_concept_total"] == "50758"
    assert metadata["indicator_set_total"] == "1297"
    assert metadata["dataset_indicator_set_total"] == "3257"
    assert metadata["projection_policy_version"] == "facts-only-v1"
    assert index.connection.execute(
        "SELECT COUNT(*) FROM datasets WHERE description IS NOT NULL"
    ).fetchone()[0] == 0
    assert index.path.stat().st_size < 30 * 1024 * 1024
    assert len(matches) <= 8
    assert len(payload) < 10_000
    assert matches[0]["executable"] is True
    assert matches[0]["matched_indicators"]


def test_expenditure_side_growth_intent_surfaces_executable_wdi_concepts() -> None:
    index = default_planning_source_index()
    query = """I want to understand whether China's growth model is really shifting from
    investment toward household consumption, and whether the pandemic changed that trend.
    China only. Expenditure-side GDP decomposition. Both level shares and growth contributions.
    Pre/post-2020 descriptive split. Annual data from 2000. No forecast."""

    matches = index.for_planning(
        query,
        ["imf_data", "world_bank", "oecd", "eurostat", "adb", "ecb", "bis", "un_sdg"],
    )
    wdi = next(
        item
        for item in matches
        if item["connector_id"] == "world_bank" and item["dataset"] == "2"
    )

    assert wdi["executable"] is True
    assert {
        "NY.GDP.MKTP.KD.ZG",
        "NE.GDI.TOTL.ZS",
        "NE.CON.PRVT.ZS",
    } <= {item["code"] for item in wdi["matched_indicators"]}
    assert len(wdi["matched_indicators"]) <= 5
    assert len(json.dumps(matches, ensure_ascii=False)) < 10_000
