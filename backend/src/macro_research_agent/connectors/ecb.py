"""Bounded ECB Data Portal connector for monthly euro reference exchange rates."""

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
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class EcbConnectorError(ValueError):
    pass


class EcbConnector(DataConnector):
    base_url = "https://data-api.ecb.europa.eu/service"
    version = "1.0.0"
    dataset = "EXCHANGE_RATES"
    dataflow = "EXR"
    dataflow_version = "1.0"
    allowed_indicators = {
        "EUR_REFERENCE_RATE": "Euro foreign-exchange reference rate, monthly average"
    }
    iso3_to_currency = {
        "AUS": "AUD",
        "BRA": "BRL",
        "CAN": "CAD",
        "CHE": "CHF",
        "CHN": "CNY",
        "CZE": "CZK",
        "DNK": "DKK",
        "GBR": "GBP",
        "HKG": "HKD",
        "HUN": "HUF",
        "IDN": "IDR",
        "IND": "INR",
        "ISL": "ISK",
        "JPN": "JPY",
        "KOR": "KRW",
        "MEX": "MXN",
        "MYS": "MYR",
        "NOR": "NOK",
        "NZL": "NZD",
        "PHL": "PHP",
        "POL": "PLN",
        "ROU": "RON",
        "SGP": "SGD",
        "SWE": "SEK",
        "THA": "THB",
        "TUR": "TRY",
        "USA": "USD",
        "ZAF": "ZAR",
    }
    expected_dimensions = (
        "FREQ",
        "CURRENCY",
        "CURRENCY_DENOM",
        "EXR_TYPE",
        "EXR_SUFFIX",
    )
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    shared_cache_ttl_seconds = 6 * 60 * 60
    accept = "text/csv"

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        shared_cache_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.cache = PublicResponseCache(raw_dir, shared_cache_dir, self.shared_cache_ttl_seconds)
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="ecb",
            display_name="ECB · Monthly euro reference exchange rates",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("data-api.ecb.europa.eu",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise EcbConnectorError("Only the registered ECB exchange-rate query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise EcbConnectorError("ECB exchange rates require country and indicator codes.")
        countries = query.dimensions["country"]
        if not 1 <= len(countries) <= 20 or any(
            item not in cls.iso3_to_currency for item in countries
        ):
            raise EcbConnectorError("Unsupported ECB reference-rate country code.")
        if query.dimensions["indicator"] != ["EUR_REFERENCE_RATE"]:
            raise EcbConnectorError("ECB supports EUR_REFERENCE_RATE only.")
        if query.frequency != "M":
            raise EcbConnectorError("ECB reference rates currently require monthly frequency.")
        month = re.compile(r"[12][0-9]{3}-(0[1-9]|1[0-2])")
        if not query.start_period or not query.end_period:
            raise EcbConnectorError("Explicit ECB start/end months are required.")
        if not month.fullmatch(query.start_period) or not month.fullmatch(query.end_period):
            raise EcbConnectorError("ECB periods must use YYYY-MM.")
        start_y, start_m = map(int, query.start_period.split("-"))
        end_y, end_m = map(int, query.end_period.split("-"))
        periods = (end_y - start_y) * 12 + end_m - start_m + 1
        if periods < 1 or periods > 600:
            raise EcbConnectorError("ECB requests must cover one month through 50 years.")
        if periods * len(countries) > cls.max_observations:
            raise EcbConnectorError("ECB query can exceed 20,000 observations.")

    @classmethod
    def _key(cls, query: DataQuery) -> str:
        currencies = "+".join(cls.iso3_to_currency[item] for item in query.dimensions["country"])
        return f"M.{currencies}.EUR.SP00.A"

    async def _request(self, query: DataQuery) -> tuple[bytes, str]:
        path = f"data/{self.dataflow}/{self._key(query)}"
        params = {
            "startPeriod": str(query.start_period),
            "endPeriod": str(query.end_period),
            "detail": "full",
            "includeHistory": "false",
            "format": "csvdata",
        }
        try:
            return await cached_public_get(
                provider="ECB",
                member="data",
                base_url=self.base_url,
                path=path,
                params=params,
                accept=self.accept,
                media_tokens=("csv", "text/plain"),
                cache=self.cache,
                attempts=self.attempts,
                max_bytes=self.max_bytes,
                client=self.client,
            )
        except ConnectorHttpError as error:
            raise EcbConnectorError(str(error)) from error

    def _normalize(self, raw: bytes, query: DataQuery) -> list[Observation]:
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        except UnicodeDecodeError as error:
            raise EcbConnectorError("ECB returned non-UTF-8 CSV.") from error
        required = {*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise EcbConnectorError("ECB CSV schema is missing registered dimensions.")
        ordered = [item for item in reader.fieldnames if item in required]
        if ordered != [*self.expected_dimensions, "TIME_PERIOD", "OBS_VALUE"]:
            raise EcbConnectorError("ECB dimension order changed; re-admission required.")
        currency_to_iso3 = {value: key for key, value in self.iso3_to_currency.items()}
        expected = {self.iso3_to_currency[item] for item in query.dimensions["country"]}
        observations: list[Observation] = []
        for row in reader:
            currency = str(row.get("CURRENCY") or "")
            period = str(row.get("TIME_PERIOD") or "")
            if currency not in expected:
                raise EcbConnectorError("ECB returned a currency outside the reviewed query.")
            if (
                row.get("FREQ") != "M"
                or row.get("CURRENCY_DENOM") != "EUR"
                or row.get("EXR_TYPE") != "SP00"
                or row.get("EXR_SUFFIX") != "A"
                or not str(query.start_period) <= period <= str(query.end_period)
            ):
                raise EcbConnectorError("ECB returned a series outside the pinned contract.")
            dataflow = str(row.get("DATAFLOW") or "")
            if dataflow and dataflow not in {"ECB:EXR(1.0)", "ECB,EXR,1.0"}:
                raise EcbConnectorError("ECB dataflow version changed; re-admission required.")
            raw_value = str(row.get("OBS_VALUE") or "")
            value: float | None = None
            if raw_value not in {"", "NaN"}:
                try:
                    value = float(raw_value)
                except ValueError as error:
                    raise EcbConnectorError("ECB returned a non-numeric value.") from error
                if not math.isfinite(value):
                    raise EcbConnectorError("ECB returned a non-finite value.")
            iso3 = currency_to_iso3[currency]
            observations.append(
                Observation(
                    provider="European Central Bank",
                    dataset=self.dataset,
                    series_id=f"{iso3}.EUR_REFERENCE_RATE.M",
                    entity_code=iso3,
                    entity_name=str(row.get("CURRENCY_NAME") or "") or None,
                    indicator_code="EUR_REFERENCE_RATE",
                    indicator_name=self.allowed_indicators["EUR_REFERENCE_RATE"],
                    frequency="M",
                    period=period,
                    value=value,
                    unit=str(row.get("UNIT") or "Foreign currency per euro"),
                    scale=(
                        f"10^{row['UNIT_MULT']}" if row.get("UNIT_MULT") not in {None, ""} else None
                    ),
                    status=str(row.get("OBS_STATUS") or "") or None,
                    attributes={
                        "ecb": {key: item for key, item in row.items() if key not in required}
                        | {"provider_currency": currency, "denominator": "EUR"}
                    },
                )
            )
        return observations

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise EcbConnectorError("Discovery term is too long.")
        normalized = term.strip().casefold()
        return [
            {"dataset": self.dataset, "dimension": "indicator", "id": code, "label": label}
            for code, label in self.allowed_indicators.items()
            if normalized in code.casefold() or normalized in label.casefold()
        ]

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        raw, raw_hash = await self._request(query)
        observations = self._normalize(raw, query)
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise EcbConnectorError("ECB returned duplicate observation keys.")
        if not observations:
            raise EcbConnectorError("No ECB observations matched the reviewed query.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "European Central Bank",
                "dataset": self.dataset,
                "dataflow": self.dataflow,
                "dataflow_version": self.dataflow_version,
                "include_history": False,
                "iso3_to_currency": {
                    item: self.iso3_to_currency[item] for item in query.dimensions["country"]
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
                connector_id="ecb",
                connector_version=self.version,
                provider="European Central Bank",
                dataset=self.dataset,
                source_identifier=f"{self.base_url}/data/{self.dataflow}/[reviewed-key]",
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "dataflow": self.dataflow,
                    "dataflow_version": self.dataflow_version,
                    "data_key": self._key(query),
                    "detail": "full",
                    "include_history": False,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=(
                    "European Central Bank, euro foreign exchange reference rates. "
                    f"Accessed {retrieved_at.date().isoformat()}."
                ),
            ),
        )
