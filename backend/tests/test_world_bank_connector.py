import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.world_bank import (
    WorldBankConnector,
    WorldBankConnectorError,
)
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from macro_research_agent.workflow.data_service import WorkflowDataService
from macro_research_agent.workflow.data_workspace import DataWorkspaceError
from macro_research_agent.workflow.planning_provider import DeterministicPlanningProvider
from test_workflow_planning import planning_session


def query() -> DataQuery:
    return DataQuery(
        dataset="WDI",
        dimensions={"country": ["CHN"], "indicator": ["SP.POP.TOTL"]},
        frequency="A",
        start_period="2023",
        end_period="2024",
    )


def metadata_payload() -> bytes:
    return json.dumps(
        [
            {"page": 1, "pages": 1, "per_page": "10", "total": 1},
            [
                {
                    "id": "SP.POP.TOTL",
                    "name": "Population, total",
                    "unit": "people",
                    "source": {"id": "2", "value": "World Development Indicators"},
                    "sourceNote": "Total population.",
                    "sourceOrganization": "World Bank",
                    "topics": [{"id": "8", "value": "Health"}],
                }
            ],
        ]
    ).encode()


def data_payload(*, country: str = "CHN", page: int = 1, pages: int = 1) -> bytes:
    rows = [
        {
            "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
            "country": {"id": "CN", "value": "China"},
            "countryiso3code": country,
            "date": "2024",
            "value": 1_408_975_000,
            "unit": "",
            "obs_status": "",
            "decimal": 0,
            "footnote": "",
        },
        {
            "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
            "country": {"id": "CN", "value": "China"},
            "countryiso3code": country,
            "date": "2023",
            "value": None,
            "unit": "",
            "obs_status": "",
            "decimal": 0,
            "footnote": "provider missing value",
        },
    ]
    return json.dumps(
        [
            {
                "page": page,
                "pages": pages,
                "per_page": "1000",
                "total": len(rows),
                "lastupdated": "2026-07-15",
            },
            rows,
        ]
    ).encode()


def is_metadata_request(request: httpx.Request) -> bool:
    return request.url.path == "/v2/indicator/SP.POP.TOTL"


@pytest.mark.parametrize(
    ("code", "label", "expected"),
    [
        ("NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)", "Percent"),
        ("NE.GDI.TOTL.ZS", "Gross capital formation (% of GDP)", "Percent of GDP"),
        (
            "NE.CON.PRVT.ZS",
            "Households and NPISHs final consumption expenditure (% of GDP)",
            "Percent of GDP",
        ),
    ],
)
def test_world_bank_derives_canonical_units_from_official_indicator_labels(
    code: str, label: str, expected: str
) -> None:
    unit, source = WorldBankConnector._normalized_unit("", "", label)

    assert unit == expected, code
    assert source == "indicator_label"


@pytest.mark.asyncio
async def test_world_bank_fetch_normalizes_wdi_and_reuses_across_sessions(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Accept"] == "application/json"
        assert request.url.host == "api.worldbank.org"
        assert request.url.params["source"] == "2"
        content = (
            metadata_payload()
            if is_metadata_request(request)
            else data_payload()
        )
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = WorldBankConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        second = WorldBankConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 2
    observations = first_result.dataset.observations
    assert [(item.period, item.value) for item in observations] == [
        ("2023", None),
        ("2024", 1_408_975_000.0),
    ]
    assert observations[0].unit == "people"
    assert observations[0].attributes["world_bank"]["indicator_metadata_unit"] == "people"
    assert observations[0].attributes["world_bank"]["unit_source"] == "indicator_metadata"
    assert observations[0].entity_code == "CHN"
    assert first_result.provenance.request_parameters["provider_updates"] == {
        "SP.POP.TOTL": "2026-07-15"
    }
    assert first_result.provenance.request_parameters["indicator_units"] == {
        "SP.POP.TOTL": {
            "raw": "people",
            "normalized": "people",
            "source": "indicator_metadata",
        }
    }
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert {item["status"] for item in second.attempts} == {"reused_shared"}
    assert len(list((tmp_path / "session-b").glob("*.raw"))) == 2

    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(planning_session()))
    payload = app.state.data_workspace_manager.initialize_connector("planning-1", first_result)
    assert payload["sourceRuns"][0]["connectorId"] == "world_bank"
    assert payload["sourceRuns"][0]["dataset"] == "WDI"


