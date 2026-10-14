from __future__ import annotations

from macro_research_agent.connectors.registry import connector_catalog
from macro_research_agent.knowledge.data_sources import default_data_source_knowledge


def test_catalog_is_valid_versioned_and_aligned_with_available_connectors() -> None:
    catalog = default_data_source_knowledge()
    available_connectors = {
        connector_id
        for connector_id, capability in connector_catalog().items()
        if capability.availability == "available" and connector_id != "local_file"
    }

    assert catalog.schema_version == "data-source-knowledge-v1"
    assert catalog.catalog_version == "1.2.0"
    assert len(catalog.content_sha256 or "") == 64
    assert {provider.connector_id for provider in catalog.providers} == available_connectors
    verified = {
        provider.connector_id: provider.verified_on.isoformat()
        for provider in catalog.providers
    }
    assert verified["imf_data"] == "2026-09-11"
    assert set(verified.values()) <= {"2026-09-10", "2026-09-11"}
    assert all(provider.catalog_examples_not_executable for provider in catalog.providers)


def test_plan_index_ranks_relevant_sources_and_retains_execution_boundary() -> None:
    catalog = default_data_source_knowledge()
    available = [
        "imf_data",
        "world_bank",
        "oecd",
        "eurostat",
        "adb",
        "ecb",
        "bis",
        "un_sdg",
    ]

    inflation = catalog.for_planning("研究中国月度通货膨胀 consumer price index", available)
    forecast = catalog.for_planning("Compare the annual inflation forecast", available)
    population = catalog.for_planning("Compare population and demographics", available)

    assert ("imf_data", "CPI") in {
        (item["connector_id"], item["dataset"]) for item in inflation[:3]
    }
    assert (forecast[0]["connector_id"], forecast[0]["dataset"]) == ("imf_data", "WEO")
    assert population[0]["connector_id"] == "world_bank"
    assert population[0]["indicators"][0]["code"] == "SP.POP.TOTL"
    policy = catalog.for_planning("Compare central bank policy rates", available)
    assert (policy[0]["connector_id"], policy[0]["dataset"]) == ("bis", "POLICY_RATES")
    sdg = catalog.for_planning("SDG 8.1.1 real GDP per capita growth", available)
    assert (sdg[0]["connector_id"], sdg[0]["dataset"]) == ("un_sdg", "SDG_INDICATORS")
    debt = catalog.for_planning("China general government gross debt to GDP", available)
    assert (debt[0]["connector_id"], debt[0]["dataset"]) == ("imf_data", "WEO")
    debt_indicators = {item["code"] for item in debt[0]["indicators"]}
    assert {"GGXWDG", "GGXWDG_NGDP"} <= debt_indicators
    assert all("publication_cadence" in item for item in inflation)
    assert all("not runtime provider metadata" in item["knowledge_notice"] for item in inflation)


def test_plan_index_excludes_unavailable_connector_ids_and_bounds_results() -> None:
    catalog = default_data_source_knowledge()
    matches = catalog.for_planning("inflation", ["world_bank"], max_datasets=1)

    assert len(matches) == 1
    assert matches[0]["connector_id"] == "world_bank"
    assert matches[0]["dataset"] == "WDI"
