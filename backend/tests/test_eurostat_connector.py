from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.eurostat import EurostatConnector, EurostatConnectorError
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from test_workflow_planning import planning_session


def query(*, countries: list[str] | None = None) -> DataQuery:
    return DataQuery(
        dataset="HICP_INDEX",
        dimensions={"country": countries or ["DEU"], "indicator": ["TOTAL"]},
        frequency="M",
        start_period="2024-01",
        end_period="2024-03",
    )


def payload(
    *, geo: str = "DE", updated: str = "2026-02-06T23:00:00+0100", drift: bool = False
) -> bytes:
    dimensions = ["freq", "unit", "coicop18", "geo", "time"]
    if drift:
        dimensions = ["unit", "freq", "coicop18", "geo", "time"]
    return json.dumps(
        {
            "version": "2.0",
            "class": "dataset",
            "label": "HICP (2025 = 100) - monthly data",
            "source": "ESTAT",
            "updated": updated,
            "id": dimensions,
            "size": [1, 1, 1, 1, 3],
            "dimension": {
                "freq": {"category": {"index": {"M": 0}, "label": {"M": "Monthly"}}},
                "unit": {"category": {"index": {"I25": 0}, "label": {"I25": "Index"}}},
                "coicop18": {
                    "category": {"index": {"TOTAL": 0}, "label": {"TOTAL": "All-items HICP"}}
                },
                "geo": {
                    "category": {"index": {geo: 0}, "label": {geo: "Germany"}}
                },
                "time": {
                    "category": {
                        "index": {"2024-01": 0, "2024-02": 1, "2024-03": 2}
                    }
                },
            },
            "value": {"0": 126.4, "2": 128.0},
            "status": {"2": "p"},
        }
    ).encode()


@pytest.mark.asyncio
async def test_eurostat_normalizes_json_stat_and_reuses_across_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "ec.europa.eu"
        assert request.url.path.endswith("/data/prc_hicp_minr")
        assert request.url.params["geo"] == "DE"
        assert request.url.params["unit"] == "I25"
        return httpx.Response(200, content=payload(), headers={"Content-Type": "application/json"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = EurostatConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        second = EurostatConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 1
    observations = first_result.dataset.observations
    assert [(item.period, item.value, item.status) for item in observations] == [
        ("2024-01", 126.4, None),
        ("2024-02", None, None),
        ("2024-03", 128.0, "p"),
    ]
    assert observations[0].entity_code == "DEU"
    assert observations[0].attributes["eurostat"]["provider_geo"] == "DE"
    assert first_result.dataset.metadata["provider_update"] == "2026-02-06T23:00:00+0100"
    assert "10.2908/PRC_HICP_MINR" in str(first_result.provenance.attribution)
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert {item["status"] for item in second.attempts} == {"reused_shared"}

    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_repository.create(
        WorkflowSessionDocument.model_validate(planning_session())
    )

    async def fixture_fetch(_: EurostatConnector, requested: DataQuery):
        assert requested == query()
        return first_result

    monkeypatch.setattr(EurostatConnector, "fetch", fixture_fetch)
    session = planning_session()
    session["currentPlan"] = {
        "dataSources": [
            {
                "connectorId": "eurostat",
                "dataset": "HICP_INDEX",
                "indicators": ["TOTAL"],
            }
        ],
        "geographyResolutions": [{"memberCodes": ["DEU"]}],
        "period": {"frequency": "monthly", "start": "2024-01", "end": "2024-03"},
    }
    workspace = await app.state.workflow_data_service.initialize_registered_connector_payload(
        session, "eurostat"
    )
    assert workspace["sourceRuns"][0]["connectorId"] == "eurostat"
    assert workspace["quality"]["observations"] == 3


@pytest.mark.asyncio
async def test_eurostat_rejects_dimension_drift_and_wrong_geo(tmp_path: Path) -> None:
    contents = [payload(drift=True), payload(geo="FR")]
    for index, content in enumerate(contents):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _, content=content: httpx.Response(
                    200, content=content, headers={"Content-Type": "application/json"}
                )
            )
        ) as client:
            with pytest.raises(EurostatConnectorError):
                await EurostatConnector(tmp_path / str(index), client).fetch(query())


@pytest.mark.asyncio
async def test_eurostat_rejects_update_drift_across_countries(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        geo = request.url.params["geo"]
        content = payload(
            geo=geo,
            updated=(
                "2026-02-06T23:00:00+0100"
                if geo == "DE"
                else "2026-02-07T11:00:00+0100"
            ),
        )
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EurostatConnectorError, match="changed"):
            await EurostatConnector(tmp_path, client).fetch(query(countries=["DEU", "FRA"]))


@pytest.mark.asyncio
async def test_eurostat_rejects_media_type_and_oversized_response(tmp_path: Path) -> None:
    responses = [
        httpx.Response(200, content=payload(), headers={"Content-Type": "text/html"}),
        httpx.Response(
            200,
            content=b"x" * (EurostatConnector.max_bytes + 1),
            headers={"Content-Type": "application/json"},
        ),
    ]
    for index, response in enumerate(responses):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            with pytest.raises(EurostatConnectorError):
                await EurostatConnector(tmp_path / str(index), client).fetch(query())


@pytest.mark.asyncio
async def test_eurostat_retry_exhaustion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"Content-Type": "application/json"})

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("macro_research_agent.connectors.eurostat.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = EurostatConnector(tmp_path, client)
        with pytest.raises(EurostatConnectorError, match="503"):
            await connector.fetch(query())
    assert calls == 3
    assert [item["status"] for item in connector.attempts] == [
        "retryable",
        "retryable",
        "failed",
    ]


@pytest.mark.asyncio
async def test_eurostat_rejects_malformed_json_and_duplicate_keys(tmp_path: Path) -> None:
    duplicate_payload = json.loads(payload())
    duplicate_payload["dimension"]["time"]["category"]["index"] = [
        "2024-01",
        "2024-01",
        "2024-03",
    ]
    contents = [(b"{", "malformed"), (json.dumps(duplicate_payload).encode(), "duplicate")]
    for index, (content, message) in enumerate(contents):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _, content=content: httpx.Response(
                    200, content=content, headers={"Content-Type": "application/json"}
                )
            )
        ) as client:
            with pytest.raises(EurostatConnectorError, match=message):
                await EurostatConnector(tmp_path / str(index), client).fetch(query())


@pytest.mark.parametrize(
    "candidate",
    [
        DataQuery(
            dataset="HICP_INDEX",
            dimensions={"country": ["USA"], "indicator": ["TOTAL"]},
            frequency="M",
            start_period="2024-01",
            end_period="2024-03",
        ),
        DataQuery(
            dataset="HICP_INDEX",
            dimensions={"country": ["DEU"], "indicator": ["CP01"]},
            frequency="M",
            start_period="2024-01",
            end_period="2024-03",
        ),
        DataQuery(
            dataset="OTHER",
            dimensions={"country": ["DEU"], "indicator": ["TOTAL"]},
            frequency="M",
            start_period="2024-01",
            end_period="2024-03",
        ),
    ],
)
def test_eurostat_rejects_unregistered_query_shapes(candidate: DataQuery) -> None:
    with pytest.raises(EurostatConnectorError):
        EurostatConnector.validate_query(candidate)
