"""Streaming SDMX structure-catalog harvesting for Source Index v2."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlparse
from uuid import uuid4
from xml.etree import ElementTree as ET

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


class SdmxCatalogHarvestError(ValueError):
    pass


@dataclass(frozen=True)
class SdmxProviderConfig:
    provider_id: str
    provider_name: str
    base_url: str
    catalog_url: str
    dataflow_path: str
    dataflow_references: str
    structure_path: str | None = None
    structure_references: str = "all"
    executable_flows: tuple[tuple[str, str, str], ...] = ()
    max_bytes: int = 512 * 1024 * 1024
    constraint_paths: tuple[str, ...] = ()
    availability_path_template: str | None = None
    availability_components: Literal["all", "explicit"] = "all"
    allow_unadvertised_availability: bool = False
    availability_request_interval_seconds: float = 0.1


@dataclass(frozen=True)
class SdmxFlow:
    agency_id: str
    flow_id: str
    version: str
    title: str
    description: str | None
    structure_agency_id: str | None
    structure_id: str | None
    structure_version: str | None
    attributes: dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class SdmxCatalogResult:
    snapshot: ProviderSourceSnapshot
    structure_paths: tuple[Path, ...]
    availability: tuple[SdmxAvailability, ...] = ()
    geography_codelists: tuple[tuple[str, str, str], ...] = ()

    def codelists(self) -> Iterator[SourceCodelist]:
        seen: dict[tuple[str, str, str], str] = {}
        source_codelists: dict[tuple[str, str, str], SourceCodelist] = {}
        source_value_codes: dict[tuple[str, str, str], frozenset[str]] = {}
        flow_labels = {
            (
                dataset.agency_id,
                str(dataset.attributes.get("dataflow_id") or ""),
                dataset.version,
            ): f"{dataset.title} {dataset.description or ''}"
            for dataset in self.snapshot.datasets
        }
        geography = set(self.geography_codelists)
        for path in self.structure_paths:
            for codelist in iter_sdmx_codelists(path):
                key = (codelist.agency_id, codelist.codelist_id, codelist.version)
                digest = hashlib.sha256(codelist.model_dump_json().encode()).hexdigest()
                previous = seen.get(key)
                if previous is not None:
                    if previous != digest:
                        raise SdmxCatalogHarvestError(
                            f"Conflicting SDMX codelist across resources: {key}."
                        )
                    continue
                seen[key] = digest
                if key in geography:
                    codelist = codelist.model_copy(
                        update={
                            "values": [
                                _classify_sdmx_geography(value)
                                for value in codelist.values
                            ]
                        }
                    )
                source_codelists[key] = codelist
                source_value_codes[key] = frozenset(
                    value.code for value in codelist.values
                )
                yield codelist
        for item in self.availability:
            source_reference = item.source_codelist
            if source_reference is None and item.role != "time":
                source_reference = _match_codelist_by_available_codes(
                    item,
                    source_codelists,
                    source_value_codes,
                    flow_labels.get(
                        (item.agency_id, item.flow_id, item.flow_version), ""
                    ),
                )
            if source_reference is None:
                label = item.dimension_id
                values = [_availability_only_value(code) for code in item.codes]
            else:
                source = source_codelists.get(source_reference)
                if source is None:
                    matched_reference = _match_codelist_by_available_codes(
                        item,
                        source_codelists,
                        source_value_codes,
                        flow_labels.get(
                            (item.agency_id, item.flow_id, item.flow_version), ""
                        ),
                    )
                    source = (
                        source_codelists.get(matched_reference)
                        if matched_reference is not None
                        else None
                    )
                label = source.label if source is not None else item.dimension_id
                lookup = (
                    {value.code: value for value in source.values}
                    if source is not None
                    else {}
                )
                if set(item.codes) - set(lookup):
                    matched_reference = _match_codelist_by_available_codes(
                        item,
                        source_codelists,
                        source_value_codes,
                        flow_labels.get(
                            (item.agency_id, item.flow_id, item.flow_version), ""
                        ),
                    )
                    if matched_reference is not None:
                        source = source_codelists[matched_reference]
                        label = source.label
                        lookup = {value.code: value for value in source.values}
                values = [
                    lookup.get(code) or _availability_only_value(code)
                    for code in item.codes
                ]
            yield SourceCodelist(
                agency_id=item.availability_agency,
                codelist_id=item.availability_codelist_id,
                version=self.snapshot.snapshot_version,
                label=f"{item.flow_id} available {label}",
                description="Provider-published actual or allowed dataflow positions.",
                values=values,
            )


@dataclass(frozen=True)
class SdmxAvailability:
    agency_id: str
    flow_id: str
    flow_version: str
    dimension_id: str
    role: DimensionRole
    codes: tuple[str, ...]
    source_codelist: tuple[str, str, str] | None
    constraint_type: str
    availability_agency: str
    availability_codelist_id: str


@dataclass(frozen=True)
class SdmxFlowConstraint:
    constraint_type: str
    constraint_ids: tuple[str, ...]
    values: dict[str, tuple[str, ...]]


SDMX_PROVIDER_CONFIGS: dict[str, SdmxProviderConfig] = {
    "imf_data": SdmxProviderConfig(
        provider_id="imf_data",
        provider_name="International Monetary Fund",
        base_url="https://api.imf.org/external/sdmx/2.1",
        catalog_url="https://data.imf.org/en/Resource-Pages/IMF-API",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="all",
        executable_flows=(
            ("IMF.STA", "CPI", "CPI"),
            ("IMF.RES", "WEO", "WEO"),
        ),
        availability_path_template=(
            "availableconstraint/{agency},{flow},{version}/all/all/all"
        ),
        allow_unadvertised_availability=True,
        availability_request_interval_seconds=0.2,
    ),
    "oecd": SdmxProviderConfig(
        provider_id="oecd",
        provider_name="Organisation for Economic Co-operation and Development",
        base_url="https://sdmx.oecd.org/public/rest",
        catalog_url="https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="parents",
        structure_path="datastructure/all/all/all",
        structure_references="all",
        executable_flows=(("OECD.SDD.STES", "DSD_STES@DF_CLI", "CLI"),),
        max_bytes=1024 * 1024 * 1024,
        constraint_paths=(
            "contentconstraint/all/all/latest",
            "https://sdmx.oecd.org/dcd-public/rest/contentconstraint/all/all/latest",
            "https://sdmx.oecd.org/sti-public/rest/contentconstraint/all/all/latest",
            "https://sdmx.oecd.org/archive/rest/contentconstraint/all/all/latest",
        ),
        availability_path_template=(
            "availableconstraint/{agency},{flow},{version}/all/all/all"
        ),
        allow_unadvertised_availability=True,
    ),
    "ecb": SdmxProviderConfig(
        provider_id="ecb",
        provider_name="European Central Bank",
        base_url="https://data-api.ecb.europa.eu/service",
        catalog_url="https://data.ecb.europa.eu/help/api/data",
        dataflow_path="dataflow/all/all/latest",
        dataflow_references="all",
        executable_flows=(("ECB", "EXR", "EXCHANGE_RATES"),),
        constraint_paths=("contentconstraint/all/all/latest",),
        allow_unadvertised_availability=True,
    ),
    "bis": SdmxProviderConfig(
        provider_id="bis",
        provider_name="Bank for International Settlements",
        base_url="https://stats.bis.org/api/v2",
        catalog_url="https://stats.bis.org/api-doc/v2/",
        dataflow_path="structure/dataflow/all/all/latest",
        dataflow_references="all",
        executable_flows=(("BIS", "WS_CBPOL", "POLICY_RATES"),),
        max_bytes=128 * 1024 * 1024,
        availability_path_template=(
            "availability/dataflow/{agency}/{flow}/{version}/*/{components}"
        ),
        availability_components="explicit",
        allow_unadvertised_availability=True,
        availability_request_interval_seconds=0.2,
    ),
}


class SdmxCatalogHarvester:
    xml_accept = "application/vnd.sdmx.structure+xml;version=2.1"

    def __init__(
        self,
        config: SdmxProviderConfig,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        resume_max_age_seconds: int = 24 * 60 * 60,
    ) -> None:
        self.config = config
        self.raw_dir = raw_dir
        self.client = client
        self.resume_max_age_seconds = resume_max_age_seconds

    async def harvest(self) -> SdmxCatalogResult:
        if self.client is not None:
            return await self._harvest(self.client)
        async with httpx.AsyncClient() as client:
            return await self._harvest(client)

    async def _harvest(self, client: httpx.AsyncClient) -> SdmxCatalogResult:
        flow_path, flow_hash = await self._download(
            client,
            "dataflows",
            self.config.dataflow_path,
            {"references": self.config.dataflow_references},
        )
        if self.config.structure_path:
            structure_path, structure_hash = await self._download(
                client,
                "structures",
                self.config.structure_path,
                {"references": self.config.structure_references},
            )
        else:
            structure_path, structure_hash = flow_path, flow_hash

        flows = parse_sdmx_dataflows(flow_path)
        structure_paths = [structure_path]
        source_hashes = {"dataflows": flow_hash, "structures": structure_hash}
        if self.config.provider_id == "oecd":
            external = [item for item in flows.values() if item.structure_id is None]
            for index, flow in enumerate(external):
                structure_url = str(flow.attributes.get("structure_url") or "")
                parsed = urlparse(structure_url)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "sdmx.oecd.org"
                    or not parsed.path.startswith(
                        (
                            "/public/rest/",
                            "/dcd-public/rest/",
                            "/sti-public/rest/",
                            "/archive/rest/",
                        )
                    )
                ):
                    raise SdmxCatalogHarvestError(
                        f"OECD dataflow {flow.agency_id}:{flow.flow_id} has an "
                        "unapproved external structure URL."
                    )
                label = "external-" + hashlib.sha256(
                    f"{flow.agency_id}:{flow.flow_id}:{flow.version}".encode()
                ).hexdigest()[:12]
                external_path, external_hash = await self._download(
                    client,
                    label,
                    "",
                    {"references": "all"},
                    absolute_url=structure_url,
                )
                detail_flows = parse_sdmx_dataflows(external_path)
                detail = detail_flows.get((flow.agency_id, flow.flow_id, flow.version))
                if detail is None or detail.structure_id is None:
                    raise SdmxCatalogHarvestError(
                        f"OECD external dataflow {flow.agency_id}:{flow.flow_id} "
                        "did not resolve its data structure."
                    )
                flows[(flow.agency_id, flow.flow_id, flow.version)] = detail
                structure_paths.append(external_path)
                source_hashes[label] = external_hash
                if index + 1 < len(external):
                    await asyncio.sleep(3.1)

        concepts: dict[tuple[str, str, str, str], str] = {}
        structures: dict[
            tuple[str | None, str | None, str | None], list[SourceDimension]
        ] = {}
        codelist_keys: set[tuple[str, str, str]] = set()
        raw_codelist_total = 0
        raw_code_total = 0
        for path in structure_paths:
            for concept_key, concept_label in parse_sdmx_concepts(path).items():
                previous_label = concepts.get(concept_key)
                if previous_label is not None and previous_label != concept_label:
                    raise SdmxCatalogHarvestError(
                        f"Conflicting SDMX concept {concept_key}."
                    )
                concepts[concept_key] = concept_label
        for path in structure_paths:
            for structure_key, structure_dimensions in parse_sdmx_structures(
                path, concepts
            ).items():
                previous_dimensions = structures.get(structure_key)
                if (
                    previous_dimensions is not None
                    and previous_dimensions != structure_dimensions
                ):
                    raise SdmxCatalogHarvestError(
                        f"Conflicting SDMX structure {structure_key}."
                    )
                structures[structure_key] = structure_dimensions
            path_keys, path_codelists, path_codes = scan_sdmx_codelists(path)
            codelist_keys.update(path_keys)
            raw_codelist_total += path_codelists
            raw_code_total += path_codes
        prepared = read_sdmx_prepared(flow_path)
        snapshot_version = f"sdmx:{prepared or flow_hash[:12]}"
        availability_by_flow: dict[tuple[str, str, str], SdmxFlowConstraint] = {}
        availability_items: list[SdmxAvailability] = []
        availability_constraint_total = 0
        unadvertised_flows: set[tuple[str, str, str]] = set()
        if self.config.constraint_paths or self.config.availability_path_template:
            (
                availability_by_flow,
                availability_constraint_total,
                availability_hashes,
                unadvertised_flows,
            ) = await self._collect_availability(client, flows, structures)
            source_hashes.update(availability_hashes)
        geography_codelists = {
            (
                str(dimension.codelist_agency_id),
                str(dimension.codelist_id),
                str(dimension.codelist_version),
            )
            for dimensions in structures.values()
            for dimension in dimensions
            if dimension.role == "geography" and dimension.codelist_id
        }
        executable = {
            (agency, flow): connector_dataset
            for agency, flow, connector_dataset in self.config.executable_flows
        }
        datasets: list[SourceDataset] = []
        unresolved_structures = 0
        unresolved_codelists: set[tuple[str, str, str]] = set()
        availability_only_dimension_total = 0
        for flow in sorted(flows.values(), key=lambda item: (item.agency_id, item.flow_id)):
            structure_key = (
                flow.structure_agency_id,
                flow.structure_id,
                flow.structure_version,
            )
            dimensions = list(structures.get(structure_key, []))
            if not all(structure_key) or structure_key not in structures:
                unresolved_structures += 1
            for dimension in dimensions:
                reference = (
                    dimension.codelist_agency_id,
                    dimension.codelist_id,
                    dimension.codelist_version,
                )
                if all(reference) and reference not in codelist_keys:
                    unresolved_codelists.add(
                        (str(reference[0]), str(reference[1]), str(reference[2]))
                    )
            constraint = availability_by_flow.get(
                (flow.agency_id, flow.flow_id, flow.version)
            )
            indexed_dimensions = {item.dimension_id: item for item in dimensions}
            constrained_dimensions = []
            availability_only_dimensions: list[str] = []
            if constraint is not None:
                unknown = set(constraint.values) - set(indexed_dimensions)
                if unknown:
                    positioned = [
                        item.key_position
                        for item in dimensions
                        if item.key_position is not None
                    ]
                    next_position = max(positioned, default=-1) + 1
                    for offset, dimension_id in enumerate(sorted(unknown)):
                        dimensions.append(
                            SourceDimension(
                                dimension_id=dimension_id,
                                label=dimension_id,
                                role=_dimension_role(
                                    dimension_id, dimension_id, "dimension"
                                ),
                                component_kind="dimension",
                                key_position=next_position + offset,
                            )
                        )
                    availability_only_dimensions = sorted(unknown)
                    availability_only_dimension_total += len(unknown)
                for dimension in dimensions:
                    codes = constraint.values.get(dimension.dimension_id)
                    if codes is None:
                        constrained_dimensions.append(dimension)
                        continue
                    source_codelist = (
                        (
                            str(dimension.codelist_agency_id),
                            str(dimension.codelist_id),
                            str(dimension.codelist_version),
                        )
                        if dimension.codelist_id
                        else None
                    )
                    if source_codelist is None and dimension.role != "time":
                        source_codelist = _infer_codelist_reference(
                            flow, dimension.dimension_id, codelist_keys
                        )
                    availability_agency = f"{self.config.provider_id.upper()}.AVAILABILITY"
                    availability_codelist_id = (
                        f"{flow.agency_id}:{flow.flow_id}@{dimension.dimension_id}"
                    )
                    availability_items.append(
                        SdmxAvailability(
                            agency_id=flow.agency_id,
                            flow_id=flow.flow_id,
                            flow_version=flow.version,
                            dimension_id=dimension.dimension_id,
                            role=dimension.role,
                            codes=codes,
                            source_codelist=source_codelist,
                            constraint_type=constraint.constraint_type,
                            availability_agency=availability_agency,
                            availability_codelist_id=availability_codelist_id,
                        )
                    )
                    constrained_dimensions.append(
                        dimension.model_copy(
                            update={
                                "codelist_agency_id": availability_agency,
                                "codelist_id": availability_codelist_id,
                                "codelist_version": snapshot_version,
                                "values": [],
                            }
                        )
                    )
                dimensions = constrained_dimensions
            connector_dataset = executable.get((flow.agency_id, flow.flow_id))
            complete = bool(
                self.config.constraint_paths or self.config.availability_path_template
            )
            availability_status = (
                constraint.constraint_type
                if constraint is not None
                else "not_advertised"
                if (flow.agency_id, flow.flow_id, flow.version) in unadvertised_flows
                else "not_collected"
            )
            datasets.append(
                SourceDataset(
                    dataset_id=f"{flow.agency_id}:{flow.flow_id}",
                    agency_id=flow.agency_id,
                    version=flow.version,
                    title=flow.title,
                    description=flow.description,
                    executable=connector_dataset is not None,
                    coverage_status="complete" if complete else "partial",
                    documentation_urls=[],
                    attributes={
                        **flow.attributes,
                        "dataflow_id": flow.flow_id,
                        "structure_agency_id": flow.structure_agency_id,
                        "structure_id": flow.structure_id,
                        "structure_version": flow.structure_version,
                        "connector_dataset_id": connector_dataset,
                        "availability_status": availability_status,
                        "availability_only_dimensions": ";".join(
                            availability_only_dimensions
                        )
                        or None,
                        "constraint_ids": ";".join(constraint.constraint_ids)
                        if constraint
                        else None,
                    },
                    dimensions=dimensions,
                )
            )

        combined_hash = hashlib.sha256(
            "".join(
                f"{label}:{digest}\n" for label, digest in sorted(source_hashes.items())
            ).encode()
        ).hexdigest()
        snapshot = ProviderSourceSnapshot(
            provider_id=self.config.provider_id,
            provider_name=self.config.provider_name,
            catalog_url=self.config.catalog_url,
            snapshot_version=snapshot_version,
            retrieved_at=datetime.now(timezone.utc),
            coverage_status=(
                "complete"
                if self.config.constraint_paths or self.config.availability_path_template
                else "partial"
            ),
            source_sha256=combined_hash,
            attributes={
                "dataflow_total": len(flows),
                "datastructure_total": len(structures),
                "raw_codelist_element_total": raw_codelist_total,
                "raw_code_element_total": raw_code_total,
                "unique_codelist_total": len(codelist_keys),
                "unresolved_structure_total": unresolved_structures,
                "unresolved_codelist_total": len(unresolved_codelists),
                "availability_constraint_total": availability_constraint_total,
                "availability_flow_total": len(availability_by_flow),
                "unadvertised_availability_flow_total": len(unadvertised_flows),
                "availability_only_dimension_total": availability_only_dimension_total,
                "coverage_note": (
                    "Complete structural and availability catalog. A not_advertised status means "
                    "the provider publishes the dataflow but no separate availability constraint."
                    if self.config.constraint_paths or self.config.availability_path_template
                    else "Structural catalog collected; availability metadata is not configured."
                ),
            },
            datasets=datasets,
        )
        return SdmxCatalogResult(
            snapshot=snapshot,
            structure_paths=tuple(dict.fromkeys(structure_paths)),
            availability=tuple(availability_items),
            geography_codelists=tuple(sorted(geography_codelists)),
        )

    async def _collect_availability(
        self,
        client: httpx.AsyncClient,
        flows: dict[tuple[str, str, str], SdmxFlow],
        structures: dict[
            tuple[str | None, str | None, str | None], list[SourceDimension]
        ],
    ) -> tuple[
        dict[tuple[str, str, str], SdmxFlowConstraint],
        int,
        dict[str, str],
        set[tuple[str, str, str]],
    ]:
        by_pair = {(item.agency_id, item.flow_id): key for key, item in flows.items()}
        constraints: dict[tuple[str, str, str], SdmxFlowConstraint] = {}
        hashes: dict[str, str] = {}
        raw_constraint_total = 0
        for index, resource in enumerate(self.config.constraint_paths):
            label = f"constraints-{index}"
            absolute = resource if resource.startswith("https://") else None
            path, digest = await self._download(
                client,
                label,
                "" if absolute else resource,
                {"detail": "full", "references": "none"},
                absolute_url=absolute,
            )
            parsed, total = parse_sdmx_constraints(path, by_pair=by_pair)
            raw_constraint_total += total
            hashes[label] = digest
            for key, value in parsed.items():
                constraints.setdefault(key, value)
            if index + 1 < len(self.config.constraint_paths):
                await asyncio.sleep(self.config.availability_request_interval_seconds)

        missing = [key for key in flows if key not in constraints]
        template = self.config.availability_path_template
        if template:
            for index, key in enumerate(missing):
                flow = flows[key]
                structure_key = (
                    flow.structure_agency_id,
                    flow.structure_id,
                    flow.structure_version,
                )
                dimensions = structures.get(structure_key, [])
                components = "all"
                if self.config.availability_components == "explicit":
                    selected = [
                        item.dimension_id
                        for item in dimensions
                        if item.component_kind == "dimension" and item.codelist_id
                    ]
                    if not selected:
                        raise SdmxCatalogHarvestError(
                            f"{self.config.provider_name} {flow.flow_id} has no "
                            "availability components."
                        )
                    components = ",".join(selected)
                resource = template.format(
                    agency=flow.agency_id,
                    flow=flow.flow_id,
                    version=flow.version,
                    components=components,
                )
                label = "availability-" + hashlib.sha256(
                    f"{flow.agency_id}:{flow.flow_id}:{flow.version}".encode()
                ).hexdigest()[:12]
                negative_cache = (
                    self.raw_dir
                    / self.config.provider_id
                    / f"{label}.not-advertised"
                )
                negative_hash = hashlib.sha256(
                    f"{resource}:HTTP404".encode()
                ).hexdigest()
                if (
                    negative_cache.exists()
                    and time.time() - negative_cache.stat().st_mtime
                    <= self.resume_max_age_seconds
                ):
                    hashes[label] = negative_hash
                    continue
                try:
                    path, digest = await self._download(
                        client,
                        label,
                        resource,
                        {"mode": "exact", "references": "none"},
                    )
                except SdmxCatalogHarvestError as error:
                    if (
                        self.config.allow_unadvertised_availability
                        and "(HTTP 404)" in str(error)
                    ):
                        negative_cache.parent.mkdir(parents=True, exist_ok=True)
                        negative_cache.write_text(
                            f"{resource}\nHTTP 404\n", encoding="utf-8"
                        )
                        hashes[label] = negative_hash
                        continue
                    raise
                negative_cache.unlink(missing_ok=True)
                parsed, total = parse_sdmx_constraints(
                    path,
                    by_pair=by_pair,
                    expected_flow=key,
                )
                raw_constraint_total += total
                hashes[label] = digest
                if key not in parsed:
                    raise SdmxCatalogHarvestError(
                        f"{self.config.provider_name} {flow.flow_id} returned no availability."
                    )
                constraints[key] = parsed[key]
                if index + 1 < len(missing):
                    await asyncio.sleep(self.config.availability_request_interval_seconds)

        unresolved = set(flows) - set(constraints)
        if unresolved and not self.config.allow_unadvertised_availability:
            sample = sorted(f"{key[0]}:{key[1]}" for key in unresolved)[:8]
            raise SdmxCatalogHarvestError(
                f"{self.config.provider_name} has dataflows without availability metadata: "
                + ", ".join(sample)
            )
        return constraints, raw_constraint_total, hashes, unresolved

    async def _download(
        self,
        client: httpx.AsyncClient,
        label: str,
        resource: str,
        params: dict[str, str],
        *,
        absolute_url: str | None = None,
    ) -> tuple[Path, str]:
        directory = self.raw_dir / self.config.provider_id
        directory.mkdir(parents=True, exist_ok=True)
        request_url = absolute_url or f"{self.config.base_url}/{resource}"
        request_descriptor = f"{request_url}?{urlencode(sorted(params.items()))}"
        request_key = hashlib.sha256(request_descriptor.encode()).hexdigest()[:12]
        cache_label = f"{label}-{request_key}"
        now = time.time()
        for candidate in sorted(
            directory.glob(f"{cache_label}-*.xml"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if now - candidate.stat().st_mtime > self.resume_max_age_seconds:
                continue
            cached_hash = _file_sha256(candidate)
            if candidate.stem.rsplit("-", 1)[-1] == cached_hash[:12]:
                _validate_xml(candidate)
                return candidate, cached_hash

        temporary = directory / f".{cache_label}-{uuid4().hex}.partial"
        try:
            for attempt in range(3):
                try:
                    async with client.stream(
                        "GET",
                        request_url,
                        params=params,
                        headers={
                            "Accept": self.xml_accept,
                            "Accept-Encoding": "identity",
                        },
                        follow_redirects=False,
                        timeout=httpx.Timeout(connect=15, read=300, write=15, pool=15),
                    ) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(float(attempt + 1))
                            continue
                        if response.status_code != 200:
                            raise SdmxCatalogHarvestError(
                                f"{self.config.provider_name} {label} failed "
                                f"(HTTP {response.status_code})."
                            )
                        media = response.headers.get("content-type", "").casefold()
                        if "xml" not in media:
                            raise SdmxCatalogHarvestError(
                                f"{self.config.provider_name} returned non-XML {label}."
                            )
                        response_hash = hashlib.sha256()
                        size = 0
                        with temporary.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self.config.max_bytes:
                                    raise SdmxCatalogHarvestError(
                                        f"{self.config.provider_name} {label} exceeds the "
                                        "configured catalog limit."
                                    )
                                response_hash.update(chunk)
                                output.write(chunk)
                        raw_hash = response_hash.hexdigest()
                        target = directory / f"{cache_label}-{raw_hash[:12]}.xml"
                        temporary.replace(target)
                        _validate_xml(target)
                        return target, raw_hash
                except httpx.TransportError as error:
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise SdmxCatalogHarvestError(
                        f"{self.config.provider_name} {label} connection failed."
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)
        raise SdmxCatalogHarvestError(f"{self.config.provider_name} {label} failed.")


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _best_text(element: ET.Element, local_name: str) -> str | None:
    candidates = [
        item
        for item in element
        if _local(item) == local_name and item.text and item.text.strip()
    ]
    english = next(
        (
            item
            for item in candidates
            if item.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        ),
        None,
    )
    selected = english or (candidates[0] if candidates else None)
    return " ".join(selected.text.split()) if selected is not None and selected.text else None


def _maintainable_key(element: ET.Element) -> tuple[str, str, str]:
    agency = str(element.attrib.get("agencyID") or "").strip()
    item_id = str(element.attrib.get("id") or "").strip()
    version = str(element.attrib.get("version") or "").strip()
    if not agency or not item_id or not version:
        raise SdmxCatalogHarvestError(
            f"SDMX {_local(element)} is missing agency, ID or version."
        )
    return agency, item_id, version


def _structure_ref(element: ET.Element) -> tuple[str, str, str] | None:
    for item in element.iter():
        if _local(item) == "Ref" and item.attrib.get("class") == "DataStructure":
            agency = str(item.attrib.get("agencyID") or "").strip()
            item_id = str(item.attrib.get("id") or "").strip()
            version = str(item.attrib.get("version") or "").strip()
            if agency and item_id and version:
                return agency, item_id, version
    return None


def _iter_elements(path: Path, local_name: str) -> Iterator[ET.Element]:
    active_depth = 0
    for event, element in ET.iterparse(path, events=("start", "end")):
        name = _local(element)
        if event == "start" and name == local_name:
            active_depth += 1
        elif event == "end" and name == local_name:
            yield element
            active_depth -= 1
            if active_depth == 0:
                element.clear()
        elif event == "end" and active_depth == 0:
            element.clear()


def parse_sdmx_dataflows(path: Path) -> dict[tuple[str, str, str], SdmxFlow]:
    flows: dict[tuple[str, str, str], SdmxFlow] = {}
    for element in _iter_elements(path, "Dataflow"):
        if not element.attrib.get("id"):
            continue
        key = _maintainable_key(element)
        reference = _structure_ref(element)
        title = _best_text(element, "Name") or key[1]
        flow = SdmxFlow(
            agency_id=key[0],
            flow_id=key[1],
            version=key[2],
            title=title,
            description=_best_text(element, "Description"),
            structure_agency_id=reference[0] if reference else None,
            structure_id=reference[1] if reference else None,
            structure_version=reference[2] if reference else None,
            attributes={
                "is_final": element.attrib.get("isFinal") == "true",
                "is_external_reference": element.attrib.get("isExternalReference") == "true",
                "structure_url": element.attrib.get("structureURL"),
            },
        )
        previous = flows.get(key)
        if previous is None or (
            previous.structure_id is None and flow.structure_id is not None
        ):
            flows[key] = flow
        elif (
            flow.structure_id is not None
            and previous.structure_id is not None
            and (
                flow.structure_agency_id,
                flow.structure_id,
                flow.structure_version,
            )
            != (
                previous.structure_agency_id,
                previous.structure_id,
                previous.structure_version,
            )
        ):
            raise SdmxCatalogHarvestError(f"Conflicting SDMX dataflow {key}.")
    if not flows:
        raise SdmxCatalogHarvestError("SDMX response contained no dataflows.")
    return flows


def parse_sdmx_concepts(path: Path) -> dict[tuple[str, str, str, str], str]:
    concepts: dict[tuple[str, str, str, str], str] = {}
    for scheme in _iter_elements(path, "ConceptScheme"):
        agency, scheme_id, version = _maintainable_key(scheme)
        for item in scheme:
            if _local(item) != "Concept":
                continue
            concept_id = str(item.attrib.get("id") or "").strip()
            if concept_id:
                concepts[(agency, scheme_id, version, concept_id)] = (
                    _best_text(item, "Name") or concept_id
                )
    return concepts


def parse_sdmx_structures(
    path: Path,
    concepts: dict[tuple[str, str, str, str], str],
) -> dict[tuple[str | None, str | None, str | None], list[SourceDimension]]:
    structures: dict[
        tuple[str | None, str | None, str | None], list[SourceDimension]
    ] = {}
    component_names: dict[str, ComponentKind] = {
        "Dimension": "dimension",
        "TimeDimension": "time",
        "MeasureDimension": "measure",
        "Attribute": "attribute",
        "PrimaryMeasure": "measure",
    }
    for structure in _iter_elements(path, "DataStructure"):
        if not structure.attrib.get("id"):
            continue
        key = _maintainable_key(structure)
        dimensions: list[SourceDimension] = []
        seen: set[str] = set()
        component_lists = [
            item
            for item in structure.iter()
            if _local(item) in {"DimensionList", "AttributeList", "MeasureList"}
        ]
        for component in (
            item for component_list in component_lists for item in component_list
        ):
            name = _local(component)
            if name not in component_names:
                continue
            component_id = str(component.attrib.get("id") or "").strip()
            if not component_id:
                raise SdmxCatalogHarvestError(f"SDMX structure {key} has an unnamed component.")
            if component_id in seen:
                continue
            seen.add(component_id)
            concept_ref = next(
                (
                    item
                    for item in component.iter()
                    if _local(item) == "Ref" and item.attrib.get("class") == "Concept"
                ),
                None,
            )
            label = component_id
            if concept_ref is not None:
                concept_key = (
                    str(concept_ref.attrib.get("agencyID") or ""),
                    str(concept_ref.attrib.get("maintainableParentID") or ""),
                    str(concept_ref.attrib.get("maintainableParentVersion") or ""),
                    str(concept_ref.attrib.get("id") or ""),
                )
                label = concepts.get(concept_key, component_id)
            codelist_ref = next(
                (
                    item
                    for item in component.iter()
                    if _local(item) == "Ref" and item.attrib.get("class") == "Codelist"
                ),
                None,
            )
            codelist = (
                (
                    str(codelist_ref.attrib.get("agencyID") or "").strip(),
                    str(codelist_ref.attrib.get("id") or "").strip(),
                    str(codelist_ref.attrib.get("version") or "").strip(),
                )
                if codelist_ref is not None
                else (None, None, None)
            )
            position_value = component.attrib.get("position")
            try:
                position = int(position_value) if position_value else None
            except ValueError as error:
                raise SdmxCatalogHarvestError(
                    f"SDMX structure {key} has an invalid component position."
                ) from error
            kind = component_names[name]
            dimensions.append(
                SourceDimension(
                    dimension_id=component_id,
                    label=label,
                    role=_dimension_role(component_id, label, kind),
                    component_kind=kind,
                    key_position=position,
                    codelist_agency_id=codelist[0],
                    codelist_id=codelist[1],
                    codelist_version=codelist[2],
                )
            )
        positioned = [
            item.key_position for item in dimensions if item.key_position is not None
        ]
        if positioned and 0 not in positioned:
            dimensions = [
                item.model_copy(
                    update={
                        "key_position": item.key_position - 1
                        if item.key_position is not None
                        else None
                    }
                )
                for item in dimensions
            ]
        previous = structures.get(key)
        if previous is not None and previous != dimensions:
            raise SdmxCatalogHarvestError(f"Conflicting SDMX data structure {key}.")
        structures[key] = dimensions
    if not structures:
        raise SdmxCatalogHarvestError("SDMX response contained no data structures.")
    return structures


def _dimension_role(
    component_id: str, label: str, component_kind: ComponentKind
) -> DimensionRole:
    term = re.sub(r"[^a-z0-9]+", " ", f"{component_id} {label}".casefold())
    if component_kind == "time" or re.search(r"\b(time period|time|year|date)\b", term):
        return "time"
    if re.search(r"\b(freq|frequency|periodicity)\b", term):
        return "frequency"
    if re.search(r"\b(ref area|country|economy|geography|geo area|territory)\b", term):
        return "geography"
    if re.search(r"\b(series|indicator)\b", term):
        return "indicator"
    if re.search(r"\b(unit)\b", term):
        return "unit"
    if component_kind == "measure" or re.search(r"\b(measure|obs value)\b", term):
        return "measure"
    if re.search(r"\b(status|nature|confidentiality)\b", term):
        return "status"
    return "classification"


def scan_sdmx_codelists(path: Path) -> tuple[set[tuple[str, str, str]], int, int]:
    keys: set[tuple[str, str, str]] = set()
    raw_total = 0
    code_total = 0
    for codelist in _iter_elements(path, "Codelist"):
        raw_total += 1
        key = _maintainable_key(codelist)
        keys.add(key)
        code_total += sum(_local(item) == "Code" for item in codelist)
    return keys, raw_total, code_total


def iter_sdmx_codelists(path: Path) -> Iterator[SourceCodelist]:
    seen: dict[tuple[str, str, str], str] = {}
    for element in _iter_elements(path, "Codelist"):
        agency, codelist_id, version = _maintainable_key(element)
        values = []
        for item in element:
            if _local(item) != "Code":
                continue
            code = str(item.attrib.get("id") or "").strip()
            if not code:
                raise SdmxCatalogHarvestError(
                    f"SDMX codelist {codelist_id} contains an unnamed code."
                )
            parents = [
                str(ref.attrib.get("id") or "").strip()
                for parent in item
                if _local(parent) == "Parent"
                for ref in parent.iter()
                if _local(ref) == "Ref" and ref.attrib.get("id")
            ]
            values.append(
                SourceDimensionValue(
                    code=code,
                    label=_best_text(item, "Name") or code,
                    description=_best_text(item, "Description"),
                    is_aggregate=_aggregate_flag(item),
                    parent_codes=list(dict.fromkeys(parents)),
                )
            )
        codelist = SourceCodelist(
            agency_id=agency,
            codelist_id=codelist_id,
            version=version,
            label=_best_text(element, "Name") or codelist_id,
            description=_best_text(element, "Description"),
            values=values,
        )
        digest = hashlib.sha256(codelist.model_dump_json().encode()).hexdigest()
        key = (agency, codelist_id, version)
        previous = seen.get(key)
        if previous is not None:
            if previous != digest:
                raise SdmxCatalogHarvestError(f"Conflicting SDMX codelist {key}.")
            continue
        seen[key] = digest
        yield codelist


def parse_sdmx_constraints(
    path: Path,
    *,
    by_pair: dict[tuple[str, str], tuple[str, str, str]],
    expected_flow: tuple[str, str, str] | None = None,
) -> tuple[dict[tuple[str, str, str], SdmxFlowConstraint], int]:
    """Stream availability constraints and retain the most specific type per flow."""

    selected: dict[tuple[str, str, str], tuple[int, SdmxFlowConstraint]] = {}
    current_id: str | None = None
    current_type = "unspecified"
    current_flow: tuple[str, str] | None = None
    current_values: dict[str, dict[str, None]] = {}
    cube_included = False
    constraint_total = 0
    for event, element in ET.iterparse(path, events=("start", "end")):
        name = _local(element)
        if event == "start" and name == "ContentConstraint":
            current_id = str(element.attrib.get("id") or "").strip()
            current_type = str(element.attrib.get("type") or "unspecified").strip()
            current_flow = None
            current_values = {}
            constraint_total += 1
        elif event == "start" and name == "CubeRegion" and current_id is not None:
            cube_included = str(element.attrib.get("include") or "true").casefold() != "false"
        elif event == "end" and name == "Ref" and current_id is not None:
            if element.attrib.get("class") == "Dataflow":
                agency = str(element.attrib.get("agencyID") or "").strip()
                flow_id = str(element.attrib.get("id") or "").strip()
                if agency and flow_id:
                    current_flow = (agency, flow_id)
        elif (
            event == "end"
            and name == "KeyValue"
            and current_id is not None
            and cube_included
        ):
            dimension_id = str(element.attrib.get("id") or "").strip()
            codes = [
                str(child.text or "").strip()
                for child in element
                if _local(child) == "Value" and str(child.text or "").strip()
            ]
            if not dimension_id:
                raise SdmxCatalogHarvestError(
                    f"SDMX constraint {current_id} contains an invalid key value."
                )
            if not codes:
                # An empty KeyValue is a provider-published wildcard (commonly
                # TIME_PERIOD), not an empty set of available observations.
                element.clear()
                continue
            target = current_values.setdefault(dimension_id, {})
            target.update(dict.fromkeys(codes))
            element.clear()
        elif event == "end" and name == "CubeRegion":
            cube_included = False
        elif event == "end" and name == "ContentConstraint":
            if current_id is None:
                raise SdmxCatalogHarvestError("SDMX constraint parser lost its context.")
            key = by_pair.get(current_flow) if current_flow else expected_flow
            if key is not None:
                priority = 2 if current_type.casefold() == "actual" else 1
                candidate = SdmxFlowConstraint(
                    constraint_type=current_type,
                    constraint_ids=(current_id,),
                    values={
                        dimension_id: tuple(values)
                        for dimension_id, values in current_values.items()
                    },
                )
                previous = selected.get(key)
                if previous is None or priority > previous[0]:
                    selected[key] = (priority, candidate)
                elif priority == previous[0]:
                    merged = {
                        dimension_id: dict.fromkeys(values)
                        for dimension_id, values in previous[1].values.items()
                    }
                    for dimension_id, values in candidate.values.items():
                        merged.setdefault(dimension_id, {}).update(dict.fromkeys(values))
                    selected[key] = (
                        priority,
                        SdmxFlowConstraint(
                            constraint_type=current_type,
                            constraint_ids=tuple(
                                dict.fromkeys(
                                    [*previous[1].constraint_ids, *candidate.constraint_ids]
                                )
                            ),
                            values={
                                dimension_id: tuple(values)
                                for dimension_id, values in merged.items()
                            },
                        ),
                    )
            current_id = None
            current_flow = None
            current_values = {}
            element.clear()
    if constraint_total == 0:
        raise SdmxCatalogHarvestError("SDMX availability response contains no constraints.")
    return {key: value for key, (_, value) in selected.items()}, constraint_total


def _classify_sdmx_geography(value: SourceDimensionValue) -> SourceDimensionValue:
    if value.is_aggregate is not None:
        return value
    label = " ".join(value.label.casefold().split())
    exact_aggregates = {
        "world",
        "global",
        "africa",
        "asia",
        "oceania",
        "europe",
        "latin america",
        "euro area",
        "european union",
        "oecd",
        "g20",
        "g7",
        "sub-saharan africa",
    }
    aggregate = label in exact_aggregates or bool(
        re.search(
            r"\b(countries|economies|regions|income group|lending group|aggregate)\b",
            label,
        )
    )
    return value.model_copy(update={"is_aggregate": True}) if aggregate else value


def _infer_codelist_reference(
    flow: SdmxFlow,
    dimension_id: str,
    codelist_keys: set[tuple[str, str, str]],
) -> tuple[str, str, str] | None:
    """Resolve IMF-style convention-based references omitted from generated DSDs."""

    flow_id = re.sub(r"[^A-Z0-9]+", "_", flow.flow_id.upper()).strip("_")
    dimension = re.sub(r"[^A-Z0-9]+", "_", dimension_id.upper()).strip("_")
    shared_dimension = {"FREQUENCY": "FREQ"}.get(dimension, dimension)
    exact_ids = (
        f"CL_{flow_id}_{dimension}",
        f"CL_{flow_id.removeprefix('DF_')}_{dimension}",
        f"CL_{dimension}",
        f"CL_{shared_dimension}",
    )
    for candidate_id in exact_ids:
        matches = [
            key
            for key in codelist_keys
            if key[1].upper() == candidate_id
            and key[0] in {flow.agency_id, flow.agency_id.split(".", 1)[0], "IMF"}
        ]
        if matches:
            return max(matches, key=lambda item: _version_key(item[2]))
    contains = [
        key
        for key in codelist_keys
        if key[0] == flow.agency_id
        and flow_id in key[1].upper()
        and key[1].upper().endswith(f"_{dimension}")
    ]
    if contains:
        return max(contains, key=lambda item: _version_key(item[2]))
    return None


def _match_codelist_by_available_codes(
    item: SdmxAvailability,
    codelists: dict[tuple[str, str, str], SourceCodelist],
    value_codes: dict[tuple[str, str, str], frozenset[str]],
    flow_label: str,
) -> tuple[str, str, str] | None:
    """Resolve an omitted reference without silently accepting an ambiguous match."""

    required = set(item.codes)
    candidates = [
        key for key, codes in value_codes.items() if required and required <= codes
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    flow_id = re.sub(r"_20\d{2}_[A-Z]+_VINTAGE$", "", item.flow_id.upper())
    flow_aliases = {flow_id, flow_id.removeprefix("DF_")}
    if flow_id.startswith("A") and len(flow_id) > 3:
        flow_aliases.add(flow_id[1:])
    dimension = re.sub(r"[^A-Z0-9]+", "_", item.dimension_id.upper()).strip("_")
    dimension_aliases = {
        dimension,
        {
            "COUNTERPART_COUNTRY": "COUNTRY",
            "COUNTERPART_SECTOR": "SECTOR",
            "FFS": "FOSSIL_FUEL_SUBSIDY",
            "GS_MS": "MS",
            "NSDP_CAT": "NSDP_CATEGORY",
            "PRODUCTION_INDEX": "PRODUCTION_INDEX",
            "SUB_TYPE": "SUBSIDIES_TYPE",
            "WGT_TYPE": "WEIGHT_TYPE",
        }.get(dimension, dimension),
    }
    label_tokens = set(re.findall(r"[a-z0-9]+", flow_label.casefold()))

    def score(key: tuple[str, str, str]) -> tuple[int, int]:
        codelist = codelists[key]
        codelist_id = re.sub(r"[^A-Z0-9]+", "_", key[1].upper()).strip("_")
        codelist_tokens = set(
            re.findall(r"[a-z0-9]+", f"{codelist.label} {codelist.description or ''}".casefold())
        )
        points = 0
        if key[0] == item.agency_id:
            points += 20
        if any(
            re.search(rf"(?:^|_){re.escape(alias)}(?:_|$)", codelist_id)
            for alias in flow_aliases
        ):
            points += 100
        if any(
            re.search(rf"(?:^|_){re.escape(alias)}(?:_|$)", codelist_id)
            for alias in dimension_aliases
        ):
            points += 35
        points += min(30, 3 * len(label_tokens & codelist_tokens))
        if len(value_codes[key]) == len(required):
            points += 15
        if item.role == "geography" and {
            "country",
            "economy",
            "geography",
        } & codelist_tokens:
            points += 10
        return points, -len(value_codes[key])

    ranked = sorted(candidates, key=lambda key: (score(key), key), reverse=True)
    best = ranked[0]
    if score(best) <= score(ranked[1]):
        return None
    return best


def _availability_only_value(code: str) -> SourceDimensionValue:
    return SourceDimensionValue(
        code=code,
        label=code,
        attributes={"catalog_status": "availability_only"},
    )


def _version_key(version: str) -> tuple[tuple[int, str], ...]:
    return tuple(
        (0, f"{int(item):012d}") if item.isdigit() else (1, item.casefold())
        for item in re.split(r"[._-]", version)
    )


def _aggregate_flag(element: ET.Element) -> bool | None:
    for annotation in element.iter():
        if _local(annotation) != "Annotation":
            continue
        annotation_type = next(
            (
                item.text.strip().casefold()
                for item in annotation
                if _local(item) == "AnnotationType" and item.text
            ),
            "",
        )
        if annotation_type not in {"isaggregate", "is_aggregate", "aggregate"}:
            continue
        value = next(
            (
                item.text.strip().casefold()
                for item in annotation.iter()
                if _local(item) in {"AnnotationTitle", "AnnotationText"} and item.text
            ),
            "",
        )
        if value in {"true", "1", "yes"}:
            return True
        if value in {"false", "0", "no"}:
            return False
    return None


def read_sdmx_prepared(path: Path) -> str | None:
    for _, element in ET.iterparse(path, events=("end",)):
        if _local(element) == "Prepared":
            return element.text.strip() if element.text else None
        element.clear()
    return None


def _validate_xml(path: Path) -> None:
    try:
        event, root = next(iter(ET.iterparse(path, events=("start",))))
    except (ET.ParseError, StopIteration) as error:
        raise SdmxCatalogHarvestError("SDMX catalog is empty or malformed XML.") from error
    if event != "start" or _local(root) not in {"Structure", "Error"}:
        raise SdmxCatalogHarvestError("SDMX catalog has an unexpected root element.")
    if _local(root) == "Error":
        raise SdmxCatalogHarvestError("SDMX provider returned an error message.")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
