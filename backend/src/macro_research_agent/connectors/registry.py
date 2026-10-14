from __future__ import annotations

from macro_research_agent.connectors.base import AuthenticationMode, ConnectorCapability

_CATALOG: dict[str, ConnectorCapability] = {
    "local_file": ConnectorCapability(
        connector_id="local_file",
        display_name="Local XLSX/CSV/JSON",
        authentication=AuthenticationMode.NONE,
        supports_discovery=False,
        provider_hosts=(),
    ),
    "imf_data": ConnectorCapability(
        connector_id="imf_data",
        display_name="IMF Data Portal · CPI and WEO",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("api.imf.org",),
        supports_discovery=True,
        supports_observations=True,
        availability="available",
    ),
    "world_bank": ConnectorCapability(
        connector_id="world_bank",
        display_name="World Bank · World Development Indicators",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("api.worldbank.org",),
        supports_discovery=True,
        supports_observations=True,
        availability="available",
    ),
    "oecd": ConnectorCapability(
        connector_id="oecd",
        display_name="OECD Data Explorer · Composite Leading Indicators",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("sdmx.oecd.org",),
        supports_discovery=True,
        supports_observations=True,
        availability="available",
    ),
    "eurostat": ConnectorCapability(
        connector_id="eurostat",
        display_name="Eurostat · Monthly all-items HICP index",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("ec.europa.eu",),
        supports_discovery=True,
        supports_observations=True,
        availability="available",
    ),
    "adb": ConnectorCapability(
        connector_id="adb",
        display_name="ADB Key Indicators · National Accounts",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("kidb.adb.org",),
        supports_discovery=True,
        supports_observations=True,
        availability="available",
    ),
    "ecb": ConnectorCapability(
        connector_id="ecb",
        display_name="ECB · Monthly euro reference exchange rates",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("data-api.ecb.europa.eu",),
        availability="available",
    ),
    "bis": ConnectorCapability(
        connector_id="bis",
        display_name="BIS · Monthly central bank policy rates",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("stats.bis.org",),
        availability="available",
    ),
    "un_sdg": ConnectorCapability(
        connector_id="un_sdg",
        display_name="UN Statistics · SDG 8.1.1 real GDP per capita growth",
        authentication=AuthenticationMode.NONE,
        provider_hosts=("unstats.un.org",),
        availability="available",
    ),
}


def connector_catalog() -> dict[str, ConnectorCapability]:
    return dict(_CATALOG)


def capability_for(connector_id: str) -> ConnectorCapability:
    try:
        return _CATALOG[connector_id]
    except KeyError as exc:
        raise ValueError(f"Connector is not registered: {connector_id}") from exc
