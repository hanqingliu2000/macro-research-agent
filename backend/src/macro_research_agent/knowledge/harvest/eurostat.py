"""Eurostat main, Comext and Prodcom catalog harvesting for Source Index v2."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import re
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4
from xml.etree import ElementTree as ET

import httpx

from macro_research_agent.knowledge.harvest.sdmx import (
    SdmxCatalogHarvestError,
    SdmxFlow,
    iter_sdmx_codelists,
    parse_sdmx_dataflows,
    parse_sdmx_structures,
    read_sdmx_prepared,
    scan_sdmx_codelists,
)
from macro_research_agent.knowledge.source_index import (
    DimensionRole,
    ProviderSourceSnapshot,
    SourceCodelist,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
)


class EurostatCatalogHarvestError(ValueError):
    pass


@dataclass(frozen=True)
class EurostatTocEntry:
    code: str
    title: str
    description: str | None
    product_type: str
    updated_at: datetime | None
    attributes: dict[str, str | int | float | bool | None]
    documentation_urls: tuple[str, ...]


@dataclass(frozen=True)
class EurostatCatalogResult:
    snapshot: ProviderSourceSnapshot
    metabase_path: Path
    main_codelist_path: Path
    comext_codelist_path: Path
    comext_constraint_paths: tuple[tuple[str, Path], ...]
    comext_dimension_codelists: tuple[tuple[str, str, str | None], ...]

    def codelists(self) -> Iterator[SourceCodelist]:
        codebooks = _codebooks((self.main_codelist_path, self.comext_codelist_path))
        version = self.snapshot.snapshot_version
        for dataset_id, dimension_id, codes in _iter_metabase_groups(self.metabase_path):
            yield _availability_codelist(
                "ESTAT.AVAILABILITY",
                dataset_id,
                dimension_id,
                version,
                codes,
                codebooks,
            )
        for flow_id, path in self.comext_constraint_paths:
            references = {
                dimension_id: codelist_id
                for candidate_flow, dimension_id, codelist_id in self.comext_dimension_codelists
                if candidate_flow == flow_id
            }
            for dimension_id, codes in _parse_constraint(path, flow_id).items():
                yield _availability_codelist(
                    "ESTAT.COMEXT.AVAILABILITY",
                    flow_id,
                    dimension_id,
                    version,
                    codes,
                    codebooks,
                    source_codelist_id=references.get(dimension_id),
                )


class EurostatCatalogHarvester:
    main_base_url = "https://ec.europa.eu/eurostat/api/dissemination"
    comext_base_url = "https://ec.europa.eu/eurostat/api/comext/dissemination"
    catalog_url = (
        "https://ec.europa.eu/eurostat/web/user-guides/data-browser/"
        "api-data-access/api-getting-started/catalogue-api"
    )
    max_download_bytes = 512 * 1024 * 1024
    max_inflated_bytes = 768 * 1024 * 1024

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        resume_max_age_seconds: int = 12 * 60 * 60,
        request_interval_seconds: float = 0.1,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client
        self.resume_max_age_seconds = resume_max_age_seconds
        self.request_interval_seconds = request_interval_seconds

    async def harvest(self) -> EurostatCatalogResult:
        if self.client is not None:
            return await self._harvest(self.client)
        async with httpx.AsyncClient() as client:
            return await self._harvest(client)

    async def _harvest(self, client: httpx.AsyncClient) -> EurostatCatalogResult:
        requests: tuple[tuple[str, str, dict[str, str], str, bool], ...] = (
            (
                "main-toc",
                f"{self.main_base_url}/catalogue/toc/xml",
                {},
                ".xml",
                False,
            ),
            (
                "main-metabase",
                f"{self.main_base_url}/catalogue/metabase.txt.gz",
                {},
                ".txt.gz",
                True,
            ),
            (
                "main-codelists",
                f"{self.main_base_url}/sdmx/3.0/structure/codelist/ESTAT/*",
                {"compress": "true"},
                ".xml.gz",
                True,
            ),
            (
                "comext-dataflows",
                f"{self.comext_base_url}/sdmx/2.1/dataflow/ESTAT/all",
                {},
                ".xml",
                False,
            ),
            (
                "comext-structures",
                f"{self.comext_base_url}/sdmx/2.1/datastructure/all/all/latest",
                {},
                ".xml",
                False,
            ),
            (
                "comext-codelists",
                f"{self.comext_base_url}/sdmx/2.1/codelist/all/all/latest",
                {},
                ".xml",
                False,
            ),
        )
        paths: dict[str, Path] = {}
        hashes: dict[str, str] = {}
        for index, (label, url, parameters, suffix, compressed) in enumerate(requests):
            path, digest, reused = await self._download(
                client, label, url, parameters, suffix, compressed=compressed
            )
            paths[label] = path
            hashes[label] = digest
            if not reused and index + 1 < len(requests):
                await asyncio.sleep(self.request_interval_seconds)

        main_codelists = self._inflate_xml(paths["main-codelists"])
        toc = _parse_toc(paths["main-toc"])
        main_dimensions, main_rows, frequency_by_dataset = _scan_metabase(
            paths["main-metabase"]
        )
        main_keys, main_codelist_total, main_code_total = scan_sdmx_codelists(
            main_codelists
        )
        available_ids = {item[1].casefold() for item in main_keys}
        missing_dimensions = {
            dimension.casefold()
            for dimensions in main_dimensions.values()
            for dimension in dimensions
            if dimension.casefold() not in available_ids
        }
        if missing_dimensions:
            raise EurostatCatalogHarvestError(
                "Eurostat Metabase references missing codelists: "
                + ", ".join(sorted(missing_dimensions)[:8])
            )

        flows = parse_sdmx_dataflows(paths["comext-dataflows"])
        structures = parse_sdmx_structures(paths["comext-structures"], {})
        comext_keys, comext_codelist_total, comext_code_total = scan_sdmx_codelists(
            paths["comext-codelists"]
        )
        comext_ids = {item[1] for item in comext_keys}
        constraint_paths: list[tuple[str, Path]] = []
        constraint_rows = 0
        for index, flow in enumerate(sorted(flows.values(), key=lambda item: item.flow_id)):
            url = (
                f"{self.comext_base_url}/sdmx/2.1/contentconstraint/"
                f"{flow.agency_id}/{flow.flow_id}/latest"
            )
            path, digest, reused = await self._download(
                client,
                f"comext-constraint-{flow.flow_id}",
                url,
                {},
                ".xml",
                compressed=False,
            )
            hashes[f"comext-constraint-{flow.flow_id}"] = digest
            constraint_paths.append((flow.flow_id, path))
            parsed = _parse_constraint(path, flow.flow_id)
            constraint_rows += sum(len(values) for values in parsed.values())
            if not reused and index + 1 < len(flows):
                await asyncio.sleep(self.request_interval_seconds)

        combined_hash = hashlib.sha256(
            "".join(f"{key}:{value}\n" for key, value in sorted(hashes.items())).encode()
        ).hexdigest()
        prepared = read_sdmx_prepared(paths["comext-dataflows"])
        toc_creation = _toc_creation(paths["main-toc"])
        snapshot_version = f"eurostat:{toc_creation}:{prepared or combined_hash[:12]}"
        datasets = self._main_datasets(
            main_dimensions, frequency_by_dataset, toc, snapshot_version
        )
        datasets.extend(
            self._comext_datasets(
                flows,
                structures,
                dict(constraint_paths),
                comext_ids,
                snapshot_version,
            )
        )
        snapshot = ProviderSourceSnapshot(
            provider_id="eurostat",
            provider_name="Eurostat",
            catalog_url=self.catalog_url,
            snapshot_version=snapshot_version,
            retrieved_at=datetime.now(timezone.utc),
            coverage_status="complete",
            source_sha256=combined_hash,
            attributes={
                "main_dataset_total": len(main_dimensions),
                "main_metabase_relation_total": main_rows,
                "main_toc_product_total": len(toc),
                "main_codelist_total": main_codelist_total,
                "main_codelist_code_total": main_code_total,
                "comext_prodcom_dataset_total": len(flows),
                "comext_datastructure_total": len(structures),
                "comext_codelist_total": comext_codelist_total,
                "comext_codelist_code_total": comext_code_total,
                "comext_constraint_relation_total": constraint_rows,
                "catalog_refresh_schedule": "twice daily at 11:00 and 23:00 Brussels time",
            },
            datasets=datasets,
        )
        return EurostatCatalogResult(
            snapshot=snapshot,
            metabase_path=paths["main-metabase"],
            main_codelist_path=main_codelists,
            comext_codelist_path=paths["comext-codelists"],
            comext_constraint_paths=tuple(constraint_paths),
            comext_dimension_codelists=tuple(
                (
                    flow.flow_id,
                    dimension.dimension_id,
                    dimension.codelist_id,
                )
                for flow in flows.values()
                for dimension in structures[
                    (
                        flow.structure_agency_id,
                        flow.structure_id,
                        flow.structure_version,
                    )
                ]
            ),
        )

    def _main_datasets(
        self,
        dimensions_by_dataset: dict[str, list[str]],
        frequencies: dict[str, list[str]],
        toc: dict[str, EurostatTocEntry],
        snapshot_version: str,
    ) -> list[SourceDataset]:
        result = []
        for dataset_id, dimension_ids in sorted(dimensions_by_dataset.items()):
            entry = toc.get(dataset_id)
            dimensions = [
                SourceDimension(
                    dimension_id=dimension_id,
                    label=dimension_id.replace("_", " ").title(),
                    role=_eurostat_role(dimension_id),
                    component_kind="time"
                    if dimension_id.casefold() in {"time", "time_period"}
                    else "dimension",
                    key_position=index,
                    codelist_agency_id="ESTAT.AVAILABILITY",
                    codelist_id=f"{dataset_id}@{dimension_id}",
                    codelist_version=snapshot_version,
                )
                for index, dimension_id in enumerate(dimension_ids)
            ]
            dimensions.append(
                SourceDimension(
                    dimension_id="FREQ",
                    label="Frequency",
                    role="frequency",
                    values=[
                        SourceDimensionValue(code=code, label=_frequency_label(code))
                        for code in frequencies[dataset_id]
                    ],
                )
            )
            executable = dataset_id == "prc_hicp_minr"
            result.append(
                SourceDataset(
                    dataset_id=f"ESTAT:{dataset_id}",
                    agency_id="ESTAT",
                    version=None,
                    title=entry.title if entry else dataset_id,
                    description=entry.description if entry else None,
                    executable=executable,
                    coverage_status="complete",
                    updated_at=entry.updated_at if entry else None,
                    documentation_urls=list(entry.documentation_urls) if entry else [],
                    attributes={
                        **(entry.attributes if entry else {}),
                        "provider_dataset_id": dataset_id,
                        "catalog_scope": "main",
                        "connector_dataset_id": "HICP" if executable else None,
                        "toc_match": entry is not None,
                    },
                    dimensions=dimensions,
                )
            )
        return result

    def _comext_datasets(
        self,
        flows: dict[tuple[str, str, str], SdmxFlow],
        structures: dict[tuple[str | None, str | None, str | None], list[SourceDimension]],
        constraints: dict[str, Path],
        codelist_ids: set[str],
        snapshot_version: str,
    ) -> list[SourceDataset]:
        datasets = []
        for flow in sorted(flows.values(), key=lambda item: item.flow_id):
            structure_key = (
                flow.structure_agency_id,
                flow.structure_id,
                flow.structure_version,
            )
            if structure_key not in structures:
                raise EurostatCatalogHarvestError(
                    f"Eurostat Comext {flow.flow_id} references a missing structure."
                )
            allowed = _parse_constraint(constraints[flow.flow_id], flow.flow_id)
            dimensions = []
            for dimension in structures[structure_key]:
                codes = allowed.get(dimension.dimension_id)
                if codes is None:
                    if dimension.component_kind in {"measure", "attribute"}:
                        dimensions.append(dimension)
                        continue
                    raise EurostatCatalogHarvestError(
                        f"Eurostat Comext {flow.flow_id}/{dimension.dimension_id} "
                        "is missing an availability constraint."
                    )
                if dimension.codelist_id and dimension.codelist_id not in codelist_ids:
                    raise EurostatCatalogHarvestError(
                        f"Eurostat Comext {flow.flow_id} references a missing codelist."
                    )
                dimensions.append(
                    dimension.model_copy(
                        update={
                            "role": _eurostat_role(dimension.dimension_id),
                            "codelist_agency_id": "ESTAT.COMEXT.AVAILABILITY",
                            "codelist_id": f"{flow.flow_id}@{dimension.dimension_id}",
                            "codelist_version": snapshot_version,
                            "values": [],
                        }
                    )
                )
            datasets.append(
                SourceDataset(
                    dataset_id=f"ESTAT:{flow.flow_id}",
                    agency_id=flow.agency_id,
                    version=flow.version,
                    title=flow.title,
                    description=flow.description,
                    executable=False,
                    coverage_status="complete",
                    documentation_urls=[
                        f"{self.comext_base_url}/sdmx/2.1/dataflow/{flow.agency_id}/{flow.flow_id}"
                    ],
                    attributes={
                        **flow.attributes,
                        "provider_dataset_id": flow.flow_id,
                        "catalog_scope": "comext_prodcom",
                        "structure_id": flow.structure_id,
                        "structure_version": flow.structure_version,
                    },
                    dimensions=dimensions,
                )
            )
        return datasets

    async def _download(
        self,
        client: httpx.AsyncClient,
        label: str,
        url: str,
        parameters: dict[str, str],
        suffix: str,
        *,
        compressed: bool,
    ) -> tuple[Path, str, bool]:
        request_key = hashlib.sha256(
            f"{url}?{urlencode(sorted(parameters.items()))}".encode()
        ).hexdigest()[:12]
        directory = self.raw_dir / "eurostat"
        directory.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for candidate in sorted(
            directory.glob(f"{label}-{request_key}-*{suffix}"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if now - candidate.stat().st_mtime > self.resume_max_age_seconds:
                continue
            digest = _file_sha256(candidate)
            expected = candidate.name.removesuffix(suffix).rsplit("-", 1)[-1]
            if expected == digest[:12]:
                self._validate(candidate, compressed)
                return candidate, digest, True

        temporary = directory / f".{label}-{uuid4().hex}.partial"
        try:
            for attempt in range(3):
                try:
                    async with client.stream(
                        "GET",
                        url,
                        params=parameters,
                        headers={"Accept-Encoding": "identity"},
                        timeout=httpx.Timeout(connect=15, read=600, write=15, pool=15),
                    ) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(float(attempt + 1))
                            continue
                        if response.status_code != 200:
                            raise EurostatCatalogHarvestError(
                                f"Eurostat {label} failed (HTTP {response.status_code})."
                            )
                        digest_builder = hashlib.sha256()
                        size = 0
                        with temporary.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self.max_download_bytes:
                                    raise EurostatCatalogHarvestError(
                                        f"Eurostat {label} exceeds the catalog limit."
                                    )
                                digest_builder.update(chunk)
                                output.write(chunk)
                        digest = digest_builder.hexdigest()
                        target = directory / f"{label}-{request_key}-{digest[:12]}{suffix}"
                        temporary.replace(target)
                        self._validate(target, compressed)
                        return target, digest, False
                except httpx.TransportError as error:
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise EurostatCatalogHarvestError(
                        f"Eurostat {label} connection failed."
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)
        raise EurostatCatalogHarvestError(f"Eurostat {label} failed.")

    def _validate(self, path: Path, compressed: bool) -> None:
        try:
            if compressed:
                with gzip.open(path, "rb") as source:
                    source.read(1)
            elif path.suffix == ".xml":
                next(iter(ET.iterparse(path, events=("start",))))
        except (OSError, ET.ParseError, StopIteration) as error:
            raise EurostatCatalogHarvestError(
                f"Eurostat catalog {path.name} is malformed."
            ) from error

    def _inflate_xml(self, path: Path) -> Path:
        target = path.with_suffix("")
        if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
            try:
                next(iter(ET.iterparse(target, events=("start",))))
                return target
            except (ET.ParseError, StopIteration):
                target.unlink(missing_ok=True)
        temporary = target.with_name(f".{target.name}-{uuid4().hex}.partial")
        size = 0
        try:
            with gzip.open(path, "rb") as source, temporary.open("wb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(chunk)
                    if size > self.max_inflated_bytes:
                        raise EurostatCatalogHarvestError(
                            "Eurostat codelist archive exceeds the inflated catalog limit."
                        )
                    output.write(chunk)
            temporary.replace(target)
            next(iter(ET.iterparse(target, events=("start",))))
            return target
        except (OSError, ET.ParseError, StopIteration) as error:
            raise EurostatCatalogHarvestError(
                "Eurostat codelist archive is malformed."
            ) from error
        finally:
            temporary.unlink(missing_ok=True)


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _english_text(element: ET.Element, name: str) -> str | None:
    candidates = [
        child
        for child in element
        if _local(child) == name and child.text and child.text.strip()
    ]
    english = next(
        (
            child
            for child in candidates
            if child.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        ),
        None,
    )
    selected = english or (candidates[0] if candidates else None)
    return " ".join(selected.text.split()) if selected is not None and selected.text else None


def _parse_toc(path: Path) -> dict[str, EurostatTocEntry]:
    entries: dict[str, EurostatTocEntry] = {}
    for _, element in ET.iterparse(path, events=("end",)):
        if _local(element) != "leaf":
            continue
        code = _english_text(element, "code")
        title = _english_text(element, "title")
        if not code or not title:
            raise EurostatCatalogHarvestError("Eurostat TOC contains an unnamed product.")
        updated_text = _english_text(element, "lastUpdate")
        updated_at = None
        if updated_text:
            try:
                updated_at = datetime.strptime(updated_text, "%d.%m.%Y").replace(
                    tzinfo=timezone.utc
                )
            except ValueError as error:
                raise EurostatCatalogHarvestError(
                    f"Eurostat TOC product {code} has an invalid update date."
                ) from error
        urls = tuple(
            child.text.strip()
            for child in element
            if _local(child) == "metadata" and child.text and child.text.strip()
        )
        values_text = _english_text(element, "values")
        attributes: dict[str, str | int | float | bool | None] = {
            "toc_type": element.attrib.get("type"),
            "data_start": _english_text(element, "dataStart"),
            "data_end": _english_text(element, "dataEnd"),
            "last_modified": _english_text(element, "lastModified"),
            "observation_total": (
                int(values_text) if values_text and values_text.isdigit() else None
            ),
        }
        entry = EurostatTocEntry(
            code=code,
            title=title,
            description=_english_text(element, "shortDescription"),
            product_type=str(element.attrib.get("type") or "unknown"),
            updated_at=updated_at,
            attributes=attributes,
            documentation_urls=urls,
        )
        previous = entries.get(code)
        if previous is not None and previous != entry:
            raise EurostatCatalogHarvestError(f"Eurostat TOC product {code} conflicts.")
        entries[code] = entry
        element.clear()
    if not entries:
        raise EurostatCatalogHarvestError("Eurostat TOC contains no products.")
    return entries


def _toc_creation(path: Path) -> str:
    try:
        _, root = next(iter(ET.iterparse(path, events=("start",))))
    except (ET.ParseError, StopIteration) as error:
        raise EurostatCatalogHarvestError("Eurostat TOC is malformed.") from error
    value = str(root.attrib.get("creationDate") or "").strip()
    if not value:
        raise EurostatCatalogHarvestError("Eurostat TOC is missing its creation date.")
    return value


def _scan_metabase(
    path: Path,
) -> tuple[dict[str, list[str]], int, dict[str, list[str]]]:
    dimensions: dict[str, list[str]] = defaultdict(list)
    frequencies: dict[str, set[str]] = defaultdict(set)
    seen_groups: set[tuple[str, str]] = set()
    previous_group: tuple[str, str] | None = None
    group_codes: set[str] = set()
    row_total = 0
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) != 3 or not all(fields):
                raise EurostatCatalogHarvestError(
                    f"Eurostat Metabase row {line_number} is malformed."
                )
            dataset_id, dimension_id, code = fields
            group = (dataset_id, dimension_id)
            if group != previous_group:
                if group in seen_groups:
                    raise EurostatCatalogHarvestError(
                        f"Eurostat Metabase group {dataset_id}/{dimension_id} is not contiguous."
                    )
                seen_groups.add(group)
                dimensions[dataset_id].append(dimension_id)
                previous_group = group
                group_codes = set()
            if code in group_codes:
                raise EurostatCatalogHarvestError(
                    f"Eurostat Metabase contains duplicate {dataset_id}/{dimension_id}/{code}."
                )
            group_codes.add(code)
            row_total += 1
            if dimension_id.casefold() in {"time", "time_period"}:
                frequencies[dataset_id].add(_frequency(code))
    if not dimensions:
        raise EurostatCatalogHarvestError("Eurostat Metabase contains no datasets.")
    return (
        dict(dimensions),
        row_total,
        {key: sorted(value) for key, value in frequencies.items()},
    )


def _iter_metabase_groups(path: Path) -> Iterator[tuple[str, str, list[str]]]:
    group: tuple[str, str] | None = None
    codes: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            dataset_id, dimension_id, code = line.rstrip("\r\n").split("\t")
            current = (dataset_id, dimension_id)
            if group is not None and current != group:
                yield group[0], group[1], codes
                codes = []
            group = current
            codes.append(code)
    if group is not None:
        yield group[0], group[1], codes


def _parse_constraint(path: Path, expected_flow: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    attached_flow: str | None = None
    for _, element in ET.iterparse(path, events=("end",)):
        name = _local(element)
        if name == "Ref" and element.attrib.get("class") == "Dataflow":
            attached_flow = str(element.attrib.get("id") or "").strip()
        elif name == "KeyValue":
            dimension_id = str(element.attrib.get("id") or "").strip()
            codes = [
                str(child.text or "").strip()
                for child in element
                if _local(child) == "Value" and str(child.text or "").strip()
            ]
            if not dimension_id or not codes:
                raise EurostatCatalogHarvestError(
                    f"Eurostat Comext {expected_flow} has an invalid constraint."
                )
            if dimension_id in values:
                raise EurostatCatalogHarvestError(
                    f"Eurostat Comext {expected_flow}/{dimension_id} is constrained twice."
                )
            if len(codes) != len(set(codes)):
                raise EurostatCatalogHarvestError(
                    f"Eurostat Comext {expected_flow}/{dimension_id} contains duplicate codes."
                )
            values[dimension_id] = codes
            element.clear()
    if attached_flow != expected_flow or not values:
        raise EurostatCatalogHarvestError(
            f"Eurostat Comext constraint does not match {expected_flow}."
        )
    return values


def _codebooks(paths: tuple[Path, ...]) -> dict[str, SourceCodelist]:
    result: dict[str, SourceCodelist] = {}
    for path in paths:
        try:
            codelists = iter_sdmx_codelists(path)
            for codelist in codelists:
                key = codelist.codelist_id.casefold()
                previous = result.get(key)
                if previous is not None and previous != codelist:
                    raise EurostatCatalogHarvestError(
                        f"Eurostat codelist ID {codelist.codelist_id} is ambiguous."
                    )
                result[key] = codelist
        except SdmxCatalogHarvestError as error:
            raise EurostatCatalogHarvestError("Eurostat codelist parsing failed.") from error
    return result


def _availability_codelist(
    agency_id: str,
    dataset_id: str,
    dimension_id: str,
    version: str,
    codes: list[str],
    codebooks: dict[str, SourceCodelist],
    *,
    source_codelist_id: str | None = None,
) -> SourceCodelist:
    role = _eurostat_role(dimension_id)
    source = codebooks.get((source_codelist_id or dimension_id).casefold())
    if role == "time":
        label = "Time period"
        values = [SourceDimensionValue(code=code, label=code) for code in codes]
    elif source is None:
        raise EurostatCatalogHarvestError(
            f"Eurostat {dataset_id}/{dimension_id} has no source codelist."
        )
    else:
        label = source.label
        lookup = {item.code: item for item in source.values}
        missing = set(codes) - set(lookup)
        if missing:
            raise EurostatCatalogHarvestError(
                f"Eurostat {dataset_id}/{dimension_id} contains unknown codes: "
                + ", ".join(sorted(missing)[:8])
            )
        values = [
            _classify_geography(lookup[code])
            if role == "geography"
            else lookup[code]
            for code in codes
        ]
    return SourceCodelist(
        agency_id=agency_id,
        codelist_id=f"{dataset_id}@{dimension_id}",
        version=version,
        label=f"{dataset_id} available {label}",
        description=(
            "Provider-published available positions from the Eurostat Metabase or "
            "Comext/Prodcom content constraint."
        ),
        values=values,
    )


def _eurostat_role(dimension_id: str) -> DimensionRole:
    value = dimension_id.casefold()
    if value in {"time", "time_period"}:
        return "time"
    if value in {"freq", "frequency"}:
        return "frequency"
    if value in {"geo", "reporter", "partner", "declarant", "decl"}:
        return "geography"
    if value in {"unit", "currency"}:
        return "unit"
    if "indic" in value:
        return "indicator"
    if value in {"obs_value", "value"}:
        return "measure"
    if "status" in value or "flag" in value:
        return "status"
    return "classification"


def _frequency(code: str) -> str:
    if re.fullmatch(r"\d{4}", code) or code == "LTAA":
        return "A"
    if re.fullmatch(r"\d{4}-?Q[1-4]", code):
        return "Q"
    if re.fullmatch(r"\d{4}-?S[12]", code):
        return "S"
    if re.fullmatch(r"\d{4}-?M(?:0[1-9]|1[0-2])", code):
        return "M"
    if re.fullmatch(r"\d{4}-?W\d{2}", code):
        return "W"
    if re.fullmatch(r"\d{4}(?:-\d{2}-\d{2}|M\d{2}D\d{2})", code):
        return "D"
    raise EurostatCatalogHarvestError(f"Eurostat time code {code} has an unknown frequency.")


def _frequency_label(code: str) -> str:
    return {
        "A": "Annual",
        "Q": "Quarterly",
        "S": "Semiannual",
        "M": "Monthly",
        "W": "Weekly",
        "D": "Daily",
    }[code]


def _classify_geography(value: SourceDimensionValue) -> SourceDimensionValue:
    label = " ".join(value.label.casefold().split())
    exact_aggregates = {
        "world",
        "africa",
        "asia",
        "oceania",
        "europe",
        "latin america",
        "european union",
        "euro area",
    }
    aggregate = bool(
        label in exact_aggregates
        or
        re.search(
            r"\b(countries|economic area|free trade association|candidate countries|"
            r"member states|global|aggregate|extra-eu|intra-eu)\b",
            label,
        )
        or re.match(r"^(eu|ea|efta|eea|nms)\d*(?:_|$)", value.code.casefold())
    )
    return value.model_copy(update={"is_aggregate": aggregate})


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
