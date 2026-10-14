"""Bounded Eurostat Statistics API connector for monthly all-items HICP indices."""

from __future__ import annotations

import asyncio
import hashlib
import itertools
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
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class EurostatConnectorError(ValueError):
    pass


class EurostatConnector(DataConnector):
    base_url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0"
    version = "1.0.0"
    dataset = "HICP_INDEX"
    provider_dataset = "prc_hicp_minr"
    allowed_indicators = {"TOTAL": "All-items HICP (COICOP 2018 total)"}
    iso3_to_geo = {
        "AUT": "AT",
        "BEL": "BE",
        "BGR": "BG",
        "CHE": "CH",
        "CYP": "CY",
        "CZE": "CZ",
        "DEU": "DE",
        "DNK": "DK",
        "ESP": "ES",
        "EST": "EE",
        "FIN": "FI",
        "FRA": "FR",
        "GRC": "EL",
        "HRV": "HR",
        "HUN": "HU",
        "IRL": "IE",
        "ISL": "IS",
        "ITA": "IT",
        "LTU": "LT",
        "LUX": "LU",
        "LVA": "LV",
        "MLT": "MT",
        "NLD": "NL",
        "NOR": "NO",
        "POL": "PL",
        "PRT": "PT",
        "ROU": "RO",
        "SVK": "SK",
        "SVN": "SI",
        "SWE": "SE",
    }
    expected_dimensions = ("freq", "unit", "coicop18", "geo", "time")
    shared_cache_ttl_seconds = 6 * 60 * 60
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    accept = "application/json"

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
            connector_id="eurostat",
            display_name="Eurostat · Monthly all-items HICP index",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("ec.europa.eu",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise EurostatConnectorError("Only the registered Eurostat HICP index is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise EurostatConnectorError("Eurostat HICP requires country and indicator codes.")
        countries = query.dimensions["country"]
        indicators = query.dimensions["indicator"]
        if not 1 <= len(countries) <= 20 or any(item not in cls.iso3_to_geo for item in countries):
            raise EurostatConnectorError("Unsupported Eurostat HICP country code.")
        if indicators != ["TOTAL"]:
            raise EurostatConnectorError("Eurostat HICP currently supports COICOP 2018 TOTAL only.")
        if query.frequency != "M":
            raise EurostatConnectorError("Eurostat HICP currently supports monthly frequency only.")
        if not query.start_period or not query.end_period:
            raise EurostatConnectorError("Explicit Eurostat start/end months are required.")
        month = re.compile(r"[12][0-9]{3}-(0[1-9]|1[0-2])")
        if not month.fullmatch(query.start_period) or not month.fullmatch(query.end_period):
            raise EurostatConnectorError("Eurostat periods must use YYYY-MM.")
        if query.start_period > query.end_period:
            raise EurostatConnectorError("Start month must not follow end month.")
        start_year, start_month = (int(item) for item in query.start_period.split("-"))
        end_year, end_month = (int(item) for item in query.end_period.split("-"))
        periods = (end_year - start_year) * 12 + end_month - start_month + 1
        if periods > 600:
            raise EurostatConnectorError("Eurostat HICP requests are limited to 50 years.")
        if periods * len(countries) > cls.max_observations:
            raise EurostatConnectorError("Eurostat query can exceed 20,000 observations.")

    async def _request(self, geo: str, query: DataQuery) -> tuple[bytes, str]:
        path = f"data/{self.provider_dataset}"
        params = {
            "lang": "EN",
            "freq": "M",
            "unit": "I25",
            "coicop18": "TOTAL",
            "geo": geo,
            "sinceTimePeriod": str(query.start_period),
            "untilTimePeriod": str(query.end_period),
        }
        request_key = self.cache.request_key("eurostat", "GET", path, params, self.accept)
        cached = self.cache.get(request_key)
        if cached is not None:
            self.attempts.append(
                {
                    "member": geo,
                    "attempt": 0,
                    "status": cached.scope,
                    "raw_sha256": cached.raw_sha256,
                }
            )
            return cached.content, cached.raw_sha256

        async def read(client: httpx.AsyncClient) -> bytes:
            for attempt in range(3):
                try:
                    async with client.stream(
                        "GET",
                        f"{self.base_url}/{path}",
                        params=params,
                        headers={"Accept": self.accept, "Accept-Encoding": "identity"},
                        follow_redirects=False,
                        timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10),
                    ) as response:
                        retryable = response.status_code == 429 or response.status_code in {
                            500,
                            502,
                            503,
                            504,
                        }
                        if retryable and attempt < 2:
                            self.attempts.append(
                                {"member": geo, "attempt": attempt + 1, "status": "retryable"}
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
                                {"member": geo, "attempt": attempt + 1, "status": "failed"}
                            )
                            error_detail = ""
                            error_bytes = (await response.aread())[:4096]
                            try:
                                error_payload = json.loads(error_bytes)
                                if isinstance(error_payload, dict):
                                    candidate = error_payload.get("error") or error_payload.get(
                                        "label"
                                    )
                                    if isinstance(candidate, dict):
                                        candidate = candidate.get("label") or candidate.get(
                                            "message"
                                        )
                                    if isinstance(candidate, str):
                                        error_detail = f" {candidate[:200]}"
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                if "text/plain" in response.headers.get(
                                    "content-type", ""
                                ).lower():
                                    candidate = error_bytes.decode("utf-8", errors="replace")
                                    error_detail = f" {candidate[:200]}"
                            raise EurostatConnectorError(
                                f"Eurostat request failed (HTTP {response.status_code})."
                                f"{error_detail}"
                            )
                        if "json" not in response.headers.get("content-type", "").lower():
                            raise EurostatConnectorError(
                                "Eurostat returned an unexpected media type."
                            )
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise EurostatConnectorError(
                                    "Eurostat response exceeds the 10 MB response limit."
                                )
                        return bytes(chunks)
                except httpx.TransportError as error:
                    self.attempts.append(
                        {
                            "member": geo,
                            "attempt": attempt + 1,
                            "status": "retryable" if attempt < 2 else "failed",
                        }
                    )
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise EurostatConnectorError(
                        "Eurostat connection failed; retry later."
                    ) from error
            raise EurostatConnectorError("Eurostat request failed.")

        if self.client is not None:
            raw = await read(self.client)
        else:
            async with httpx.AsyncClient() as client:
                raw = await read(client)
        stored = self.cache.put(request_key, raw)
        self.attempts.append(
            {
                "member": geo,
                "attempt": 1,
                "status": "completed",
                "raw_sha256": stored.raw_sha256,
            }
        )
        return raw, stored.raw_sha256

    @staticmethod
    def _category_codes(payload: dict[str, Any], dimension_id: str) -> list[str]:
        try:
            index = payload["dimension"][dimension_id]["category"]["index"]
        except (KeyError, TypeError) as error:
            raise EurostatConnectorError(
                "Eurostat JSON-stat category metadata is incomplete."
            ) from error
        if isinstance(index, list) and all(isinstance(item, str) for item in index):
            return index
        if isinstance(index, dict) and all(
            isinstance(key, str) and isinstance(value, int) for key, value in index.items()
        ):
            return [key for key, _ in sorted(index.items(), key=lambda item: item[1])]
        raise EurostatConnectorError("Eurostat JSON-stat category index is invalid.")

    @staticmethod
    def _cell(collection: Any, index: int) -> Any:
        if isinstance(collection, list):
            return collection[index] if index < len(collection) else None
        if isinstance(collection, dict):
            return collection.get(str(index))
        raise EurostatConnectorError("Eurostat JSON-stat values are invalid.")

    def _normalize(
        self, raw: bytes, query: DataQuery, requested_iso3: str, requested_geo: str
    ) -> tuple[list[Observation], str]:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EurostatConnectorError("Eurostat returned malformed JSON.") from error
        if not isinstance(payload, dict) or payload.get("class") != "dataset":
            raise EurostatConnectorError("Eurostat returned an invalid JSON-stat dataset.")
        dimensions = payload.get("id")
        sizes = payload.get("size")
        if dimensions != list(self.expected_dimensions) or not isinstance(sizes, list):
            raise EurostatConnectorError(
                "Eurostat dimension schema changed; re-admission required."
            )
        if len(sizes) != len(dimensions) or any(
            not isinstance(item, int) or item < 1 for item in sizes
        ):
            raise EurostatConnectorError("Eurostat dimension sizes are invalid.")
        codes = [self._category_codes(payload, item) for item in dimensions]
        if any(len(items) != size for items, size in zip(codes, sizes, strict=True)):
            raise EurostatConnectorError("Eurostat dimension categories do not match their sizes.")
        expected = {
            "freq": {"M"},
            "unit": {"I25"},
            "coicop18": {"TOTAL"},
            "geo": {requested_geo},
        }
        for dimension_id, allowed in expected.items():
            actual = set(codes[dimensions.index(dimension_id)])
            if actual != allowed:
                raise EurostatConnectorError(
                    f"Eurostat returned {dimension_id} values outside the reviewed query."
                )
        updated = str(payload.get("updated") or "")
        if not updated:
            raise EurostatConnectorError("Eurostat response is missing its update timestamp.")
        values = payload.get("value")
        statuses = payload.get("status", {})
        observations: list[Observation] = []
        multipliers = [math.prod(sizes[position + 1 :]) for position in range(len(sizes))]
        for positions in itertools.product(*(range(size) for size in sizes)):
            flat_index = sum(
                position * multiplier
                for position, multiplier in zip(positions, multipliers, strict=True)
            )
            cell_codes = {
                dimension_id: codes[index][positions[index]]
                for index, dimension_id in enumerate(dimensions)
            }
            period = cell_codes["time"]
            if not (str(query.start_period) <= period <= str(query.end_period)):
                raise EurostatConnectorError("Eurostat returned a period outside the query.")
            raw_value = self._cell(values, flat_index)
            value: float | None = None
            if raw_value is not None:
                try:
                    value = float(raw_value)
                except (TypeError, ValueError) as error:
                    raise EurostatConnectorError(
                        "Eurostat returned a non-numeric value."
                    ) from error
                if not math.isfinite(value):
                    raise EurostatConnectorError("Eurostat returned a non-finite value.")
            geo_dimension = payload["dimension"]["geo"]["category"]
            geo_labels = geo_dimension.get("label", {})
            observations.append(
                Observation(
                    provider="Eurostat",
                    dataset=self.dataset,
                    series_id=f"{requested_iso3}.TOTAL.M.I25",
                    entity_code=requested_iso3,
                    entity_name=(
                        str(geo_labels.get(requested_geo) or "")
                        if isinstance(geo_labels, dict)
                        else None
                    )
                    or None,
                    indicator_code="TOTAL",
                    indicator_name=self.allowed_indicators["TOTAL"],
                    frequency="M",
                    period=period,
                    value=value,
                    unit="Index, 2025=100",
                    status=str(self._cell(statuses, flat_index) or "") or None,
                    attributes={
                        "eurostat": {
                            "provider_geo": requested_geo,
                            "unit": "I25",
                            "updated": updated,
                        }
                    },
                )
            )
        return observations, updated

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise EurostatConnectorError("Discovery term is too long.")
        normalized = term.strip().casefold()
        label = self.allowed_indicators["TOTAL"]
        if normalized not in {"total", label.casefold()} and normalized not in label.casefold():
            return []
        return [
            {
                "dataset": self.dataset,
                "dimension": "indicator",
                "id": "TOTAL",
                "label": label,
            }
        ]

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        observations: list[Observation] = []
        raw_hashes: dict[str, str] = {}
        updates: dict[str, str] = {}
        for country in query.dimensions["country"]:
            geo = self.iso3_to_geo[country]
            raw, raw_hash = await self._request(geo, query)
            rows, updated = self._normalize(raw, query, country, geo)
            observations.extend(rows)
            raw_hashes[country] = raw_hash
            updates[country] = updated
        if len(set(updates.values())) != 1:
            raise EurostatConnectorError("Eurostat update changed during the multi-country fetch.")
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise EurostatConnectorError("Eurostat returned duplicate observation keys.")
        if not observations:
            raise EurostatConnectorError("No Eurostat HICP observations matched the query.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "Eurostat",
                "dataset": self.dataset,
                "provider_dataset": self.provider_dataset,
                "provider_update": next(iter(updates.values())),
                "iso3_to_geo": {
                    item: self.iso3_to_geo[item] for item in query.dimensions["country"]
                },
            },
        )
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        raw_hash = hashlib.sha256(
            json.dumps(raw_hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        retrieved_at = datetime.now(timezone.utc)
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="eurostat",
                connector_version=self.version,
                provider="Eurostat",
                dataset=self.dataset,
                source_identifier=f"{self.base_url}/data/{self.provider_dataset}",
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "provider_dataset": self.provider_dataset,
                    "unit": "I25",
                    "provider_updates": updates,
                    "raw_response_hashes": raw_hashes,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=(
                    "Source: Eurostat, https://doi.org/10.2908/PRC_HICP_MINR, "
                    f"accessed {retrieved_at.date().isoformat()}."
                ),
            ),
        )
