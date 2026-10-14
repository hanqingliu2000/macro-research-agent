"""Bounded BIS SDMX v2 connector for monthly central-bank policy rates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from macro_research_agent.connectors.base import (
    AuthenticationMode,
    ConnectorCapability,
    DataConnector,
    DataQuery,
    FetchResult,
    SourceProvenance,
)
from macro_research_agent.connectors.cache import PublicResponseCache
from macro_research_agent.connectors.http import ConnectorHttpError, cached_public_get
from macro_research_agent.connectors.rate_limit import PersistentRateLimiter, RateWindow
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class BisConnectorError(ValueError):
    pass


class BisConnector(DataConnector):
    base_url = "https://stats.bis.org/api/v2"
    version = "1.0.0"
    dataset = "POLICY_RATES"
    dataflow = "BIS:WS_CBPOL(1.0)"
    resource_id = "WS_CBPOL"
    dataflow_version = "1.0"
    allowed_indicators = {"POLICY_RATE": "Central bank policy rate"}
    iso3_to_bis = {
        "ARG": "AR",
        "AUS": "AU",
        "BRA": "BR",
        "CAN": "CA",
        "CHE": "CH",
        "CHL": "CL",
        "CHN": "CN",
        "COL": "CO",
        "CZE": "CZ",
        "DNK": "DK",
        "GBR": "GB",
        "HKG": "HK",
        "HUN": "HU",
        "IDN": "ID",
        "IND": "IN",
        "ISR": "IL",
        "JPN": "JP",
        "KOR": "KR",
        "MEX": "MX",
        "MYS": "MY",
        "NOR": "NO",
        "NZL": "NZ",
        "PER": "PE",
        "PHL": "PH",
        "POL": "PL",
        "ROU": "RO",
        "RUS": "RU",
        "SAU": "SA",
        "SGP": "SG",
        "SWE": "SE",
        "THA": "TH",
        "TUR": "TR",
        "USA": "US",
        "ZAF": "ZA",
    }
    expected_dimensions = ("FREQ", "REF_AREA")
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    shared_cache_ttl_seconds = 6 * 60 * 60
    data_accept = "application/vnd.sdmx.data+csv;version=1.0.0"
    structure_accept = "application/vnd.sdmx.structure+json;version=1.0.0"

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        shared_cache_dir: Path | None = None,
        rate_limit_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.cache = PublicResponseCache(raw_dir, shared_cache_dir, self.shared_cache_ttl_seconds)
        root = shared_cache_dir or raw_dir
        self.rate_limiter = PersistentRateLimiter(
            rate_limit_dir or root / "rate_limits", "bis", (RateWindow(60, 20),)
        )
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="bis",
            display_name="BIS · Monthly central bank policy rates",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("stats.bis.org",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise BisConnectorError("Only the registered BIS policy-rate query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise BisConnectorError("BIS policy rates require country and indicator codes.")
        countries = query.dimensions["country"]
        if not 1 <= len(countries) <= 20 or any(item not in cls.iso3_to_bis for item in countries):
            raise BisConnectorError("Unsupported BIS policy-rate country code.")
        if query.dimensions["indicator"] != ["POLICY_RATE"]:
            raise BisConnectorError("BIS supports POLICY_RATE only.")
        if query.frequency != "M":
            raise BisConnectorError("BIS policy rates currently require monthly frequency.")
        month = re.compile(r"[12][0-9]{3}-(0[1-9]|1[0-2])")
        if not query.start_period or not query.end_period:
            raise BisConnectorError("Explicit BIS start/end months are required.")
        if not month.fullmatch(query.start_period) or not month.fullmatch(query.end_period):
            raise BisConnectorError("BIS periods must use YYYY-MM.")
        start_y, start_m = map(int, query.start_period.split("-"))
        end_y, end_m = map(int, query.end_period.split("-"))
        periods = (end_y - start_y) * 12 + end_m - start_m + 1
        if periods < 1 or periods > 1200:
            raise BisConnectorError("BIS requests must cover one month through 100 years.")
        if periods * len(countries) > cls.max_observations:
            raise BisConnectorError("BIS query can exceed 20,000 observations.")

    @classmethod
    def _key(cls, query: DataQuery) -> str:
        areas = "+".join(cls.iso3_to_bis[item] for item in query.dimensions["country"])
        return f"M.{areas}"

    async def _get(
        self,
        *,
        path: str,
        params: dict[str, Any],
        accept: str,
        media_tokens: tuple[str, ...],
        member: str,
    ) -> tuple[bytes, str]:
        try:
            return await cached_public_get(
                provider="BIS",
                member=member,
                base_url=self.base_url,
                path=path,
                params=params,
                accept=accept,
                media_tokens=media_tokens,
                cache=self.cache,
                attempts=self.attempts,
                max_bytes=self.max_bytes,
                client=self.client,
                rate_limiter=self.rate_limiter,
            )
        except (ConnectorHttpError, ValueError) as error:
            raise BisConnectorError(str(error)) from error

    async def _verify_availability(self, query: DataQuery) -> str:
        path = (
            f"availability/dataflow/BIS/{self.resource_id}/{self.dataflow_version}/"
            f"{self._key(query)}/REF_AREA"
        )
        raw, raw_hash = await self._get(
            path=path,
            params={"mode": "exact", "references": "none"},
            accept=self.structure_accept,
            media_tokens=("json",),
            member="availability",
        )
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BisConnectorError("BIS availability response is malformed JSON.") from error

        expected = {self.iso3_to_bis[item] for item in query.dimensions["country"]}
        if payload.get("meta", {}).get("test") is not False:
            raise BisConnectorError("BIS availability came from a test or unmarked surface.")
        available: set[str] = set()
        try:
            constraints = payload["data"]["contentConstraints"]
            for constraint in constraints:
                if constraint.get("agencyID") != "BIS" or constraint.get("version") != "1.0":
                    raise BisConnectorError("BIS availability contract version changed.")
                attachments = constraint["constraintAttachment"]["dataflows"]
                if not any(self.dataflow in item for item in attachments):
                    raise BisConnectorError("BIS availability references the wrong dataflow.")
                for region in constraint["cubeRegions"]:
                    for key_value in region["keyValues"]:
                        if key_value.get("id") == "REF_AREA":
                            available.update(str(item) for item in key_value.get("values", []))
        except (KeyError, TypeError) as error:
            raise BisConnectorError("BIS availability schema is incomplete.") from error
        if not expected.issubset(available):
            raise BisConnectorError("BIS availability does not cover every reviewed economy.")
        return raw_hash

    async def _request_data(self, query: DataQuery) -> tuple[bytes, str]:
        path = f"data/dataflow/BIS/{self.resource_id}/{self.dataflow_version}/{self._key(query)}"
        params = {
            "c[TIME_PERIOD]": f"ge:{query.start_period}+le:{query.end_period}",
            "dimensionAtObservation": "TIME_PERIOD",
        }
        return await self._get(
            path=path,
            params=params,
            accept=self.data_accept,
            media_tokens=("csv",),
            member="data",
        )

    def _normalize(self, raw: bytes, query: DataQuery) -> list[Observation]:
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        except UnicodeDecodeError as error:
            raise BisConnectorError("BIS returned non-UTF-8 CSV.") from error
        required = {*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise BisConnectorError("BIS CSV schema is missing registered dimensions.")
        ordered = [item for item in reader.fieldnames if item in required]
        if ordered != [*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"]:
            raise BisConnectorError("BIS dimension order changed; re-admission required.")
        bis_to_iso3 = {value: key for key, value in self.iso3_to_bis.items()}
        expected = {self.iso3_to_bis[item] for item in query.dimensions["country"]}
        observations: list[Observation] = []
        for row in reader:
            area = str(row.get("REF_AREA") or "")
            period = str(row.get("TIME_PERIOD") or "")
            if area not in expected:
                raise BisConnectorError("BIS returned an economy outside the reviewed query.")
            if row.get("FREQ") != "M" or not (
                str(query.start_period) <= period <= str(query.end_period)
            ):
                raise BisConnectorError("BIS returned a frequency or period outside the query.")
            if row.get("DATAFLOW") != self.dataflow:
                raise BisConnectorError("BIS dataflow version changed; re-admission required.")
            raw_value = str(row.get("OBS_VALUE") or "")
            value: float | None = None
            if raw_value not in {"", "NaN"}:
                try:
                    value = float(raw_value)
                except ValueError as error:
                    raise BisConnectorError("BIS returned a non-numeric value.") from error
                if not math.isfinite(value):
                    raise BisConnectorError("BIS returned a non-finite value.")
            iso3 = bis_to_iso3[area]
            observations.append(
                Observation(
                    provider="Bank for International Settlements",
                    dataset=self.dataset,
                    series_id=f"{iso3}.POLICY_RATE.M",
                    entity_code=iso3,
                    entity_name=str(row.get("Reference area") or row.get("REF_AREA_NAME") or "")
                    or None,
                    indicator_code="POLICY_RATE",
                    indicator_name=self.allowed_indicators["POLICY_RATE"],
                    frequency="M",
                    period=period,
                    value=value,
                    unit=(
                        "Per cent per year"
                        if row.get("UNIT_MEASURE") == "368"
                        else str(
                            row.get("Unit of measure")
                            or row.get("UNIT_MEASURE")
                            or "Per cent per year"
                        )
                    ),
                    scale=(
                        f"10^{row['UNIT_MULT']}" if row.get("UNIT_MULT") not in {None, ""} else None
                    ),
                    status=str(row.get("OBS_STATUS") or "") or None,
                    attributes={
                        "bis": {key: item for key, item in row.items() if key not in required}
                        | {"provider_area": area, "collection": "end_of_period"}
                    },
                )
            )
        return observations

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise BisConnectorError("Discovery term is too long.")
        normalized = term.strip().casefold()
        return [
            {"dataset": self.dataset, "dimension": "indicator", "id": code, "label": label}
            for code, label in self.allowed_indicators.items()
            if normalized in code.casefold() or normalized in label.casefold()
        ]

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        availability_hash = await self._verify_availability(query)
        raw, raw_hash = await self._request_data(query)
        observations = self._normalize(raw, query)
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise BisConnectorError("BIS returned duplicate observation keys.")
        if not observations:
            raise BisConnectorError("No BIS observations matched the reviewed query.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "Bank for International Settlements",
                "dataset": self.dataset,
                "dataflow": self.dataflow,
                "api_version": "v2",
                "availability_sha256": availability_hash,
                "iso3_to_bis": {
                    item: self.iso3_to_bis[item] for item in query.dimensions["country"]
                },
            },
        )
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        retrieved_at = datetime.now(timezone.utc)
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="bis",
                connector_version=self.version,
                provider="Bank for International Settlements",
                dataset=self.dataset,
                source_identifier=(
                    f"{self.base_url}/data/dataflow/BIS/{self.resource_id}/"
                    f"{self.dataflow_version}/[reviewed-key]"
                ),
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "dataflow": self.dataflow,
                    "data_key": self._key(query),
                    "availability_sha256": availability_hash,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=(
                    "Bank for International Settlements, central bank policy rates. "
                    "BIS does not endorse conclusions derived from its statistics. "
                    f"Accessed {retrieved_at.date().isoformat()}."
                ),
            ),
        )
