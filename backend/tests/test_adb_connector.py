from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.adb import AdbConnector, AdbConnectorError
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from test_workflow_planning import planning_session


def query() -> DataQuery:
    return DataQuery(
        dataset="NATIONAL_ACCOUNTS",
        dimensions={"country": ["PHL"], "indicator": ["NGDP_XDC"]},
        frequency="A",
        start_period="2023",
        end_period="2024",
    )


def payload(*, economy: str = "PHI", dataflow: str = "ADB:DF_NA(1.0)") -> bytes:
    header = (
        "DATAFLOW,FREQ,INDICATOR,ECONOMY_CODE,TIME_PERIOD,OBS_VALUE,UNIT,UNIT_MULT,"
        "DECIMALS,FOOTNOTE,OBS_STATUS,REF_YEAR,BASE_YEAR,DATA_SOURCE,METHODOLOGY\n"
    )
    rows = [
        f"{dataflow},A,NGDP_XDC,{economy},2023,24313.56,PHP,9,0,,A,Calendar Year,,PSA,\n",
        f"{dataflow},A,NGDP_XDC,{economy},2024,,PHP,9,0,Missing,A,Calendar Year,,PSA,\n",
    ]
    return (header + "".join(rows)).encode()


@pytest.mark.asyncio
async def test_adb_normalizes_crosswalk_and_reuses_across_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "kidb.adb.org"
        assert request.url.path.endswith("/data/ADB,DF_NA/A.NGDP_XDC.PHI")
        assert request.url.params["version"] == "3.0"
        assert request.url.params["format"] == "sdmx-csv"
        return httpx.Response(200, content=payload(), headers={"Content-Type": "text/csv"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = AdbConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        second = AdbConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 1
    observations = first_result.dataset.observations
    assert [(item.period, item.value) for item in observations] == [
        ("2023", 24313.56),
        ("2024", None),
    ]
    assert observations[0].entity_code == "PHL"
    assert observations[0].unit == "PHP"
    assert observations[0].scale == "10^9"
    assert observations[0].attributes["adb"]["provider_economy_code"] == "PHI"
    assert "Asian Development Bank: Key Indicators Database Online" in str(
        first_result.provenance.attribution
    )
    assert "PSA" in str(first_result.provenance.attribution)
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert {item["status"] for item in second.attempts} == {"reused_shared"}
    assert first.rate_limiter.windows[0].max_requests == 18

    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_repository.create(
        WorkflowSessionDocument.model_validate(planning_session())
    )

    async def fixture_fetch(_: AdbConnector, requested: DataQuery):
        assert requested == query()
        return first_result

    monkeypatch.setattr(AdbConnector, "fetch", fixture_fetch)
    session = planning_session()
    session["currentPlan"] = {
        "dataSources": [
            {
                "connectorId": "adb",
                "dataset": "NATIONAL_ACCOUNTS",
                "indicators": ["NGDP_XDC"],
            }
        ],
        "geographyResolutions": [{"memberCodes": ["PHL"]}],
        "period": {"frequency": "annual", "start": "2023", "end": "2024"},
    }
    workspace = await app.state.workflow_data_service.initialize_registered_connector_payload(
        session, "adb"
    )
    assert workspace["sourceRuns"][0]["connectorId"] == "adb"
    assert workspace["quality"]["observations"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "message"),
    [
        (payload(economy="SIN"), "outside"),
        (payload(dataflow="ADB:DF_NA(2.0)"), "version changed"),
        (payload() + payload().split(b"\n", 1)[1], "duplicate"),
    ],
)
async def test_adb_rejects_scope_version_and_duplicate_drift(
    tmp_path: Path, content: bytes, message: str
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=content, headers={"Content-Type": "text/csv"}
            )
        )
    ) as client:
        with pytest.raises(AdbConnectorError, match=message):
            await AdbConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_adb_retry_exhaustion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"Content-Type": "text/csv"})

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("macro_research_agent.connectors.adb.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = AdbConnector(tmp_path, client)
        with pytest.raises(AdbConnectorError, match="503"):
            await connector.fetch(query())
    assert calls == 3
    assert [item["status"] for item in connector.attempts] == [
        "retryable",
        "retryable",
        "failed",
    ]


@pytest.mark.asyncio
async def test_adb_rejects_media_type_oversize_and_schema_drift(tmp_path: Path) -> None:
    responses = [
        httpx.Response(200, content=payload(), headers={"Content-Type": "application/json"}),
        httpx.Response(
            200,
            content=b"x" * (AdbConnector.max_bytes + 1),
            headers={"Content-Type": "text/csv"},
        ),
        httpx.Response(200, content=b"wrong,schema\n1,2", headers={"Content-Type": "text/csv"}),
    ]
    for index, response in enumerate(responses):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            with pytest.raises(AdbConnectorError):
                await AdbConnector(tmp_path / str(index), client).fetch(query())


@pytest.mark.parametrize(
    "candidate",
    [
        DataQuery(
            dataset="NATIONAL_ACCOUNTS",
            dimensions={"country": ["USA"], "indicator": ["NGDP_XDC"]},
            frequency="A",
            start_period="2020",
            end_period="2024",
        ),
        DataQuery(
            dataset="NATIONAL_ACCOUNTS",
            dimensions={"country": ["PHL"], "indicator": ["OTHER"]},
            frequency="A",
            start_period="2020",
            end_period="2024",
        ),
        DataQuery(
            dataset="NATIONAL_ACCOUNTS",
            dimensions={"country": ["PHL"], "indicator": ["NGDP_XDC"]},
            frequency="A",
            start_period="1999",
            end_period="2024",
        ),
    ],
)
def test_adb_rejects_unregistered_query_shapes(candidate: DataQuery) -> None:
    with pytest.raises(AdbConnectorError):
        AdbConnector.validate_query(candidate)
