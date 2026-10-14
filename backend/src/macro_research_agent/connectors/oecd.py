"""Bounded OECD Data Explorer connector for monthly leading indicators."""

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
from xml.etree import ElementTree

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


class OecdConnectorError(ValueError):
    pass


class OecdConnector(DataConnector):
    base_url = "https://sdmx.oecd.org/public/rest"
    version = "1.0.0"
    dataset = "CLI"
    agency = "OECD.SDD.STES"
    dataflow = "DSD_STES@DF_CLI"
    # A latest-version change can alter dimensions, so the admitted version is explicit.
    registered_version = "4.1"
    dimension_ids = (
        "REF_AREA",
        "FREQ",
        "MEASURE",
        "UNIT_MEASURE",
        "ACTIVITY",
        "ADJUSTMENT",
        "TRANSFORMATION",
        "TIME_HORIZ",
        "METHODOLOGY",
    )
    allowed_measures = {"LI": "Composite leading indicator (CLI)"}
    shared_cache_ttl_seconds = 6 * 60 * 60
    max_bytes = 10 * 1024 * 1024
    max_observations = 20_000
    csv_accept = "text/csv"
    xml_accept = "application/vnd.sdmx.structure+xml;version=2.1"

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
            "oecd",
            (RateWindow(60, 20), RateWindow(60 * 60, 60)),
        )
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="oecd",
            display_name="OECD Data Explorer · Composite Leading Indicators",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("sdmx.oecd.org",),
        )

    @classmethod
    def validate_query(cls, query: DataQuery) -> None:
        if query.dataset != cls.dataset or query.options:
            raise OecdConnectorError("Only the registered OECD CLI query is supported.")
        if set(query.dimensions) != {"country", "indicator"}:
            raise OecdConnectorError("OECD CLI requires country and indicator codes.")
        countries = query.dimensions["country"]
        indicators = query.dimensions["indicator"]
        if not 1 <= len(countries) <= 20 or any(
            not re.fullmatch(r"[A-Z]{3}", item) for item in countries
        ):
            raise OecdConnectorError("Invalid OECD reference-area codes.")
        if not 1 <= len(indicators) <= len(cls.allowed_measures) or any(
            item not in cls.allowed_measures for item in indicators
        ):
            raise OecdConnectorError("Unsupported OECD CLI indicator code.")
        if query.frequency != "M":
            raise OecdConnectorError("OECD CLI currently supports monthly frequency only.")
        if not query.start_period or not query.end_period:
            raise OecdConnectorError("Explicit OECD CLI start/end months are required.")
        month = re.compile(r"[12][0-9]{3}-(0[1-9]|1[0-2])")
        if not month.fullmatch(query.start_period) or not month.fullmatch(query.end_period):
            raise OecdConnectorError("OECD CLI periods must use YYYY-MM.")
        if query.start_period > query.end_period:
            raise OecdConnectorError("Start month must not follow end month.")
        start_year, start_month = (int(item) for item in query.start_period.split("-"))
        end_year, end_month = (int(item) for item in query.end_period.split("-"))
        periods = (end_year - start_year) * 12 + end_month - start_month + 1
        if periods > 600:
            raise OecdConnectorError("OECD CLI requests are limited to 50 years.")
        if periods * len(countries) * len(indicators) > cls.max_observations:
            raise OecdConnectorError("OECD CLI query can exceed 20,000 observations.")

    async def _request(
        self,
        path: str,
        params: dict[str, str],
        accept: str,
        expected_media: tuple[str, ...],
        label: str,
    ) -> tuple[bytes, str]:
        request_key = self.cache.request_key("oecd", "GET", path, params, accept)
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
                    self.rate_limiter.acquire()
                    async with client.stream(
                        "GET",
                        f"{self.base_url}/{path}",
                        params=params,
                        headers={"Accept": accept, "Accept-Encoding": "identity"},
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
                                {"member": label, "attempt": attempt + 1, "status": "retryable"}
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
                            raise OecdConnectorError(
                                f"OECD request failed (HTTP {response.status_code})."
                            )
                        media = response.headers.get("content-type", "").lower()
                        if not any(item in media for item in expected_media):
                            raise OecdConnectorError("OECD returned an unexpected media type.")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise OecdConnectorError(
                                    "OECD response exceeds the 10 MB response limit."
                                )
                        return bytes(chunks)
                except ProviderRateLimitError as error:
                    self.attempts.append(
                        {"member": label, "attempt": attempt + 1, "status": "rate_limited"}
                    )
                    raise OecdConnectorError(str(error)) from error
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
                    raise OecdConnectorError("OECD connection failed; retry later.") from error
            raise OecdConnectorError("OECD request failed.")

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
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    async def metadata(self) -> dict[str, Any]:
        path = f"dataflow/{self.agency}/{self.dataflow}/{self.registered_version}"
        raw, raw_hash = await self._request(
            path,
            {"references": "all"},
            self.xml_accept,
            ("xml", "sdmx"),
            "metadata",
        )
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise OecdConnectorError(
                "OECD structural metadata contains forbidden XML declarations."
            )
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as error:
            raise OecdConnectorError("OECD returned malformed structural metadata.") from error
        dataflows = [
            node
            for node in root.iter()
            if self._local_name(node.tag) == "Dataflow"
            and node.attrib.get("id") == self.dataflow
            and node.attrib.get("agencyID") == self.agency
        ]
        if len(dataflows) != 1:
            raise OecdConnectorError("OECD metadata did not identify the registered dataflow.")
        actual_version = dataflows[0].attrib.get("version")
        if actual_version != self.registered_version:
            raise OecdConnectorError("OECD dataflow version changed; re-admission is required.")
        structures = [
            node
            for node in root.iter()
            if self._local_name(node.tag) == "DataStructure"
            and node.attrib.get("id") == "DSD_STES"
            and node.attrib.get("agencyID") == self.agency
        ]
        if len(structures) != 1:
            raise OecdConnectorError("OECD metadata did not include the registered DSD.")
        dimension_lists = [
            node
            for node in structures[0].iter()
            if self._local_name(node.tag) == "DimensionList"
        ]
        if len(dimension_lists) != 1:
            raise OecdConnectorError("OECD metadata has an invalid dimension list.")
        dimensions = [
            node.attrib.get("id")
            for node in list(dimension_lists[0])
            if self._local_name(node.tag) in {"Dimension", "TimeDimension"}
        ]
        expected = [*self.dimension_ids, "TIME_PERIOD"]
        if dimensions != expected:
            raise OecdConnectorError("OECD CLI dimensions changed; re-admission is required.")
        return {
            "agency": self.agency,
            "dataflow": self.dataflow,
            "version": actual_version,
            "dimensions": dimensions,
            "raw_sha256": raw_hash,
        }

    async def discover(self, term: str) -> list[dict[str, str]]:
        if len(term) > 80:
            raise OecdConnectorError("Discovery term is too long.")
        normalized = term.strip().lower()
        return [
            {
                "dataset": self.dataset,
                "dimension": "indicator",
                "id": code,
                "label": label,
            }
            for code, label in self.allowed_measures.items()
            if normalized in {code.lower(), label.lower()} or normalized in label.lower()
        ]

    @classmethod
    def _data_key(cls, query: DataQuery) -> str:
        countries = "+".join(query.dimensions["country"])
        indicators = "+".join(query.dimensions["indicator"])
        # Registered DSD order. Blank components intentionally mean all values;
        # returned rows are then checked against the admitted fixed contract.
        return f"{countries}.M.{indicators}...AA...H"

    def _normalize(self, raw: bytes, query: DataQuery) -> list[Observation]:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise OecdConnectorError("OECD returned non-UTF-8 CSV.") from error
        reader = csv.DictReader(io.StringIO(text))
        required = {*self.dimension_ids, "TIME_PERIOD", "OBS_VALUE"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise OecdConnectorError("OECD CSV schema is missing registered dimensions.")
        code_columns = [item for item in reader.fieldnames if item in required]
        expected_code_columns = [*self.dimension_ids, "TIME_PERIOD", "OBS_VALUE"]
        if code_columns != expected_code_columns:
            raise OecdConnectorError("OECD CSV dimension order changed; re-admission is required.")
        observations: list[Observation] = []
        for row in reader:
            country = str(row.get("REF_AREA") or "")
            indicator = str(row.get("MEASURE") or "")
            period = str(row.get("TIME_PERIOD") or "")
            if country not in query.dimensions["country"]:
                raise OecdConnectorError("OECD returned a reference area outside the query.")
            if indicator not in query.dimensions["indicator"]:
                raise OecdConnectorError("OECD returned a measure outside the query.")
            if row.get("FREQ") != "M" or not (
                str(query.start_period) <= period <= str(query.end_period)
            ):
                raise OecdConnectorError("OECD returned a frequency or period outside the query.")
            if row.get("ADJUSTMENT") != "AA" or row.get("METHODOLOGY") != "H":
                raise OecdConnectorError("OECD returned an unregistered CLI methodology.")
            raw_value = row.get("OBS_VALUE")
            raw_value_text = "" if raw_value is None else str(raw_value)
            value: float | None = None
            if raw_value_text not in {"", ".."}:
                try:
                    value = float(raw_value_text)
                except ValueError as error:
                    raise OecdConnectorError("OECD returned a non-numeric value.") from error
                if not math.isfinite(value):
                    raise OecdConnectorError("OECD returned a non-finite value.")
            attributes = {
                key: item
                for key, item in row.items()
                if key not in {"REF_AREA", "MEASURE", "FREQ", "TIME_PERIOD", "OBS_VALUE"}
            }
            observations.append(
                Observation(
                    provider="OECD",
                    dataset=self.dataset,
                    series_id=f"{country}.{indicator}.M.AA.H",
                    entity_code=country,
                    entity_name=str(row.get("Reference area") or "") or None,
                    indicator_code=indicator,
                    indicator_name=str(row.get("Measure") or self.allowed_measures[indicator]),
                    frequency="M",
                    period=period,
                    value=value,
                    unit=str(row.get("Unit of measure") or row.get("UNIT_MEASURE") or "") or None,
                    scale=None,
                    status=str(row.get("OBS_STATUS") or "") or None,
                    attributes={"oecd": attributes},
                )
            )
        return observations

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        self.validate_query(query)
        metadata = await self.metadata()
        flow_ref = f"{self.agency},{self.dataflow},{self.registered_version}"
        path = f"data/{flow_ref}/{self._data_key(query)}"
        params = {
            "startPeriod": str(query.start_period),
            "endPeriod": str(query.end_period),
            "dimensionAtObservation": "AllDimensions",
            "format": "csvfilewithlabels",
        }
        raw, raw_hash = await self._request(
            path,
            params,
            self.csv_accept,
            ("csv", "text/plain", "octet-stream"),
            "data",
        )
        observations = self._normalize(raw, query)
        keys = [(item.series_id, item.period) for item in observations]
        if len(keys) != len(set(keys)):
            raise OecdConnectorError("OECD returned duplicate observation keys.")
        if not observations:
            raise OecdConnectorError("No OECD CLI observations matched the reviewed query.")
        if len(observations) > self.max_observations:
            raise OecdConnectorError("OECD result exceeds 20,000 observations.")
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={"provider": "OECD", "dataset": self.dataset, **metadata},
        )
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        combined_hash = hashlib.sha256(f"{metadata['raw_sha256']}:{raw_hash}".encode()).hexdigest()
        retrieved_at = datetime.now(timezone.utc)
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="oecd",
                connector_version=self.version,
                provider="OECD",
                dataset=self.dataset,
                source_identifier=f"{self.base_url}/data/{flow_ref}/[reviewed-key]",
                retrieved_at=retrieved_at,
                request_parameters={
                    **query.model_dump(mode="json"),
                    "agency": self.agency,
                    "dataflow": self.dataflow,
                    "dataflow_version": self.registered_version,
                    "data_key": self._data_key(query),
                    "raw_response_hash": raw_hash,
                    "metadata_hash": metadata["raw_sha256"],
                },
                raw_sha256=combined_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=(
                    "OECD (2026), Composite leading indicators, OECD Data Explorer, "
                    f"{self.source_identifier_url()} (accessed on "
                    f"{retrieved_at.date().isoformat()})."
                ),
            ),
        )

    @classmethod
    def source_identifier_url(cls) -> str:
        return f"{cls.base_url}/data/{cls.agency},{cls.dataflow},{cls.registered_version}"
