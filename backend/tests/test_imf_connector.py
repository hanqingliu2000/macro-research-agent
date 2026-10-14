import os
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.imf import ImfConnectorError, ImfDataConnector
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from test_workflow_planning import planning_session

SDMX_RESPONSE = b"""<?xml version="1.0" encoding="utf-8"?>
<message:StructureSpecificData
 xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
 <message:DataSet>
  <Series COUNTRY="CHN" INDEX_TYPE="CPI" COICOP_1999="_T"
   TYPE_OF_TRANSFORMATION="IX" FREQUENCY="M" SCALE="0">
   <Obs TIME_PERIOD="2025-M01" OBS_VALUE="109.2" OBS_STATUS="A" />
   <Obs TIME_PERIOD="2025-M02" OBS_VALUE="108.5" OBS_STATUS="A" />
  </Series>
 </message:DataSet>
</message:StructureSpecificData>"""

WEO_RESPONSE = b"""<?xml version="1.0" encoding="utf-8"?>
<message:StructureSpecificData
 xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
 <message:DataSet>
  <Series COUNTRY="CHN" INDICATOR="PCPI" FREQUENCY="A" SCALE="0">
   <Obs TIME_PERIOD="2024" OBS_VALUE="115.312315" />
   <Obs TIME_PERIOD="2025" OBS_VALUE="115.369057" />
  </Series>
 </message:DataSet>
</message:StructureSpecificData>"""

WEO_DEBT_RESPONSE = b"""<?xml version="1.0" encoding="utf-8"?>
<message:StructureSpecificData
 xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
 <message:DataSet>
  <Series COUNTRY="CHN" INDICATOR="GGXWDG_NGDP" FREQUENCY="A" SCALE="0">
   <Obs TIME_PERIOD="2024" OBS_VALUE="88.3" />
  </Series>
  <Series COUNTRY="CHN" INDICATOR="GGXWDG" FREQUENCY="A" SCALE="9">
   <Obs TIME_PERIOD="2024" OBS_VALUE="1200" />
  </Series>
 </message:DataSet>
</message:StructureSpecificData>"""


def query() -> DataQuery:
    return DataQuery(
        dataset="CPI",
        dimensions={"country": ["CHN"], "coicop": ["_T"]},
        frequency="M",
        start_period="2025-01",
        end_period="2025-02",
    )


def test_imf_registry_exposes_only_reviewed_dataflow_contracts() -> None:
    datasets = ImfDataConnector.registered_datasets()
    assert [item["dataset"] for item in datasets] == ["CPI", "WEO"]
    assert datasets[0]["query_dimensions"] == ["country", "coicop"]
    assert datasets[1]["query_dimensions"] == ["country", "indicator"]
    assert datasets[1]["frequencies"] == ["A"]


@pytest.mark.asyncio
async def test_imf_fetch_is_bounded_normalized_and_archives_raw_response(tmp_path: Path) -> None:
    request_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_url
        request_url = str(request.url)
        assert request.headers["Accept"] == (
            "application/vnd.sdmx.structurespecificdata+xml;version=2.1"
        )
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=SDMX_RESPONSE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = ImfDataConnector(tmp_path, client)
        result = await connector.fetch(query())

    assert "/data/CPI/CHN.CPI._T.IX.M" in request_url
    assert "startPeriod=2025-01" in request_url
    assert [item.period for item in result.dataset.observations] == ["2025-01", "2025-02"]
    assert result.dataset.observations[0].series_id == "CHN.CPI._T.IX.M"
    assert result.dataset.observations[0].indicator_code == "CPI._T.IX"
    assert result.provenance.attribution
    raw_hash = result.provenance.request_parameters["raw_response_hashes"]["CHN"]
    assert (tmp_path / f"{raw_hash}.xml").read_bytes() == SDMX_RESPONSE

    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(planning_session()))
    payload = app.state.data_workspace_manager.initialize_connector("planning-1", result)
    record = app.state.data_workspace_manager.get_snapshot(
        "planning-1", payload["activeSnapshotId"]
    )
    frame = app.state.data_workspace_manager.frame(record)
    assert frame["frequency"].tolist() == ["monthly", "monthly"]
    assert payload["quality"]["observations"] == 2
    assert payload["sourceRuns"][0]["connectorId"] == "imf_data"


@pytest.mark.parametrize(
    "candidate",
    [
        DataQuery(
            dataset="BOP",
            dimensions={"country": ["CHN"], "coicop": ["_T"]},
            frequency="M",
            start_period="2025-01",
            end_period="2025-02",
        ),
        DataQuery(
            dataset="CPI",
            dimensions={"country": ["CHN"], "coicop": ["bad"]},
            frequency="M",
            start_period="2025-01",
            end_period="2025-02",
        ),
        DataQuery(
            dataset="CPI",
            dimensions={"country": ["CHN"], "coicop": ["_T"]},
            frequency="M",
            start_period="2000-01",
            end_period="2025-02",
        ),
    ],
)
def test_imf_query_rejects_unregistered_or_unbounded_requests(candidate: DataQuery) -> None:
    with pytest.raises(ImfConnectorError):
        ImfDataConnector.validate_query(candidate)


