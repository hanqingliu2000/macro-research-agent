import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from macro_research_agent.knowledge.data_sources import default_data_source_knowledge
from macro_research_agent.knowledge.source_index import (
    ProviderSourceSnapshot,
    SourceCodelist,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
    SourceIndexRepository,
    seed_source_index,
)


def complete_weo_snapshot() -> ProviderSourceSnapshot:
    return ProviderSourceSnapshot(
        provider_id="imf_data",
        provider_name="International Monetary Fund",
        catalog_url="https://data.imf.org/",
        snapshot_version="2026-09",
        retrieved_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        coverage_status="complete",
        source_sha256="sha256:metadata",
        attributes={"dataflow_total": 1},
        dimensions=[
            SourceDimension(
                dimension_id="topic",
                label="Topic",
                role="classification",
                values=[
                    SourceDimensionValue(code="fiscal", label="Fiscal policy"),
                ],
            )
        ],
        datasets=[
            SourceDataset(
                dataset_id="WEO",
                agency_id="IMF",
                version="latest",
                title="World Economic Outlook",
                description="Macroeconomic estimates and projections",
                executable=True,
                coverage_status="complete",
                dimensions=[
                    SourceDimension(
                        dimension_id="INDICATOR",
                        label="Indicator",
                        role="indicator",
                        key_position=1,
                        values=[
                            SourceDimensionValue(
                                code="GGXWDG_NGDP",
                                label="Gross debt, General government, Percent of GDP",
                            )
                        ],
                    ),
                    SourceDimension(
                        dimension_id="COUNTRY",
                        label="Country",
                        role="geography",
                        key_position=0,
                        values=[
                            SourceDimensionValue(code="CHN", label="China", is_aggregate=False),
                            SourceDimensionValue(
                                code="WEO001", label="World", is_aggregate=True
                            ),
                        ],
                    ),
                    SourceDimension(
                        dimension_id="FREQUENCY",
                        label="Frequency",
                        role="frequency",
                        key_position=2,
                        values=[SourceDimensionValue(code="A", label="Annual")],
                    ),
                ],
            )
        ],
    )


def test_index_searches_across_dataset_and_separate_dimensions() -> None:
    repository = SourceIndexRepository(":memory:")
    repository.replace_provider(complete_weo_snapshot())

    matches = repository.search("China general government debt")

    assert len(matches) == 1
    assert matches[0].dataset_id == "WEO"
    assert {item["code"] for item in matches[0].matched_values} == {
        "CHN",
        "GGXWDG_NGDP",
    }
    assert {item["role"] for item in matches[0].dimensions} == {
        "indicator",
        "geography",
        "frequency",
        "classification",
    }
    assert next(
        item for item in matches[0].matched_values if item["code"] == "CHN"
    )["is_aggregate"] == 0


def test_provider_replacement_is_atomic_and_preserves_last_known_good() -> None:
    repository = SourceIndexRepository(":memory:")
    repository.replace_provider(complete_weo_snapshot())
    replacement = complete_weo_snapshot().model_copy(
        update={"datasets": [], "coverage_status": "partial", "snapshot_version": "next"}
    )
    with pytest.raises(ValueError, match="last-known-good"):
        repository.replace_provider(replacement)

    assert repository.search("government debt")[0].dataset_id == "WEO"
    assert repository.provider_summaries()[0]["dataset_count"] == 1
    assert repository.provider_summaries()[0]["attributes"] == {"dataflow_total": 1}


def test_provider_dimension_values_are_paginated_and_searchable() -> None:
    repository = SourceIndexRepository(":memory:")
    repository.replace_provider(complete_weo_snapshot())

    page = repository.provider_dimension_values("imf_data", "topic", query="fiscal")
    match = repository.search("fiscal government debt")[0]

    assert page["total"] == 1
    assert page["values"][0]["code"] == "fiscal"
    assert next(item for item in match.matched_values if item["code"] == "fiscal")[
        "scope"
    ] == "provider"


