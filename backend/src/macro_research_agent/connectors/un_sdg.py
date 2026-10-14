"""Bounded UN Statistics SDG API connector for annual real GDP-per-capita growth."""

from __future__ import annotations

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
from macro_research_agent.connectors.http import ConnectorHttpError, cached_public_get
from macro_research_agent.connectors.rate_limit import PersistentRateLimiter, RateWindow
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class UnSdgConnectorError(ValueError):
    pass


class UnSdgConnector(DataConnector):
    base_url = "https://unstats.un.org/SDGAPI"
    version = "1.0.0"
    dataset = "SDG_INDICATORS"
    indicator_code = "8.1.1"
    allowed_indicators = {"NY_GDP_PCAP": "Annual growth rate of real GDP per capita"}
    iso3_to_m49 = {
        "ARG": "032",
        "AUS": "036",
        "BRA": "076",
        "CAN": "124",
        "CHE": "756",
        "CHL": "152",
        "CHN": "156",
        "COL": "170",
        "DEU": "276",
        "FRA": "250",
        "GBR": "826",
        "IDN": "360",
        "IND": "356",
        "ITA": "380",
        "JPN": "392",
        "KOR": "410",
        "MEX": "484",
        "PHL": "608",
        "TUR": "792",
        "USA": "840",
        "ZAF": "710",
    }
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    max_pages = 25
    page_size = 1000
    shared_cache_ttl_seconds = 12 * 60 * 60
    accept = "application/json"

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
            rate_limit_dir or root / "rate_limits", "un_sdg", (RateWindow(60, 20),)
        )
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="un_sdg",
            display_name="UN Statistics · SDG 8.1.1 real GDP per capita growth",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("unstats.un.org",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise UnSdgConnectorError("Only the registered UN SDG indicator query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise UnSdgConnectorError("UN SDG data requires country and series codes.")
        countries = query.dimensions["country"]
        if not 1 <= len(countries) <= 20 or any(item not in cls.iso3_to_m49 for item in countries):
            raise UnSdgConnectorError("Unsupported UN SDG country code.")
        if query.dimensions["indicator"] != ["NY_GDP_PCAP"]:
            raise UnSdgConnectorError("UN SDG currently supports series NY_GDP_PCAP only.")
        if query.frequency != "A":
            raise UnSdgConnectorError("UN SDG 8.1.1 requires annual frequency.")
        if not query.start_period or not query.end_period:
            raise UnSdgConnectorError("Explicit UN SDG start/end years are required.")
        if not re.fullmatch(r"(?:19|20)[0-9]{2}", query.start_period) or not re.fullmatch(
            r"(?:19|20)[0-9]{2}", query.end_period
        ):
            raise UnSdgConnectorError("UN SDG periods must use four-digit years.")
        start, end = int(query.start_period), int(query.end_period)
        if start > end or end - start + 1 > 75:
            raise UnSdgConnectorError("UN SDG requests are limited to 75 ordered years.")

    async def _get(self, path: str, params: dict[str, Any], member: str) -> tuple[bytes, str]:
        try:
            return await cached_public_get(
                provider="UN SDG",
                member=member,
                base_url=self.base_url,
                path=path,
                params=params,
                accept=self.accept,
                media_tokens=("json", "text/plain"),
                cache=self.cache,
                attempts=self.attempts,
                max_bytes=self.max_bytes,
                client=self.client,
                rate_limiter=self.rate_limiter,
            )
        except (ConnectorHttpError, ValueError) as error:
            raise UnSdgConnectorError(str(error)) from error

    async def _release_metadata(self) -> tuple[str, str, str]:
        raw, raw_hash = await self._get(
            f"v1/sdg/Indicator/{self.indicator_code}/Series/List", {}, "release"
        )
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnSdgConnectorError("UN SDG series metadata is malformed JSON.") from error
        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], dict)
            or str(payload[0].get("code")) != self.indicator_code
        ):
            raise UnSdgConnectorError("UN SDG returned the wrong indicator metadata.")
        series = payload[0].get("series")
        if not isinstance(series, list):
            raise UnSdgConnectorError("UN SDG series metadata is incomplete.")
        matches = [item for item in series if item.get("code") == "NY_GDP_PCAP"]
        if len(matches) != 1 or not isinstance(matches[0].get("release"), str):
            raise UnSdgConnectorError("UN SDG registered series or release is unavailable.")
        release = str(matches[0]["release"])
        if not release or len(release) > 100:
            raise UnSdgConnectorError("UN SDG returned an invalid release identifier.")
        description = str(
            matches[0].get("description") or self.allowed_indicators[matches[0]["code"]]
        )
        return release, description[:500], raw_hash

    async def _pages(self, query: DataQuery) -> tuple[list[dict[str, Any]], list[str]]:
        expected_totals: tuple[int, int] | None = None
        observations: list[dict[str, Any]] = []
        hashes: list[str] = []
        page = 1
        while True:
            raw, raw_hash = await self._get(
                "v1/sdg/Indicator/Data",
                {
                    "indicator": self.indicator_code,
                    "areaCode": [
                        int(self.iso3_to_m49[item]) for item in query.dimensions["country"]
                    ],
                    "timePeriodStart": int(str(query.start_period)),
                    "timePeriodEnd": int(str(query.end_period)),
                    "page": page,
                    "pageSize": self.page_size,
                },
                f"page-{page}",
            )
            hashes.append(raw_hash)
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UnSdgConnectorError("UN SDG observation page is malformed JSON.") from error
            if not isinstance(payload, dict):
                raise UnSdgConnectorError("UN SDG observation page is invalid.")
            page_number = payload.get("pageNumber")
            total_pages = payload.get("totalPages")
            total_elements = payload.get("totalElements")
            data = payload.get("data")
            if (
                page_number != page
                or not isinstance(total_pages, int)
                or not isinstance(total_elements, int)
                or not isinstance(data, list)
                or total_pages < 1
                or total_elements < 0
            ):
                raise UnSdgConnectorError("UN SDG pagination contract is inconsistent.")
            if total_pages > self.max_pages or total_elements > self.max_observations:
                raise UnSdgConnectorError("UN SDG response exceeds the admitted pagination limit.")
            totals = (total_pages, total_elements)
            if expected_totals is None:
                expected_totals = totals
            elif totals != expected_totals:
                raise UnSdgConnectorError("UN SDG pagination totals changed during acquisition.")
            if any(not isinstance(item, dict) for item in data):
                raise UnSdgConnectorError("UN SDG page contains invalid observations.")
            observations.extend(data)
            if page == total_pages:
                if len(observations) != total_elements:
                    raise UnSdgConnectorError("UN SDG totalElements does not match returned data.")
                break
            page += 1
        return observations, hashes

    def _normalize(
        self, rows: list[dict[str, Any]], query: DataQuery, description: str
    ) -> list[Observation]:
        m49_to_iso3 = {value: key for key, value in self.iso3_to_m49.items()}
        expected = {self.iso3_to_m49[item] for item in query.dimensions["country"]}
        observations: list[Observation] = []
        for row in rows:
            series = str(row.get("series") or "")
            area = str(row.get("geoAreaCode") or "").zfill(3)
            raw_period = row.get("timePeriodStart")
            period = str(int(raw_period)) if isinstance(raw_period, (int, float)) else ""
            indicators = row.get("indicator")
            if series != "NY_GDP_PCAP" or indicators != [self.indicator_code]:
                raise UnSdgConnectorError("UN SDG returned a series outside the pinned contract.")
            if area not in expected or not (
                str(query.start_period) <= period <= str(query.end_period)
            ):
                raise UnSdgConnectorError(
                    "UN SDG returned a geography or period outside the query."
                )
            dimensions = row.get("dimensions") or {}
            attributes = row.get("attributes") or {}
            if not isinstance(dimensions, dict) or not isinstance(attributes, dict):
                raise UnSdgConnectorError("UN SDG disaggregation metadata is invalid.")
            series_attributes = {
                key: value
                for key, value in attributes.items()
                if key not in {"Observation Status", "OBS_STATUS"}
            }
            qualifier_wire = json.dumps(
                {"dimensions": dimensions, "attributes": series_attributes},
                sort_keys=True,
                separators=(",", ":"),
            )
            qualifier = hashlib.sha256(qualifier_wire.encode()).hexdigest()[:12]
            raw_value = str(row.get("value") or "").strip()
            value: float | None = None
            if raw_value:
                try:
                    value = float(raw_value.replace(",", ""))
                except ValueError as error:
                    raise UnSdgConnectorError(
                        "UN SDG registered series returned a non-numeric value."
                    ) from error
                if not math.isfinite(value):
                    raise UnSdgConnectorError("UN SDG returned a non-finite value.")
            iso3 = m49_to_iso3[area]
            observations.append(
                Observation(
                    provider="United Nations Statistics Division",
                    dataset=self.dataset,
                    series_id=f"{iso3}.NY_GDP_PCAP.A.{qualifier}",
                    entity_code=iso3,
                    entity_name=str(row.get("geoAreaName") or "") or None,
                    indicator_code="NY_GDP_PCAP",
                    indicator_name=str(row.get("seriesDescription") or description),
                    frequency="A",
                    period=period,
                    value=value,
                    unit=str(attributes.get("Units") or attributes.get("units") or "") or None,
                    status=str(
                        attributes.get("Observation Status")
                        or attributes.get("OBS_STATUS")
                        or row.get("valueType")
                        or ""
                    )
                    or None,
                    attributes={
                        "un_sdg": {
                            "goal": row.get("goal"),
                            "target": row.get("target"),
                            "indicator": indicators,
                            "dimensions": dimensions,
                            "attributes": attributes,
                            "value_type": row.get("valueType"),
                            "original_value": raw_value,
                            "upper_bound": row.get("upperBound"),
                            "lower_bound": row.get("lowerBound"),
                            "base_period": row.get("basePeriod"),
                            "source": row.get("source"),
                            "footnotes": row.get("footnotes"),
                            "provider_m49": area,
                        }
                    },
                )
            )
        return observations

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise UnSdgConnectorError("Discovery term is too long.")
        normalized = term.strip().casefold()
        return [
            {"dataset": self.dataset, "dimension": "indicator", "id": code, "label": label}
            for code, label in self.allowed_indicators.items()
            if normalized in code.casefold() or normalized in label.casefold()
        ]

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        release, description, release_hash = await self._release_metadata()
        rows, page_hashes = await self._pages(query)
        observations = self._normalize(rows, query, description)
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise UnSdgConnectorError("UN SDG returned duplicate disaggregated observation keys.")
        if not observations:
            raise UnSdgConnectorError("No UN SDG observations matched the reviewed query.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        manifest = json.dumps(
            {"release_metadata_sha256": release_hash, "page_sha256": page_hashes},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        manifest_key = self.cache.request_key(
            "un_sdg",
            "COMPOSITE",
            "observation-manifest",
            query.model_dump(mode="json"),
            "json",
        )
        raw_hash = self.cache.put(manifest_key, manifest).raw_sha256
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={
                "provider": "United Nations Statistics Division",
                "dataset": self.dataset,
                "indicator": self.indicator_code,
                "series": "NY_GDP_PCAP",
                "release": release,
                "release_metadata_sha256": release_hash,
                "page_sha256": page_hashes,
                "iso3_to_m49": {
                    item: self.iso3_to_m49[item] for item in query.dimensions["country"]
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
                connector_id="un_sdg",
                connector_version=self.version,
                provider="United Nations Statistics Division",
                dataset=self.dataset,
                source_identifier=f"{self.base_url}/v1/sdg/Indicator/Data",
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "indicator": self.indicator_code,
                    "series": "NY_GDP_PCAP",
                    "release": release,
                    "release_metadata_sha256": release_hash,
                    "page_sha256": page_hashes,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=(
                    "United Nations Statistics Division, Global SDG Indicators Database, "
                    f"release {release}. Accessed {retrieved_at.date().isoformat()}."
                ),
            ),
        )
