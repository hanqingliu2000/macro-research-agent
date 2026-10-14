from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.bis import BisConnector, BisConnectorError


def query() -> DataQuery:
    return DataQuery(
        dataset="POLICY_RATES",
        dimensions={"country": ["USA"], "indicator": ["POLICY_RATE"]},
        frequency="M",
        start_period="2025-01",
        end_period="2025-02",
    )


def availability(area: str = "US") -> dict:
    return {
        "meta": {"test": False},
        "data": {
            "contentConstraints": [
                {
                    "agencyID": "BIS",
                    "version": "1.0",
                    "constraintAttachment": {
                        "dataflows": [
                            "urn:sdmx:org.sdmx.infomodel.datastructure.Dataflow=BIS:WS_CBPOL(1.0)"
                        ]
                    },
                    "cubeRegions": [{"keyValues": [{"id": "REF_AREA", "values": [area]}]}],
                }
            ]
        },
    }


def payload(*, area: str = "US") -> bytes:
    return (
        "DATAFLOW,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,UNIT_MEASURE,UNIT_MULT,"
        "OBS_STATUS,TITLE,SOURCE_REF\n"
        f"BIS:WS_CBPOL(1.0),M,{area},2025-01,4.375,368,0,A,Policy rate,Federal Reserve\n"
        f"BIS:WS_CBPOL(1.0),M,{area},2025-02,4.375,368,0,A,Policy rate,Federal Reserve\n"
    ).encode()


@pytest.mark.asyncio
async def test_bis_checks_availability_and_normalizes_policy_rates(tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if "/availability/" in request.url.path:
            return httpx.Response(200, json=availability())
        assert request.url.params["c[TIME_PERIOD]"] == "ge:2025-01+le:2025-02"
        return httpx.Response(200, content=payload(), headers={"Content-Type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await BisConnector(tmp_path, client).fetch(query())

    assert len(paths) == 2
    assert result.dataset.observations[0].unit == "Per cent per year"
    assert result.dataset.observations[0].attributes["bis"]["provider_area"] == "US"
    assert result.dataset.metadata["availability_sha256"]
    assert "does not endorse" in str(result.provenance.attribution)


@pytest.mark.asyncio
async def test_bis_rejects_unavailable_country(tmp_path: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=availability("GB")))
    ) as client:
        with pytest.raises(BisConnectorError, match="availability"):
            await BisConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_bis_rejects_rows_outside_query(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/availability/" in request.url.path:
            return httpx.Response(200, json=availability())
        return httpx.Response(200, content=payload(area="GB"), headers={"Content-Type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BisConnectorError, match="outside"):
            await BisConnector(tmp_path, client).fetch(query())


def test_bis_rejects_unregistered_query() -> None:
    with pytest.raises(BisConnectorError):
        BisConnector.validate_query(query().model_copy(update={"frequency": "D"}))
