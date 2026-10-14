from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.base import DataQuery
from macro_research_agent.connectors.oecd import OecdConnector, OecdConnectorError
from macro_research_agent.connectors.rate_limit import (
    PersistentRateLimiter,
    ProviderRateLimitError,
    RateWindow,
)
from macro_research_agent.workflow.planning_provider import DeterministicPlanningProvider
from test_workflow_planning import planning_session


def query() -> DataQuery:
    return DataQuery(
        dataset="CLI",
        dimensions={"country": ["GBR"], "indicator": ["LI"]},
        frequency="M",
        start_period="2024-01",
        end_period="2024-03",
    )


def metadata_payload(*, version: str = "4.1", extra_dimension: bool = False) -> bytes:
    dimensions = "".join(
        f'<Dimension id="{item}" position="{position}" />'
        for position, item in enumerate(OecdConnector.dimension_ids, start=1)
    )
    if extra_dimension:
        dimensions += '<Dimension id="DRIFT" position="10" />'
    return (
        "<Structure>"
        f'<Dataflow agencyID="OECD.SDD.STES" id="DSD_STES@DF_CLI" version="{version}" />'
        '<DataStructure agencyID="OECD.SDD.STES" id="DSD_STES" version="4.1">'
        f"<DataStructureComponents><DimensionList>{dimensions}"
        '<TimeDimension id="TIME_PERIOD" position="10" />'
        "</DimensionList></DataStructureComponents></DataStructure>"
        "</Structure>"
    ).encode()


