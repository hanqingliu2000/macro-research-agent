from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.knowledge.harvest.adb import AdbCatalogHarvester
from macro_research_agent.knowledge.source_index import SourceIndexRepository


def envelope(key: str, values: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "$schema": "https://json.sdmx.org/2.1/sdmx-json-structure-schema.json",
            "meta": {"prepared": "2026-09-11T12:00:00Z"},
            "data": {key: values},
        }
    ).encode()


@pytest.mark.asyncio
async def test_adb_catalog_harvester_applies_indicator_constraints(
    tmp_path: Path,
) -> None:
    responses = {
        "dataflow": envelope(
            "dataflows",
            [
                {
                    "agencyID": "ADB",
                    "id": "DF_NA",
                    "version": "1.0",
                    "name": "National Accounts",
                    "structure": (
                        "urn:sdmx:org.sdmx.infomodel.datastructure."
                        "DataStructure=ADB:KIDB_DSD(1.1)"
                    ),
                }
            ],
        ),
        "datastructure": envelope(
            "datastructures",
            [
                {
                    "agencyID": "ADB",
                    "id": "KIDB_DSD",
                    "version": "1.1",
                    "dataStructureComponents": {
                        "dimensionList": {
                            "dimensions": [
                                {
                                    "id": "FREQ",
                                    "position": 1,
                                    "conceptIdentity": (
                                        "urn:sdmx:org.sdmx.infomodel.conceptscheme."
                                        "Concept=SDMX:CS(1.0).FREQ"
                                    ),
                                    "localRepresentation": {
                                        "enumeration": (
                                            "urn:sdmx:org.sdmx.infomodel.codelist."
                                            "Codelist=SDMX:CL_FREQ(1.0)"
                                        )
                                    },
                                },
                                {
                                    "id": "INDICATOR",
                                    "position": 2,
                                    "name": "Indicator",
                                    "conceptIdentity": (
                                        "urn:sdmx:org.sdmx.infomodel.conceptscheme."
                                        "Concept=ADB:CS(1.0).INDICATOR"
                                    ),
                                    "localRepresentation": {
                                        "enumeration": (
                                            "urn:sdmx:org.sdmx.infomodel.codelist."
                                            "Codelist=ADB:CL_INDICATOR(1.0)"
                                        )
                                    },
                                },
                            ],
                            "timeDimension": {
                                "id": "TIME_PERIOD",
                                "conceptIdentity": (
                                    "urn:sdmx:org.sdmx.infomodel.conceptscheme."
                                    "Concept=SDMX:CS(1.0).TIME_PERIOD"
                                ),
                            },
                        }
                    },
                }
            ],
        ),
        "conceptscheme": envelope(
            "conceptschemes",
            [
                {
                    "agencyID": "ADB",
                    "id": "CS",
                    "version": "1.0",
                    "concepts": [{"id": "INDICATOR", "name": "Indicator"}],
                },
                {
                    "agencyID": "SDMX",
                    "id": "CS",
                    "version": "1.0",
                    "concepts": [
                        {"id": "FREQ", "name": "Frequency"},
                        {"id": "TIME_PERIOD", "name": "Time period"},
                    ],
                },
            ],
        ),
        "codelist": envelope(
            "codelists",
            [
                {
                    "agencyID": "SDMX",
                    "id": "CL_FREQ",
                    "version": "1.0",
                    "name": "Frequency",
                    "isPartial": False,
                    "codes": [{"id": "A", "name": "Annual"}],
                },
                {
                    "agencyID": "ADB",
                    "id": "CL_INDICATOR",
                    "version": "1.0",
                    "name": "Indicators",
                    "isPartial": False,
                    "codes": [
                        {"id": "GDP", "name": "Gross domestic product"},
                        {"id": "POP", "name": "Population"},
                    ],
                },
            ],
        ),
        "dataconstraint": envelope(
            "dataConstraints",
            [
                {
                    "agencyID": "ADB",
                    "id": "DF_NA_CONSTRAINT",
                    "version": "1.0",
                    "role": "Allowed",
                    "constraintAttachment": {
                        "dataflows": [
                            "urn:sdmx:org.sdmx.infomodel.datastructure."
                            "Dataflow=ADB:DF_NA(1.0)"
                        ]
                    },
                    "cubeRegions": [
                        {
                            "include": True,
                            "keyValues": [{"id": "INDICATOR", "values": ["GDP"]}],
                        }
                    ],
                }
            ],
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        resource = request.url.path.split("/")[-4]
        return httpx.Response(
            200,
            content=responses[resource],
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AdbCatalogHarvester(
            tmp_path / "raw", client, request_interval_seconds=0
        ).harvest()

    assert result.snapshot.coverage_status == "complete"
    assert result.snapshot.attributes["dataflow_total"] == 1
    assert result.snapshot.attributes["constraint_total"] == 1
    dataset = result.snapshot.datasets[0]
    assert dataset.dataset_id == "ADB:DF_NA"
    assert dataset.executable is True
    indicator = next(item for item in dataset.dimensions if item.dimension_id == "INDICATOR")
    assert indicator.codelist_agency_id == "ADB.CONSTRAINT"

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider_with_codelists(result.snapshot, result.codelists)
    allowed = repository.dimension_values("adb", "ADB:DF_NA", "INDICATOR")
    assert allowed["total"] == 1
    assert allowed["values"][0]["code"] == "GDP"
    assert repository.search("gross domestic product")[0].dataset_id == "ADB:DF_NA"
