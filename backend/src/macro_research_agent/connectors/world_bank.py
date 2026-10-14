"""Bounded World Bank Indicators API v2 connector for WDI annual series."""

from __future__ import annotations

import asyncio
import hashlib
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


class WorldBankConnectorError(ValueError):
    pass


class WorldBankConnector(DataConnector):
    base_url = "https://api.worldbank.org/v2"
    version = "1.0.0"
    source_id = "2"
    max_bytes = 10 * 1024 * 1024
    max_pages = 20
    max_observations = 20_000
    shared_cache_ttl_seconds = 6 * 60 * 60
    accept = "application/json"

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        shared_cache_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.cache = PublicResponseCache(
            raw_dir,
            shared_cache_dir,
            self.shared_cache_ttl_seconds,
        )
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="world_bank",
            display_name="World Bank · World Development Indicators",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("api.worldbank.org",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != "WDI" or query.options:
            raise WorldBankConnectorError("Only the registered WDI query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise WorldBankConnectorError("WDI requires explicit country and indicator codes.")
        countries = query.dimensions["country"]
        indicators = query.dimensions["indicator"]
        if not 1 <= len(countries) <= 20 or any(
            not re.fullmatch(r"[A-Z]{3}", code) for code in countries
        ):
            raise WorldBankConnectorError("Invalid WDI country codes.")
        if not 1 <= len(indicators) <= 20 or any(
            not re.fullmatch(r"[A-Z0-9][A-Z0-9._]{1,49}", code) for code in indicators
        ):
            raise WorldBankConnectorError("Invalid WDI indicator codes.")
        if query.frequency != "A":
            raise WorldBankConnectorError("WDI currently supports annual frequency only.")
        if not query.start_period or not query.end_period:
            raise WorldBankConnectorError("Explicit WDI start/end years are required.")
        if not re.fullmatch(r"[12][0-9]{3}", query.start_period) or not re.fullmatch(
            r"[12][0-9]{3}", query.end_period
        ):
            raise WorldBankConnectorError("WDI periods must be four-digit years.")
        start = int(query.start_period)
        end = int(query.end_period)
        if start > end:
            raise WorldBankConnectorError("Start year must not follow end year.")
        if end - start > 50:
            raise WorldBankConnectorError("WDI requests are limited to 50 years.")
        estimate = len(countries) * len(indicators) * (end - start + 1)
        if estimate > cls.max_observations:
            raise WorldBankConnectorError("WDI query can exceed 20,000 observations.")

    async def _request(self, path: str, params: dict[str, str], label: str) -> tuple[bytes, str]:
        request_key = self.cache.request_key(
            "world_bank",
            "GET",
            path,
            params,
            self.accept,
        )
        cached = self.cache.get(request_key)
        if cached is not None:
            self.attempts.append(
                {
                    "member": label,
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
                                {"member": label, "attempt": 1, "status": "retryable"}
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
                                {"member": label, "attempt": attempt + 1, "status": "failed"}
                            )
                            raise WorldBankConnectorError(
                                f"World Bank request failed (HTTP {response.status_code})."
                            )
                        content_type = response.headers.get("content-type", "").lower()
                        if "json" not in content_type:
                            raise WorldBankConnectorError(
                                "World Bank returned an unexpected media type."
                            )
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise WorldBankConnectorError(
                                    "World Bank response exceeds the 10 MB page limit."
                                )
                        return bytes(chunks)
                except httpx.TransportError as error:
                    self.attempts.append(
                        {
                            "member": label,
                            "attempt": attempt + 1,
                            "status": "retryable" if attempt < 2 else "failed",
                        }
                    )
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise WorldBankConnectorError(
                        "World Bank connection failed; retry later."
                    ) from error
            raise WorldBankConnectorError("World Bank request failed.")

        if self.client is not None:
            raw = await read(self.client)
        else:
            async with httpx.AsyncClient() as client:
                raw = await read(client)
        stored = self.cache.put(request_key, raw)
        self.attempts.append(
            {
                "member": label,
                "attempt": 1,
                "status": "completed",
                "raw_sha256": stored.raw_sha256,
            }
        )
        return raw, stored.raw_sha256

    @staticmethod
    def _json(raw: bytes) -> Any:
        try:
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorldBankConnectorError("World Bank returned malformed JSON.") from error

    @classmethod
    def _envelope(cls, raw: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        payload = cls._json(raw)
        if (
            not isinstance(payload, list)
            or len(payload) != 2
            or not isinstance(payload[0], dict)
            or not isinstance(payload[1], list)
            or any(not isinstance(row, dict) for row in payload[1])
        ):
            raise WorldBankConnectorError("World Bank returned an invalid page envelope.")
        return payload[0], payload[1]

    async def indicator_metadata(self, indicator: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._]{1,49}", indicator):
            raise WorldBankConnectorError("Invalid WDI indicator code.")
        raw, _ = await self._request(
            f"indicator/{indicator}",
            {"format": "json", "source": self.source_id, "per_page": "10"},
            f"metadata:{indicator}",
        )
        metadata, rows = self._envelope(raw)
        if int(metadata.get("total", 0)) != 1 or len(rows) != 1:
            raise WorldBankConnectorError(f"Unknown WDI indicator {indicator}.")
        row = rows[0]
        source = row.get("source")
        if (
            row.get("id") != indicator
            or not isinstance(source, dict)
            or str(source.get("id")) != "2"
        ):
            raise WorldBankConnectorError("World Bank indicator metadata does not match WDI.")
        return row

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 50:
            raise WorldBankConnectorError("Discovery term is too long.")
        code = term.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._]{1,49}", code):
            return []
        try:
            item = await self.indicator_metadata(code)
        except WorldBankConnectorError as error:
            if str(error).startswith("Unknown WDI indicator"):
                return []
            raise
        return [
            {
                "dataset": "WDI",
                "dimension": "indicator",
                "id": code,
                "label": str(item["name"]),
            }
        ]

    @staticmethod
    def _normalized_unit(
        observation_unit: object, metadata_unit: object, indicator_label: object
    ) -> tuple[str | None, str]:
        def canonical_explicit(value: object) -> str:
            raw = str(value or "").strip()
            normalized = " ".join(raw.casefold().split())
            if normalized in {"%", "percent", "percentage"}:
                return "Percent"
            if normalized in {"% of gdp", "percent of gdp", "percentage of gdp"}:
                return "Percent of GDP"
            return raw

        row_value = str(observation_unit or "").strip()
        if row_value:
            return canonical_explicit(row_value), "observation"
        metadata_value = str(metadata_unit or "").strip()
        if metadata_value:
            return canonical_explicit(metadata_value), "indicator_metadata"
        label = " ".join(str(indicator_label or "").casefold().split())
        if "% of gdp" in label or "percent of gdp" in label:
            return "Percent of GDP", "indicator_label"
        if re.search(r"\((?:annual )?%\)", label) or "percent change" in label:
            return "Percent", "indicator_label"
        share = re.search(r"\(% of ([^)]+)\)", label)
        if share:
            return "Percent of " + share.group(1), "indicator_label"
        current_dollars = re.search(r"\(current (?:us\$|u\.s\. dollars?)\)", label)
        if current_dollars:
            return "Current US dollars", "indicator_label"
        constant_dollars = re.search(
            r"\(constant ([12][0-9]{3}) (?:us\$|u\.s\. dollars?)\)", label
        )
        if constant_dollars:
            return f"Constant {constant_dollars.group(1)} US dollars", "indicator_label"
        return None, "unresolved"

    @staticmethod
    def _page_number(metadata: dict[str, Any], key: str) -> int:
        try:
            value = int(metadata[key])
        except (KeyError, TypeError, ValueError) as error:
            raise WorldBankConnectorError(
                f"World Bank page is missing valid {key} metadata."
            ) from error
        if value < 0:
            raise WorldBankConnectorError(f"World Bank page has invalid {key} metadata.")
        return value

    async def _indicator_rows(
        self,
        query: DataQuery,
        indicator: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
        countries = ";".join(query.dimensions["country"])
        base_params = {
            "date": f"{query.start_period}:{query.end_period}",
            "format": "json",
            "source": self.source_id,
            "footnote": "y",
            "per_page": "1000",
        }
        rows: list[dict[str, Any]] = []
        hashes: dict[str, str] = {}
        expected_pages: int | None = None
        expected_total: int | None = None
        last_updated: str | None = None
        page = 1
        while expected_pages is None or page <= expected_pages:
            params = {**base_params, "page": str(page)}
            raw, raw_hash = await self._request(
                f"country/{countries}/indicator/{indicator}",
                params,
                f"{indicator}:page:{page}",
            )
            metadata, page_rows = self._envelope(raw)
            actual_page = self._page_number(metadata, "page")
            pages = self._page_number(metadata, "pages")
            total = self._page_number(metadata, "total")
            if actual_page != page or pages < 1 or pages > self.max_pages:
                raise WorldBankConnectorError("World Bank pagination is inconsistent or excessive.")
            if expected_pages is None:
                expected_pages, expected_total = pages, total
                last_updated = str(metadata.get("lastupdated") or "") or None
                if total > self.max_observations:
                    raise WorldBankConnectorError("World Bank result exceeds 20,000 observations.")
            elif pages != expected_pages or total != expected_total or (
                str(metadata.get("lastupdated") or "") or None
            ) != last_updated:
                raise WorldBankConnectorError(
                    "World Bank pagination metadata changed during fetch."
                )
            hashes[str(page)] = raw_hash
            rows.extend(page_rows)
            if len(rows) > self.max_observations:
                raise WorldBankConnectorError("World Bank result exceeds 20,000 observations.")
            page += 1
        if expected_total != len(rows):
            raise WorldBankConnectorError(
                "World Bank pagination did not return the declared total."
            )
        return rows, hashes, last_updated

    def _normalize_rows(
        self,
        rows: list[dict[str, Any]],
        query: DataQuery,
        indicator: str,
        indicator_metadata: dict[str, Any],
        last_updated: str | None,
    ) -> list[Observation]:
        observations = []
        for row in rows:
            row_indicator = row.get("indicator")
            country = str(row.get("countryiso3code") or "")
            period = str(row.get("date") or "")
            if not isinstance(row_indicator, dict) or row_indicator.get("id") != indicator:
                raise WorldBankConnectorError("World Bank returned a different indicator.")
            if country not in query.dimensions["country"]:
                raise WorldBankConnectorError("World Bank returned an economy outside the query.")
            if not re.fullmatch(r"[12][0-9]{3}", period) or not (
                str(query.start_period) <= period <= str(query.end_period)
            ):
                raise WorldBankConnectorError("World Bank returned a period outside the query.")
            value = row.get("value")
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError) as error:
                    raise WorldBankConnectorError(
                        "World Bank returned a non-numeric value."
                    ) from error
                if not math.isfinite(value):
                    raise WorldBankConnectorError("World Bank returned a non-finite value.")
            row_unit, row_unit_source = self._normalized_unit(
                row.get("unit"),
                indicator_metadata.get("unit"),
                indicator_metadata.get("name"),
            )
            attributes = {
                key: item
                for key, item in row.items()
                if key not in {"value", "countryiso3code", "date", "indicator", "country"}
            }
            attributes.update(
                {
                    "source_id": self.source_id,
                    "source_name": indicator_metadata["source"]["value"],
                    "source_note": indicator_metadata.get("sourceNote"),
                    "source_organization": indicator_metadata.get("sourceOrganization"),
                    "provider_last_updated": last_updated,
                    "observation_unit": str(row.get("unit") or "") or None,
                    "indicator_metadata_unit": str(indicator_metadata.get("unit") or "")
                    or None,
                    "normalized_unit": row_unit,
                    "unit_source": row_unit_source,
                }
            )
            observations.append(
                Observation(
                    provider="World Bank",
                    dataset="WDI",
                    series_id=f"{country}.{indicator}.A",
                    entity_code=country,
                    entity_name=str((row.get("country") or {}).get("value") or "") or None,
                    indicator_code=indicator,
                    indicator_name=str(indicator_metadata.get("name") or "") or None,
                    frequency="A",
                    period=period,
                    value=value,
                    unit=row_unit,
                    scale=None,
                    status=str(row.get("obs_status") or "") or None,
                    attributes={"world_bank": attributes},
                )
            )
        return observations

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        observations: list[Observation] = []
        raw_hashes: dict[str, dict[str, str]] = {}
        provider_updates: dict[str, str | None] = {}
        indicator_units: dict[str, dict[str, str | None]] = {}
        for indicator in query.dimensions["indicator"]:
            metadata = await self.indicator_metadata(indicator)
            normalized_unit, unit_source = self._normalized_unit(
                None, metadata.get("unit"), metadata.get("name")
            )
            indicator_units[indicator] = {
                "raw": str(metadata.get("unit") or "") or None,
                "normalized": normalized_unit,
                "source": unit_source,
            }
            rows, hashes, last_updated = await self._indicator_rows(query, indicator)
            raw_hashes[indicator] = hashes
            provider_updates[indicator] = last_updated
            observations.extend(
                self._normalize_rows(rows, query, indicator, metadata, last_updated)
            )
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise WorldBankConnectorError("World Bank returned duplicate observation keys.")
        if len(observations) > self.max_observations:
            raise WorldBankConnectorError("World Bank result exceeds 20,000 observations.")
        if not observations:
            raise WorldBankConnectorError("No WDI observations matched the reviewed query.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "World Bank",
                "dataset": "WDI",
                "source_id": self.source_id,
                "provider_updates": provider_updates,
                "indicator_units": indicator_units,
            },
        )
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        raw_hash = hashlib.sha256(
            json.dumps(raw_hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="world_bank",
                connector_version=self.version,
                provider="World Bank",
                dataset="WDI",
                source_identifier=(
                    f"{self.base_url}/country/[reviewed-economies]/indicator/"
                    "[reviewed-indicator]?source=2"
                ),
                retrieved_at=datetime.now(timezone.utc),
                request_parameters={
                    **query.model_dump(mode="json"),
                    "source_id": self.source_id,
                    "provider_updates": provider_updates,
                    "indicator_units": indicator_units,
                    "raw_response_hashes": raw_hashes,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution="Source: World Bank, World Development Indicators.",
            ),
        )
