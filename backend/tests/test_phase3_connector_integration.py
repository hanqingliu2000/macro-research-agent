from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.connectors.base import DataQuery, FetchResult, SourceProvenance
from macro_research_agent.connectors.bis import BisConnector
from macro_research_agent.connectors.ecb import EcbConnector
from macro_research_agent.connectors.imf import ImfDataConnector
from macro_research_agent.connectors.un_sdg import UnSdgConnector
from macro_research_agent.connectors.world_bank import WorldBankConnector
from macro_research_agent.data.schemas import NormalizedDataset, Observation
from macro_research_agent.workflow.api_schemas import WorkflowSessionDocument
from test_workflow_planning import meta, planning_session


def fixture_result(
    connector_id: str, dataset: str, indicator: str, query: DataQuery
) -> FetchResult:
    return FetchResult(
        dataset=NormalizedDataset(
            observations=[
                Observation(
                    provider="Fixture",
                    dataset=dataset,
                    series_id=f"CHN.{indicator}.A",
                    entity_code="CHN",
                    indicator_code=indicator,
                    frequency="A",
                    period="2023",
                    value=1.0,
                )
            ],
            dimensions=query.dimensions,
        ),
        provenance=SourceProvenance(
            connector_id=connector_id,
            connector_version="1.0.0",
            provider="Fixture",
            dataset=dataset,
            source_identifier=f"fixture:{connector_id}:{dataset}",
            retrieved_at=datetime.now(timezone.utc),
            request_parameters=query.model_dump(mode="json"),
            raw_sha256=("a" if connector_id == "imf_data" else "b") * 64,
            normalized_sha256=("c" if connector_id == "imf_data" else "d") * 64,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connector_id", "connector_class", "dataset", "indicator", "frequency", "plan_frequency"),
    [
        ("ecb", EcbConnector, "EXCHANGE_RATES", "EUR_REFERENCE_RATE", "M", "monthly"),
        ("bis", BisConnector, "POLICY_RATES", "POLICY_RATE", "M", "monthly"),
        ("un_sdg", UnSdgConnector, "SDG_INDICATORS", "NY_GDP_PCAP", "A", "annual"),
    ],
)
async def test_plan_source_initializes_session_owned_data_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connector_id: str,
    connector_class: type,
    dataset: str,
    indicator: str,
    frequency: str,
    plan_frequency: str,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path / connector_id))
    session = planning_session()
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(session))
    start, end, period = (
        ("2023-01", "2023-02", "2023-01") if frequency == "M" else ("2022", "2023", "2022")
    )
    session["currentPlan"] = {
        "dataSources": [
            {"connectorId": connector_id, "dataset": dataset, "indicators": [indicator]}
        ],
        "geographyResolutions": [{"memberCodes": ["CHN"]}],
        "period": {"frequency": plan_frequency, "start": start, "end": end},
    }
    expected_query = DataQuery(
        dataset=dataset,
        dimensions={"country": ["CHN"], "indicator": [indicator]},
        frequency=frequency,
        start_period=start,
        end_period=end,
    )
    result = FetchResult(
        dataset=NormalizedDataset(
            observations=[
                Observation(
                    provider="Fixture",
                    dataset=dataset,
                    series_id=f"CHN.{indicator}.{frequency}",
                    entity_code="CHN",
                    indicator_code=indicator,
                    frequency=frequency,
                    period=period,
                    value=1.0,
                )
            ],
            dimensions=expected_query.dimensions,
        ),
        provenance=SourceProvenance(
            connector_id=connector_id,
            connector_version="1.0.0",
            provider="Fixture",
            dataset=dataset,
            source_identifier="fixture:registered",
            retrieved_at=datetime.now(timezone.utc),
            request_parameters=expected_query.model_dump(mode="json"),
            raw_sha256="a" * 64,
            normalized_sha256="b" * 64,
        ),
    )

    async def fixture_fetch(_: Any, requested: DataQuery) -> FetchResult:
        assert requested == expected_query
        return result

    monkeypatch.setattr(connector_class, "fetch", fixture_fetch)
    workspace = await app.state.workflow_data_service.initialize_registered_connector_payload(
        session, connector_id
    )

    assert workspace["sourceRuns"][0]["connectorId"] == connector_id
    assert workspace["quality"]["observations"] == 1
    assert workspace["activeSnapshotId"]


@pytest.mark.asyncio
async def test_open_ended_annual_plan_uses_a_concrete_audited_query_upper_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path))
    session = planning_session()
    app.state.workflow_repository.create(WorkflowSessionDocument.model_validate(session))
    session["currentPlan"] = {
        "dataSources": [
            {
                "connectorId": "world_bank",
                "dataset": "WDI",
                "indicators": ["NY.GDP.MKTP.KD.ZG"],
            }
        ],
        "geographyResolutions": [{"memberCodes": ["CHN"]}],
        "period": {
            "frequency": "annual",
            "start": "2020",
            "end": "latest available year",
        },
    }
    expected_end = str(datetime.now(timezone.utc).year)

    async def world_bank_fetch(_: Any, query: DataQuery) -> FetchResult:
        assert query.end_period == expected_end
        return fixture_result("world_bank", "WDI", "NY.GDP.MKTP.KD.ZG", query)

    monkeypatch.setattr(WorldBankConnector, "fetch", world_bank_fetch)
    workspace = await app.state.workflow_data_service.initialize_registered_connector_payload(
        session, "world_bank"
    )

    run = workspace["sourceRuns"][0]
    assert run["requestedPeriodEnd"] == "latest available year"
    assert run["resolvedPeriodEnd"] == expected_end
    assert run["periodResolution"] == "query_upper_bound"
    event = next(
        item
        for item in app.state.workflow_repository.trace("planning-1")
        if item.event_type == "data.period_bound_resolved"
    )
    assert event.payload["resolved_end"] == expected_end
    assert event.payload["semantics"] == "query_upper_bound"


