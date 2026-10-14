"""Complete UN Global SDG Database catalog harvesting for Source Index v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from macro_research_agent.knowledge.source_index import (
    DimensionRole,
    ProviderSourceSnapshot,
    SourceCodelist,
    SourceDataset,
    SourceDimension,
    SourceDimensionValue,
)


class UnSdgCatalogHarvestError(ValueError):
    pass


@dataclass(frozen=True)
class UnSdgCatalogResult:
    snapshot: ProviderSourceSnapshot
    codelists: tuple[SourceCodelist, ...]


class UnSdgCatalogHarvester:
    """Harvest current SDG hierarchy plus release and disaggregation history."""

    base_url = "https://unstats.un.org/SDGAPI/v1/sdg"
    catalog_url = "https://unstats.un.org/SDGAPI/swagger/index.html"
    max_bytes = 64 * 1024 * 1024

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        resume_max_age_seconds: int = 24 * 60 * 60,
        request_interval_seconds: float = 0.05,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client
        self.resume_max_age_seconds = resume_max_age_seconds
        self.request_interval_seconds = request_interval_seconds

    async def harvest(self) -> UnSdgCatalogResult:
        if self.client is not None:
            return await self._harvest(self.client)
        async with httpx.AsyncClient() as client:
            return await self._harvest(client)

    async def _harvest(self, client: httpx.AsyncClient) -> UnSdgCatalogResult:
        resources = {
            "goals": ("GET", "Goal/List", {"includechildren": "true"}),
            "series-current": ("GET", "Series/List", {"allreleases": "false"}),
            "series-history": ("GET", "Series/List", {"allreleases": "true"}),
            "geographies": ("GET", "GeoArea/List", {}),
            "geography-tree": ("GET", "GeoArea/Tree", {}),
            "last-updated": ("GET", "Series/LastUpdated", {}),
            "disaggregations": (
                "POST",
                "CompareTrends/GetSeriesDisaggregationDimensions",
                {},
            ),
        }
        payloads: dict[str, Any] = {}
        hashes: dict[str, str] = {}
        for index, (label, (method, path, parameters)) in enumerate(resources.items()):
            payload, digest, reused = await self._read_json(
                client, label, method, path, parameters
            )
            payloads[label] = payload
            hashes[label] = digest
            if not reused and index + 1 < len(resources):
                await asyncio.sleep(self.request_interval_seconds)

        goals = self._list(payloads["goals"], "goals")
        current_series = self._list(payloads["series-current"], "current series")
        history = self._list(payloads["series-history"], "series history")
        geographies = self._list(payloads["geographies"], "geographies")
        geography_tree = self._list(payloads["geography-tree"], "geography tree")
        disaggregations = self._list(payloads["disaggregations"], "disaggregations")
        last_updated = self._timestamp(payloads["last-updated"])

        goal_codes = [self._text(item, "code", "goal") for item in goals]
        detail_tasks: list[Coroutine[Any, Any, tuple[Any, str, bool]]] = []
        for goal_code in goal_codes:
            detail_tasks.extend(
                (
                    self._read_json(
                        client,
                        f"goal-{goal_code}-dimensions",
                        "GET",
                        f"Goal/{goal_code}/Dimensions",
                        {},
                    ),
                    self._read_json(
                        client,
                        f"goal-{goal_code}-attributes",
                        "GET",
                        f"Goal/{goal_code}/Attributes",
                        {},
                    ),
                )
            )
        details = await asyncio.gather(*detail_tasks)
        provider_dimensions: dict[str, dict[str, Any]] = {}
        for index, goal_code in enumerate(goal_codes):
            for component_kind, suffix, result in (
                ("dimension", "dimensions", details[index * 2]),
                ("attribute", "attributes", details[index * 2 + 1]),
            ):
                payload, digest, _ = result
                hashes[f"goal-{goal_code}-{suffix}"] = digest
                for item in self._list(payload, f"goal {goal_code} {suffix}"):
                    component_id = self._text(item, "id", f"goal {goal_code} {suffix}")
                    entry = provider_dimensions.setdefault(
                        component_id,
                        {"kind": component_kind, "goals": set(), "values": {}},
                    )
                    if entry["kind"] != component_kind:
                        raise UnSdgCatalogHarvestError(
                            f"UN SDG component {component_id} changes kind across goals."
                        )
                    entry["goals"].add(goal_code)
                    for raw_value in self._list(
                        item.get("codes"), f"UN SDG component {component_id} codes"
                    ):
                        code = self._text(raw_value, "code", f"component {component_id}")
                        value = SourceDimensionValue(
                            code=code,
                            label=self._text(
                                raw_value,
                                "description",
                                f"component {component_id} code {code}",
                            ),
                            attributes={"sdmx_code": raw_value.get("sdmx")},
                        )
                        previous = entry["values"].get(code)
                        if previous is not None and previous != value:
                            raise UnSdgCatalogHarvestError(
                                f"UN SDG component {component_id}/{code} conflicts across goals."
                            )
                        entry["values"][code] = value

        hierarchy = self._hierarchy(goals, history)
        release_codes = sorted(
            {self._text(item, "release", "series history") for item in history}
        )
        current_codes = {
            self._text(item, "code", "current series") for item in current_series
        }
        history_by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in history:
            history_by_series[self._text(item, "code", "series history")].append(item)
        if not current_codes.issubset(history_by_series):
            raise UnSdgCatalogHarvestError(
                "UN SDG current series are missing from the release-history catalog."
            )

        disaggregation_by_series: dict[str, dict[str, SourceDimensionValue]] = defaultdict(dict)
        for item in disaggregations:
            series_code = self._text(item, "seriesCode", "series disaggregation")
            category = self._text(
                item, "disaggregatedCategory", f"series {series_code} disaggregation"
            ).strip()
            if category:
                disaggregation_by_series[series_code][category] = SourceDimensionValue(
                    code=category,
                    label=category,
                )

        geo_values = self._geographies(geographies, geography_tree)
        shared_codelists = [
            SourceCodelist(
                agency_id="UNSDG",
                codelist_id="GEO_AREA",
                version=last_updated.isoformat(),
                label="UN SDG geography",
                description="Countries, areas and regional aggregates published by the UN SDG API.",
                values=geo_values,
            ),
            SourceCodelist(
                agency_id="UNSDG",
                codelist_id="FREQ",
                version="1.0",
                label="Frequency",
                values=[SourceDimensionValue(code="A", label="Annual")],
            ),
        ]

        datasets: list[SourceDataset] = []
        constrained_codelists: list[SourceCodelist] = []
        executable_code = "NY_GDP_PCAP"
        for series_code, releases in sorted(history_by_series.items()):
            ordered = sorted(releases, key=lambda item: self._text(item, "release", series_code))
            latest = ordered[-1]
            goals_for_series = self._string_list(latest.get("goal"), f"series {series_code} goals")
            targets_for_series = self._string_list(
                latest.get("target"), f"series {series_code} targets"
            )
            indicators_for_series = self._string_list(
                latest.get("indicator"), f"series {series_code} indicators"
            )
            dimensions = [
                self._series_dimension("GOAL", "Goal", "other", goals_for_series, hierarchy),
                self._series_dimension(
                    "TARGET", "Target", "classification", targets_for_series, hierarchy
                ),
                self._series_dimension(
                    "INDICATOR",
                    "Indicator",
                    "indicator",
                    indicators_for_series,
                    hierarchy,
                ),
                SourceDimension(
                    dimension_id="FREQ",
                    label="Frequency",
                    role="frequency",
                    key_position=0,
                    codelist_agency_id="UNSDG",
                    codelist_id="FREQ",
                    codelist_version="1.0",
                ),
                SourceDimension(
                    dimension_id="GEO_AREA",
                    label="Geography",
                    role="geography",
                    key_position=1,
                    codelist_agency_id="UNSDG",
                    codelist_id="GEO_AREA",
                    codelist_version=last_updated.isoformat(),
                ),
                SourceDimension(
                    dimension_id="RELEASE",
                    label="Release",
                    role="status",
                    values=[
                        SourceDimensionValue(code=value, label=value)
                        for value in sorted(
                            {
                                self._text(item, "release", f"series {series_code}")
                                for item in ordered
                            }
                        )
                    ],
                ),
            ]
            combinations = list(disaggregation_by_series.get(series_code, {}).values())
            if combinations:
                codelist_id = f"{series_code}@DISAGGREGATION"
                constrained_codelists.append(
                    SourceCodelist(
                        agency_id="UNSDG.SERIES",
                        codelist_id=codelist_id,
                        version=last_updated.isoformat(),
                        label=f"{series_code} published disaggregation combinations",
                        values=combinations,
                    )
                )
                dimensions.append(
                    SourceDimension(
                        dimension_id="DISAGGREGATION",
                        label="Published disaggregation combination",
                        role="classification",
                        codelist_agency_id="UNSDG.SERIES",
                        codelist_id=codelist_id,
                        codelist_version=last_updated.isoformat(),
                    )
                )
            active = series_code in current_codes
            datasets.append(
                SourceDataset(
                    dataset_id=f"UNSDG:{series_code}",
                    agency_id="UNSDG",
                    version=self._text(latest, "release", f"series {series_code}"),
                    title=self._text(latest, "description", f"series {series_code}"),
                    description=self._text(latest, "description", f"series {series_code}"),
                    executable=active and series_code == executable_code,
                    coverage_status="complete",
                    updated_at=last_updated if active else None,
                    documentation_urls=[
                        f"{self.base_url}/Series/{series_code}/List",
                        "https://unstats.un.org/sdgs/metadata/",
                    ],
                    attributes={
                        "series_code": series_code,
                        "active_in_current_release": active,
                        "release_total": len(
                            {
                                self._text(item, "release", f"series {series_code}")
                                for item in ordered
                            }
                        ),
                        "connector_dataset_id": "SDG_8_1_1"
                        if series_code == executable_code
                        else None,
                    },
                    dimensions=dimensions,
                )
            )

        provider_dimension_models = [
            SourceDimension(
                dimension_id=component_id,
                label=component_id,
                role="status" if entry["kind"] == "attribute" else "classification",
                component_kind=entry["kind"],
                values=list(entry["values"].values()),
            )
            for component_id, entry in sorted(provider_dimensions.items())
        ]
        combined_hash = hashlib.sha256(
            "".join(f"{key}:{value}\n" for key, value in sorted(hashes.items())).encode()
        ).hexdigest()
        snapshot = ProviderSourceSnapshot(
            provider_id="un_sdg",
            provider_name="United Nations Statistics Division",
            catalog_url=self.catalog_url,
            snapshot_version=f"un-sdg:{last_updated.isoformat()}",
            retrieved_at=datetime.now(timezone.utc),
            coverage_status="complete",
            source_sha256=combined_hash,
            attributes={
                "goal_total": len(hierarchy["GOAL"]),
                "target_total": len(hierarchy["TARGET"]),
                "indicator_total": len(hierarchy["INDICATOR"]),
                "current_series_total": len(current_codes),
                "historical_series_total": len(history_by_series),
                "release_total": len(release_codes),
                "geography_total": len(geo_values),
                "disaggregation_combination_total": sum(
                    len(item) for item in disaggregation_by_series.values()
                ),
                "component_total": len(provider_dimension_models),
                "last_updated": last_updated.isoformat(),
            },
            dimensions=[
                SourceDimension(
                    dimension_id=key,
                    label=key.title(),
                    role="indicator" if key == "INDICATOR" else "classification",
                    values=list(values.values()),
                )
                for key, values in hierarchy.items()
            ]
            + provider_dimension_models,
            datasets=datasets,
        )
        return UnSdgCatalogResult(
            snapshot=snapshot,
            codelists=tuple([*shared_codelists, *constrained_codelists]),
        )

    async def _read_json(
        self,
        client: httpx.AsyncClient,
        label: str,
        method: str,
        resource: str,
        parameters: dict[str, str],
    ) -> tuple[Any, str, bool]:
        url = f"{self.base_url}/{resource}"
        descriptor = f"{method}:{url}?{urlencode(sorted(parameters.items()))}"
        request_key = hashlib.sha256(descriptor.encode()).hexdigest()[:12]
        directory = self.raw_dir / "un_sdg"
        directory.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for candidate in sorted(
            directory.glob(f"{label}-{request_key}-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if now - candidate.stat().st_mtime > self.resume_max_age_seconds:
                continue
            raw = candidate.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if candidate.stem.rsplit("-", 1)[-1] == digest[:12]:
                return self._json(raw, label), digest, True

        temporary = directory / f".{label}-{uuid4().hex}.partial"
        try:
            for attempt in range(3):
                try:
                    async with client.stream(
                        method,
                        url,
                        params=parameters if method == "GET" else None,
                        content=b"" if method == "POST" else None,
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                        timeout=httpx.Timeout(connect=15, read=600, write=15, pool=15),
                    ) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(float(attempt + 1))
                            continue
                        if response.status_code != 200:
                            raise UnSdgCatalogHarvestError(
                                f"UN SDG {label} failed (HTTP {response.status_code})."
                            )
                        digest_builder = hashlib.sha256()
                        size = 0
                        with temporary.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self.max_bytes:
                                    raise UnSdgCatalogHarvestError(
                                        f"UN SDG {label} exceeds the catalog limit."
                                    )
                                digest_builder.update(chunk)
                                output.write(chunk)
                        raw = temporary.read_bytes()
                        payload = self._json(raw, label)
                        digest = digest_builder.hexdigest()
                        target = directory / f"{label}-{request_key}-{digest[:12]}.json"
                        temporary.replace(target)
                        return payload, digest, False
                except httpx.TransportError as error:
                    if attempt < 2:
                        await asyncio.sleep(float(attempt + 1))
                        continue
                    raise UnSdgCatalogHarvestError(
                        f"UN SDG {label} connection failed."
                    ) from error
        finally:
            temporary.unlink(missing_ok=True)
        raise UnSdgCatalogHarvestError(f"UN SDG {label} failed.")

    @staticmethod
    def _json(raw: bytes, label: str) -> Any:
        try:
            return json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnSdgCatalogHarvestError(f"UN SDG {label} returned malformed JSON.") from error

    @staticmethod
    def _list(payload: Any, label: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise UnSdgCatalogHarvestError(f"UN SDG {label} is not an object list.")
        return payload

    @staticmethod
    def _text(item: dict[str, Any], field: str, label: str) -> str:
        value = str(item.get(field) or "").strip()
        if not value:
            raise UnSdgCatalogHarvestError(f"UN SDG {label} is missing {field}.")
        return value

    @staticmethod
    def _string_list(value: Any, label: str) -> list[str]:
        if not isinstance(value, list) or not all(str(item).strip() for item in value):
            raise UnSdgCatalogHarvestError(f"UN SDG {label} is not a code list.")
        return list(dict.fromkeys(str(item).strip() for item in value))

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if not isinstance(value, str):
            raise UnSdgCatalogHarvestError("UN SDG last-updated marker is invalid.")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise UnSdgCatalogHarvestError("UN SDG last-updated marker is invalid.") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _hierarchy(
        self, goals: list[dict[str, Any]], history: list[dict[str, Any]]
    ) -> dict[str, dict[str, SourceDimensionValue]]:
        result: dict[str, dict[str, SourceDimensionValue]] = {
            "GOAL": {},
            "TARGET": {},
            "INDICATOR": {},
        }
        for goal in goals:
            goal_code = self._text(goal, "code", "goal")
            result["GOAL"][goal_code] = SourceDimensionValue(
                code=goal_code,
                label=self._text(goal, "title", f"goal {goal_code}"),
                description=str(goal.get("description") or "").strip() or None,
            )
            for target in self._list(goal.get("targets"), f"goal {goal_code} targets"):
                target_code = self._text(target, "code", f"goal {goal_code} target")
                result["TARGET"][target_code] = SourceDimensionValue(
                    code=target_code,
                    label=self._text(target, "title", f"target {target_code}"),
                    description=str(target.get("description") or "").strip() or None,
                    parent_codes=[goal_code],
                )
                for indicator in self._list(
                    target.get("indicators"), f"target {target_code} indicators"
                ):
                    indicator_code = self._text(
                        indicator, "code", f"target {target_code} indicator"
                    )
                    result["INDICATOR"][indicator_code] = SourceDimensionValue(
                        code=indicator_code,
                        label=self._text(
                            indicator, "description", f"indicator {indicator_code}"
                        ),
                        parent_codes=[target_code],
                        attributes={"tier": indicator.get("tier")},
                    )
        for row in history:
            for key, field in (
                ("GOAL", "goal"),
                ("TARGET", "target"),
                ("INDICATOR", "indicator"),
            ):
                for code in self._string_list(row.get(field), f"series history {field}"):
                    result[key].setdefault(code, SourceDimensionValue(code=code, label=code))
        return result

    @staticmethod
    def _series_dimension(
        dimension_id: str,
        label: str,
        role: DimensionRole,
        codes: list[str],
        hierarchy: dict[str, dict[str, SourceDimensionValue]],
    ) -> SourceDimension:
        return SourceDimension(
            dimension_id=dimension_id,
            label=label,
            role=role,
            values=[hierarchy[dimension_id][code] for code in codes],
        )

    def _geographies(
        self, flat: list[dict[str, Any]], tree: list[dict[str, Any]]
    ) -> list[SourceDimensionValue]:
        tree_types: dict[str, str] = {}
        parents: dict[str, set[str]] = defaultdict(set)

        def walk(node: dict[str, Any], parent: str | None = None) -> None:
            code = str(node.get("geoAreaCode") or "").strip()
            node_type = str(node.get("type") or "").strip()
            if not code or not node_type:
                raise UnSdgCatalogHarvestError("UN SDG geography tree contains an invalid node.")
            previous = tree_types.get(code)
            if previous is not None and previous != node_type:
                raise UnSdgCatalogHarvestError(f"UN SDG geography {code} changes type.")
            tree_types[code] = node_type
            if parent:
                parents[code].add(parent)
            children = node.get("children") or []
            if not isinstance(children, list):
                raise UnSdgCatalogHarvestError(
                    f"UN SDG geography {code} contains invalid children."
                )
            for child in children:
                if not isinstance(child, dict):
                    raise UnSdgCatalogHarvestError(
                        f"UN SDG geography {code} contains an invalid child."
                    )
                walk(child, code)

        for root in tree:
            walk(root)
        known_non_tree_aggregate = {
            "198",
            "908",
            "909",
            "910",
            "935",
            "936",
            "937",
            "938",
            "99042",
            "99043",
            "99044",
            "99045",
            "99046",
            "99047",
            "99048",
        }
        values = []
        for item in flat:
            code = self._text(item, "geoAreaCode", "geography")
            node_type = tree_types.get(code)
            if node_type is None and code not in known_non_tree_aggregate and code != "920":
                raise UnSdgCatalogHarvestError(
                    f"UN SDG geography {code} is absent from the reviewed hierarchy."
                )
            values.append(
                SourceDimensionValue(
                    code=code,
                    label=self._text(item, "geoAreaName", f"geography {code}"),
                    is_aggregate=(node_type != "Country")
                    if node_type is not None
                    else code in known_non_tree_aggregate,
                    parent_codes=sorted(parents.get(code, set())),
                    attributes={"geography_type": node_type or "reviewed exception"},
                )
            )
        return values
