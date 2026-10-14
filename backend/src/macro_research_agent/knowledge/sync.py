"""Command-line entry point for rebuilding local Source Index snapshots."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from macro_research_agent.knowledge.harvest.adb import AdbCatalogHarvester
from macro_research_agent.knowledge.harvest.eurostat import EurostatCatalogHarvester
from macro_research_agent.knowledge.harvest.sdmx import (
    SDMX_PROVIDER_CONFIGS,
    SdmxCatalogHarvester,
)
from macro_research_agent.knowledge.harvest.un_sdg import UnSdgCatalogHarvester
from macro_research_agent.knowledge.harvest.world_bank import WorldBankCatalogHarvester
from macro_research_agent.knowledge.planning_source_index import PlanningSourceIndexBuilder
from macro_research_agent.knowledge.source_index import SourceIndexRepository

PROVIDER_ORDER = (
    "world_bank",
    "imf_data",
    "oecd",
    "eurostat",
    "adb",
    "ecb",
    "bis",
    "un_sdg",
)


async def sync_world_bank(database: Path, raw_dir: Path) -> None:
    harvester = WorldBankCatalogHarvester(raw_dir)
    snapshot = await harvester.harvest()
    repository = SourceIndexRepository(database)
    try:
        repository.replace_provider(snapshot)
    finally:
        repository.close()
    print(
        f"world_bank: {len(snapshot.datasets)} sources; "
        f"{harvester.manifest['indicator']['total']} indicators; "
        f"coverage={snapshot.coverage_status}; sha256={snapshot.source_sha256}"
    )


async def sync_sdmx(provider: str, database: Path, raw_dir: Path) -> None:
    result = await SdmxCatalogHarvester(SDMX_PROVIDER_CONFIGS[provider], raw_dir).harvest()
    repository = SourceIndexRepository(database)
    try:
        repository.replace_provider_with_codelists(result.snapshot, result.codelists())
    finally:
        repository.close()
    print(
        f"{provider}: {len(result.snapshot.datasets)} dataflows; "
        f"{result.snapshot.attributes['unique_codelist_total']} codelists; "
        f"coverage={result.snapshot.coverage_status}; "
        f"sha256={result.snapshot.source_sha256}"
    )


async def sync_adb(database: Path, raw_dir: Path) -> None:
    result = await AdbCatalogHarvester(raw_dir).harvest()
    repository = SourceIndexRepository(database)
    try:
        repository.replace_provider_with_codelists(result.snapshot, result.codelists)
    finally:
        repository.close()
    print(
        f"adb: {len(result.snapshot.datasets)} dataflows; "
        f"{result.snapshot.attributes['codelist_total']} codelists; "
        f"coverage={result.snapshot.coverage_status}; "
        f"sha256={result.snapshot.source_sha256}"
    )


async def sync_eurostat(database: Path, raw_dir: Path) -> None:
    result = await EurostatCatalogHarvester(raw_dir).harvest()
    repository = SourceIndexRepository(database)
    try:
        repository.replace_provider_with_codelists(result.snapshot, result.codelists())
    finally:
        repository.close()
    print(
        f"eurostat: {len(result.snapshot.datasets)} datasets; "
        f"{result.snapshot.attributes['main_metabase_relation_total']} main positions; "
        f"coverage={result.snapshot.coverage_status}; "
        f"sha256={result.snapshot.source_sha256}"
    )


async def sync_un_sdg(database: Path, raw_dir: Path) -> None:
    result = await UnSdgCatalogHarvester(raw_dir).harvest()
    repository = SourceIndexRepository(database)
    try:
        repository.replace_provider_with_codelists(result.snapshot, result.codelists)
    finally:
        repository.close()
    print(
        f"un_sdg: {len(result.snapshot.datasets)} series; "
        f"{result.snapshot.attributes['indicator_total']} indicators; "
        f"coverage={result.snapshot.coverage_status}; "
        f"sha256={result.snapshot.source_sha256}"
    )


async def sync_provider(provider: str, database: Path, raw_dir: Path) -> None:
    if provider == "world_bank":
        await sync_world_bank(database, raw_dir)
    elif provider == "adb":
        await sync_adb(database, raw_dir)
    elif provider == "eurostat":
        await sync_eurostat(database, raw_dir)
    elif provider == "un_sdg":
        await sync_un_sdg(database, raw_dir)
    else:
        await sync_sdmx(provider, database, raw_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Source Index provider metadata.")
    parser.add_argument(
        "--provider",
        choices=["all", *PROVIDER_ORDER],
        required=True,
    )
    parser.add_argument(
        "--database", type=Path, default=Path("runtime/workflow/source_index.sqlite3")
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=Path("runtime/source_index/raw")
    )
    parser.add_argument(
        "--lite-output",
        type=Path,
        help="Optionally rebuild the content-deduplicated Plan AI discovery index.",
    )
    arguments = parser.parse_args()
    providers = PROVIDER_ORDER if arguments.provider == "all" else (arguments.provider,)
    for provider in providers:
        asyncio.run(sync_provider(provider, arguments.database, arguments.raw_dir))
    if arguments.lite_output is not None:
        summary = PlanningSourceIndexBuilder().build(
            arguments.database, arguments.lite_output
        )
        print(
            f"lite: {summary['dataset_total']} datasets; "
            f"{summary['indicator_concept_total']} indicators; "
            f"{summary['indicator_set_total']} reusable sets"
        )


if __name__ == "__main__":
    main()
