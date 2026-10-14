"""Normalized, provider-derived metadata index for source discovery."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from macro_research_agent.knowledge.data_sources import DataSourceKnowledgeCatalog

DimensionRole = Literal[
    "indicator",
    "frequency",
    "geography",
    "time",
    "unit",
    "measure",
    "classification",
    "status",
    "other",
]
ComponentKind = Literal["dimension", "time", "measure", "attribute"]
CoverageStatus = Literal["seed", "complete", "partial", "failed"]


class SourceDimensionValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = None
    is_aggregate: bool | None = None
    parent_codes: list[str] = Field(default_factory=list)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SourceDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: DimensionRole
    component_kind: ComponentKind = "dimension"
    key_position: int | None = Field(default=None, ge=0)
    codelist_agency_id: str | None = None
    codelist_id: str | None = None
    codelist_version: str | None = None
    values: list[SourceDimensionValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_values(self) -> SourceDimension:
        references = (
            self.codelist_agency_id,
            self.codelist_id,
            self.codelist_version,
        )
        if any(references) and not all(references):
            raise ValueError("A codelist reference requires agency, ID and version.")
        codes = [item.code for item in self.values]
        if len(codes) != len(set(codes)):
            raise ValueError(f"Duplicate value in dimension {self.dimension_id}.")
        return self


class SourceCodelist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agency_id: str = Field(min_length=1)
    codelist_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = None
    values: list[SourceDimensionValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_values(self) -> SourceCodelist:
        codes = [item.code for item in self.values]
        if len(codes) != len(set(codes)):
            raise ValueError(f"Duplicate value in codelist {self.codelist_id}.")
        return self


class SourceDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    agency_id: str | None = None
    version: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    executable: bool = False
    coverage_status: CoverageStatus
    updated_at: datetime | None = None
    documentation_urls: list[str] = Field(default_factory=list)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    dimensions: list[SourceDimension] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_dimensions(self) -> SourceDataset:
        ids = [item.dimension_id for item in self.dimensions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate dimension in dataset {self.dataset_id}.")
        return self


class ProviderSourceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    catalog_url: str
    snapshot_version: str = Field(min_length=1)
    retrieved_at: datetime
    coverage_status: CoverageStatus
    source_sha256: str = Field(min_length=1)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    dimensions: list[SourceDimension] = Field(default_factory=list)
    datasets: list[SourceDataset] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_datasets(self) -> ProviderSourceSnapshot:
        ids = [item.dataset_id for item in self.datasets]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate dataset for provider {self.provider_id}.")
        if self.coverage_status == "complete" and any(
            item.coverage_status != "complete" for item in self.datasets
        ):
            raise ValueError("A complete provider snapshot cannot contain incomplete datasets.")
        dimension_ids = [item.dimension_id for item in self.dimensions]
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError(f"Duplicate provider dimension for {self.provider_id}.")
        return self


class SourceIndexMatch(BaseModel):
    provider_id: str
    provider_name: str
    dataset_id: str
    title: str
    description: str | None
    executable: bool
    coverage_status: CoverageStatus
    score: float
    dimensions: list[dict[str, Any]]
    matched_values: list[dict[str, Any]]


class SourceIndexRepository:
    """SQLite/FTS index; stores codelists without materializing their Cartesian product."""

    schema_version = "source-index-v2"

    def __init__(self, path: Path | str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_providers (
                provider_id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                catalog_url TEXT NOT NULL,
                snapshot_version TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                coverage_status TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                attributes TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS source_datasets (
                provider_id TEXT NOT NULL
                    REFERENCES source_providers(provider_id) ON DELETE CASCADE,
                dataset_id TEXT NOT NULL,
                agency_id TEXT,
                version TEXT,
                title TEXT NOT NULL,
                description TEXT,
                executable INTEGER NOT NULL,
                coverage_status TEXT NOT NULL,
                updated_at TEXT,
                documentation_urls TEXT NOT NULL,
                attributes TEXT NOT NULL,
                PRIMARY KEY (provider_id, dataset_id)
            );
            CREATE TABLE IF NOT EXISTS source_codelists (
                provider_id TEXT NOT NULL
                    REFERENCES source_providers(provider_id) ON DELETE CASCADE,
                agency_id TEXT NOT NULL,
                codelist_id TEXT NOT NULL,
                version TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT,
                PRIMARY KEY (provider_id, agency_id, codelist_id, version)
            );
            CREATE TABLE IF NOT EXISTS source_codelist_values (
                provider_id TEXT NOT NULL,
                agency_id TEXT NOT NULL,
                codelist_id TEXT NOT NULL,
                version TEXT NOT NULL,
                code TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT,
                is_aggregate INTEGER,
                parent_codes TEXT NOT NULL,
                attributes TEXT NOT NULL,
                PRIMARY KEY (provider_id, agency_id, codelist_id, version, code),
                FOREIGN KEY (provider_id, agency_id, codelist_id, version)
                    REFERENCES source_codelists(provider_id, agency_id, codelist_id, version)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS source_provider_dimensions (
                provider_id TEXT NOT NULL
                    REFERENCES source_providers(provider_id) ON DELETE CASCADE,
                dimension_id TEXT NOT NULL,
                label TEXT NOT NULL,
                role TEXT NOT NULL,
                key_position INTEGER,
                PRIMARY KEY (provider_id, dimension_id)
            );
            CREATE TABLE IF NOT EXISTS source_provider_dimension_values (
                provider_id TEXT NOT NULL,
                dimension_id TEXT NOT NULL,
                code TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT,
                is_aggregate INTEGER,
                parent_codes TEXT NOT NULL,
                attributes TEXT NOT NULL,
                PRIMARY KEY (provider_id, dimension_id, code),
                FOREIGN KEY (provider_id, dimension_id)
                    REFERENCES source_provider_dimensions(provider_id, dimension_id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS source_dimensions (
                provider_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                dimension_id TEXT NOT NULL,
                label TEXT NOT NULL,
                role TEXT NOT NULL,
                component_kind TEXT NOT NULL DEFAULT 'dimension',
                key_position INTEGER,
                codelist_agency_id TEXT,
                codelist_id TEXT,
                codelist_version TEXT,
                PRIMARY KEY (provider_id, dataset_id, dimension_id),
                FOREIGN KEY (provider_id, dataset_id)
                    REFERENCES source_datasets(provider_id, dataset_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS source_dimension_values (
                provider_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                dimension_id TEXT NOT NULL,
                code TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT,
                is_aggregate INTEGER,
                parent_codes TEXT NOT NULL,
                attributes TEXT NOT NULL,
                PRIMARY KEY (provider_id, dataset_id, dimension_id, code),
                FOREIGN KEY (provider_id, dataset_id, dimension_id)
                    REFERENCES source_dimensions(provider_id, dataset_id, dimension_id)
                    ON DELETE CASCADE
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS source_dataset_fts USING fts5(
                provider_id UNINDEXED,
                dataset_id UNINDEXED,
                content,
                tokenize = "unicode61 remove_diacritics 2 tokenchars '._-'"
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS source_codelist_value_fts USING fts5(
                provider_id UNINDEXED,
                agency_id UNINDEXED,
                codelist_id UNINDEXED,
                version UNINDEXED,
                code UNINDEXED,
                content,
                tokenize = "unicode61 remove_diacritics 2 tokenchars '._-'"
            );
            """
        )
        provider_columns = {
            str(item[1]) for item in self.connection.execute("PRAGMA table_info(source_providers)")
        }
        if "attributes" not in provider_columns:
            self.connection.execute(
                "ALTER TABLE source_providers ADD COLUMN attributes TEXT NOT NULL DEFAULT '{}'"
            )
        dimension_columns = {
            str(item[1]) for item in self.connection.execute("PRAGMA table_info(source_dimensions)")
        }
        if "component_kind" not in dimension_columns:
            self.connection.execute(
                """
                ALTER TABLE source_dimensions
                ADD COLUMN component_kind TEXT NOT NULL DEFAULT 'dimension'
                """
            )
        for column in ("codelist_agency_id", "codelist_id", "codelist_version"):
            if column not in dimension_columns:
                self.connection.execute(f"ALTER TABLE source_dimensions ADD COLUMN {column} TEXT")
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS source_dimensions_codelist_lookup
            ON source_dimensions(
                provider_id, codelist_agency_id, codelist_id,
                codelist_version, dataset_id, dimension_id
            )
            """
        )
        self.connection.commit()

    def replace_provider(self, snapshot: ProviderSourceSnapshot) -> None:
        self.replace_provider_with_codelists(snapshot, ())

    def replace_provider_with_codelists(
        self,
        snapshot: ProviderSourceSnapshot,
        codelists: Iterable[SourceCodelist],
    ) -> None:
        searchable: list[tuple[str, str, str]] = []
        with self.connection:
            existing = self.connection.execute(
                "SELECT coverage_status FROM source_providers WHERE provider_id = ?",
                (snapshot.provider_id,),
            ).fetchone()
            if (
                existing
                and existing["coverage_status"] == "complete"
                and snapshot.coverage_status != "complete"
            ):
                raise ValueError("An incomplete snapshot cannot replace last-known-good metadata.")
            self.connection.execute(
                "DELETE FROM source_dataset_fts WHERE provider_id = ?", (snapshot.provider_id,)
            )
            self.connection.execute(
                "DELETE FROM source_codelist_value_fts WHERE provider_id = ?",
                (snapshot.provider_id,),
            )
            self.connection.execute(
                "DELETE FROM source_providers WHERE provider_id = ?", (snapshot.provider_id,)
            )
            self.connection.execute(
                """
                INSERT INTO source_providers(
                    provider_id, provider_name, catalog_url, snapshot_version, retrieved_at,
                    coverage_status, source_sha256, attributes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.provider_id,
                    snapshot.provider_name,
                    snapshot.catalog_url,
                    snapshot.snapshot_version,
                    snapshot.retrieved_at.astimezone(timezone.utc).isoformat(),
                    snapshot.coverage_status,
                    snapshot.source_sha256,
                    json.dumps(snapshot.attributes, ensure_ascii=False, sort_keys=True),
                ),
            )
            provider_terms = [snapshot.provider_name, snapshot.provider_id]
            for dimension in snapshot.dimensions:
                self._insert_provider_dimension(snapshot.provider_id, dimension)
                provider_terms.extend([dimension.dimension_id, dimension.label, dimension.role])
                for value in dimension.values:
                    provider_terms.extend([value.code, value.label])
                    if value.description:
                        provider_terms.append(value.description)
            for codelist in codelists:
                self._insert_codelist(snapshot.provider_id, codelist)
            for dataset in snapshot.datasets:
                self._insert_dataset(snapshot.provider_id, dataset)
                terms = [*provider_terms, dataset.dataset_id, dataset.title]
                if dataset.description:
                    terms.append(dataset.description)
                for dimension in dataset.dimensions:
                    terms.extend([dimension.dimension_id, dimension.label, dimension.role])
                    for value in dimension.values:
                        terms.extend([value.code, value.label])
                        if value.description:
                            terms.append(value.description)
                searchable.append((snapshot.provider_id, dataset.dataset_id, "\n".join(terms)))
            self.connection.executemany(
                "INSERT INTO source_dataset_fts(provider_id, dataset_id, content) VALUES (?, ?, ?)",
                searchable,
            )
            missing = self.connection.execute(
                """
                SELECT d.dataset_id, d.dimension_id, d.codelist_agency_id,
                       d.codelist_id, d.codelist_version
                FROM source_dimensions d
                LEFT JOIN source_codelists c
                  ON c.provider_id = d.provider_id
                 AND c.agency_id = d.codelist_agency_id
                 AND c.codelist_id = d.codelist_id
                 AND c.version = d.codelist_version
                WHERE d.provider_id = ? AND d.codelist_id IS NOT NULL
                  AND c.codelist_id IS NULL
                LIMIT 1
                """,
                (snapshot.provider_id,),
            ).fetchone()
            if missing and snapshot.coverage_status == "complete":
                raise ValueError(
                    "Dataset dimension references a missing provider codelist: "
                    f"{missing['dataset_id']}/{missing['dimension_id']}."
                )

    def _insert_codelist(self, provider_id: str, codelist: SourceCodelist) -> None:
        self.connection.execute(
            "INSERT INTO source_codelists VALUES (?, ?, ?, ?, ?, ?)",
            (
                provider_id,
                codelist.agency_id,
                codelist.codelist_id,
                codelist.version,
                codelist.label,
                codelist.description,
            ),
        )
        rows = [
            (
                provider_id,
                codelist.agency_id,
                codelist.codelist_id,
                codelist.version,
                value.code,
                value.label,
                value.description,
                None if value.is_aggregate is None else int(value.is_aggregate),
                json.dumps(value.parent_codes, ensure_ascii=False),
                json.dumps(value.attributes, ensure_ascii=False, sort_keys=True),
            )
            for value in codelist.values
        ]
        self.connection.executemany(
            "INSERT INTO source_codelist_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.connection.executemany(
            """
            INSERT INTO source_codelist_value_fts(
                provider_id, agency_id, codelist_id, version, code, content
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    provider_id,
                    codelist.agency_id,
                    codelist.codelist_id,
                    codelist.version,
                    value.code,
                    "\n".join(
                        item
                        for item in (value.code, value.label, value.description)
                        if item
                    ),
                )
                for value in codelist.values
            ],
        )

    def _insert_provider_dimension(
        self, provider_id: str, dimension: SourceDimension
    ) -> None:
        self.connection.execute(
            "INSERT INTO source_provider_dimensions VALUES (?, ?, ?, ?, ?)",
            (
                provider_id,
                dimension.dimension_id,
                dimension.label,
                dimension.role,
                dimension.key_position,
            ),
        )
        self.connection.executemany(
            "INSERT INTO source_provider_dimension_values VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    provider_id,
                    dimension.dimension_id,
                    value.code,
                    value.label,
                    value.description,
                    None if value.is_aggregate is None else int(value.is_aggregate),
                    json.dumps(value.parent_codes, ensure_ascii=False),
                    json.dumps(value.attributes, ensure_ascii=False, sort_keys=True),
                )
                for value in dimension.values
            ],
        )

    def _insert_dataset(self, provider_id: str, dataset: SourceDataset) -> None:
        self.connection.execute(
            "INSERT INTO source_datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                provider_id,
                dataset.dataset_id,
                dataset.agency_id,
                dataset.version,
                dataset.title,
                dataset.description,
                int(dataset.executable),
                dataset.coverage_status,
                dataset.updated_at.astimezone(timezone.utc).isoformat()
                if dataset.updated_at
                else None,
                json.dumps(dataset.documentation_urls, ensure_ascii=False),
                json.dumps(dataset.attributes, ensure_ascii=False, sort_keys=True),
            ),
        )
        for dimension in dataset.dimensions:
            self.connection.execute(
                """
                INSERT INTO source_dimensions(
                    provider_id, dataset_id, dimension_id, label, role, component_kind,
                    key_position,
                    codelist_agency_id, codelist_id, codelist_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider_id,
                    dataset.dataset_id,
                    dimension.dimension_id,
                    dimension.label,
                    dimension.role,
                    dimension.component_kind,
                    dimension.key_position,
                    dimension.codelist_agency_id,
                    dimension.codelist_id,
                    dimension.codelist_version,
                ),
            )
            self.connection.executemany(
                "INSERT INTO source_dimension_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        provider_id,
                        dataset.dataset_id,
                        dimension.dimension_id,
                        value.code,
                        value.label,
                        value.description,
                        None if value.is_aggregate is None else int(value.is_aggregate),
                        json.dumps(value.parent_codes, ensure_ascii=False),
                        json.dumps(value.attributes, ensure_ascii=False, sort_keys=True),
                    )
                    for value in dimension.values
                ],
            )

    def provider_summaries(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM source_datasets d
                    WHERE d.provider_id = p.provider_id) AS dataset_count,
                   (SELECT COUNT(*) FROM source_dimension_values v
                    WHERE v.provider_id = p.provider_id)
                   + (SELECT COUNT(*) FROM source_codelist_values cv
                      WHERE cv.provider_id = p.provider_id)
                   + (SELECT COUNT(*) FROM source_provider_dimension_values pv
                      WHERE pv.provider_id = p.provider_id) AS dimension_value_count
            FROM source_providers p
            ORDER BY p.provider_id
            """
        ).fetchall()
        summaries = []
        for row in rows:
            item = dict(row)
            item["attributes"] = json.loads(item["attributes"])
            summaries.append(item)
        return summaries

    def datasets(
        self, provider_id: str, *, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT d.provider_id, d.dataset_id, d.agency_id, d.version, d.title,
                   d.description, d.executable, d.coverage_status, d.updated_at,
                   COUNT(DISTINCT x.dimension_id) AS dimension_count,
                   COALESCE(SUM(
                       (SELECT COUNT(*) FROM source_dimension_values v
                        WHERE v.provider_id = x.provider_id
                          AND v.dataset_id = x.dataset_id
                          AND v.dimension_id = x.dimension_id)
                       + (SELECT COUNT(*) FROM source_codelist_values cv
                          WHERE cv.provider_id = x.provider_id
                            AND cv.agency_id = x.codelist_agency_id
                            AND cv.codelist_id = x.codelist_id
                            AND cv.version = x.codelist_version)
                   ), 0) AS dimension_value_count
            FROM source_datasets d
            LEFT JOIN source_dimensions x USING (provider_id, dataset_id)
            WHERE d.provider_id = ?
            GROUP BY d.provider_id, d.dataset_id
            ORDER BY d.dataset_id LIMIT ? OFFSET ?
            """,
            (provider_id, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def dimension_values(
        self,
        provider_id: str,
        dataset_id: str,
        dimension_id: str,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        dimension = self.connection.execute(
            """
            SELECT codelist_agency_id, codelist_id, codelist_version
            FROM source_dimensions
            WHERE provider_id = ? AND dataset_id = ? AND dimension_id = ?
            """,
            (provider_id, dataset_id, dimension_id),
        ).fetchone()
        if dimension and dimension["codelist_id"]:
            return self._dimension_values(
                "source_codelist_values",
                [
                    provider_id,
                    dimension["codelist_agency_id"],
                    dimension["codelist_id"],
                    dimension["codelist_version"],
                ],
                "provider_id = ? AND agency_id = ? AND codelist_id = ? AND version = ?",
                query=query,
                offset=offset,
                limit=limit,
            )
        return self._dimension_values(
            "source_dimension_values",
            [provider_id, dataset_id, dimension_id],
            "provider_id = ? AND dataset_id = ? AND dimension_id = ?",
            query=query,
            offset=offset,
            limit=limit,
        )

    def _dimension_values(
        self,
        table: str,
        keys: list[str],
        predicate: str,
        *,
        query: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if table not in {
            "source_dimension_values",
            "source_provider_dimension_values",
            "source_codelist_values",
        }:
            raise ValueError("Unsupported source-index dimension table.")
        parameters: list[Any] = list(keys)
        filter_sql = ""
        if query.strip():
            wildcard = f"%{query.casefold().strip()}%"
            filter_sql = (
                " AND (lower(code) LIKE ? OR lower(label) LIKE ? "
                "OR lower(COALESCE(description, '')) LIKE ?)"
            )
            parameters.extend([wildcard, wildcard, wildcard])
        total = self.connection.execute(
            f"""
            SELECT COUNT(*) FROM {table}
            WHERE {predicate}{filter_sql}
            """,
            parameters,
        ).fetchone()[0]
        rows = self.connection.execute(
            f"""
            SELECT code, label, description, is_aggregate, parent_codes, attributes
            FROM {table}
            WHERE {predicate}{filter_sql}
            ORDER BY code LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        ).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            item["is_aggregate"] = (
                None if item["is_aggregate"] is None else bool(item["is_aggregate"])
            )
            item["parent_codes"] = json.loads(item["parent_codes"])
            item["attributes"] = json.loads(item["attributes"])
            values.append(item)
        return {"total": total, "offset": offset, "limit": limit, "values": values}

    def provider_dimension_values(
        self,
        provider_id: str,
        dimension_id: str,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._dimension_values(
            "source_provider_dimension_values",
            [provider_id, dimension_id],
            "provider_id = ? AND dimension_id = ?",
            query=query,
            offset=offset,
            limit=limit,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 12,
        provider_id: str | None = None,
        executable_only: bool = False,
    ) -> list[SourceIndexMatch]:
        if limit < 1 or limit > 50:
            raise ValueError("Source-index result limit must be between 1 and 50.")
        tokens = self._tokens(query)
        conditions: list[str] = []
        parameters: list[Any] = []
        if provider_id:
            conditions.append("d.provider_id = ?")
            parameters.append(provider_id)
        if executable_only:
            conditions.append("d.executable = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        if tokens:
            candidates: set[tuple[str, str]] | None = None
            for token in tokens:
                match_token = f'"{token.replace(chr(34), chr(34) * 2)}"*'
                token_candidates = {
                    (str(item["provider_id"]), str(item["dataset_id"]))
                    for item in self.connection.execute(
                        """
                        SELECT provider_id, dataset_id FROM source_dataset_fts
                        WHERE source_dataset_fts MATCH ?
                        UNION
                        SELECT d.provider_id, d.dataset_id
                        FROM source_codelist_value_fts f
                        JOIN source_dimensions d
                          ON d.provider_id = f.provider_id
                         AND d.codelist_agency_id = f.agency_id
                         AND d.codelist_id = f.codelist_id
                         AND d.codelist_version = f.version
                        WHERE source_codelist_value_fts MATCH ?
                        """,
                        (match_token, match_token),
                    ).fetchall()
                }
                candidates = (
                    token_candidates
                    if candidates is None
                    else candidates & token_candidates
                )
                if not candidates:
                    break
            all_token_query = " AND ".join(
                f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens
            )
            strong_dataset_matches = {
                (str(item["provider_id"]), str(item["dataset_id"]))
                for item in self.connection.execute(
                    """
                    SELECT provider_id, dataset_id FROM source_dataset_fts
                    WHERE source_dataset_fts MATCH ?
                    """,
                    (all_token_query,),
                ).fetchall()
            }
            strong_value_matches = {
                (str(item["provider_id"]), str(item["dataset_id"]))
                for item in self.connection.execute(
                    """
                    SELECT DISTINCT d.provider_id, d.dataset_id
                    FROM source_codelist_value_fts f
                    JOIN source_dimensions d
                      ON d.provider_id = f.provider_id
                     AND d.codelist_agency_id = f.agency_id
                     AND d.codelist_id = f.codelist_id
                     AND d.codelist_version = f.version
                    WHERE source_codelist_value_fts MATCH ?
                    """,
                    (all_token_query,),
                ).fetchall()
            }
            near_value_matches: set[tuple[str, str]] = set()
            if len(tokens) >= 3:
                for omitted in range(len(tokens)):
                    subset_query = " AND ".join(
                        f'"{token.replace(chr(34), chr(34) * 2)}"*'
                        for index, token in enumerate(tokens)
                        if index != omitted
                    )
                    near_value_matches.update(
                        (str(item["provider_id"]), str(item["dataset_id"]))
                        for item in self.connection.execute(
                            """
                            SELECT DISTINCT d.provider_id, d.dataset_id
                            FROM source_codelist_value_fts f
                            JOIN source_dimensions d
                              ON d.provider_id = f.provider_id
                             AND d.codelist_agency_id = f.agency_id
                             AND d.codelist_id = f.codelist_id
                             AND d.codelist_version = f.version
                            WHERE source_codelist_value_fts MATCH ?
                            """,
                            (subset_query,),
                        ).fetchall()
                    )
            all_rows = self.connection.execute(
                """
                SELECT d.*, p.provider_name, -1.0 AS rank
                FROM source_datasets d JOIN source_providers p USING (provider_id)
                ORDER BY d.provider_id, d.dataset_id
                """
            ).fetchall()
            rows = [
                row
                for row in all_rows
                if candidates is not None
                and (row["provider_id"], row["dataset_id"]) in candidates
                and (provider_id is None or row["provider_id"] == provider_id)
                and (not executable_only or bool(row["executable"]))
            ]
            ranked_rows = sorted(
                (
                    (
                        self._relevance_score(
                            row,
                            tokens,
                            (row["provider_id"], row["dataset_id"])
                            in strong_dataset_matches,
                            (row["provider_id"], row["dataset_id"])
                            in strong_value_matches,
                            (row["provider_id"], row["dataset_id"])
                            in near_value_matches,
                        ),
                        row,
                    )
                    for row in rows
                ),
                key=lambda item: (
                    -item[0],
                    str(item[1]["provider_id"]),
                    str(item[1]["dataset_id"]),
                ),
            )[:limit]
            return [self._match(row, tokens, score) for score, row in ranked_rows]
        else:
            rows = self.connection.execute(
                f"""
                SELECT d.*, p.provider_name, 0.0 AS rank
                FROM source_datasets d JOIN source_providers p USING (provider_id)
                {where} ORDER BY d.provider_id, d.dataset_id LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._match(row, tokens) for row in rows]

    @staticmethod
    def _relevance_score(
        row: sqlite3.Row,
        tokens: list[str],
        strong_dataset_match: bool,
        strong_value_match: bool,
        near_value_match: bool,
    ) -> float:
        title = str(row["title"]).casefold()
        description = str(row["description"] or "").casefold()
        dataset_id = str(row["dataset_id"]).casefold()
        phrase = " ".join(tokens)
        score = 0.0
        if phrase and phrase in title:
            score += 80.0
        if strong_value_match:
            score += 80.0
        elif near_value_match:
            score += 65.0
        if strong_dataset_match:
            score += 20.0
        score += 8.0 * sum(token in title for token in tokens)
        score += 3.0 * sum(token in dataset_id for token in tokens)
        score += 1.0 * sum(token in description for token in tokens)
        if bool(row["executable"]):
            score += 12.0
        return score

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"[\w.-]+", query.casefold(), flags=re.UNICODE)))[:12]

    def _match(
        self, row: sqlite3.Row, tokens: list[str], score: float | None = None
    ) -> SourceIndexMatch:
        provider_dimensions = [
            {**dict(item), "scope": "provider"}
            for item in self.connection.execute(
                """
                SELECT d.dimension_id, d.label, d.role, d.key_position, COUNT(v.code) AS value_count
                FROM source_provider_dimensions d LEFT JOIN source_provider_dimension_values v
                  USING (provider_id, dimension_id)
                WHERE d.provider_id = ?
                GROUP BY d.dimension_id ORDER BY d.key_position, d.dimension_id
                """,
                (row["provider_id"],),
            ).fetchall()
        ]
        dataset_dimensions = [
            {**dict(item), "scope": "dataset"}
            for item in self.connection.execute(
                """
                SELECT d.dimension_id, d.label, d.role, d.component_kind, d.key_position,
                       d.codelist_agency_id, d.codelist_id, d.codelist_version,
                       (SELECT COUNT(*) FROM source_dimension_values v
                        WHERE v.provider_id = d.provider_id
                          AND v.dataset_id = d.dataset_id
                          AND v.dimension_id = d.dimension_id)
                       + (SELECT COUNT(*) FROM source_codelist_values cv
                          WHERE cv.provider_id = d.provider_id
                            AND cv.agency_id = d.codelist_agency_id
                            AND cv.codelist_id = d.codelist_id
                            AND cv.version = d.codelist_version) AS value_count
                FROM source_dimensions d
                WHERE d.provider_id = ? AND d.dataset_id = ?
                ORDER BY d.key_position, d.dimension_id
                """,
                (row["provider_id"], row["dataset_id"]),
            ).fetchall()
        ]
        dimensions = [*provider_dimensions, *dataset_dimensions]
        matched_values: list[dict[str, Any]] = []
        if tokens:
            clauses: list[str] = []
            parameters: list[Any] = [row["provider_id"], row["dataset_id"]]
            for token in tokens:
                clauses.append(
                    "(lower(v.code) LIKE ? OR lower(v.label) LIKE ? "
                    "OR lower(COALESCE(v.description, '')) LIKE ?)"
                )
                wildcard = f"%{token}%"
                parameters.extend([wildcard, wildcard, wildcard])
            matched_values = [
                {**dict(item), "scope": "dataset"}
                for item in self.connection.execute(
                    f"""
                    SELECT v.dimension_id, d.role, v.code, v.label, v.description,
                           v.is_aggregate
                    FROM source_dimension_values v JOIN source_dimensions d
                      USING (provider_id, dataset_id, dimension_id)
                    WHERE v.provider_id = ? AND v.dataset_id = ?
                      AND ({' OR '.join(clauses)})
                    ORDER BY d.key_position, v.code LIMIT 16
                    """,
                    parameters,
                ).fetchall()
            ]
            provider_parameters: list[Any] = [row["provider_id"]]
            provider_clauses: list[str] = []
            for token in tokens:
                provider_clauses.append(
                    "(lower(v.code) LIKE ? OR lower(v.label) LIKE ? "
                    "OR lower(COALESCE(v.description, '')) LIKE ?)"
                )
                wildcard = f"%{token}%"
                provider_parameters.extend([wildcard, wildcard, wildcard])
            matched_values.extend(
                {
                    **dict(item),
                    "scope": "provider",
                }
                for item in self.connection.execute(
                    f"""
                    SELECT v.dimension_id, d.role, v.code, v.label, v.description,
                           v.is_aggregate
                    FROM source_provider_dimension_values v
                    JOIN source_provider_dimensions d USING (provider_id, dimension_id)
                    WHERE v.provider_id = ? AND ({' OR '.join(provider_clauses)})
                    ORDER BY d.key_position, v.code LIMIT 16
                    """,
                    provider_parameters,
                ).fetchall()
            )
            match_query = " OR ".join(
                f'"{item.replace(chr(34), chr(34) * 2)}"*' for item in tokens
            )
            matched_values.extend(
                {
                    **dict(item),
                    "scope": "codelist",
                }
                for item in self.connection.execute(
                    """
                    SELECT d.dimension_id, d.role, cv.code, cv.label,
                           cv.description, cv.is_aggregate
                    FROM source_codelist_value_fts f
                    JOIN source_codelist_values cv
                      ON cv.provider_id = f.provider_id
                     AND cv.agency_id = f.agency_id
                     AND cv.codelist_id = f.codelist_id
                     AND cv.version = f.version
                     AND cv.code = f.code
                    JOIN source_dimensions d
                      ON d.provider_id = f.provider_id
                     AND d.codelist_agency_id = f.agency_id
                     AND d.codelist_id = f.codelist_id
                     AND d.codelist_version = f.version
                    WHERE d.provider_id = ? AND d.dataset_id = ?
                      AND source_codelist_value_fts MATCH ?
                    ORDER BY d.key_position, cv.code LIMIT 16
                    """,
                    (row["provider_id"], row["dataset_id"], match_query),
                ).fetchall()
            )
        return SourceIndexMatch(
            provider_id=row["provider_id"],
            provider_name=row["provider_name"],
            dataset_id=row["dataset_id"],
            title=row["title"],
            description=row["description"],
            executable=bool(row["executable"]),
            coverage_status=row["coverage_status"],
            score=score if score is not None else float(-row["rank"]),
            dimensions=dimensions,
            matched_values=matched_values,
        )