def data_payload(*, country: str = "GBR", adjustment: str = "AA") -> bytes:
    header = (
        "STRUCTURE,STRUCTURE_ID,REF_AREA,Reference area,FREQ,Frequency of observation,"
        "MEASURE,Measure,UNIT_MEASURE,Unit of measure,ACTIVITY,Economic activity,"
        "ADJUSTMENT,Adjustment,TRANSFORMATION,Transformation,TIME_HORIZ,Time horizon,"
        "METHODOLOGY,Calculation methodology,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    )
    rows = [
        (
            f"DATAFLOW,OECD.SDD.STES:DSD_STES@DF_CLI(4.1),{country},United Kingdom,"
            f"M,Monthly,LI,Composite leading indicator (CLI),IX,Index,_Z,Not applicable,"
            f"{adjustment},Amplitude adjusted,IX,Index,_Z,Not applicable,H,"
            f"OECD harmonised,{period},{value},A\n"
        )
        for period, value in [("2024-01", "99.61"), ("2024-02", ".."), ("2024-03", "99.97")]
    ]
    return (header + "".join(rows)).encode()


def is_metadata(request: httpx.Request) -> bool:
    return request.url.path.startswith("/public/rest/dataflow/")


@pytest.mark.asyncio
async def test_oecd_fetch_pins_structure_normalizes_and_reuses_across_sessions(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if is_metadata(request):
            assert request.url.path.endswith("/DSD_STES@DF_CLI/4.1")
            return httpx.Response(
                200, content=metadata_payload(), headers={"Content-Type": "application/xml"}
            )
        assert "OECD.SDD.STES,DSD_STES@DF_CLI,4.1" in request.url.path
        assert request.url.params["startPeriod"] == "2024-01"
        return httpx.Response(200, content=data_payload(), headers={"Content-Type": "text/csv"})

    shared = tmp_path / "shared"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = OecdConnector(tmp_path / "session-a", client, shared)
        first_result = await first.fetch(query())
        second = OecdConnector(tmp_path / "session-b", client, shared)
        second_result = await second.fetch(query())

    assert calls == 2
    observations = first_result.dataset.observations
    assert [(item.period, item.value) for item in observations] == [
        ("2024-01", 99.61),
        ("2024-02", None),
        ("2024-03", 99.97),
    ]
    assert observations[0].entity_name == "United Kingdom"
    assert observations[0].unit == "Index"
    assert observations[0].status == "A"
    assert first_result.provenance.request_parameters["dataflow_version"] == "4.1"
    assert "OECD Data Explorer" in str(first_result.provenance.attribution)
    assert "accessed on" in str(first_result.provenance.attribution)
    assert second_result.provenance.raw_sha256 == first_result.provenance.raw_sha256
    assert {item["status"] for item in second.attempts} == {"reused_shared"}
    assert len(list((tmp_path / "session-b").glob("*.raw"))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        (metadata_payload(version="4.2"), "version changed"),
        (metadata_payload(extra_dimension=True), "dimensions changed"),
    ],
)
async def test_oecd_rejects_structure_drift(
    tmp_path: Path, metadata: bytes, message: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=metadata, headers={"Content-Type": "application/xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OecdConnectorError, match=message):
            await OecdConnector(tmp_path, client).metadata()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "message"),
    [
        (data_payload(country="USA"), "outside"),
        (data_payload(adjustment="SA"), "methodology"),
    ],
)
async def test_oecd_rejects_rows_outside_registered_contract(
    tmp_path: Path, content: bytes, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if is_metadata(request):
            return httpx.Response(
                200, content=metadata_payload(), headers={"Content-Type": "application/xml"}
            )
        return httpx.Response(200, content=content, headers={"Content-Type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OecdConnectorError, match=message):
            await OecdConnector(tmp_path, client).fetch(query())


@pytest.mark.asyncio
async def test_oecd_rejects_unsafe_xml_wrong_media_and_oversized_data(
    tmp_path: Path,
) -> None:
    unsafe = b'<!DOCTYPE x [<!ENTITY x "bad">]><Structure>&x;</Structure>'
    responses = [
        (unsafe, "application/xml", "forbidden XML"),
        (metadata_payload(), "text/html", "media type"),
    ]
    for index, (content, media, message) in enumerate(responses):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _, content=content, media=media: httpx.Response(
                    200, content=content, headers={"Content-Type": media}
                )
            )
        ) as client:
            with pytest.raises(OecdConnectorError, match=message):
                await OecdConnector(tmp_path / str(index), client).metadata()

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        content = metadata_payload() if is_metadata(request) else b"x" * (
            OecdConnector.max_bytes + 1
        )
        media = "application/xml" if is_metadata(request) else "text/csv"
        return httpx.Response(200, content=content, headers={"Content-Type": media})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(oversized_handler)
    ) as client:
        with pytest.raises(OecdConnectorError, match="10 MB"):
            await OecdConnector(tmp_path / "oversized", client).fetch(query())


@pytest.mark.asyncio
async def test_oecd_retry_exhaustion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"Content-Type": "application/xml"})

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("macro_research_agent.connectors.oecd.asyncio.sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = OecdConnector(tmp_path, client)
        with pytest.raises(OecdConnectorError, match="503"):
            await connector.metadata()
    assert calls == 3
    assert [item["status"] for item in connector.attempts] == [
        "retryable",
        "retryable",
        "failed",
    ]


@pytest.mark.asyncio
async def test_oecd_rejects_malformed_csv_and_duplicate_keys(tmp_path: Path) -> None:
    duplicate = data_payload() + data_payload().split(b"\n", 1)[1]
    contents = [(b"not,the,registered,schema\n1,2,3,4", "schema"), (duplicate, "duplicate")]
    for index, (content, message) in enumerate(contents):
        def handler(request: httpx.Request, content: bytes = content) -> httpx.Response:
            if is_metadata(request):
                return httpx.Response(
                    200, content=metadata_payload(), headers={"Content-Type": "application/xml"}
                )
            return httpx.Response(200, content=content, headers={"Content-Type": "text/csv"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(OecdConnectorError, match=message):
                await OecdConnector(tmp_path / str(index), client).fetch(query())


def test_oecd_rate_budget_is_shared_and_immediate(tmp_path: Path) -> None:
    now = 1_000.0
    first = PersistentRateLimiter(
        tmp_path, "oecd-test", (RateWindow(60, 2),), clock=lambda: now
    )
    second = PersistentRateLimiter(
        tmp_path, "oecd-test", (RateWindow(60, 2),), clock=lambda: now
    )
    first.acquire()
    second.acquire()
    with pytest.raises(ProviderRateLimitError) as caught:
        first.acquire()
    assert caught.value.retry_after_seconds == 60


@pytest.mark.parametrize(
    "candidate",
    [
        DataQuery(
            dataset="CLI",
            dimensions={"country": ["GBR"], "indicator": ["LI"]},
            frequency="A",
            start_period="2023",
            end_period="2024",
        ),
        DataQuery(
            dataset="OTHER",
            dimensions={"country": ["GBR"], "indicator": ["LI"]},
            frequency="M",
            start_period="2024-01",
            end_period="2024-03",
        ),
        DataQuery(
            dataset="CLI",
            dimensions={"country": ["GBR"], "indicator": ["CPI"]},
            frequency="M",
            start_period="2024-01",
            end_period="2024-03",
        ),
    ],
)
def test_oecd_rejects_unregistered_query_shapes(candidate: DataQuery) -> None:
    with pytest.raises(OecdConnectorError):
        OecdConnector.validate_query(candidate)


@pytest.mark.asyncio
async def test_oecd_plan_approval_creates_data_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if is_metadata(request):
            return httpx.Response(
                200, content=metadata_payload(), headers={"Content-Type": "application/xml"}
            )
        return httpx.Response(200, content=data_payload(), headers={"Content-Type": "text/csv"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider_client:
        fixture_result = await OecdConnector(tmp_path / "fixture", provider_client).fetch(query())

    async def fixture_fetch(_: OecdConnector, requested: DataQuery):
        assert requested.dataset == "CLI"
        assert requested.dimensions == {"country": ["GBR"], "indicator": ["LI"]}
        return fixture_result

    class OecdPlanningProvider(DeterministicPlanningProvider):
        async def draft_plan(self, context, data_access=None):
            plan = await super().draft_plan(context, data_access)
            plan.period.start = "2024-01"
            plan.period.end = "2024-03"
            plan.period.frequency = "monthly"
            plan.geography_resolutions[0].label = "United Kingdom"
            plan.geography_resolutions[0].member_codes = ["GBR"]
            plan.data_sources[0].connector_id = "oecd"
            plan.data_sources[0].dataset = "CLI"
            plan.data_sources[0].indicators = ["LI"]
            plan.model_intents[0].variables[0].indicator_code = "LI"
            plan.unresolved_items = []
            return plan

    monkeypatch.setattr(OecdConnector, "fetch", fixture_fetch)
    app = create_app(Settings(environment="test", runtime_dir=tmp_path / "runtime"))
    app.state.workflow_planning_service.provider = OecdPlanningProvider()
    document = planning_session()
    document["request"] = "Review the UK composite leading indicator in early 2024."
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/v1/workflow/sessions", json={"session": document})
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": {
                    "command_id": "command-oecd-draft",
                    "idempotency_key": "oecd-draft",
                    "session_id": "planning-1",
                    "expected_stage": "plan",
                    "expected_snapshot_hash": created.json()["projection"][
                        "current_snapshot_hash"
                    ],
                    "actor": "user",
                    "requested_at": "2026-09-10T12:00:00Z",
                },
                "command": {"type": "submit_clarification", "answers": {}},
            },
        )
        resolution_id = drafted.json()["session"]["currentPlan"]["geographyResolutions"][
            0
        ]["id"]
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": {
                    "command_id": "command-oecd-confirm",
                    "idempotency_key": "oecd-confirm",
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
                    "command_id": "command-oecd-approve",
                    "idempotency_key": "oecd-approve",
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
    assert session["data"]["sourceRuns"][0]["connectorId"] == "oecd"
    assert session["data"]["quality"]["observations"] == 3
