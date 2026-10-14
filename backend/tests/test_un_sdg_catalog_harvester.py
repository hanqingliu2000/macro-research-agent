from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.knowledge.harvest.un_sdg import UnSdgCatalogHarvester
from macro_research_agent.knowledge.source_index import SourceIndexRepository


@pytest.mark.asyncio
async def test_un_sdg_catalog_harvester_preserves_hierarchy_and_availability(
    tmp_path: Path,
) -> None:
    goal = {
        "code": "8",
        "title": "Decent work and economic growth",
        "description": "Promote inclusive and sustainable economic growth.",
        "targets": [
            {
                "goal": "8",
                "code": "8.1",
                "title": "Sustain economic growth",
                "description": "Sustain per capita economic growth.",
                "indicators": [
                    {
                        "goal": "8",
                        "target": "8.1",
                        "code": "8.1.1",
                        "description": "Annual growth rate of real GDP per capita",
                        "tier": "1",
                        "series": [],
                    }
                ],
            }
        ],
    }
    series = {
        "goal": ["8"],
        "target": ["8.1"],
        "indicator": ["8.1.1"],
        "release": "2026.Q2.G.02",
        "code": "NY_GDP_PCAP",
        "description": "Annual growth rate of real GDP per capita",
        "uri": "/v1/sdg/Series/NY_GDP_PCAP",
    }
    responses: dict[tuple[str, str], object] = {
        ("GET", "/SDGAPI/v1/sdg/Goal/List"): [goal],
        ("GET", "/SDGAPI/v1/sdg/Series/List"): [series],
        ("GET", "/SDGAPI/v1/sdg/GeoArea/List"): [
            {"geoAreaCode": "1", "geoAreaName": "World"},
            {"geoAreaCode": "156", "geoAreaName": "China"},
        ],
        ("GET", "/SDGAPI/v1/sdg/GeoArea/Tree"): [
            {
                "geoAreaCode": 1,
                "geoAreaName": "World",
                "type": "Region",
                "children": [
                    {
                        "geoAreaCode": 156,
                        "geoAreaName": "China",
                        "type": "Country",
                        "children": None,
                    }
                ],
            }
        ],
        ("GET", "/SDGAPI/v1/sdg/Series/LastUpdated"): "2026-08-24T07:15:35",
        ("POST", "/SDGAPI/v1/sdg/CompareTrends/GetSeriesDisaggregationDimensions"): [
            {
                "seriesCode": "NY_GDP_PCAP",
                "disaggregatedCategory": "ALLAGE | BOTHSEX",
            }
        ],
        ("GET", "/SDGAPI/v1/sdg/Goal/8/Dimensions"): [
            {
                "id": "Sex",
                "codes": [
                    {"code": "BOTHSEX", "description": "Both sexes", "sdmx": "_T"}
                ],
            }
        ],
        ("GET", "/SDGAPI/v1/sdg/Goal/8/Attributes"): [
            {
                "id": "Nature",
                "codes": [{"code": "C", "description": "Country data", "sdmx": "C"}],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = responses[(request.method, request.url.path)]
        return httpx.Response(200, content=json.dumps(payload).encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await UnSdgCatalogHarvester(
            tmp_path / "raw", client, request_interval_seconds=0
        ).harvest()

    assert result.snapshot.coverage_status == "complete"
    assert result.snapshot.attributes["goal_total"] == 1
    assert result.snapshot.attributes["indicator_total"] == 1
    assert result.snapshot.attributes["geography_total"] == 2
    dataset = result.snapshot.datasets[0]
    assert dataset.dataset_id == "UNSDG:NY_GDP_PCAP"
    assert dataset.executable is True
    indicator = next(item for item in dataset.dimensions if item.dimension_id == "INDICATOR")
    assert indicator.values[0].label == "Annual growth rate of real GDP per capita"

    repository = SourceIndexRepository(tmp_path / "source-index.sqlite3")
    repository.replace_provider_with_codelists(result.snapshot, result.codelists)
    geographies = repository.dimension_values("un_sdg", dataset.dataset_id, "GEO_AREA")
    assert geographies["total"] == 2
    aggregate = next(item for item in geographies["values"] if item["code"] == "1")
    country = next(item for item in geographies["values"] if item["code"] == "156")
    assert aggregate["is_aggregate"] is True
    assert country["is_aggregate"] is False
    assert repository.search("real GDP per capita", provider_id="un_sdg")[0].dataset_id == (
        "UNSDG:NY_GDP_PCAP"
    )
