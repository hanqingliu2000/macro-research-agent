"""Validated high-level public data-source knowledge for Plan AI retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IndicatorKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1)
    unit_or_measure: str | None = None
    notes: str | None = None


class DatasetKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    provider_dataset_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    availability: Literal["available", "planned"]
    description: str = Field(min_length=1)
    topics: list[str] = Field(min_length=1)
    search_terms: list[str] = Field(min_length=1)
    frequencies: list[str] = Field(min_length=1)
    geographic_coverage: str = Field(min_length=1)
    temporal_coverage: str = Field(min_length=1)
    publication_cadence: str = Field(min_length=1)
    metadata_fields: list[str] = Field(min_length=1)
    indicators: list[IndicatorKnowledge] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    documentation_urls: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_indicator_codes(self) -> DatasetKnowledge:
        codes = [item.code for item in self.indicators]
        if len(codes) != len(set(codes)):
            raise ValueError(f"Duplicate indicator code in {self.dataset_id}.")
        return self


class ProviderKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    availability: Literal["available", "planned"]
    catalog_summary: str = Field(min_length=1)
    catalog_topics: list[str] = Field(min_length=1)
    catalog_examples_not_executable: list[str] = Field(default_factory=list)
    official_catalog_url: str
    terms_url: str
    verified_on: date
    review_interval_days: int = Field(ge=30, le=366)
    datasets: list[DatasetKnowledge] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_dataset_ids(self) -> ProviderKnowledge:
        ids = [item.dataset_id for item in self.datasets]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate dataset ID for {self.connector_id}.")
        return self


class DataSourceKnowledgeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["data-source-knowledge-v1"]
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    purpose: str = Field(min_length=1)
    providers: list[ProviderKnowledge] = Field(min_length=1)
    content_sha256: str | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def unique_connector_ids(self) -> DataSourceKnowledgeCatalog:
        ids = [item.connector_id for item in self.providers]
        if len(ids) != len(set(ids)):
            raise ValueError("Data-source knowledge contains duplicate connector IDs.")
        return self

    def for_planning(
        self,
        research_request: str,
        available_connector_ids: list[str],
        *,
        max_datasets: int = 12,
    ) -> list[dict[str, Any]]:
        """Return compact, ranked knowledge without turning catalog scope into capability."""

        if max_datasets < 1 or max_datasets > 50:
            raise ValueError("Planning knowledge result limit must be between 1 and 50.")
        query = research_request.casefold()
        available = set(available_connector_ids)
        candidates: list[tuple[int, str, ProviderKnowledge, DatasetKnowledge]] = []
        for provider in self.providers:
            if provider.connector_id not in available:
                continue
            for dataset in provider.datasets:
                if dataset.availability != "available":
                    continue
                score = self._score(query, provider, dataset)
                candidates.append((score, dataset.dataset_id, provider, dataset))
        candidates.sort(key=lambda item: (-item[0], item[2].connector_id, item[1]))
        selected = candidates[:max_datasets]
        return [self._planning_record(provider, dataset) for _, _, provider, dataset in selected]

    @staticmethod
    def _score(query: str, provider: ProviderKnowledge, dataset: DatasetKnowledge) -> int:
        score = 0
        searchable = [
            provider.provider_name,
            provider.connector_id,
            dataset.dataset_id,
            dataset.provider_dataset_id,
            dataset.title,
            *provider.catalog_topics,
            *dataset.topics,
            *dataset.search_terms,
        ]
        for indicator in dataset.indicators:
            searchable.extend([indicator.code, indicator.label, *indicator.concepts])
        for term in searchable:
            normalized = term.casefold().strip()
            if normalized and normalized in query:
                exact_ids = {dataset.dataset_id.casefold(), provider.connector_id}
                score += 8 if normalized in exact_ids else 2
        query_tokens = set(re.findall(r"[a-z0-9_.]+", query))
        record_tokens = set(re.findall(r"[a-z0-9_.]+", " ".join(searchable).casefold()))
        score += len(query_tokens & record_tokens)
        return score

    @staticmethod
    def _planning_record(
        provider: ProviderKnowledge, dataset: DatasetKnowledge
    ) -> dict[str, Any]:
        return {
            "connector_id": provider.connector_id,
            "provider": provider.provider_name,
            "provider_catalog_summary": provider.catalog_summary,
            "provider_catalog_topics": provider.catalog_topics,
            "catalog_examples_not_executable": provider.catalog_examples_not_executable,
            "dataset": dataset.dataset_id,
            "provider_dataset_id": dataset.provider_dataset_id,
            "title": dataset.title,
            "description": dataset.description,
            "topics": dataset.topics,
            "frequencies": dataset.frequencies,
            "geographic_coverage": dataset.geographic_coverage,
            "temporal_coverage": dataset.temporal_coverage,
            "publication_cadence": dataset.publication_cadence,
            "metadata_fields": dataset.metadata_fields,
            "indicators": [item.model_dump(mode="json") for item in dataset.indicators],
            "constraints": dataset.constraints,
            "verified_on": provider.verified_on.isoformat(),
            "review_interval_days": provider.review_interval_days,
            "documentation_urls": dataset.documentation_urls,
            "knowledge_notice": (
                "Curated discovery knowledge, not runtime provider metadata. Only this dataset "
                "slice is executable; validate current metadata during acquisition."
            ),
        }


@lru_cache(maxsize=1)
def default_data_source_knowledge() -> DataSourceKnowledgeCatalog:
    path = Path(__file__).with_name("data_source_catalog.json")
    raw = path.read_bytes()
    payload = json.loads(raw)
    catalog = DataSourceKnowledgeCatalog.model_validate(payload)
    return catalog.model_copy(update={"content_sha256": hashlib.sha256(raw).hexdigest()})
