"""Bounded public IMF Data Portal SDMX 2.1 access; never accepts arbitrary URLs."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from macro_research_agent.connectors.base import (
    AuthenticationMode,
    ConnectorCapability,
    DataConnector,
    DataQuery,
    FetchResult,
    SourceProvenance,
)
from macro_research_agent.data.schemas import NormalizedDataset, Observation


class ImfConnectorError(ValueError):
    pass


@dataclass(frozen=True)
class ImfDatasetContract:
    dataset: str
    agency: str
    display_name: str
    key_dimensions: tuple[str, ...]
    query_dimensions: tuple[str, ...]
    code_patterns: dict[str, str]
    frequencies: tuple[str, ...]
    indicator_dimension: str
    fixed_dimensions: dict[str, str]
    codelists: tuple[str, ...]
    max_years: int
    default_unit: str | None
    attribution: str


IMF_DATASETS: dict[str, ImfDatasetContract] = {
    "CPI": ImfDatasetContract(
        dataset="CPI",
        agency="IMF.STA",
        display_name="Consumer Price Index",
        key_dimensions=("country", "=CPI", "coicop", "=IX", "@frequency"),
        query_dimensions=("country", "coicop"),
        code_patterns={"country": r"[A-Z]{3}", "coicop": r"(?:_T|CP[0-9]{2,6})"},
        frequencies=("M", "Q", "A"),
        indicator_dimension="COICOP_1999",
        fixed_dimensions={"INDEX_TYPE": "CPI", "TYPE_OF_TRANSFORMATION": "IX"},
        codelists=(
            "CL_COUNTRY",
            "CL_INDEX_TYPE",
            "CL_COICOP_1999",
            "CL_TRANSFORMATION",
            "CL_FREQ",
        ),
        max_years=20,
        default_unit="Index",
        attribution="Source: International Monetary Fund, IMF Data Portal, CPI.",
    ),
    "WEO": ImfDatasetContract(
        dataset="WEO",
        agency="IMF.RES",
        display_name="World Economic Outlook",
        key_dimensions=("country", "indicator", "@frequency"),
        query_dimensions=("country", "indicator"),
        code_patterns={"country": r"[A-Z]{3}", "indicator": r"[A-Z][A-Z0-9_]{1,31}"},
        frequencies=("A",),
        indicator_dimension="INDICATOR",
        fixed_dimensions={},
        codelists=("CL_WEO_COUNTRY", "CL_WEO_INDICATOR", "CL_FREQ"),
        max_years=50,
        default_unit=None,
        attribution="Source: International Monetary Fund, World Economic Outlook Database.",
    ),
}

WEO_INDICATOR_DETAILS: dict[str, tuple[str, str]] = {
    "GGXWDG_NGDP": ("Gross debt, General government, Percent of GDP", "Percent of GDP"),
    "GGXWDG": ("Gross debt, General government, Domestic currency", "Domestic currency"),
}


class ImfDataConnector(DataConnector):
    base_url = "https://api.imf.org/external/sdmx/2.1"
    version = "2.1.0"
    max_bytes = 10 * 1024 * 1024
    shared_cache_ttl_seconds = 6 * 60 * 60

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        shared_cache_dir: Path | None = None,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client
        self.shared_cache_dir = shared_cache_dir
        self.attempts: list[dict[str, Any]] = []

    @property
    def capability(self) -> ConnectorCapability:
        return ConnectorCapability(
            connector_id="imf_data",
            display_name="IMF Data Portal · CPI and WEO",
            authentication=AuthenticationMode.NONE,
            provider_hosts=("api.imf.org",),
        )

    @staticmethod
    def registered_datasets() -> list[dict[str, Any]]:
        return [
            {
                "dataset": contract.dataset,
                "agency": contract.agency,
                "display_name": contract.display_name,
                "query_dimensions": list(contract.query_dimensions),
                "frequencies": list(contract.frequencies),
                "max_years": contract.max_years,
            }
            for contract in IMF_DATASETS.values()
        ]

    async def _read(
        self, path: str, params: dict[str, str], accept: str, label: str | None = None
    ) -> bytes:
        async def request(client: httpx.AsyncClient) -> bytes:
            for attempt in range(2):
                try:
                    async with client.stream(
                        "GET",
                        f"{self.base_url}/{path}",
                        params=params,
                        headers={"Accept": accept, "Accept-Encoding": "identity"},
                        follow_redirects=False,
                        timeout=30,
                    ) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                            if label:
                                self.attempts.append(
                                    {"member": label, "attempt": attempt + 1, "status": "retryable"}
                                )
                            await asyncio.sleep(1)
                            continue
                        if response.status_code != 200:
                            if label:
                                self.attempts.append(
                                    {"member": label, "attempt": attempt + 1, "status": "failed"}
                                )
                            raise ImfConnectorError(
                                f"IMF request failed (HTTP {response.status_code})."
                            )
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise ImfConnectorError("IMF response exceeds the 10 MB limit.")
                        if label:
                            self.attempts.append(
                                {"member": label, "attempt": attempt + 1, "status": "completed"}
                            )
                        return bytes(chunks)
                except httpx.TransportError as error:
                    if label:
                        self.attempts.append(
                            {
                                "member": label,
                                "attempt": attempt + 1,
                                "status": "retryable" if attempt == 0 else "failed",
                            }
                        )
                    if attempt == 0:
                        await asyncio.sleep(1)
                        continue
                    raise ImfConnectorError("IMF connection failed; retry later.") from error
            raise ImfConnectorError("IMF request failed.")

        if self.client is not None:
            return await request(self.client)
        async with httpx.AsyncClient() as client:
            return await request(client)

    async def _cached_data_read(
        self, path: str, params: dict[str, str], accept: str, member: str
    ) -> tuple[bytes, str]:
        request_key = hashlib.sha256(
            json.dumps({"path": path, "params": params, "accept": accept}, sort_keys=True).encode()
        ).hexdigest()
        cached = self._read_cache(self.raw_dir, request_key)
        if cached is not None:
            raw, raw_hash = cached
            self.attempts.append(
                {
                    "member": member,
                    "attempt": 0,
                    "status": "reused_session",
                    "raw_sha256": raw_hash,
                }
            )
            return raw, raw_hash
        if self.shared_cache_dir is not None:
            cached = self._read_cache(
                self.shared_cache_dir,
                request_key,
                max_age_seconds=self.shared_cache_ttl_seconds,
            )
            if cached is not None:
                raw, raw_hash = cached
                self._write_cache(self.raw_dir, request_key, raw, raw_hash)
                self.attempts.append(
                    {
                        "member": member,
                        "attempt": 0,
                        "status": "reused_shared",
                        "raw_sha256": raw_hash,
                    }
                )
                return raw, raw_hash
        raw = await self._read(path, params, accept, member)
        raw_hash = hashlib.sha256(raw).hexdigest()
        self._write_cache(self.raw_dir, request_key, raw, raw_hash)
        if self.shared_cache_dir is not None:
            self._write_cache(self.shared_cache_dir, request_key, raw, raw_hash)
        self.attempts[-1]["raw_sha256"] = raw_hash
        return raw, raw_hash

    async def _cached_structure_read(
        self, path: str, params: dict[str, str], accept: str
    ) -> bytes:
        request_key = hashlib.sha256(
            json.dumps({"path": path, "params": params, "accept": accept}, sort_keys=True).encode()
        ).hexdigest()
        cache_dir = self.shared_cache_dir or self.raw_dir
        cached = self._read_cache(
            cache_dir,
            request_key,
            max_age_seconds=self.shared_cache_ttl_seconds,
        )
        if cached is not None:
            return cached[0]
        raw = await self._read(path, params, accept)
        self._write_cache(cache_dir, request_key, raw, hashlib.sha256(raw).hexdigest())
        return raw

    @staticmethod
    def _read_cache(
        cache_dir: Path,
        request_key: str,
        max_age_seconds: int | None = None,
    ) -> tuple[bytes, str] | None:
        manifest_path = cache_dir / "requests" / f"{request_key}.json"
        if manifest_path.exists():
            try:
                if (
                    max_age_seconds is not None
                    and time.time() - manifest_path.stat().st_mtime > max_age_seconds
                ):
                    return None
                raw_hash = str(json.loads(manifest_path.read_text())["raw_sha256"])
                if not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
                    return None
                raw_path = cache_dir / f"{raw_hash}.xml"
                raw = raw_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() == raw_hash:
                    return raw, raw_hash
            except (KeyError, OSError, ValueError, json.JSONDecodeError):
                pass
        return None

    @classmethod
    def _write_cache(
        cls, cache_dir: Path, request_key: str, raw: bytes, raw_hash: str
    ) -> None:
        request_dir = cache_dir / "requests"
        cache_dir.mkdir(parents=True, exist_ok=True)
        request_dir.mkdir(parents=True, exist_ok=True)
        cls._atomic_write(cache_dir / f"{raw_hash}.xml", raw)
        cls._atomic_write(
            request_dir / f"{request_key}.json",
            json.dumps({"raw_sha256": raw_hash}, sort_keys=True).encode(),
        )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)

    @staticmethod
    def _xml(raw: bytes) -> ET.Element:
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ImfConnectorError("Unsafe XML in IMF response.")
        try:
            return ET.fromstring(raw)
        except ET.ParseError as error:
            raise ImfConnectorError("IMF did not return valid SDMX XML.") from error

    @staticmethod
    def _canonical_period(value: str) -> str:
        monthly = re.fullmatch(r"([12][0-9]{3})-M(0[1-9]|1[0-2])", value)
        return f"{monthly.group(1)}-{monthly.group(2)}" if monthly else value

    async def metadata(self, dataset: str = "CPI") -> dict[str, Any]:
        contract = self._contract(dataset)
        raw = await self._cached_structure_read(
            f"dataflow/{contract.agency}/{contract.dataset}/latest",
            {"references": "all"},
            "application/vnd.sdmx.structure+xml;version=2.1",
        )
        root = self._xml(raw)
        return {
            "dataset": contract.dataset,
            "agency": contract.agency,
            "display_name": contract.display_name,
            "dimensions": [
                dict(item.attrib) for item in root.findall(".//{*}Dimension") if "id" in item.attrib
            ],
            "codelists": {
                item.attrib["id"]: [
                    {
                        "id": code.attrib["id"],
                        "label": next(
                            (
                                name.text or ""
                                for name in code.findall("{*}Name")
                                if name.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                                == "en"
                            ),
                            code.findtext("{*}Name", ""),
                        ),
                    }
                    for code in item.findall("{*}Code")
                ]
                for item in root.findall(".//{*}Codelist")
                if item.attrib.get("id") in contract.codelists
            },
        }

    async def discover(self, term: str, dataset: str = "CPI") -> list[dict[str, str]]:
        if len(term) > 200:
            raise ImfConnectorError("Discovery term is too long.")
        metadata = await self.metadata(dataset)
        return [
            {"dataset": dataset, "dimension": dimension, **code}
            for dimension, codes in metadata["codelists"].items()
            for code in codes
            if term.casefold() in f"{code['id']} {code['label']}".casefold()
        ][:200]

    @staticmethod
    def _contract(dataset: str) -> ImfDatasetContract:
        try:
            return IMF_DATASETS[dataset]
        except KeyError as error:
            raise ImfConnectorError(f"IMF dataset {dataset!r} is not registered.") from error

    @classmethod
    def validate_query(cls, query: DataQuery) -> str:
        contract = cls._contract(query.dataset)
        if query.options:
            raise ImfConnectorError("IMF queries do not accept unregistered options.")
        if set(query.dimensions) != set(contract.query_dimensions):
            required = ", ".join(contract.query_dimensions)
            raise ImfConnectorError(f"{contract.dataset} requires explicit {required} codes.")
        for key, values in query.dimensions.items():
            pattern = contract.code_patterns[key]
            if not 1 <= len(values) <= 20 or any(not re.fullmatch(pattern, v) for v in values):
                raise ImfConnectorError(f"Invalid {contract.dataset} {key} codes.")
        if query.frequency not in contract.frequencies:
            allowed = ", ".join(contract.frequencies)
            raise ImfConnectorError(f"{contract.dataset} frequency must be {allowed}.")
        period_pattern = {
            "M": r"[12][0-9]{3}-(?:0[1-9]|1[0-2])",
            "Q": r"[12][0-9]{3}-Q[1-4]",
            "A": r"[12][0-9]{3}",
        }[str(query.frequency)]
        for period in (query.start_period, query.end_period):
            if not period or not re.fullmatch(period_pattern, period):
                raise ImfConnectorError(
                    f"Explicit {query.frequency} start/end periods are required."
                )
        if str(query.start_period) > str(query.end_period):
            raise ImfConnectorError("Start period must not follow end period.")
        if int(str(query.end_period)[:4]) - int(str(query.start_period)[:4]) > contract.max_years:
            raise ImfConnectorError(
                f"{contract.dataset} requests are limited to {contract.max_years} years."
            )
        parts = []
        for dimension in contract.key_dimensions:
            if dimension == "@frequency":
                parts.append(str(query.frequency))
            elif dimension.startswith("="):
                parts.append(dimension[1:])
            else:
                parts.append("+".join(query.dimensions[dimension]))
        return ".".join(parts)

    def normalize(self, raw: bytes, query: DataQuery) -> NormalizedDataset:
        contract = self._contract(query.dataset)
        root = self._xml(raw)
        observations = []
        for series in root.findall(".//{*}Series"):
            dimensions = dict(series.attrib)
            dimensions.update(
                {v.attrib["id"]: v.attrib["value"] for v in series.findall("{*}SeriesKey/{*}Value")}
            )
            series_attrs = {
                v.attrib["id"]: v.attrib.get("value", "")
                for v in series.findall("{*}Attributes/{*}Value")
            }
            for obs in series.findall("{*}Obs"):
                fields = {**dimensions, **series_attrs, **obs.attrib}
                fields.update(
                    {
                        v.attrib["id"]: v.attrib.get("value", "")
                        for v in obs.findall("{*}Attributes/{*}Value")
                    }
                )
                period = obs.find("{*}ObsDimension")
                value = obs.find("{*}ObsValue")
                raw_period = (
                    period.attrib.get("value", "")
                    if period is not None
                    else fields.get("TIME_PERIOD", "")
                )
                period_text = self._canonical_period(raw_period)
                value_text = (
                    value.attrib.get("value") if value is not None else fields.get("OBS_VALUE")
                )
                try:
                    number = None if value_text in {None, "", "NaN"} else float(str(value_text))
                except ValueError as error:
                    raise ImfConnectorError(
                        "Invalid numeric observation in IMF response."
                    ) from error
                if number is not None and not math.isfinite(number):
                    raise ImfConnectorError("Non-finite IMF observation.")
                if not period_text:
                    raise ImfConnectorError("IMF observation is missing its period.")
                country = fields.get("COUNTRY")
                indicator = fields.get(contract.indicator_dimension)
                indicator_query_key = next(
                    key for key in contract.query_dimensions if key != "country"
                )
                if country not in query.dimensions["country"] or indicator not in query.dimensions[
                    indicator_query_key
                ]:
                    raise ImfConnectorError("IMF returned observations outside the reviewed query.")
                if fields.get("FREQUENCY") != query.frequency or any(
                    fields.get(key) != expected
                    for key, expected in contract.fixed_dimensions.items()
                ):
                    raise ImfConnectorError("IMF returned a different measure or frequency.")
                if not str(query.start_period) <= period_text <= str(query.end_period):
                    raise ImfConnectorError(
                        "IMF returned observations outside the requested period."
                    )
                weo_details = WEO_INDICATOR_DETAILS.get(str(indicator))
                observations.append(
                    Observation(
                        provider="IMF",
                        dataset=contract.dataset,
                        series_id=".".join(
                            str(fields.get(name, ""))
                            for name in (
                                ("COUNTRY", "INDEX_TYPE", contract.indicator_dimension,
                                 "TYPE_OF_TRANSFORMATION", "FREQUENCY")
                                if contract.dataset == "CPI"
                                else ("COUNTRY", contract.indicator_dimension, "FREQUENCY")
                            )
                        ),
                        entity_code=country,
                        indicator_code=(
                            f"CPI.{indicator}.IX" if contract.dataset == "CPI" else str(indicator)
                        ),
                        indicator_name=(
                            weo_details[0]
                            if contract.dataset == "WEO" and weo_details
                            else None
                        ),
                        frequency=str(query.frequency),
                        period=period_text,
                        value=number,
                        unit=(
                            fields.get("UNIT_MEASURE")
                            or fields.get("UNIT")
                            or (
                                weo_details[1]
                                if contract.dataset == "WEO" and weo_details
                                else contract.default_unit
                            )
                        ),
                        scale=fields.get("SCALE", fields.get("UNIT_MULT")),
                        status=fields.get("OBS_STATUS"),
                        attributes={"imf": fields},
                    )
                )
                if len(observations) > 20000:
                    raise ImfConnectorError("IMF query exceeds 20,000 observations.")
        if not observations:
            raise ImfConnectorError(f"No {contract.dataset} observations matched the query.")
        keys = [(o.series_id, o.period) for o in observations]
        if len(keys) != len(set(keys)):
            raise ImfConnectorError("IMF returned duplicate observation keys.")
        observations.sort(key=lambda o: (o.series_id, o.period))
        return NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={"provider": "IMF", "dataset": contract.dataset},
        )

    async def fetch(self, query: DataQuery) -> FetchResult:
        self.attempts = []
        contract = self._contract(query.dataset)
        self.validate_query(query)
        observations: list[Observation] = []
        raw_hashes: dict[str, str] = {}
        accept = "application/vnd.sdmx.structurespecificdata+xml;version=2.1"
        params = {
            "startPeriod": str(query.start_period),
            "endPeriod": str(query.end_period),
        }
        for member in query.dimensions["country"]:
            member_query = query.model_copy(
                update={"dimensions": {**query.dimensions, "country": [member]}}
            )
            key = self.validate_query(member_query)
            raw, raw_hashes[member] = await self._cached_data_read(
                f"data/{contract.dataset}/{key}", params, accept, member
            )
            observations.extend(self.normalize(raw, member_query).observations)
        observations.sort(key=lambda item: (item.series_id, item.period))
        dataset = NormalizedDataset(
            observations=observations,
            dimensions=query.dimensions,
            metadata={"provider": "IMF", "dataset": contract.dataset},
        )
        raw_hash = hashlib.sha256(
            json.dumps(raw_hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        normalized = json.dumps(
            dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return FetchResult(
            dataset=dataset,
            provenance=SourceProvenance(
                connector_id="imf_data",
                connector_version=self.version,
                provider="IMF",
                dataset=contract.dataset,
                source_identifier=(
                    f"{self.base_url}/data/{contract.dataset}/"
                    f"[reviewed member and registered dimensions]"
                ),
                retrieved_at=datetime.now(timezone.utc),
                request_parameters={
                    **query.model_dump(mode="json"),
                    "raw_response_hashes": raw_hashes,
                },
                raw_sha256=raw_hash,
                normalized_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
                attribution=contract.attribution,
            ),
        )