def test_imf_normalizer_rejects_out_of_scope_rows(tmp_path: Path) -> None:
    connector = ImfDataConnector(tmp_path)
    with pytest.raises(ImfConnectorError, match="outside"):
        connector.normalize(SDMX_RESPONSE.replace(b'COUNTRY="CHN"', b'COUNTRY="USA"'), query())


def test_imf_normalizer_rejects_xml_entities(tmp_path: Path) -> None:
    with pytest.raises(ImfConnectorError, match="Unsafe XML"):
        ImfDataConnector(tmp_path).normalize(b"<!DOCTYPE x [<!ENTITY x 'bad'>]><x/>", query())


@pytest.mark.asyncio
async def test_imf_retry_reuses_completed_members(tmp_path: Path, monkeypatch) -> None:
    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("macro_research_agent.connectors.imf.asyncio.sleep", no_wait)
    calls = {"CHN": 0, "USA": 0}
    usa_fails = True

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal usa_fails
        member = "CHN" if "/CHN." in request.url.path else "USA"
        calls[member] += 1
        if member == "USA" and usa_fails:
            return httpx.Response(500)
        content = SDMX_RESPONSE.replace(
            b'COUNTRY="CHN"', f'COUNTRY="{member}"'.encode()
        )
        return httpx.Response(200, content=content)

    multi = query().model_copy(update={"dimensions": {"country": ["CHN", "USA"], "coicop": ["_T"]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = ImfDataConnector(tmp_path, client)
        with pytest.raises(ImfConnectorError):
            await first.fetch(multi)
        assert calls == {"CHN": 1, "USA": 2}
        usa_fails = False
        second = ImfDataConnector(tmp_path, client)
        result = await second.fetch(multi)

    assert calls == {"CHN": 1, "USA": 3}
    assert [item.entity_code for item in result.dataset.observations] == [
        "CHN",
        "CHN",
        "USA",
        "USA",
    ]
    assert second.attempts[0]["member"] == "CHN"
    assert second.attempts[0]["status"] == "reused_session"


@pytest.mark.asyncio
async def test_imf_weo_uses_its_registered_dimension_contract(tmp_path: Path) -> None:
    request_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_url
        request_url = str(request.url)
        return httpx.Response(200, content=WEO_RESPONSE)

    weo_query = DataQuery(
        dataset="WEO",
        dimensions={"country": ["CHN"], "indicator": ["PCPI"]},
        frequency="A",
        start_period="2024",
        end_period="2025",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ImfDataConnector(tmp_path / "session", client).fetch(weo_query)

    assert "/data/WEO/CHN.PCPI.A" in request_url
    assert result.dataset.metadata["dataset"] == "WEO"
    assert result.dataset.observations[0].series_id == "CHN.PCPI.A"
    assert result.dataset.observations[0].indicator_code == "PCPI"
    assert result.dataset.observations[0].unit is None


@pytest.mark.asyncio
async def test_imf_weo_normalizes_reviewed_general_government_debt_units(
    tmp_path: Path,
) -> None:
    request_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_url
        request_url = str(request.url)
        return httpx.Response(200, content=WEO_DEBT_RESPONSE)

    debt_query = DataQuery(
        dataset="WEO",
        dimensions={"country": ["CHN"], "indicator": ["GGXWDG_NGDP", "GGXWDG"]},
        frequency="A",
        start_period="2024",
        end_period="2024",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ImfDataConnector(tmp_path / "session", client).fetch(debt_query)

    assert "/data/WEO/CHN.GGXWDG_NGDP+GGXWDG.A" in request_url
    by_indicator = {item.indicator_code: item for item in result.dataset.observations}
    assert by_indicator["GGXWDG_NGDP"].unit == "Percent of GDP"
    assert by_indicator["GGXWDG_NGDP"].indicator_name == (
        "Gross debt, General government, Percent of GDP"
    )
    assert by_indicator["GGXWDG"].unit == "Domestic currency"
    assert by_indicator["GGXWDG"].scale == "9"


@pytest.mark.asyncio
async def test_public_response_cache_is_reused_across_isolated_sessions(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SDMX_RESPONSE)

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = ImfDataConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        second = ImfDataConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 1
    assert second.attempts[0]["status"] == "reused_shared"
    raw_hash = first_result.provenance.request_parameters["raw_response_hashes"]["CHN"]
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert (tmp_path / "session-b" / f"{raw_hash}.xml").read_bytes() == SDMX_RESPONSE


@pytest.mark.asyncio
async def test_expired_shared_response_is_refetched_for_a_new_session(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SDMX_RESPONSE)

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ImfDataConnector(tmp_path / "session-a", client, shared).fetch(query())
        manifest = next((shared / "requests").glob("*.json"))
        os.utime(manifest, (0, 0))
        second = ImfDataConnector(tmp_path / "session-b", client, shared)
        await second.fetch(query())

    assert calls == 2
    assert second.attempts[0]["status"] == "completed"
