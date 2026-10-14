"""World Bank catalog harvester for Source Index v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from macro_research_agent.knowledge.source_index import (
    DimensionRole,
    ProviderSourceSnapshot,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
)


class WorldBankCatalogHarvestError(ValueError):
    pass


class WorldBankCatalogHarvester:
    base_url = "https://api.worldbank.org/v2"
    page_size = 1_000
    max_pages = 1_000
    max_page_bytes = 10 * 1024 * 1024

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        resume_max_age_seconds: int = 24 * 60 * 60,
        concurrency: int = 4,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client
        self.resume_max_age_seconds = resume_max_age_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._raw_hashes: dict[str, str] = {}
        self.manifest: dict[str, dict[str, int]] = {}

    async def harvest(self) -> ProviderSourceSnapshot:
        self._raw_hashes = {}
        self.manifest = {}
        if self.client is not None:
            return await self._harvest(self.client)
        async with httpx.AsyncClient() as client:
            return await self._harvest(client)

    async def _harvest(self, client: httpx.AsyncClient) -> ProviderSourceSnapshot:
        sources = await self._paginated(client, "source")
        indicators = await self._paginated(client, "indicator")
        countries = await self._paginated(client, "country")
        topics = await self._paginated(client, "topic")
        source_ids = {str(item.get("id") or "") for item in sources}
        if "" in source_ids:
            raise WorldBankCatalogHarvestError("World Bank source metadata is missing an ID.")

        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen_indicators: dict[tuple[str, str], dict[str, Any]] = {}
        duplicate_indicators = 0
        for raw_indicator in indicators:
            indicator = self._normalize_indicator(raw_indicator)
            source = indicator.get("source")
            if not isinstance(source, dict) or not source.get("id"):
                raise WorldBankCatalogHarvestError(
                    "World Bank indicator metadata is missing its source database."
                )
            source_id = str(source["id"])
            if source_id not in source_ids:
                raise WorldBankCatalogHarvestError(
                    "World Bank indicator references an unknown source database."
                )
            code = str(indicator.get("id") or "")
            key = (source_id, code)
            previous = seen_indicators.get(key)
            if previous is not None:
                if previous != indicator:
                    raise WorldBankCatalogHarvestError(
                        "World Bank returned conflicting indicator metadata for one source/code."
                    )
                duplicate_indicators += 1
                continue
            seen_indicators[key] = indicator
            by_source[source_id].append(indicator)

        datasets = await asyncio.gather(
            *[
                self._dataset(
                    client,
                    item,
                    by_source[str(item["id"])],
                    self._geography_lookup(countries),
                )
                for item in sources
            ]
        )
        latest = max((str(item.get("lastupdated") or "") for item in sources), default="")
        return ProviderSourceSnapshot(
            provider_id="world_bank",
            provider_name="World Bank",
            catalog_url="https://api.worldbank.org/v2/source",
            snapshot_version=f"world-bank:{latest or 'undated'}",
            retrieved_at=datetime.now(timezone.utc),
            coverage_status="complete",
            source_sha256=self._source_sha256(),
            attributes={
                "source_total": self.manifest["source"]["total"],
                "indicator_total": self.manifest["indicator"]["total"],
                "indicator_unique_total": len(seen_indicators),
                "indicator_exact_duplicates": duplicate_indicators,
                "country_or_aggregate_total": self.manifest["country"]["total"],
                "topic_total": self.manifest["topic"]["total"],
                "advanced_resource_total": sum(
                    1 for resource in self.manifest if resource.startswith("sources/")
                ),
                "advanced_value_total": sum(
                    item["total"]
                    for resource, item in self.manifest.items()
                    if resource.startswith("sources/")
                ),
                "sources_with_metadata": sum(
                    item.get("metadataavailability") == "Y" for item in sources
                ),
                "sources_without_metadata": sum(
                    item.get("metadataavailability") != "Y" for item in sources
                ),
            },
            dimensions=[
                self._geography_dimension(countries),
                self._topic_dimension(topics),
            ],
            datasets=datasets,
        )

    @staticmethod
    def _normalize_indicator(item: dict[str, Any]) -> dict[str, Any]:
        source = item.get("source")
        topics = item.get("topics")
        normalized_topics = []
        if isinstance(topics, list):
            normalized_topics = sorted(
                [
                    {
                        "id": str(value.get("id") or "").strip(),
                        "value": str(value.get("value") or "").strip(),
                    }
                    for value in topics
                    if isinstance(value, dict)
                    and (value.get("id") or value.get("value"))
                ],
                key=lambda value: (value["id"], value["value"]),
            )
        return {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "unit": str(item.get("unit") or "").strip(),
            "source": {
                "id": str(source.get("id") or "").strip(),
                "value": str(source.get("value") or "").strip(),
            }
            if isinstance(source, dict)
            else None,
            "sourceNote": str(item.get("sourceNote") or "").strip(),
            "sourceOrganization": str(item.get("sourceOrganization") or "").strip(),
            "topics": normalized_topics,
        }

    async def _source_concepts(
        self, client: httpx.AsyncClient, source_id: str
    ) -> list[dict[str, Any]]:
        resource = f"sources/{quote(source_id, safe='')}/concepts/data"
        rows = await self._advanced_paginated(client, resource, "concept")
        concepts = []
        for item in rows:
            code = str(item.get("id") or "").strip()
            label = str(item.get("value") or item.get("name") or "").strip()
            if not code or not label:
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} returned an invalid concept."
                )
            concepts.append({"id": code, "label": label})
        return concepts

    async def _concept_variables(
        self, client: httpx.AsyncClient, source_id: str, concept_id: str
    ) -> list[dict[str, Any]]:
        resource = (
            f"sources/{quote(source_id, safe='')}/{quote(concept_id.casefold(), safe='')}/data"
        )
        return await self._advanced_paginated(client, resource, "variable")

    async def _advanced_paginated(
        self, client: httpx.AsyncClient, resource: str, item_key: str
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        expected_pages: int | None = None
        expected_total: int | None = None
        page = 1
        while expected_pages is None or page <= expected_pages:
            raw = await self._request(client, resource, page)
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WorldBankCatalogHarvestError("World Bank returned malformed JSON.") from error
            if not isinstance(payload, dict):
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} returned an invalid metadata envelope."
                )
            actual_page = self._integer(payload, "page")
            pages = self._integer(payload, "pages")
            total = self._integer(payload, "total")
            if actual_page != page or pages < 1 or pages > self.max_pages:
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} pagination is inconsistent or excessive."
                )
            if expected_pages is None:
                expected_pages, expected_total = pages, total
            elif pages != expected_pages or total != expected_total:
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} pagination changed during harvest."
                )
            sources = payload.get("source")
            if not isinstance(sources, list):
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} omitted source metadata."
                )
            for source in sources:
                concepts = source.get("concept") if isinstance(source, dict) else None
                if not isinstance(concepts, list):
                    raise WorldBankCatalogHarvestError(
                        f"World Bank {resource} omitted concept metadata."
                    )
                if item_key == "concept":
                    rows.extend(item for item in concepts if isinstance(item, dict))
                else:
                    for concept in concepts:
                        variables = concept.get("variable") if isinstance(concept, dict) else None
                        if not isinstance(variables, list):
                            raise WorldBankCatalogHarvestError(
                                f"World Bank {resource} omitted concept variables."
                            )
                        rows.extend(item for item in variables if isinstance(item, dict))
            page += 1
        if expected_total != len(rows):
            raise WorldBankCatalogHarvestError(
                f"World Bank {resource} returned {len(rows)} of {expected_total} rows."
            )
        self.manifest[resource] = {"pages": expected_pages or 0, "total": len(rows)}
        return rows

    async def _paginated(
        self, client: httpx.AsyncClient, resource: str
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        expected_pages: int | None = None
        expected_total: int | None = None
        page = 1
        while expected_pages is None or page <= expected_pages:
            raw = await self._request(client, resource, page)
            metadata, page_rows = self._envelope(raw)
            actual_page = self._integer(metadata, "page")
            pages = self._integer(metadata, "pages")
            total = self._integer(metadata, "total")
            if actual_page != page or pages < 1 or pages > self.max_pages:
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} pagination is inconsistent or excessive."
                )
            if expected_pages is None:
                expected_pages, expected_total = pages, total
            elif pages != expected_pages or total != expected_total:
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} pagination changed during harvest."
                )
            rows.extend(page_rows)
            page += 1
        if expected_total != len(rows):
            raise WorldBankCatalogHarvestError(
                f"World Bank {resource} returned {len(rows)} of {expected_total} rows."
            )
        self.manifest[resource] = {"pages": expected_pages or 0, "total": len(rows)}
        return rows

    async def _request(
        self, client: httpx.AsyncClient, resource: str, page: int
    ) -> bytes:
        cached = self._cached_raw(resource, page)
        if cached is not None:
            return cached
        for attempt in range(3):
            try:
                async with self._semaphore, client.stream(
                    "GET",
                    f"{self.base_url}/{resource}",
                    params={
                        "format": "json",
                        "page": str(page),
                        "per_page": str(self.page_size),
                    },
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    follow_redirects=False,
                    timeout=httpx.Timeout(connect=10, read=90, write=10, pool=10),
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        retry_after = response.headers.get("Retry-After", "1")
                        await asyncio.sleep(
                            min(float(retry_after), 5.0)
                            if retry_after.isdigit()
                            else float(attempt + 1)
                        )
                        continue
                    if response.status_code != 200:
                        raise WorldBankCatalogHarvestError(
                            f"World Bank {resource} metadata failed "
                            f"(HTTP {response.status_code})."
                        )
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise WorldBankCatalogHarvestError(
                            f"World Bank {resource} returned an unexpected media type."
                        )
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > self.max_page_bytes:
                            raise WorldBankCatalogHarvestError(
                                f"World Bank {resource} page exceeds 10 MB."
                            )
                    raw = bytes(chunks)
                    self._record_raw(resource, page, raw)
                    return raw
            except httpx.TransportError as error:
                if attempt < 2:
                    await asyncio.sleep(float(attempt + 1))
                    continue
                raise WorldBankCatalogHarvestError(
                    f"World Bank {resource} connection failed."
                ) from error
        raise WorldBankCatalogHarvestError(f"World Bank {resource} metadata failed.")

    def _record_raw(self, resource: str, page: int, raw: bytes) -> None:
        digest = hashlib.sha256(raw).hexdigest()
        self._raw_hashes[f"{resource}:{page}"] = digest
        target = self.raw_dir / "world_bank" / resource / f"page-{page:04d}-{digest[:12]}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(target)

    def _cached_raw(self, resource: str, page: int) -> bytes | None:
        directory = self.raw_dir / "world_bank" / resource
        candidates = sorted(
            directory.glob(f"page-{page:04d}-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        now = time.time()
        for candidate in candidates:
            if now - candidate.stat().st_mtime > self.resume_max_age_seconds:
                continue
            raw = candidate.read_bytes()
            if len(raw) > self.max_page_bytes:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if candidate.stem.rsplit("-", 1)[-1] != digest[:12]:
                continue
            self._raw_hashes[f"{resource}:{page}"] = digest
            return raw
        return None

    def _source_sha256(self) -> str:
        if not self._raw_hashes:
            raise WorldBankCatalogHarvestError("World Bank harvest produced no raw metadata.")
        manifest = "".join(
            f"{resource}:{digest}\n"
            for resource, digest in sorted(self._raw_hashes.items())
        )
        return hashlib.sha256(manifest.encode()).hexdigest()

    @staticmethod
    def _envelope(raw: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorldBankCatalogHarvestError("World Bank returned malformed JSON.") from error
        if (
            not isinstance(payload, list)
            or len(payload) != 2
            or not isinstance(payload[0], dict)
            or not isinstance(payload[1], list)
            or any(not isinstance(item, dict) for item in payload[1])
        ):
            raise WorldBankCatalogHarvestError("World Bank returned an invalid page envelope.")
        return payload[0], payload[1]

    @staticmethod
    def _integer(metadata: dict[str, Any], key: str) -> int:
        try:
            value = int(metadata[key])
        except (KeyError, TypeError, ValueError) as error:
            raise WorldBankCatalogHarvestError(
                f"World Bank page metadata is missing {key}."
            ) from error
        if value < 0:
            raise WorldBankCatalogHarvestError(f"World Bank page metadata has invalid {key}.")
        return value

    async def _dataset(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
        indicators: list[dict[str, Any]],
        geography: dict[str, SourceDimensionValue],
    ) -> SourceDataset:
        source_id = str(source["id"])
        rich_indicators = {
            str(item.get("id") or ""): item
            for item in indicators
            if str(item.get("id") or "")
        }
        metadata_available = source.get("metadataavailability") == "Y"
        dimensions: list[SourceDimension]
        series_structure_only = 0
        series_catalog_only = 0
        if metadata_available:
            concepts = await self._source_concepts(client, source_id)
            advertised_concepts = int(source.get("concepts") or 0)
            if advertised_concepts and advertised_concepts != len(concepts):
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} advertised {advertised_concepts} "
                    f"concepts but returned {len(concepts)}."
                )
            variables = await asyncio.gather(
                *[
                    self._concept_variables(client, source_id, str(concept["id"]))
                    for concept in concepts
                ]
            )
            dimensions = []
            for position, (concept, raw_values) in enumerate(
                zip(concepts, variables, strict=True)
            ):
                role = self._dimension_role(str(concept["id"]), str(concept["label"]))
                values, structure_only, catalog_only = self._concept_dimension_values(
                    source_id,
                    role,
                    raw_values,
                    rich_indicators,
                    geography,
                )
                if role == "indicator":
                    series_structure_only += structure_only
                    series_catalog_only += catalog_only
                dimensions.append(
                    SourceDimension(
                        dimension_id=str(concept["id"]),
                        label=str(concept["label"]),
                        role=role,
                        key_position=position,
                        values=values,
                    )
                )
            frequency = self._frequency_dimension(dimensions)
            if frequency is not None:
                dimensions.append(frequency)
        else:
            dimensions = [
                SourceDimension(
                    dimension_id="indicator",
                    label="Indicator / series",
                    role="indicator",
                    values=self._rich_indicator_values(source_id, rich_indicators.values()),
                )
            ]
        updated_at = None
        last_updated = str(source.get("lastupdated") or "")
        if last_updated:
            try:
                updated_at = datetime.fromisoformat(last_updated).replace(tzinfo=timezone.utc)
            except ValueError as error:
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} has an invalid update date."
                ) from error
        return SourceDataset(
            dataset_id=source_id,
            agency_id="World Bank",
            version=last_updated or None,
            title=str(source.get("name") or "").strip() or f"World Bank source {source_id}",
            description=str(source.get("description") or "") or None,
            executable=source_id == "2",
            coverage_status="complete",
            updated_at=updated_at,
            documentation_urls=[str(source.get("url") or "")]
            if source.get("url")
            else [],
            attributes={
                "code": str(source.get("code") or "") or None,
                "concept_count": int(source.get("concepts") or 0),
                "data_available": source.get("dataavailability") == "Y",
                "metadata_available": source.get("metadataavailability") == "Y",
                "connector_dataset_id": "WDI" if source_id == "2" else None,
                "series_structure_only": series_structure_only,
                "series_catalog_only": series_catalog_only,
                "coverage_note": (
                    "All metadata advertised by the provider was harvested."
                    if metadata_available
                    else "The provider does not advertise advanced metadata for this source; "
                    "the global source-scoped indicator catalog was harvested."
                ),
            },
            dimensions=dimensions,
        )

    @classmethod
    def _concept_dimension_values(
        cls,
        source_id: str,
        role: DimensionRole,
        raw_values: list[dict[str, Any]],
        rich_indicators: dict[str, dict[str, Any]],
        geography: dict[str, SourceDimensionValue],
    ) -> tuple[list[SourceDimensionValue], int, int]:
        basic: dict[str, SourceDimensionValue] = {}
        for item in raw_values:
            code = str(item.get("id") or "").strip()
            label = str(item.get("value") or item.get("name") or "").strip()
            if not code or not label:
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} returned an invalid dimension value."
                )
            value = (
                geography[code].model_copy(update={"label": label})
                if role == "geography" and code in geography
                else SourceDimensionValue(code=code, label=label)
            )
            previous = basic.get(code)
            if previous is not None and previous != value:
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} returned conflicting value {code}."
                )
            basic[code] = value
        if role != "indicator":
            return [basic[code] for code in sorted(basic)], 0, 0

        rich = {
            value.code: value
            for value in cls._rich_indicator_values(source_id, rich_indicators.values())
        }
        structure_only = set(basic) - set(rich)
        catalog_only = set(rich) - set(basic)
        values = {
            code: rich.get(code, value)
            for code, value in basic.items()
        }
        values.update({code: rich[code] for code in catalog_only})
        return [values[code] for code in sorted(values)], len(structure_only), len(catalog_only)

    @staticmethod
    def _rich_indicator_values(
        source_id: str, indicators: Iterable[dict[str, Any]]
    ) -> list[SourceDimensionValue]:
        values = []
        for item in sorted(indicators, key=lambda value: str(value.get("id") or "")):
            code = str(item.get("id") or "")
            label = str(item.get("name") or "")
            if not code or not label:
                raise WorldBankCatalogHarvestError(
                    f"World Bank source {source_id} has an invalid indicator."
                )
            topics = item.get("topics")
            topic_values = (
                [str(value.get("value") or "").strip() for value in topics]
                if isinstance(topics, list)
                else []
            )
            values.append(
                SourceDimensionValue(
                    code=code,
                    label=label,
                    description=str(item.get("sourceNote") or "") or None,
                    attributes={
                        "unit": str(item.get("unit") or "") or None,
                        "source_organization": str(item.get("sourceOrganization") or "") or None,
                        "topics": "; ".join(value for value in topic_values if value) or None,
                    },
                )
            )
        return values

    @staticmethod
    def _dimension_role(concept_id: str, label: str) -> DimensionRole:
        term = re.sub(r"[^a-z0-9]+", " ", f"{concept_id} {label}".casefold())
        if re.search(r"\b(series|indicator)\b", term):
            return "indicator"
        if re.search(r"\b(country|economy|geography|area|borrower|lender)\b", term):
            return "geography"
        if re.search(r"\b(time|year|period|date)\b", term):
            return "time"
        if re.search(r"\b(frequency|periodicity)\b", term):
            return "frequency"
        if re.search(r"\b(unit)\b", term):
            return "unit"
        if re.search(r"\b(measure)\b", term):
            return "measure"
        if re.search(r"\b(status|nature)\b", term):
            return "status"
        return "classification"

    @staticmethod
    def _frequency_dimension(dimensions: list[SourceDimension]) -> SourceDimension | None:
        if any(item.role == "frequency" for item in dimensions):
            return None
        time_values = [
            value.code
            for dimension in dimensions
            if dimension.role == "time"
            for value in dimension.values
        ]
        frequencies: dict[str, str] = {}
        for code in time_values:
            normalized = code.upper()
            if re.fullmatch(r"(?:YR)?\d{4}", normalized):
                frequencies["A"] = "Annual"
            elif re.fullmatch(r"(?:YR)?\d{4}Q[1-4]", normalized):
                frequencies["Q"] = "Quarterly"
            elif re.fullmatch(r"(?:YR)?\d{4}M(?:0[1-9]|1[0-2])", normalized):
                frequencies["M"] = "Monthly"
        if not frequencies:
            return None
        return SourceDimension(
            dimension_id="derived_frequency",
            label="Frequency observed in provider time keys",
            role="frequency",
            values=[
                SourceDimensionValue(
                    code=code,
                    label=label,
                    attributes={"derivation": "official_time_dimension_codes"},
                )
                for code, label in sorted(frequencies.items())
            ],
        )

    @classmethod
    def _geography_lookup(
        cls, countries: list[dict[str, Any]]
    ) -> dict[str, SourceDimensionValue]:
        return {value.code: value for value in cls._geography_dimension(countries).values}

    @staticmethod
    def _geography_dimension(countries: list[dict[str, Any]]) -> SourceDimension:
        values = []
        for item in sorted(countries, key=lambda value: str(value.get("id") or "")):
            code = str(item.get("id") or "")
            label = str(item.get("name") or "")
            region_value = item.get("region")
            admin_value = item.get("adminregion")
            income_value = item.get("incomeLevel")
            lending_value = item.get("lendingType")
            region: dict[str, Any] = region_value if isinstance(region_value, dict) else {}
            admin: dict[str, Any] = admin_value if isinstance(admin_value, dict) else {}
            income: dict[str, Any] = income_value if isinstance(income_value, dict) else {}
            lending: dict[str, Any] = lending_value if isinstance(lending_value, dict) else {}
            if not code or not label:
                raise WorldBankCatalogHarvestError("World Bank geography metadata is invalid.")
            is_aggregate = str(region.get("id") or "") == "NA"
            parents = []
            if not is_aggregate:
                parents = list(
                    dict.fromkeys(
                        str(parent.get("id") or "")
                        for parent in (region, admin, income, lending)
                        if parent.get("id") and parent.get("id") != "NA"
                    )
                )
            values.append(
                SourceDimensionValue(
                    code=code,
                    label=label,
                    is_aggregate=is_aggregate,
                    parent_codes=parents,
                    attributes={
                        "iso2_code": str(item.get("iso2Code") or "") or None,
                        "region": str(region.get("value") or "").strip() or None,
                        "admin_region": str(admin.get("value") or "").strip() or None,
                        "income_level": str(income.get("value") or "").strip() or None,
                        "lending_type": str(lending.get("value") or "").strip() or None,
                        "capital_city": str(item.get("capitalCity") or "") or None,
                        "longitude": str(item.get("longitude") or "") or None,
                        "latitude": str(item.get("latitude") or "") or None,
                    },
                )
            )
        return SourceDimension(
            dimension_id="geography",
            label="Country or aggregate",
            role="geography",
            values=values,
        )

    @staticmethod
    def _topic_dimension(topics: list[dict[str, Any]]) -> SourceDimension:
        values = []
        for item in sorted(topics, key=lambda value: str(value.get("id") or "")):
            code = str(item.get("id") or "")
            label = str(item.get("value") or "").strip()
            if not code or not label:
                raise WorldBankCatalogHarvestError("World Bank topic metadata is invalid.")
            values.append(
                SourceDimensionValue(
                    code=code,
                    label=label,
                    description=str(item.get("sourceNote") or "") or None,
                )
            )
        return SourceDimension(
            dimension_id="topic",
            label="Topic",
            role="classification",
            values=values,
        )