@pytest.mark.asyncio
async def test_multi_source_plan_requires_reviewed_canonical_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def imf_fetch(_: Any, query: DataQuery) -> FetchResult:
        return fixture_result("imf_data", query.dataset, "NGDP_RPCH", query)

    async def world_bank_fetch(_: Any, query: DataQuery) -> FetchResult:
        return fixture_result("world_bank", query.dataset, "NE.GDI.TOTL.ZS", query)

    monkeypatch.setattr(ImfDataConnector, "fetch", imf_fetch)
    monkeypatch.setattr(WorldBankConnector, "fetch", world_bank_fetch)
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/workflow/sessions", json={"session": planning_session()}
        )
        drafted = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(created.json()["projection"]["current_snapshot_hash"], "draft-multi"),
                "command": {
                    "type": "submit_clarification",
                    "answers": {
                        "geography_scope": "China",
                        "period_frequency": "2020-2024 annual",
                    },
                },
            },
        )
        assert drafted.status_code == 200, drafted.text
        saved = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(drafted.json()["projection"]["current_snapshot_hash"], "save-multi"),
                "command": {
                    "type": "save_plan",
                    "changes": {
                        "dataSources": [
                            {
                                "connectorId": "imf_data",
                                "dataset": "WEO",
                                "indicators": ["NGDP_RPCH"],
                                "queryIntent": "Real GDP growth",
                            },
                            {
                                "connectorId": "world_bank",
                                "dataset": "WDI",
                                "indicators": ["NE.GDI.TOTL.ZS"],
                                "queryIntent": "Investment share",
                            },
                        ],
                        "modelIntents": [
                            {
                                "capabilityId": "descriptive",
                                "id": "descriptive",
                                "purpose": "Describe growth and investment.",
                                "label": "Describe growth and investment.",
                                "enabled": True,
                                "variables": [
                                    {
                                        "indicatorCode": "NGDP_RPCH",
                                        "role": "descriptive",
                                        "order": 1,
                                    },
                                    {
                                        "indicatorCode": "NE.GDI.TOTL.ZS",
                                        "role": "descriptive",
                                        "order": 2,
                                    },
                                ],
                                "targetIndicators": ["NGDP_RPCH", "NE.GDI.TOTL.ZS"],
                            }
                        ],
                        "unresolvedItems": [],
                    },
                },
            },
        )
        confirmed = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(saved.json()["projection"]["current_snapshot_hash"], "confirm-multi"),
                "command": {"type": "confirm_geography", "resolutionId": "geo-primary"},
            },
        )
        acquired = await client.post(
            "/api/v1/workflow/sessions/planning-1/plan/commands",
            json={
                "meta": meta(
                    confirmed.json()["projection"]["current_snapshot_hash"], "acquire-multi"
                ),
                "command": {"type": "plan_next"},
            },
        )
        assert acquired.status_code == 200, acquired.text
        data = acquired.json()["session"]["data"]
        assert len(data["sourceRuns"]) == 2
        assert len(data["snapshots"]) == 3
        assert data["mergeReview"]["status"] == "waiting_for_review"
        preview = await client.get(
            "/api/v1/workflow/sessions/planning-1/data/preview?offset=0&limit=10"
        )
        assert {row["source_connector_id"] for row in preview.json()["rows"]} == {
            "imf_data",
            "world_bank",
        }
        blocked = await client.post(
            "/api/v1/workflow/sessions/planning-1/data/commands",
            json={
                "meta": {
                    **meta(
                        acquired.json()["projection"]["current_snapshot_hash"],
                        "blocked-before-merge",
                    ),
                    "expected_stage": "data",
                },
                "command": {"type": "data_next"},
            },
        )
        assert blocked.status_code == 422
        approved = await client.post(
            "/api/v1/workflow/sessions/planning-1/data/commands",
            json={
                "meta": {
                    **meta(
                        acquired.json()["projection"]["current_snapshot_hash"],
                        "approve-merge",
                    ),
                    "expected_stage": "data",
                },
                "command": {"type": "approve_data_merge"},
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["session"]["data"]["mergeReview"]["status"] == "approved"
        assert any(
            node["kind"] == "data_merge" and node["status"] == "approved"
            for node in approved.json()["session"]["nodes"]
        )
        advanced = await client.post(
            "/api/v1/workflow/sessions/planning-1/data/commands",
            json={
                "meta": {
                    **meta(
                        approved.json()["projection"]["current_snapshot_hash"],
                        "data-next-after-merge",
                    ),
                    "expected_stage": "data",
                },
                "command": {"type": "data_next"},
            },
        )
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["session"]["activeStage"] == "transformation"
