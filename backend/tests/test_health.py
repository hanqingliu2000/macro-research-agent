import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings


def test_environment_cannot_select_a_planning_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")

    settings = Settings.from_environment()

    assert settings.llm_provider == "deepseek"


@pytest.mark.asyncio
async def test_health_reports_local_environment(tmp_path) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["environment"] == "test"


@pytest.mark.asyncio
async def test_capabilities_expose_policy_boundaries(tmp_path) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["research_modes"] == ["workflow", "agent"]
    assert body["workflow_stages"] == ["plan", "data", "transformation", "output"]
    assert body["workflow_statuses"] == [
        "clarifying",
        "plan_review",
        "acquiring",
        "data_review",
        "pipeline_editing",
        "pipeline_running",
        "output_generating",
        "output_review",
        "completed",
        "failed",
        "cancelled",
    ]
    assert body["acquisition_policy"] == "registered-connectors-only"
    assert body["visual_test_policy"] == "structural-codex-local-and-human-review"
    assert set(body["connectors"]) == {
        "local_file",
        "imf_data",
        "world_bank",
        "oecd",
        "eurostat",
        "adb",
        "ecb",
        "bis",
        "un_sdg",
    }
    assert body["planned_connectors"] == []
    assert body["models"] == [
        "adf",
        "arima",
        "correlation",
        "descriptive",
        "ols",
        "sarimax",
        "var",
    ]
    assert body["planned_models"] == []
    assert body["llm_provider"] == "deepseek"
    assert body["report_author_provider"] == "deepseek"
    assert body["report_author_model"] == "deepseek-flash"
    assert "png" not in body["exports"]
    assert body["planned_exports"] == ["png"]
    assert body["output_review_provider"] == "codex-local"
    assert body["output_review_model"] is None
    assert body["output_review_api_credential_configured"] is False
    assert body["remote_output_review_status"] == "codex_local_enabled"


def test_environment_cannot_select_an_output_review_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MRA_OUTPUT_REVIEW_PROVIDER", "deterministic-local")

    with pytest.raises(ValueError, match="locked to codex-local"):
        Settings.from_environment()


@pytest.mark.asyncio
async def test_capabilities_report_opt_in_codex_local_visual_review(tmp_path) -> None:
    app = create_app(
        Settings(
            environment="test",
            llm_provider="test",
            runtime_dir=tmp_path,
            output_review_provider="codex-local",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = (await client.get("/api/v1/capabilities")).json()
        available = (
            await client.get("/api/v1/registry/capabilities?stage=output&availability=available")
        ).json()

    assert body["output_review_provider"] == "codex-local"
    assert body["output_review_api_credential_configured"] is False
    assert body["remote_output_review_status"] == "codex_local_enabled"
    remote = next(
        item for item in available if item["capability_id"] == "output.review.remote_visual"
    )
    assert remote["handler_ref"] == "workflow.output:review_codex_local"


@pytest.mark.asyncio
async def test_data_source_knowledge_endpoint_is_versioned_ranked_and_bounded(tmp_path) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/data-source-knowledge", params={"q": "population", "limit": 2}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "data-source-knowledge-v1"
    assert body["catalog_version"] == "1.2.0"
    assert len(body["content_sha256"]) == 64
    assert len(body["matches"]) == 2
    assert body["matches"][0]["connector_id"] == "world_bank"
    assert body["matches"][0]["dataset"] == "WDI"


@pytest.mark.asyncio
async def test_source_index_exposes_coverage_and_paginated_dimensions(tmp_path) -> None:
    app = create_app(
        Settings(environment="test", llm_provider="test", runtime_dir=tmp_path / "runtime")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        providers = (await client.get("/api/v1/source-index/providers")).json()
        search = (
            await client.get("/api/v1/source-index/search", params={"q": "government debt"})
        ).json()
        indicators = (
            await client.get(
                "/api/v1/source-index/providers/imf_data/datasets/WEO/dimensions/indicator",
                params={"q": "debt", "limit": 10},
            )
        ).json()

    assert {item["provider_id"] for item in providers} >= {"imf_data", "world_bank"}
    assert {item["coverage_status"] for item in providers} == {"seed"}
    assert search["schema_version"] == "source-index-v2"
    assert search["matches"][0]["dataset_id"] == "WEO"
    assert {item["code"] for item in indicators["values"]} == {
        "GGXWDG",
        "GGXWDG_NGDP",
    }


@pytest.mark.asyncio
async def test_phase3_connector_contract_endpoints_are_bounded(tmp_path) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        ecb = (await client.get("/api/v1/workflow/connectors/ecb")).json()
        bis = (await client.get("/api/v1/workflow/connectors/bis")).json()
        un_sdg = (await client.get("/api/v1/workflow/connectors/un-sdg")).json()

    assert (ecb["dataflow"], ecb["frequency"]) == ("EXR", "M")
    assert (bis["dataflow"], bis["collection"]) == (
        "BIS:WS_CBPOL(1.0)",
        "end_of_period",
    )
    assert (un_sdg["indicator"], list(un_sdg["series"])) == ("8.1.1", ["NY_GDP_PCAP"])