@pytest.mark.asyncio
async def test_world_bank_rejects_pagination_drift(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if is_metadata_request(request):
            content = metadata_payload()
        elif request.url.params["page"] == "1":
            payload = json.loads(data_payload())
            payload[0].update({"pages": 2, "total": 4})
            content = json.dumps(payload).encode()
        else:
            payload = json.loads(data_payload(page=2, pages=2))
            payload[0].update({"total": 5})
            content = json.dumps(payload).encode()
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WorldBankConnectorError, match="changed"):
            await WorldBankConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_world_bank_rejects_excessive_pages(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if is_metadata_request(request):
            content = metadata_payload()
        else:
            payload = json.loads(data_payload())
            payload[0]["pages"] = 21
            content = json.dumps(payload).encode()
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WorldBankConnectorError, match="excessive"):
            await WorldBankConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_world_bank_rejects_out_of_query_economy(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            metadata_payload()
            if is_metadata_request(request)
            else data_payload(country="USA")
        )
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WorldBankConnectorError, match="outside"):
            await WorldBankConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_world_bank_expired_shared_cache_refetches(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = (
            metadata_payload()
            if is_metadata_request(request)
            else data_payload()
        )
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await WorldBankConnector(tmp_path / "session-a", client, shared).fetch(query())
        for manifest in (shared / "requests").glob("*.json"):
            os.utime(manifest, (0, 0))
        await WorldBankConnector(tmp_path / "session-b", client, shared).fetch(query())
    assert calls == 4


@pytest.mark.asyncio
async def test_world_bank_corrupt_shared_cache_refetches(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = metadata_payload() if is_metadata_request(request) else data_payload()
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await WorldBankConnector(tmp_path / "session-a", client, shared).fetch(query())
        for raw_path in shared.glob("*.raw"):
            raw_path.write_bytes(b"corrupt")
        await WorldBankConnector(tmp_path / "session-b", client, shared).fetch(query())
    assert calls == 4


@pytest.mark.asyncio
async def test_world_bank_rejects_wrong_media_type_and_oversized_page(tmp_path: Path) -> None:
    def wrong_type(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[]", headers={"Content-Type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(wrong_type)) as client:
        with pytest.raises(WorldBankConnectorError, match="media type"):
            await WorldBankConnector(tmp_path / "wrong-type", client).fetch(query())

    def oversized(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 101,
            headers={"Content-Type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(oversized)) as client:
        connector = WorldBankConnector(tmp_path / "oversized", client)
        connector.max_bytes = 100
        with pytest.raises(WorldBankConnectorError, match="10 MB page limit"):
            await connector.fetch(query())


@pytest.mark.asyncio
async def test_world_bank_retry_exhaustion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def no_wait(_: float) -> None:
        return None

    def unavailable(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"Content-Type": "application/json"})

    monkeypatch.setattr("macro_research_agent.connectors.world_bank.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(WorldBankConnectorError, match="HTTP 503"):
            await WorldBankConnector(tmp_path, client).fetch(query())
    assert calls == 3


@pytest.mark.asyncio
async def test_world_bank_rejects_malformed_json_and_duplicate_keys(tmp_path: Path) -> None:
    def malformed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as client:
        with pytest.raises(WorldBankConnectorError, match="malformed JSON"):
            await WorldBankConnector(tmp_path / "malformed", client).fetch(query())

    def duplicate(request: httpx.Request) -> httpx.Response:
        if is_metadata_request(request):
            content = metadata_payload()
        else:
            payload = json.loads(data_payload())
            payload[1][1]["date"] = "2024"
            content = json.dumps(payload).encode()
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(duplicate)) as client:
        with pytest.raises(WorldBankConnectorError, match="duplicate"):
            await WorldBankConnector(tmp_path / "duplicate", client).fetch(query())


@pytest.mark.parametrize(
    "candidate",
    [
        DataQuery(
            dataset="WDI",
            dimensions={"country": ["CHN"], "indicator": ["SP.POP.TOTL"]},
            frequency="M",
            start_period="2023-01",
            end_period="2024-01",
        ),
        DataQuery(
            dataset="OTHER",
            dimensions={"country": ["CHN"], "indicator": ["SP.POP.TOTL"]},
            frequency="A",
            start_period="2023",
            end_period="2024",
        ),
    ],
)
def test_world_bank_rejects_unregistered_query_shapes(candidate: DataQuery) -> None:
    with pytest.raises(WorldBankConnectorError):
        WorldBankConnector.validate_query(candidate)


@pytest.mark.asyncio
async def test_world_bank_plan_approval_creates_data_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = metadata_payload() if is_metadata_request(request) else data_payload()
        return httpx.Response(200, content=content, headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider_client:
        fixture_result = await WorldBankConnector(
            tmp_path / "fixture", provider_client
        ).fetch(query())

    async def fixture_fetch(_: WorldBankConnector, requested: DataQuery):
        assert requested.dataset == "WDI"
        assert requested.dimensions == {
            "country": ["CHN"],
            "indicator": ["SP.POP.TOTL"],
        }
        assert requested.start_period == "2023"
        assert requested.end_period == "2024"
        return fixture_result

    class WorldBankPlanningProvider(DeterministicPlanningProvider):
        async def draft_plan(self, context, data_access=None):
            plan = await super().draft_plan(context, data_access)
            plan.period.start = "2023"
            plan.period.end = "2024"
            plan.period.frequency = "annual"
            plan.data_sources[0].connector_id = "world_bank"
            plan.data_sources[0].dataset = "WDI"
            plan.data_sources[0].indicators = ["SP.POP.TOTL"]
            plan.model_intents[0].variables[0].indicator_code = "SP.POP.TOTL"
            plan.unresolved_items = []
            return plan

    monkeypatch.setattr(WorldBankConnector, "fetch", fixture_fetch)
    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_planning_service.provider = WorldBankPlanningProvider()
    document = planning_session()
    document["request"] = "Compare China's population in 2023 and 2024."
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": document}
        )
        session_hash = created.json()["projection"]["current_snapshot_hash"]
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": {
                    "command_id": "command-wb-draft",
                    "idempotency_key": "wb-draft",
                    "session_id": "planning-1",
                    "expected_stage": "plan",
                    "expected_snapshot_hash": session_hash,
                    "actor": "user",
                    "requested_at": "2026-09-10T12:00:00Z",
                },
                "command": {"type": "submit_clarification", "answers": {}},
            },
        )
        resolution_id = drafted.json()["session"]["currentPlan"]["geographyResolutions"][0][
            "id"
        ]
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": {
                    "command_id": "command-wb-confirm",
                    "idempotency_key": "wb-confirm",
                    "session_id": "planning-1",
                    "expected_stage": "plan",
                    "expected_snapshot_hash": drafted.json()["projection"][
                        "current_snapshot_hash"
                    ],
                    "actor": "user",
                    "requested_at": "2026-09-10T12:01:00Z",
                },
                "command": {"type": "confirm_geography", "resolutionId": resolution_id},
            },
        )
        approved = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": {
                    "command_id": "command-wb-approve",
                    "idempotency_key": "wb-approve",
                    "session_id": "planning-1",
                    "expected_stage": "plan",
                    "expected_snapshot_hash": confirmed.json()["projection"][
                        "current_snapshot_hash"
                    ],
                    "actor": "user",
                    "requested_at": "2026-09-10T12:02:00Z",
                },
                "command": {"type": "plan_next"},
            },
        )

    assert approved.status_code == 200, approved.text
    session = approved.json()["session"]
    assert session["status"] == "data_review"
    assert session["data"]["sourceRuns"][0]["connectorId"] == "world_bank"
    assert "requestedPeriodStart" not in session["data"]["sourceRuns"][0]
    assert "periodResolution" not in session["data"]["sourceRuns"][0]
    assert session["data"]["quality"]["observations"] == 2


def test_world_bank_period_resolution_supports_latest_and_rejects_bad_fiscal_range() -> None:
    current_year = str(datetime.now(timezone.utc).year)
    assert WorkflowDataService._resolve_query_period(
        "world_bank", "2011-12", "latest", "annual"
    ) == ("2012", current_year, "calendar_year_mapping")

    with pytest.raises(DataWorkspaceError, match="Fiscal-year label"):
        WorkflowDataService._resolve_query_period(
            "world_bank", "2011-13", "2024", "annual"
        )
