from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.ecb import EcbConnector, EcbConnectorError


def query() -> DataQuery:
    return DataQuery(
        dataset="EXCHANGE_RATES",
        dimensions={"country": ["USA"], "indicator": ["EUR_REFERENCE_RATE"]},
        frequency="M",
        start_period="2025-01",
        end_period="2025-02",
    )


def payload(*, currency: str = "USD", dataflow: str = "ECB:EXR(1.0)") -> bytes:
    return (
        "DATAFLOW,KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,"
        "TIME_PERIOD,OBS_VALUE,UNIT,UNIT_MULT,OBS_STATUS,TITLE\n"
        f"{dataflow},EXR.M.{currency}.EUR.SP00.A,M,{currency},EUR,SP00,A,"
        "2025-01,1.0354,USD,0,A,US dollar per euro\n"
        f"{dataflow},EXR.M.{currency}.EUR.SP00.A,M,{currency},EUR,SP00,A,"
        "2025-02,1.0413,USD,0,A,US dollar per euro\n"
    ).encode()


@pytest.mark.asyncio
async def test_ecb_normalizes_and_reuses_304_shared_response(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/data/EXR/M.USD.EUR.SP00.A")
        assert request.url.params["includeHistory"] == "false"
        if calls == 2:
            assert request.headers["if-modified-since"] == "Wed, 10 Sep 2026 12:00:00 GMT"
            return httpx.Response(304)
        return httpx.Response(
            200,
            content=payload(),
            headers={
                "Content-Type": "text/csv",
                "Last-Modified": "Wed, 10 Sep 2026 12:00:00 GMT",
            },
        )

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = EcbConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        manifest = next((shared / "requests").glob("*.json"))
        old = manifest.stat().st_mtime - first.shared_cache_ttl_seconds - 1
        os.utime(manifest, (old, old))
        second = EcbConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 2
    assert [item.value for item in first_result.dataset.observations] == [1.0354, 1.0413]
    assert first_result.dataset.observations[0].entity_code == "USA"
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert second.attempts[-1]["status"] == "not_modified"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        payload(currency="JPY"),
        payload(dataflow="ECB:EXR(2.0)"),
        payload() + payload().split(b"\n", 1)[1],
    ],
)
async def test_ecb_rejects_scope_version_and_duplicate_drift(
    tmp_path: Path, content: bytes
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=content, headers={"Content-Type": "text/csv"})
        )
    ) as client:
        with pytest.raises(EcbConnectorError):
            await EcbConnector(tmp_path, client).fetch(query())


def test_ecb_rejects_unregistered_query() -> None:
    candidate = query().model_copy(update={"frequency": "D"})
    with pytest.raises(EcbConnectorError):
        EcbConnector.validate_query(candidate)