def test_shared_codelists_are_stored_once_and_resolved_by_dataset_dimension() -> None:
    repository = SourceIndexRepository(":memory:")
    base = complete_weo_snapshot()
    linked = base.model_copy(
        update={
            "datasets": [
                base.datasets[0].model_copy(
                    update={
                        "dimensions": [
                            SourceDimension(
                                dimension_id="COUNTRY",
                                label="Country",
                                role="geography",
                                key_position=0,
                                codelist_agency_id="IMF",
                                codelist_id="CL_COUNTRY",
                                codelist_version="1.0",
                            )
                        ]
                    }
                )
            ]
        }
    )
    codelist = SourceCodelist(
        agency_id="IMF",
        codelist_id="CL_COUNTRY",
        version="1.0",
        label="Country",
        values=[
            SourceDimensionValue(code="CHN", label="China", is_aggregate=False),
            SourceDimensionValue(code="W00", label="World", is_aggregate=True),
        ],
    )

    repository.replace_provider_with_codelists(linked, [codelist])

    page = repository.dimension_values("imf_data", "WEO", "COUNTRY", query="China")
    match = repository.search("China WEO")[0]
    assert page["total"] == 1
    assert page["values"][0]["code"] == "CHN"
    assert match.matched_values[0]["scope"] == "codelist"
    assert repository.provider_summaries()[0]["dimension_value_count"] == 3


def test_missing_shared_codelist_rolls_back_provider_replacement() -> None:
    repository = SourceIndexRepository(":memory:")
    repository.replace_provider(complete_weo_snapshot())
    base = complete_weo_snapshot()
    linked = base.model_copy(
        update={
            "snapshot_version": "next",
            "datasets": [
                base.datasets[0].model_copy(
                    update={
                        "dimensions": [
                            SourceDimension(
                                dimension_id="COUNTRY",
                                label="Country",
                                role="geography",
                                codelist_agency_id="IMF",
                                codelist_id="MISSING",
                                codelist_version="1.0",
                            )
                        ]
                    }
                )
            ],
        }
    )

    with pytest.raises(ValueError, match="missing provider codelist"):
        repository.replace_provider_with_codelists(linked, [])

    assert repository.provider_summaries()[0]["snapshot_version"] == "2026-09"


def test_seed_catalog_is_explicitly_incomplete_and_never_overwrites_harvest() -> None:
    repository = SourceIndexRepository(":memory:")
    catalog = default_data_source_knowledge()
    seed_source_index(repository, catalog)
    summaries = repository.provider_summaries()

    assert {item["provider_id"] for item in summaries} == {
        "adb",
        "bis",
        "ecb",
        "eurostat",
        "imf_data",
        "oecd",
        "un_sdg",
        "world_bank",
    }
    assert {item["coverage_status"] for item in summaries} == {"seed"}
    assert repository.search("government debt")[0].dataset_id == "WEO"

    repository.replace_provider(complete_weo_snapshot())
    seed_source_index(repository, catalog)
    imf = next(
        item
        for item in repository.provider_summaries()
        if item["provider_id"] == "imf_data"
    )
    assert imf["coverage_status"] == "complete"
    assert imf["snapshot_version"] == "2026-09"


def test_complete_snapshot_rejects_incomplete_dataset() -> None:
    snapshot = complete_weo_snapshot().model_dump()
    snapshot["datasets"][0]["coverage_status"] = "partial"
    with pytest.raises(ValueError, match="complete provider snapshot"):
        ProviderSourceSnapshot.model_validate(snapshot)


def test_search_ranks_a_relevant_executable_dataset_before_a_generic_archive() -> None:
    repository = SourceIndexRepository(":memory:")
    snapshot = complete_weo_snapshot()
    archive = snapshot.datasets[0].model_copy(
        update={
            "dataset_id": "AAA_ARCHIVE",
            "title": "Government archive",
            "executable": False,
        }
    )
    repository.replace_provider(
        snapshot.model_copy(update={"datasets": [archive, snapshot.datasets[0]]})
    )

    matches = repository.search("China general government gross debt")

    assert matches[0].dataset_id == "WEO"
    assert matches[0].score > matches[1].score


def test_schema_upgrade_adds_shared_codelist_columns_before_lookup_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source-index.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE source_dimensions (
            provider_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            dimension_id TEXT NOT NULL,
            label TEXT NOT NULL,
            role TEXT NOT NULL,
            key_position INTEGER,
            PRIMARY KEY (provider_id, dataset_id, dimension_id)
        )
        """
    )
    connection.commit()
    connection.close()

    repository = SourceIndexRepository(database)

    columns = {
        str(item[1])
        for item in repository.connection.execute("PRAGMA table_info(source_dimensions)")
    }
    indexes = {
        str(item[1])
        for item in repository.connection.execute("PRAGMA index_list(source_dimensions)")
    }
    assert {"component_kind", "codelist_agency_id", "codelist_id", "codelist_version"} <= columns
    assert "source_dimensions_codelist_lookup" in indexes
