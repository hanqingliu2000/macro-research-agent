from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.knowledge.harvest.world_bank import WorldBankCatalogHarvester
from macro_research_agent.knowledge.source_index import SourceIndexRepository


def envelope(page: int, pages: int, rows: list[dict[str, object]]) -> bytes:
    return json.dumps(
        [{"page": page, "pages": pages, "total": 2 if pages == 2 else len(rows)}, rows]
    ).encode()


def advanced_envelope(
    source_id: str,
    concept_id: str,
    rows: list[dict[str, object]],
    *,
    concepts: bool = False,
) -> bytes:
    concept_rows = (
        rows
        if concepts
        else [{"id": concept_id, "name": concept_id, "variable": rows}]
    )
    return json.dumps(
        {
            "page": 1,
            "pages": 1,
            "total": len(rows),
            "source": [
                {
                    "id": source_id,
                    "name": "World Development Indicators",
                    "concept": concept_rows,
                }
            ],
        }
    ).encode()


@pytest.mark.asyncio
async def test_world_bank_harvester_reconciles_catalog_and_preserves_aggregates(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        resource = request.url.path.removeprefix("/v2/")
        page = int(request.url.params["page"])
        if resource == "source":
            body = envelope(
                1,
                1,
                [
                    {
                        "id": "2",
                        "name": "World Development Indicators",
                        "lastupdated": "2026-09-10",
                        "dataavailability": "Y",
                        "metadataavailability": "Y",
                        "concepts": "3",
                    }
                ],
            )
        elif resource == "indicator":
            rows = [
                {
                    "id": "SP.POP.TOTL" if page == 1 else "SP.POP.0014.TO.ZS",
                    "name": "Population, total" if page == 1 else "Population ages 0-14",
                    "unit": "People",
                    "source": {"id": "2", "value": "World Development Indicators"},
                    "sourceNote": "Total population",
                    "sourceOrganization": "World Bank",
                    "topics": [{"id": "8", "value": "Health"}],
                }
            ]
            body = envelope(page, 2, rows)
        elif resource == "country":
            body = envelope(
                1,
                1,
                [
                    {
                        "id": "CHN",
                        "iso2Code": "CN",
                        "name": "China",
                        "region": {"id": "EAS", "value": "East Asia & Pacific"},
                        "adminregion": {"id": "EAP", "value": "East Asia & Pacific"},
                        "incomeLevel": {"id": "UMC", "value": "Upper middle income"},
                        "lendingType": {"id": "IBD", "value": "IBRD"},
                        "capitalCity": "Beijing",
                    },
                    {
                        "id": "WLD",
                        "iso2Code": "1W",
                        "name": "World",
                        "region": {"id": "NA", "value": "Aggregates"},
                        "adminregion": {"id": "", "value": ""},
                        "incomeLevel": {"id": "NA", "value": "Aggregates"},
                        "lendingType": {"id": "NA", "value": "Aggregates"},
                        "capitalCity": "",
                    },
                ],
            )
        elif resource == "topic":
            body = envelope(
                1,
                1,
                [{"id": "8", "value": "Health", "sourceNote": "Health indicators"}],
            )
        elif resource == "sources/2/concepts/data":
            body = advanced_envelope(
                "2",
                "concept",
                [
                    {"id": "Country", "value": "Country"},
                    {"id": "Series", "value": "Series"},
                    {"id": "Time", "value": "Time"},
                ],
                concepts=True,
            )
        elif resource == "sources/2/country/data":
            body = advanced_envelope(
                "2",
                "country",
                [{"id": "CHN", "value": "China"}, {"id": "WLD", "value": "World"}],
            )
        elif resource == "sources/2/series/data":
            body = advanced_envelope(
                "2",
                "series",
                [
                    {"id": "SP.POP.TOTL", "value": "Population, total"},
                    {"id": "SP.POP.0014.TO.ZS", "value": "Population ages 0-14"},
                ],
            )
        elif resource == "sources/2/time/data":
            body = advanced_envelope(
                "2",
                "time",
                [{"id": "YR2025", "value": "2025"}],
            )
        else:
            raise AssertionError(f"Unexpected World Bank test resource: {resource}")
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        harvester = WorldBankCatalogHarvester(tmp_path / "raw", client)
        snapshot = await harvester.harvest()

    assert snapshot.coverage_status == "complete"
    assert len(snapshot.datasets) == 1
    assert len(snapshot.datasets[0].dimensions) == 4
    indicator = next(item for item in snapshot.datasets[0].dimensions if item.role == "indicator")
    assert len(indicator.values) == 2
    frequency = next(item for item in snapshot.datasets[0].dimensions if item.role == "frequency")
    assert [(item.code, item.label) for item in frequency.values] == [("A", "Annual")]
    geography = snapshot.dimensions[0]
    assert next(item for item in geography.values if item.code == "CHN").is_aggregate is False
    assert next(item for item in geography.values if item.code == "WLD").is_aggregate is True
    assert harvester.manifest["indicator"] == {"pages": 2, "total": 2}
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 9

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider(snapshot)
    match = repository.search("China population")[0]
    assert match.dataset_id == "2"
    assert {item["code"] for item in match.matched_values} >= {"CHN", "SP.POP.TOTL"}