def seed_source_index(
    repository: SourceIndexRepository, catalog: DataSourceKnowledgeCatalog
) -> None:
    """Seed v2 from reviewed v1 records until provider harvesters replace each snapshot."""

    retrieved_at = datetime.now(timezone.utc)
    executable = {"available"}
    for provider in catalog.providers:
        existing = {
            item["provider_id"]: item for item in repository.provider_summaries()
        }.get(provider.connector_id)
        snapshot_version = f"seed:{catalog.catalog_version}"
        if existing and existing["coverage_status"] != "seed":
            continue
        if existing and existing["snapshot_version"] == snapshot_version:
            continue
        datasets: list[SourceDataset] = []
        for dataset in provider.datasets:
            datasets.append(
                SourceDataset(
                    dataset_id=dataset.dataset_id,
                    title=dataset.title,
                    description=dataset.description,
                    executable=dataset.availability in executable,
                    coverage_status="seed",
                    documentation_urls=dataset.documentation_urls,
                    attributes={
                        "provider_dataset_id": dataset.provider_dataset_id,
                        "geographic_coverage": dataset.geographic_coverage,
                        "temporal_coverage": dataset.temporal_coverage,
                        "publication_cadence": dataset.publication_cadence,
                    },
                    dimensions=[
                        SourceDimension(
                            dimension_id="indicator",
                            label="Indicator",
                            role="indicator",
                            values=[
                                SourceDimensionValue(
                                    code=item.code,
                                    label=item.label,
                                    description="; ".join(item.concepts),
                                    attributes={
                                        "unit_or_measure": item.unit_or_measure,
                                        "notes": item.notes,
                                    },
                                )
                                for item in dataset.indicators
                            ],
                        ),
                        SourceDimension(
                            dimension_id="frequency",
                            label="Frequency",
                            role="frequency",
                            values=[
                                SourceDimensionValue(code=item, label=item)
                                for item in dataset.frequencies
                            ],
                        ),
                    ],
                )
            )
        repository.replace_provider(
            ProviderSourceSnapshot(
                provider_id=provider.connector_id,
                provider_name=provider.provider_name,
                catalog_url=provider.official_catalog_url,
                snapshot_version=snapshot_version,
                retrieved_at=retrieved_at,
                coverage_status="seed",
                source_sha256=catalog.content_sha256 or catalog.catalog_version,
                datasets=datasets,
            )
        )
