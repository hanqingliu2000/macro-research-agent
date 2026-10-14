"""ADB KIDB SDMX-JSON catalog harvester for Source Index v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from macro_research_agent.knowledge.source_index import (
    ComponentKind,
    DimensionRole,
    ProviderSourceSnapshot,
    SourceCodelist,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
)


class AdbCatalogHarvestError(ValueError):
    pass


@dataclass(frozen=True)
class AdbCatalogResult:
    snapshot: ProviderSourceSnapshot
    codelists: tuple[SourceCodelist, ...]


class AdbCatalogHarvester:
    base_url = "https://kidb.adb.org/api/v5/sdmx/structure"
    resources = (
        "dataflow",
        "datastructure",
        "conceptscheme",
        "codelist",
        "dataconstraint",
    )
    max_bytes = 20 * 1024 * 1024

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        resume_max_age_seconds: int = 24 * 60 * 60,
        request_interval_seconds: float = 3.4,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client
        self.resume_max_age_seconds = resume_max_age_seconds
        self.request_interval_seconds = request_interval_seconds

    async def harvest(self) -> AdbCatalogResult:
        if self.client is not None:
            return await self._harvest(self.client)
        async with httpx.AsyncClient() as client:
            return await self._harvest(client)

    async def _harvest(self, client: httpx.AsyncClient) -> AdbCatalogResult:
        payloads: dict[str, dict[str, Any]] = {}
        hashes: dict[str, str] = {}
        for index, resource in enumerate(self.resources):
            raw, raw_hash, reused = await self._read(client, resource)
            payloads[resource] = self._payload(raw, resource)
            hashes[resource] = raw_hash
            if not reused and index + 1 < len(self.resources):
                await asyncio.sleep(self.request_interval_seconds)

        concepts = self._concepts(payloads["conceptscheme"])
        base_codelists = self._codelists(payloads["codelist"])
        codelist_lookup = {
            (item.agency_id, item.codelist_id, item.version): item
            for item in base_codelists
        }
        structures = self._structures(payloads["datastructure"], concepts)
        constraints = self._constraints(payloads["dataconstraint"])
        flows = self._data(payloads["dataflow"], "dataflows", "dataflow")
        datasets: list[SourceDataset] = []
        constrained_codelists: dict[tuple[str, str, str], SourceCodelist] = {}
        constrained_dimension_total = 0
        for flow in flows:
            agency = self._required_text(flow, "agencyID", "ADB dataflow")
            flow_id = self._required_text(flow, "id", "ADB dataflow")
            version = self._required_text(flow, "version", "ADB dataflow")
            structure_key = self._urn(flow.get("structure"), "DataStructure")
            if structure_key not in structures:
                raise AdbCatalogHarvestError(
                    f"ADB dataflow {flow_id} references a missing data structure."
                )
            dimensions = []
            flow_constraints = constraints.get((agency, flow_id, version), {})
            constraint_ids: set[str] = set()
            for dimension in structures[structure_key]:
                constrained = flow_constraints.get(dimension.dimension_id)
                if constrained is None:
                    dimensions.append(dimension)
                    continue
                values, constraint_id, constraint_version = constrained
                base_key = (
                    dimension.codelist_agency_id,
                    dimension.codelist_id,
                    dimension.codelist_version,
                )
                base = codelist_lookup.get(cast(tuple[str, str, str], base_key))
                if base is None:
                    raise AdbCatalogHarvestError(
                        f"ADB constraint {constraint_id} references a dimension without a codelist."
                    )
                value_lookup = {item.code: item for item in base.values}
                missing = set(values) - set(value_lookup)
                if missing:
                    raise AdbCatalogHarvestError(
                        f"ADB constraint {constraint_id} contains unknown codes."
                    )
                constrained_id = f"{constraint_id}@{dimension.dimension_id}"
                constrained_key = ("ADB.CONSTRAINT", constrained_id, constraint_version)
                constrained_codelists[constrained_key] = SourceCodelist(
                    agency_id=constrained_key[0],
                    codelist_id=constrained_key[1],
                    version=constrained_key[2],
                    label=f"{flow_id} allowed {dimension.label}",
                    description=(
                        "Provider-published allowed values from "
                        f"ADB data constraint {constraint_id}."
                    ),
                    values=[value_lookup[code] for code in values],
                )
                dimensions.append(
                    dimension.model_copy(
                        update={
                            "codelist_agency_id": constrained_key[0],
                            "codelist_id": constrained_key[1],
                            "codelist_version": constrained_key[2],
                        }
                    )
                )
                constraint_ids.add(constraint_id)
                constrained_dimension_total += 1
            connector_dataset = "NATIONAL_ACCOUNTS" if flow_id == "DF_NA" else None
            datasets.append(
                SourceDataset(
                    dataset_id=f"{agency}:{flow_id}",
                    agency_id=agency,
                    version=version,
                    title=self._label(flow, flow_id),
                    description=self._description(flow),
                    executable=connector_dataset is not None,
                    coverage_status="complete",
                    attributes={
                        "dataflow_id": flow_id,
                        "structure_agency_id": structure_key[0],
                        "structure_id": structure_key[1],
                        "structure_version": structure_key[2],
                        "constraint_ids": ";".join(sorted(constraint_ids)) or None,
                        "connector_dataset_id": connector_dataset,
                    },
                    dimensions=dimensions,
                )
            )

        all_codelists = [*base_codelists, *constrained_codelists.values()]
        referenced = {
            (
                dimension.codelist_agency_id,
                dimension.codelist_id,
                dimension.codelist_version,
            )
            for dataset in datasets
            for dimension in dataset.dimensions
            if dimension.codelist_id
        }
        available = {
            (item.agency_id, item.codelist_id, item.version) for item in all_codelists
        }
        if not referenced.issubset(available):
            raise AdbCatalogHarvestError("ADB structures reference missing codelists.")
        prepared = self._required_text(payloads["dataflow"]["meta"], "prepared", "ADB meta")
        combined_hash = hashlib.sha256(
            "".join(f"{key}:{value}\n" for key, value in sorted(hashes.items())).encode()
        ).hexdigest()
        snapshot = ProviderSourceSnapshot(
            provider_id="adb",
            provider_name="Asian Development Bank",
            catalog_url="https://kidb.adb.org/api",
            snapshot_version=f"adb-kidb:{prepared}",
            retrieved_at=datetime.now(timezone.utc),
            coverage_status="complete",
            source_sha256=combined_hash,
            attributes={
                "dataflow_total": len(flows),
                "datastructure_total": len(structures),
                "codelist_total": len(base_codelists),
                "constraint_total": sum(len(item) for item in constraints.values()),
                "constrained_dimension_total": constrained_dimension_total,
                "code_total": sum(len(item.values) for item in base_codelists),
            },
            datasets=datasets,
        )
        return AdbCatalogResult(snapshot=snapshot, codelists=tuple(all_codelists))

    async def _read(
        self, client: httpx.AsyncClient, resource: str
    ) -> tuple[bytes, str, bool]:
        url = f"{self.base_url}/{resource}/all/all/+"
        params = {"format": "sdmx-json"}
        request_hash = hashlib.sha256(
            f"{url}?{urlencode(sorted(params.items()))}".encode()
        ).hexdigest()[:12]
        directory = self.raw_dir / "adb"
        directory.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for candidate in sorted(
            directory.glob(f"{resource}-{request_hash}-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if now - candidate.stat().st_mtime > self.resume_max_age_seconds:
                continue
            raw = candidate.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if candidate.stem.rsplit("-", 1)[-1] == digest[:12]:
                return raw, digest, True

        temporary = directory / f".{resource}-{uuid4().hex}.partial"
        try:
            for attempt in range(3):
                try:
                    async with client.stream(
                        "GET",
                        url,
                        params=params,
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                        follow_redirects=False,
                        timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
                    ) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(float(attempt + 1))
                            continue
                        if response.status_code != 200:
                            raise AdbCatalogHarvestError(
                                f"ADB {resource} catalog failed (HTTP {response.status_code})."
                            )
                        if "json" not in response.headers.get("content-type", "").casefold():
                            raise AdbCatalogHarvestError(
                                f"ADB {resource} catalog returned non-JSON content."
                            )
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_bytes:
                                raise AdbCatalogHarvestError(
                                    f"ADB {resource} catalog exceeds 20 MB."
                                )
                        raw = bytes(chunks)
                        digest = hashlib.sha256(raw).hexdigest()
                        target = directory / f"{resource}-{request_hash}-{digest[:12]}.json"
                        temporary.write_bytes(raw)
                        temporary.replace(target)
                        return raw, digest, False
                except httpx.TransportError as error:
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise AdbCatalogHarvestError("ADB catalog connection failed.") from error
        finally:
            temporary.unlink(missing_ok=True)
        raise AdbCatalogHarvestError(f"ADB {resource} catalog failed.")

    @staticmethod
    def _payload(raw: bytes, resource: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AdbCatalogHarvestError(f"ADB {resource} returned malformed JSON.") from error
        if (
            not isinstance(payload, dict)
            or not str(payload.get("$schema") or "").startswith("https://json.sdmx.org/")
            or not isinstance(payload.get("meta"), dict)
            or not isinstance(payload.get("data"), dict)
        ):
            raise AdbCatalogHarvestError(f"ADB {resource} returned an invalid SDMX envelope.")
        return cast(dict[str, Any], payload)

    @staticmethod
    def _data(
        payload: dict[str, Any], key: str, label: str
    ) -> list[dict[str, Any]]:
        values = payload["data"].get(key)
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise AdbCatalogHarvestError(f"ADB {label} catalog is missing {key}.")
        return cast(list[dict[str, Any]], values)

    @classmethod
    def _concepts(cls, payload: dict[str, Any]) -> dict[tuple[str, str, str, str], str]:
        result = {}
        for scheme in cls._data(payload, "conceptschemes", "concept"):
            key = cls._maintainable(scheme, "ADB concept scheme")
            concepts = scheme.get("concepts")
            if not isinstance(concepts, list):
                raise AdbCatalogHarvestError("ADB concept scheme omitted concepts.")
            for concept in concepts:
                if not isinstance(concept, dict):
                    raise AdbCatalogHarvestError("ADB concept is malformed.")
                concept_id = cls._required_text(concept, "id", "ADB concept")
                result[(*key, concept_id)] = cls._label(concept, concept_id)
        return result

    @classmethod
    def _codelists(cls, payload: dict[str, Any]) -> list[SourceCodelist]:
        result = []
        for item in cls._data(payload, "codelists", "codelist"):
            agency, codelist_id, version = cls._maintainable(item, "ADB codelist")
            if item.get("isPartial") is True:
                raise AdbCatalogHarvestError(f"ADB codelist {codelist_id} is partial.")
            raw_codes = item.get("codes")
            if not isinstance(raw_codes, list):
                raise AdbCatalogHarvestError(f"ADB codelist {codelist_id} omitted codes.")
            values = []
            for raw_code in raw_codes:
                if not isinstance(raw_code, dict):
                    raise AdbCatalogHarvestError("ADB codelist code is malformed.")
                code = cls._required_text(raw_code, "id", "ADB codelist code")
                parent = str(raw_code.get("parent") or "").strip()
                values.append(
                    SourceDimensionValue(
                        code=code,
                        label=cls._label(raw_code, code),
                        description=cls._description(raw_code),
                        parent_codes=[parent] if parent else [],
                    )
                )
            result.append(
                SourceCodelist(
                    agency_id=agency,
                    codelist_id=codelist_id,
                    version=version,
                    label=cls._label(item, codelist_id),
                    description=cls._description(item),
                    values=values,
                )
            )
        return result

    @classmethod
    def _structures(
        cls,
        payload: dict[str, Any],
        concepts: dict[tuple[str, str, str, str], str],
    ) -> dict[tuple[str, str, str], list[SourceDimension]]:
        result = {}
        for item in cls._data(payload, "datastructures", "data structure"):
            key = cls._maintainable(item, "ADB data structure")
            components = item.get("dataStructureComponents")
            if not isinstance(components, dict):
                raise AdbCatalogHarvestError("ADB data structure omitted components.")
            dimensions: list[SourceDimension] = []
            dimension_list = components.get("dimensionList", {})
            if not isinstance(dimension_list, dict):
                raise AdbCatalogHarvestError("ADB dimension list is malformed.")
            raw_dimensions = dimension_list.get("dimensions", [])
            if not isinstance(raw_dimensions, list):
                raise AdbCatalogHarvestError("ADB dimensions are malformed.")
            dimensions.extend(
                cls._dimension(raw, "dimension", concepts)
                for raw in raw_dimensions
                if isinstance(raw, dict)
            )
            time_dimension = dimension_list.get("timeDimension")
            if isinstance(time_dimension, dict):
                dimensions.append(cls._dimension(time_dimension, "time", concepts))
            measure_list = components.get("measureList", {})
            if isinstance(measure_list, dict):
                primary = measure_list.get("primaryMeasure")
                if isinstance(primary, dict):
                    dimensions.append(cls._dimension(primary, "measure", concepts))
            attribute_list = components.get("attributeList", {})
            if isinstance(attribute_list, dict):
                raw_attributes = attribute_list.get("attributes", [])
                if not isinstance(raw_attributes, list):
                    raise AdbCatalogHarvestError("ADB attributes are malformed.")
                dimensions.extend(
                    cls._dimension(raw, "attribute", concepts)
                    for raw in raw_attributes
                    if isinstance(raw, dict)
                )
            result[key] = dimensions
        return result

    @classmethod
    def _dimension(
        cls,
        item: dict[str, Any],
        kind: ComponentKind,
        concepts: dict[tuple[str, str, str, str], str],
    ) -> SourceDimension:
        dimension_id = cls._required_text(item, "id", "ADB component")
        concept_key = cls._urn(item.get("conceptIdentity"), "Concept", item_id=True)
        label = cls._label(
            item,
            concepts.get(cast(tuple[str, str, str, str], concept_key), dimension_id),
        )
        representation = item.get("localRepresentation")
        enumeration = (
            representation.get("enumeration")
            if isinstance(representation, dict)
            else None
        )
        codelist = cls._urn(enumeration, "Codelist") if enumeration else (None, None, None)
        position = item.get("position")
        key_position = int(position) - 1 if isinstance(position, int) else None
        return SourceDimension(
            dimension_id=dimension_id,
            label=label,
            role=cls._role(dimension_id, label, kind),
            component_kind=kind,
            key_position=key_position,
            codelist_agency_id=codelist[0],
            codelist_id=codelist[1],
            codelist_version=codelist[2],
        )

    @classmethod
    def _constraints(
        cls, payload: dict[str, Any]
    ) -> dict[
        tuple[str, str, str], dict[str, tuple[list[str], str, str]]
    ]:
        result: dict[
            tuple[str, str, str], dict[str, tuple[list[str], str, str]]
        ] = {}
        for item in cls._data(payload, "dataConstraints", "data constraint"):
            _, constraint_id, version = cls._maintainable(item, "ADB data constraint")
            if str(item.get("role") or "").casefold() != "allowed":
                raise AdbCatalogHarvestError("ADB returned a non-allowed data constraint.")
            attachment = item.get("constraintAttachment")
            flows = attachment.get("dataflows") if isinstance(attachment, dict) else None
            if not isinstance(flows, list) or not flows:
                raise AdbCatalogHarvestError("ADB data constraint omitted its dataflow.")
            regions = item.get("cubeRegions")
            if not isinstance(regions, list) or not regions:
                raise AdbCatalogHarvestError("ADB data constraint omitted cube regions.")
            dimensions: dict[str, tuple[list[str], str, str]] = {}
            for region in regions:
                if not isinstance(region, dict) or region.get("include") is not True:
                    raise AdbCatalogHarvestError("ADB returned an unsupported constraint region.")
                key_values = region.get("keyValues")
                if not isinstance(key_values, list):
                    raise AdbCatalogHarvestError("ADB constraint region omitted key values.")
                for key_value in key_values:
                    if not isinstance(key_value, dict):
                        raise AdbCatalogHarvestError("ADB constraint value is malformed.")
                    dimension_id = cls._required_text(
                        key_value, "id", "ADB constraint dimension"
                    )
                    values = key_value.get("values")
                    if not isinstance(values, list) or any(
                        not isinstance(value, str) for value in values
                    ):
                        raise AdbCatalogHarvestError("ADB constraint codes are malformed.")
                    dimensions[dimension_id] = (
                        list(dict.fromkeys(values)),
                        constraint_id,
                        version,
                    )
            for flow_urn in flows:
                flow_key = cls._urn(flow_urn, "Dataflow")
                result[cast(tuple[str, str, str], flow_key)] = dimensions
        return result

    @staticmethod
    def _urn(
        value: object,
        expected_class: str,
        *,
        item_id: bool = False,
    ) -> tuple[str | None, ...]:
        if not isinstance(value, str):
            raise AdbCatalogHarvestError(f"ADB omitted an {expected_class} reference.")
        suffix = r"\.([^.]+)$" if item_id else "$"
        match = re.search(
            rf"\.{expected_class}=([^:]+):([^()]+)\(([^()]+)\){suffix}", value
        )
        if not match:
            raise AdbCatalogHarvestError(f"ADB returned an invalid {expected_class} URN.")
        return tuple(match.groups())

    @staticmethod
    def _maintainable(
        item: dict[str, Any], label: str
    ) -> tuple[str, str, str]:
        return (
            AdbCatalogHarvester._required_text(item, "agencyID", label),
            AdbCatalogHarvester._required_text(item, "id", label),
            AdbCatalogHarvester._required_text(item, "version", label),
        )

    @staticmethod
    def _required_text(item: dict[str, Any], key: str, label: str) -> str:
        value = str(item.get(key) or "").strip()
        if not value:
            raise AdbCatalogHarvestError(f"{label} omitted {key}.")
        return value

    @staticmethod
    def _label(item: dict[str, Any], fallback: str) -> str:
        names = item.get("names")
        value = names.get("en") if isinstance(names, dict) else item.get("name")
        return " ".join(str(value or fallback).split())

    @staticmethod
    def _description(item: dict[str, Any]) -> str | None:
        descriptions = item.get("descriptions")
        value = (
            descriptions.get("en")
            if isinstance(descriptions, dict)
            else item.get("description")
        )
        normalized = " ".join(str(value or "").split())
        return normalized or None

    @staticmethod
    def _role(
        dimension_id: str, label: str, kind: ComponentKind
    ) -> DimensionRole:
        term = f"{dimension_id} {label}".casefold()
        if kind == "time" or "time" in term:
            return "time"
        if "freq" in term:
            return "frequency"
        if any(value in term for value in ("economy", "area", "country")):
            return "geography"
        if "indicator" in term:
            return "indicator"
        if "unit" in term:
            return "unit"
        if kind == "measure" or "measure" in term or "obs_value" in term:
            return "measure"
        if "status" in term or "nature" in term:
            return "status"
        return "classification"
