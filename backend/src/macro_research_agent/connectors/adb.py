"""Bounded ADB Key Indicators connector for annual national accounts."""

from __future__ import annotations

import asyncio
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
from macro_research_agent.connectors.rate_limit import (
    PersistentRateLimiter,
    ProviderRateLimitError,
    RateWindow,
)
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class AdbConnectorError(ValueError):
    pass


class AdbConnector(DataConnector):
    base_url = "https://kidb.adb.org/api/v5/sdmx"
    version = "1.0.0"
    dataset = "NATIONAL_ACCOUNTS"
    dataflow = "ADB,DF_NA"
    registered_dataflow_version = "1.0"
    allowed_indicators = {
        "NGDP_XDC": "Gross domestic product, current local currency",
        "NGDPVA_XDC": "Gross value added, current local currency",
    }
    iso3_to_adb = {
        "AFG": "AFG",
        "ARM": "ARM",
        "AUS": "AUS",
        "AZE": "AZE",
        "BGD": "BAN",
        "BTN": "BHU",
        "BRN": "BRU",
        "CHN": "PRC",
        "COK": "COO",
        "FJI": "FIJ",
        "GEO": "GEO",
        "HKG": "HKG",
        "IDN": "INO",
        "IND": "IND",
        "JPN": "JPN",
        "KAZ": "KAZ",
        "KGZ": "KGZ",
        "KHM": "CAM",
        "KIR": "KIR",
        "KOR": "KOR",
        "LAO": "LAO",
        "LKA": "SRI",
        "MDV": "MLD",
        "MHL": "RMI",
        "MMR": "MYA",
        "MNG": "MNG",
        "MYS": "MAL",
        "NAU": "NAU",
        "NPL": "NEP",
        "NZL": "NZL",
        "PAK": "PAK",
        "PHL": "PHI",
        "PLW": "PAL",
        "PNG": "PNG",
        "SGP": "SIN",
        "SLB": "SOL",
        "THA": "THA",
        "TJK": "TAJ",
        "TKM": "TKM",
        "TLS": "TLS",
        "TON": "TON",
        "TUV": "TUV",
        "UZB": "UZB",
        "VNM": "VIE",
        "VUT": "VAN",
        "WSM": "SAM",
    }
    expected_dimensions = ("FREQ", "INDICATOR", "ECONOMY_CODE")
    shared_cache_ttl_seconds = 12 * 60 * 60
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    accept = "text/csv"

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        shared_cache_dir: Path | None = None,
        rate_limit_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.cache = PublicResponseCache(raw_dir, shared_cache_dir, self.shared_cache_ttl_seconds)
        shared_root = shared_cache_dir or raw_dir
        self.rate_limiter = PersistentRateLimiter(
            rate_limit_dir or shared_root / "rate_limits",
            "adb",
            (RateWindow(60, 18),),
        )
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="adb",
            display_name="ADB Key Indicators · National Accounts",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("kidb.adb.org",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise AdbConnectorError("Only the registered ADB national-accounts query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise AdbConnectorError("ADB national accounts requires country and indicator codes.")
        countries = query.dimensions["country"]
        indicators = query.dimensions["indicator"]
        if not 1 <= len(countries) <= 20 or any(item not in cls.iso3_to_adb for item in countries):
            raise AdbConnectorError("Unsupported ADB economy code.")
        if not 1 <= len(indicators) <= 15 or any(
            item not in cls.allowed_indicators for item in indicators
        ):
            raise AdbConnectorError("Unsupported ADB national-accounts indicator.")
        if query.frequency != "A":
            raise AdbConnectorError("ADB national accounts currently supports annual frequency.")
        if not query.start_period or not query.end_period:
            raise AdbConnectorError("Explicit ADB start/end years are required.")
        if not re.fullmatch(r"20[0-2][0-9]", query.start_period) or not re.fullmatch(
            r"20[0-2][0-9]", query.end_period
        ):
            raise AdbConnectorError("ADB periods must be years from 2000 through 2024.")
        start = int(query.start_period)
        end = int(query.end_period)
        if start > end or start < 2000 or end > 2024:
            raise AdbConnectorError("ADB periods must be ordered within 2000 through 2024.")
        if (end - start + 1) * len(countries) * len(indicators) > cls.max_observations:
            raise AdbConnectorError("ADB query can exceed 20,000 observations.")

    @classmethod
    def _key(cls, query: DataQuery) -> str:
        indicators = "+".join(query.dimensions["indicator"])
        economies = "+".join(cls.iso3_to_adb[item] for item in query.dimensions["country"])
        return f"A.{indicators}.{economies}"

    async def _request(self, query: DataQuery) -> tuple[bytes, str]:
        path = f"data/{self.dataflow}/{self._key(query)}"
        params = {
            "startPeriod": str(query.start_period),
            "endPeriod": str(query.end_period),
            "version": "3.0",
            "format": "sdmx-csv",
        }
        request_key = self.cache.request_key("adb", "GET", path, params, self.accept)
        cached = self.cache.get(request_key)
        if cached is not None:
            self.attempts.append(
                {
                    "member": "data",
                    "attempt": 0,
                    "status": cached.scope,
                    "raw_sha256": cached.raw_sha256,
                }
            )
            return cached.content, cached.raw_sha256

        async def read(client: httpx.AsyncClient) -> bytes:
            for attempt in range(3):
                try:
                    self.rate_limiter.acquire()
                    async with client.stream(
                        "GET",
                        f"{self.base_url}/{path}",
                        params=params,
                        headers={"Accept": self.accept, "Accept-Encoding": "identity"},
                        follow_redirects=False,
                        timeout=httpx.Timeout(connect=10, read=90, write=10, pool=10),
                    ) as response:
                        retryable = response.status_code == 429 or response.status_code in {
                            500,
                            502,
                            503,
                            504,
                        }
                        if retryable and attempt < 2:
                            self.attempts.append(
                                {
                                    "member": "data",
                                    "attempt": attempt + 1,
                                    "status": "retryable",
                                }
                            )
                            retry_after = response.headers.get("Retry-After", "1")
                            delay = (
                                min(float(retry_after), 5.0)
                                if retry_after.isdigit()
                                else float(attempt + 1)
                            )
                            await asyncio.sleep(delay)
                            continue
                        if response.status_code != 200:
                            self.attempts.append(
                                {
                                    "member": "data",
                                    "attempt": attempt + 1,
                                    "status": "failed",
                                }
                            )
                            raise AdbConnectorError(
                                f"ADB request failed (HTTP {response.status_code})."
                            )
                        media = response.headers.get("content-type", "").lower()
                        if "csv" not in media and "text/plain" not in media:
                            raise AdbConnectorError("ADB returned an unexpected media type.")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise AdbConnectorError(
                                    "ADB response exceeds the 10 MB response limit."
                                )
                        return bytes(chunks)
                except ProviderRateLimitError as error:
                    self.attempts.append(
                        {
                            "member": "data",
                            "attempt": attempt + 1,
                            "status": "rate_limited",
                        }
                    )
                    raise AdbConnectorError(str(error)) from error
                except httpx.TransportError as error:
                    self.attempts.append(
                        {
                            "member": "data",
                            "attempt": attempt + 1,
                            "status": "retryable" if attempt < 2 else "failed",
                        }
                    )
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise AdbConnectorError("ADB connection failed; retry later.") from error
            raise AdbConnectorError("ADB request failed.")

        if self.client is not None:
            raw = await read(self.client)
        else:
            async with httpx.AsyncClient() as client:
                raw = await read(client)
        stored = self.cache.put(request_key, raw)
        self.attempts.append(
            {
                "member": "data",
                "attempt": 1,
                "status": "completed",
                "raw_sha256": stored.raw_sha256,
            }
        )
        return raw, stored.raw_sha256

    def _normalize(self, raw: bytes, query: DataQuery) -> list[Observation]:
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        except UnicodeDecodeError as error:
            raise AdbConnectorError("ADB returned non-UTF-8 CSV.") from error
        required = {*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AdbConnectorError("ADB CSV schema is missing registered dimensions.")
        code_columns = [item for item in reader.fieldnames if item in required]
        if code_columns != [*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"]:
            raise AdbConnectorError("ADB CSV dimension order changed; re-admission required.")
        adb_to_iso3 = {value: key for key, value in self.iso3_to_adb.items()}
        expected_economies = {
            self.iso3_to_adb[item] for item in query.dimensions["country"]
        }
        observations: list[Observation] = []
        for row in reader:
            economy = str(row.get("ECONOMY_CODE") or "")
            indicator = str(row.get("INDICATOR") or "")
            period = str(row.get("TIME_PERIOD") or "")
            if economy not in expected_economies or indicator not in query.dimensions["indicator"]:
                raise AdbConnectorError("ADB returned a series outside the reviewed query.")
            if row.get("DATAFLOW") != "ADB:DF_NA(1.0)":
                raise AdbConnectorError("ADB dataflow version changed; re-admission required.")
            if row.get("FREQ") != "A" or not (
                str(query.start_period) <= period <= str(query.end_period)
            ):
                raise AdbConnectorError("ADB returned a frequency or period outside the query.")
            raw_value = str(row.get("OBS_VALUE") or "")
            value: float | None = None
            if raw_value not in {"", ".."}:
                try:
                    value = float(raw_value)
                except ValueError as error:
                    raise AdbConnectorError("ADB returned a non-numeric value.") from error
                if not math.isfinite(value):
                    raise AdbConnectorError("ADB returned a non-finite value.")
            iso3 = adb_to_iso3[economy]
            observations.append(
                Observation(
                    provider="Asian Development Bank",
                    dataset=self.dataset,
                    series_id=f"{iso3}.{indicator}.A",
                    entity_code=iso3,
                    entity_name=str(row.get("Economy") or row.get("ECONOMY_NAME") or "") or None,
                    indicator_code=indicator,
                    indicator_name=str(row.get("Indicator") or "")
                    or self.allowed_indicators[indicator],
                    frequency="A",
                    period=period,
                    value=value,
                    unit=str(row.get("UNIT") or "") or None,
                    scale=(
                        f"10^{row['UNIT_MULT']}"
                        if row.get("UNIT_MULT") not in {None, ""}
                        else None
                    ),
                    status=str(row.get("OBS_STATUS") or "") or None,
                    attributes={
                        "adb": {
                            key: item
                            for key, item in row.items()
                            if key
                            not in {
                                "FREQ",
                                "INDICATOR",
                                "ECONOMY_CODE",
                                "TIME_PERIOD",
                                "OBS_VALUE",
                            }
                        }
                        | {"provider_economy_code": economy}
                    },
                )
            )
        return observations

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise AdbConnectorError("Discovery term is too long.")
        normalized = term.strip().casefold()
        return [
            {
                "dataset": self.dataset,
                "dimension": "indicator",
                "id": code,
                "label": label,
            }
            for code, label in self.allowed_indicators.items()
            if normalized in {code.casefold(), label.casefold()} or normalized in label.casefold()
        ]

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        raw, raw_hash = await self._request(query)
        observations = self._normalize(raw, query)
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise AdbConnectorError("ADB returned duplicate observation keys.")
        if not observations:
            raise AdbConnectorError("No ADB observations matched the reviewed query.")
        if len(observations) > self.max_observations:
            raise AdbConnectorError("ADB result exceeds 20,000 observations.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "Asian Development Bank",
                "dataset": self.dataset,
                "dataflow": self.dataflow,
                "api_version": "v5",
                "sdmx_version": "3.0",
                "dataflow_version": self.registered_dataflow_version,
                "iso3_to_adb": {
                    item: self.iso3_to_adb[item] for item in query.dimensions["country"]
                },
            },
        )
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        retrieved_at = datetime.now(timezone.utc)
        underlying_sources = sorted(
            {
                str(item.attributes["adb"].get("DATA_SOURCE"))
                for item in observations
                if item.attributes["adb"].get("DATA_SOURCE")
            }
        )
        attribution = (
            "Asian Development Bank: Key Indicators Database Online "
            f"(https://kidb.adb.org). Accessed on {retrieved_at.date().isoformat()}."
        )
        if underlying_sources:
            attribution += " Underlying source(s): " + "; ".join(underlying_sources) + "."
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="adb",
                connector_version=self.version,
                provider="Asian Development Bank",
                dataset=self.dataset,
                source_identifier=f"{self.base_url}/data/{self.dataflow}/[reviewed-key]",
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "dataflow": self.dataflow,
                    "api_version": "v5",
                    "sdmx_version": "3.0",
                    "dataflow_version": self.registered_dataflow_version,
                    "data_key": self._key(query),
                    "raw_response_hash": raw_hash,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=attribution,
            ),
        )
