from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.un_sdg import UnSdgConnector, UnSdgConnectorError


def query() -> DataQuery:
    return DataQuery(
        dataset="SDG_INDICATORS",
        dimensions={"country": ["CHN"], "indicator": ["NY_GDP_PCAP"]},
        frequency="A",
        start_period="2021",
        end_period="2022",
    )


def release_payload(release: str = "2026.Q2.G.02") -> list[dict]:
    return [
        {
            "goal": "8",
            "target": "8.1",
            "code": "8.1.1",
            "series": [
                {
                    "release": release,
                    "code": "NY_GDP_PCAP",
                    "description": "Annual growth rate of real GDP per capita (%)",
                }
            ],
        }
    ]


def observation(year: int, value: str) -> dict:
    return {
        "goal": ["8"],
        "target": ["8.1"],
        "indicator": ["8.1.1"],
        "series": "NY_GDP_PCAP",
        "seriesDescription": "Annual growth rate of real GDP per capita (%)",
        "geoAreaCode": "156",
        "geoAreaName": "China",
        "timePeriodStart": year,
        "value": value,
        "valueType": "Float",
        "basePeriod": "2020",
        "source": "UNSD",
        "footnotes": [],
        "dimensions": {"Reporting Type": "G"},
        "attributes": {"Nature": "CA", "Units": "PERCENT", "Observation Status": "A"},
    }


@pytest.mark.asyncio
async def test_un_sdg_pins_release_validates_pages_and_preserves_metadata(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Series/List"):
            return httpx.Response(200, json=release_payload())
        page = int(request.url.params["page"])
        assert request.url.params.get_list("areaCode") == ["156"]
        return httpx.Response(
            200,
            json={
                "size": 1,
                "totalElements": 2,
                "totalPages": 2,
                "pageNumber": page,
                "attributes": [],
                "dimensions": [],
                "data": [observation(2020 + page, str(8.4 - page))],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await UnSdgConnector(tmp_path, client).fetch(query())

    assert [item.value for item in result.dataset.observations] == [7.4, 6.4]
    assert len({item.series_id for item in result.dataset.observations}) == 1
    first = result.dataset.observations[0]
    assert first.entity_code == "CHN"
    assert first.unit == "PERCENT"
    assert first.status == "A"
    assert first.attributes["un_sdg"]["attributes"]["Nature"] == "CA"
    assert result.dataset.metadata["release"] == "2026.Q2.G.02"
    assert (tmp_path / f"{result.provenance.raw_sha256}.raw").exists()


@pytest.mark.asyncio
async def test_un_sdg_rejects_pagination_drift(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Series/List"):
            return httpx.Response(200, json=release_payload())
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "size": 1,
                "totalElements": 2,
                "totalPages": 2 if page == 1 else 3,
                "pageNumber": page,
                "data": [observation(2020 + page, "1.0")],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnSdgConnectorError, match="changed"):
            await UnSdgConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_un_sdg_rejects_wrong_series(tmp_path: Path) -> None:
    wrong = release_payload()
    wrong[0]["series"][0]["code"] = "OTHER"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wrong))
    ) as client:
        with pytest.raises(UnSdgConnectorError, match="registered series"):
            await UnSdgConnector(tmp_path, client).fetch(query())


def test_un_sdg_rejects_unregistered_query() -> None:
    with pytest.raises(UnSdgConnectorError):
        UnSdgConnector.validate_query(query().model_copy(update={"frequency": "M"}))
