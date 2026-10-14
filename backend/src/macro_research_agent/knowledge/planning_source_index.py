"""Compact, content-addressed Source Index retrieval for Plan AI."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


class PlanningSourceIndexError(ValueError):
    pass


class PlanningSourceIndexBuilder:
    """Export factual lookup fields, not provider prose or contact metadata.

    The nullable description column remains solely for v1 schema compatibility.
    """

    schema_version = "source-index-lite-v1"
    projection_policy_version = "facts-only-v1"

    def build(self, source_path: Path, output_path: Path) -> dict[str, int | str]:
        if source_path.resolve() == output_path.resolve():
            raise PlanningSourceIndexError("The lite index output must differ from its source.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.name}.building")
        temporary.unlink(missing_ok=True)
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        target = sqlite3.connect(temporary)
        target.row_factory = sqlite3.Row
        try:
            self._initialize(target)
            summary = self._populate(source, target)
            target.commit()
            target.execute("VACUUM")
            target.close()
            source.close()
            temporary.replace(output_path)
            return summary
        except Exception:
            target.close()
            source.close()
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA journal_mode = OFF;
            PRAGMA synchronous = OFF;
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE providers (
                provider_id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                catalog_url TEXT NOT NULL,
                snapshot_version TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                source_sha256 TEXT NOT NULL
            );
            CREATE TABLE datasets (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                executable INTEGER NOT NULL,
                UNIQUE (provider_id, dataset_id),
                FOREIGN KEY (provider_id) REFERENCES providers(provider_id)
            );
            CREATE TABLE indicator_concepts (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                code TEXT NOT NULL,
                label TEXT NOT NULL,
                UNIQUE (provider_id, code, label),
                FOREIGN KEY (provider_id) REFERENCES providers(provider_id)
            );
            CREATE TABLE indicator_sets (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                content_hash BLOB NOT NULL,
                value_count INTEGER NOT NULL,
                UNIQUE (provider_id, content_hash),
                FOREIGN KEY (provider_id) REFERENCES providers(provider_id)
            );
            CREATE TABLE indicator_set_members (
                set_id INTEGER NOT NULL,
                concept_id INTEGER NOT NULL,
                PRIMARY KEY (set_id, concept_id),
                FOREIGN KEY (set_id) REFERENCES indicator_sets(id),
                FOREIGN KEY (concept_id) REFERENCES indicator_concepts(id)
            );
            CREATE TABLE dataset_indicator_sets (
                dataset_rowid INTEGER NOT NULL,
                dimension_id TEXT NOT NULL,
                set_id INTEGER NOT NULL,
                PRIMARY KEY (dataset_rowid, dimension_id),
                FOREIGN KEY (dataset_rowid) REFERENCES datasets(id),
                FOREIGN KEY (set_id) REFERENCES indicator_sets(id)
            );
            CREATE INDEX indicator_set_members_by_concept
                ON indicator_set_members(concept_id, set_id);
            CREATE INDEX dataset_indicator_sets_by_set
                ON dataset_indicator_sets(set_id, dataset_rowid);
            CREATE VIRTUAL TABLE dataset_fts USING fts5(
                content,
                content = '',
                tokenize = "unicode61 remove_diacritics 2 tokenchars '._-'"
            );
            CREATE VIRTUAL TABLE indicator_fts USING fts5(
                content,
                content = '',
                tokenize = "unicode61 remove_diacritics 2 tokenchars '._-'"
            );
            """
        )

    def _populate(
        self, source: sqlite3.Connection, target: sqlite3.Connection
    ) -> dict[str, int | str]:
        providers = source.execute(
            """
            SELECT provider_id, provider_name, catalog_url, snapshot_version,
                   retrieved_at, coverage_status, source_sha256
            FROM source_providers ORDER BY provider_id
            """
        ).fetchall()
        if not providers or any(item["coverage_status"] != "complete" for item in providers):
            raise PlanningSourceIndexError(
                "A lite planning index requires complete provider snapshots."
            )
        target.executemany(
            "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    item["provider_id"],
                    item["provider_name"],
                    item["catalog_url"],
                    item["snapshot_version"],
                    item["retrieved_at"],
                    item["source_sha256"],
                )
                for item in providers
            ],
        )
        provider_names = {
            str(item["provider_id"]): str(item["provider_name"]) for item in providers
        }
        datasets = source.execute(
            """
            SELECT provider_id, dataset_id, title, executable
            FROM source_datasets ORDER BY provider_id, dataset_id
            """
        ).fetchall()
        dataset_rowids: dict[tuple[str, str], int] = {}
        for item in datasets:
            cursor = target.execute(
                """
                INSERT INTO datasets(provider_id, dataset_id, title, executable)
                VALUES (?, ?, ?, ?)
                """,
                tuple(item),
            )
            dataset_rowid = self._required_lastrowid(cursor)
            dataset_rowids[(str(item["provider_id"]), str(item["dataset_id"]))] = (
                dataset_rowid
            )
            content = "\n".join(
                value
                for value in (
                    str(item["dataset_id"]),
                    str(item["title"]),
                    provider_names[str(item["provider_id"])],
                )
                if value
            )
            target.execute(
                "INSERT INTO dataset_fts(rowid, content) VALUES (?, ?)",
                (dataset_rowid, content),
            )

        dimensions = source.execute(
            """
            SELECT provider_id, dataset_id, dimension_id, codelist_agency_id,
                   codelist_id, codelist_version
            FROM source_dimensions WHERE role = 'indicator'
            ORDER BY provider_id, dataset_id, dimension_id
            """
        ).fetchall()
        concept_ids: dict[tuple[str, str, str], int] = {}
        set_ids: dict[tuple[str, bytes], int] = {}
        dataset_indicator_set_total = 0
        for dimension in dimensions:
            values = self._indicator_values(source, dimension)
            if not values:
                continue
            provider_id = str(dimension["provider_id"])
            members: list[int] = []
            canonical_members: list[tuple[str, str]] = []
            for value in values:
                code = str(value["code"])
                label = str(value["label"])
                canonical_members.append((code, label))
                concept_key = (provider_id, code, label)
                concept_id = concept_ids.get(concept_key)
                if concept_id is None:
                    cursor = target.execute(
                        """
                        INSERT INTO indicator_concepts(provider_id, code, label)
                        VALUES (?, ?, ?)
                        """,
                        concept_key,
                    )
                    concept_id = self._required_lastrowid(cursor)
                    concept_ids[concept_key] = concept_id
                    target.execute(
                        "INSERT INTO indicator_fts(rowid, content) VALUES (?, ?)",
                        (concept_id, f"{code}\n{label}"),
                    )
                members.append(concept_id)
            unique_members = tuple(sorted(set(members)))
            content_hash = hashlib.sha256(
                json.dumps(
                    sorted(set(canonical_members)),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).digest()
            set_key = (provider_id, content_hash)
            set_id = set_ids.get(set_key)
            if set_id is None:
                cursor = target.execute(
                    """
                    INSERT INTO indicator_sets(provider_id, content_hash, value_count)
                    VALUES (?, ?, ?)
                    """,
                    (provider_id, content_hash, len(unique_members)),
                )
                set_id = self._required_lastrowid(cursor)
                set_ids[set_key] = set_id
                target.executemany(
                    "INSERT INTO indicator_set_members VALUES (?, ?)",
                    [(set_id, concept_id) for concept_id in unique_members],
                )
            target.execute(
                "INSERT INTO dataset_indicator_sets VALUES (?, ?, ?)",
                (
                    dataset_rowids[(provider_id, str(dimension["dataset_id"]))],
                    dimension["dimension_id"],
                    set_id,
                ),
            )
            dataset_indicator_set_total += 1

        snapshot_digest = hashlib.sha256(
            json.dumps(
                [
                    [item["provider_id"], item["snapshot_version"], item["source_sha256"]]
                    for item in providers
                ],
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        counts: dict[str, int | str] = {
            "provider_total": len(providers),
            "dataset_total": len(datasets),
            "indicator_concept_total": len(concept_ids),
            "indicator_set_total": len(set_ids),
            "dataset_indicator_set_total": dataset_indicator_set_total,
            "snapshot_digest": snapshot_digest,
        }
        metadata = {
            "schema_version": self.schema_version,
            "projection_policy_version": self.projection_policy_version,
            "catalog_version": (
                f"{self.schema_version}:{self.projection_policy_version}:"
                f"{snapshot_digest[:12]}"
            ),
            "built_at": datetime.now(timezone.utc).isoformat(),
            **{key: str(value) for key, value in counts.items()},
        }
        target.executemany(
            "INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items())
        )
        return counts

    @staticmethod
    def _required_lastrowid(cursor: sqlite3.Cursor) -> int:
        rowid = cursor.lastrowid
        if rowid is None:
            raise PlanningSourceIndexError("The lite index insert did not return a row id.")
        return rowid

    @staticmethod
    def _indicator_values(
        source: sqlite3.Connection, dimension: sqlite3.Row
    ) -> list[sqlite3.Row]:
        if dimension["codelist_id"]:
            return source.execute(
                """
                SELECT code, label FROM source_codelist_values
                WHERE provider_id = ? AND agency_id = ? AND codelist_id = ?
                  AND version = ? ORDER BY code
                """,
                (
                    dimension["provider_id"],
                    dimension["codelist_agency_id"],
                    dimension["codelist_id"],
                    dimension["codelist_version"],
                ),
            ).fetchall()
        return source.execute(
            """
            SELECT code, label FROM source_dimension_values
            WHERE provider_id = ? AND dataset_id = ? AND dimension_id = ?
            ORDER BY code
            """,
            (
                dimension["provider_id"],
                dimension["dataset_id"],
                dimension["dimension_id"],
            ),
        ).fetchall()


class PlanningSourceIndex:
    """Bounded provider/dataset/indicator retrieval over the committed lite index."""

    _stopwords = {
        "a",
        "an",
        "and",
        "coming",
        "both",
        "changed",
        "china",
        "data",
        "descriptive",
        "for",
        "forecast",
        "from",
        "in",
        "investigate",
        "is",
        "last",
        "level",
        "make",
        "model",
        "months",
        "next",
        "no",
        "of",
        "only",
        "pandemic",
        "really",
        "split",
        "projection",
        "the",
        "that",
        "to",
        "toward",
        "understand",
        "want",
        "whether",
        "years",
    }
    _expansions = {
        "cpi": ("consumer", "price", "inflation", "hicp"),
        "consumption": ("household", "private", "final", "expenditure", "npish"),
        "debt": ("indebtedness",),
        "expenditure-side": ("expenditure", "consumption", "investment"),
        "gdp": ("gross", "domestic", "product"),
        "growth": ("annual", "change", "rate"),
        "hicp": ("consumer", "price", "inflation", "cpi"),
        "inflation": ("consumer", "price", "cpi", "hicp"),
        "investment": ("capital", "formation", "fixed", "gdi"),
        "share": ("percent", "percentage", "ratio"),
        "shares": ("percent", "percentage", "ratio"),
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            raise PlanningSourceIndexError(f"Planning source index not found: {path}.")
        self.connection = sqlite3.connect(
            f"file:{path}?mode=ro&immutable=1", uri=True, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        metadata = {
            str(item["key"]): str(item["value"])
            for item in self.connection.execute("SELECT key, value FROM metadata")
        }
        if metadata.get("schema_version") != PlanningSourceIndexBuilder.schema_version:
            raise PlanningSourceIndexError("Unsupported planning source index schema.")
        self.catalog_version = metadata["catalog_version"]
        self.content_sha256 = self._file_sha256(path)

    def close(self) -> None:
        self.connection.close()

    def for_planning(
        self,
        research_request: str,
        available_connector_ids: list[str],
        *,
        max_datasets: int = 8,
    ) -> list[dict[str, Any]]:
        if max_datasets < 1 or max_datasets > 50:
            raise ValueError("Planning knowledge result limit must be between 1 and 50.")
        tokens = self._tokens(research_request)
        if not tokens or not available_connector_ids:
            return []
        match_query = " OR ".join(
            f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens
        )
        providers = sorted(set(available_connector_ids))
        placeholders = ",".join("?" for _ in providers)
        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        dataset_rows = self.connection.execute(
            f"""
            SELECT d.*, p.provider_name, p.snapshot_version, p.source_sha256,
                   bm25(dataset_fts) AS fts_rank
            FROM dataset_fts f
            JOIN datasets d ON d.id = f.rowid
            JOIN providers p USING(provider_id)
            WHERE dataset_fts MATCH ? AND d.provider_id IN ({placeholders})
            ORDER BY fts_rank LIMIT 1000
            """,
            (match_query, *providers),
        ).fetchall()
        for row in dataset_rows:
            item = self._candidate(row)
            item["score"] += 20.0 + self._text_score(
                research_request, tokens, f"{row['dataset_id']} {row['title']}"
            )
            if research_request.casefold().strip() in str(row["title"]).casefold():
                item["score"] += 25.0
            candidates[(str(row["provider_id"]), str(row["dataset_id"]))] = item

        indicator_rows = self.connection.execute(
            f"""
            SELECT d.*, p.provider_name, p.snapshot_version, p.source_sha256,
                   links.dimension_id, c.code, c.label,
                   bm25(indicator_fts) AS fts_rank
            FROM indicator_fts f
            JOIN indicator_concepts c ON c.id = f.rowid
            JOIN indicator_set_members members ON members.concept_id = c.id
            JOIN dataset_indicator_sets links ON links.set_id = members.set_id
            JOIN datasets d ON d.id = links.dataset_rowid
            JOIN providers p USING(provider_id)
            WHERE indicator_fts MATCH ? AND d.provider_id IN ({placeholders})
            ORDER BY fts_rank LIMIT 12000
            """,
            (match_query, *providers),
        ).fetchall()
        indicators: dict[
            tuple[str, str],
            dict[tuple[str, str, str], tuple[float, dict[str, str]]],
        ] = defaultdict(dict)
        for row in indicator_rows:
            key = (str(row["provider_id"]), str(row["dataset_id"]))
            item = candidates.setdefault(key, self._candidate(row))
            indicator_score = 30.0 + self._text_score(
                research_request, tokens, f"{row['code']} {row['label']}"
            )
            item["score"] = max(float(item["score"]), indicator_score)
            indicator_key = (
                str(row["dimension_id"]),
                str(row["code"]),
                str(row["label"]),
            )
            indicators[key][indicator_key] = (
                indicator_score,
                {
                    "dimension_id": indicator_key[0],
                    "code": indicator_key[1],
                    "label": indicator_key[2][:240],
                },
            )

        for key, item in candidates.items():
            if bool(item["executable"]):
                item["score"] = float(item["score"]) + 8.0
            ranked_indicators = sorted(
                indicators.get(key, {}).values(),
                key=lambda value: (-value[0], value[1]["dimension_id"], value[1]["code"]),
            )
            selected_indicators: list[dict[str, str]] = []
            selected_keys: set[tuple[str, str]] = set()
            for concept in self._intent_concepts(research_request):
                matches = [
                    value
                    for value in ranked_indicators
                    if self._concept_score(concept, value[1]) > 0
                ]
                if not matches:
                    continue
                best = max(
                    matches,
                    key=lambda value: (
                        self._concept_score(concept, value[1]),
                        value[0],
                        value[1]["code"],
                    ),
                )[1]
                selected_key = (best["dimension_id"], best["code"])
                if selected_key not in selected_keys:
                    selected_indicators.append(best)
                    selected_keys.add(selected_key)
            for _, indicator in ranked_indicators:
                selected_key = (indicator["dimension_id"], indicator["code"])
                if selected_key in selected_keys:
                    continue
                selected_indicators.append(indicator)
                selected_keys.add(selected_key)
                if len(selected_indicators) == 5:
                    break
            item["matched_indicators"] = selected_indicators[:5]
        selected = sorted(
            candidates.values(),
            key=lambda item: (
                -float(item["score"]),
                str(item["connector_id"]),
                str(item["dataset"]),
            ),
        )[:max_datasets]
        return [self._planning_record(item) for item in selected]

    @staticmethod
    def _candidate(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "connector_id": str(row["provider_id"]),
            "provider": str(row["provider_name"]),
            "dataset": str(row["dataset_id"]),
            "title": str(row["title"]),
            "executable": bool(row["executable"]),
            "snapshot_version": str(row["snapshot_version"]),
            "snapshot_sha256": str(row["source_sha256"]),
            "score": 0.0,
            "matched_indicators": [],
        }

    @staticmethod
    def _planning_record(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "connector_id": item["connector_id"],
            "provider": item["provider"],
            "dataset": item["dataset"],
            "title": item["title"],
            "executable": item["executable"],
            "matched_indicators": item["matched_indicators"],
            "source_index_snapshot": {
                "version": item["snapshot_version"],
                "sha256": item["snapshot_sha256"],
            },
            "knowledge_notice": (
                "Discovery metadata only. Only executable=true may enter an executable Plan; "
                "acquisition revalidates current provider metadata."
            ),
        }

    def _tokens(self, query: str) -> list[str]:
        base = [
            normalized
            for token in re.findall(r"[\w.-]+", query.casefold(), flags=re.UNICODE)
            if (normalized := token.strip(".-"))
            if len(normalized) > 1 and normalized not in self._stopwords
        ][:16]
        expanded = list(base)
        for token in base:
            expanded.extend(self._expansions.get(token, ()))
        return list(dict.fromkeys(expanded))[:32]

    @staticmethod
    def _intent_concepts(query: str) -> list[str]:
        normalized = query.casefold()
        concepts: list[str] = []
        if "growth" in normalized and ("gdp" in normalized or "growth model" in normalized):
            concepts.append("gdp_growth")
        share_intent = any(term in normalized for term in ("share", "% of gdp", "decomposition"))
        if "investment" in normalized and share_intent:
            concepts.append("investment_share")
        if "consumption" in normalized and share_intent:
            concepts.append("consumption_share")
        return concepts

    @staticmethod
    def _concept_score(concept: str, indicator: dict[str, str]) -> float:
        code = indicator["code"].upper()
        label = indicator["label"].casefold()
        percent_of_gdp = "% of gdp" in label or "percent of gdp" in label
        if concept == "gdp_growth":
            if not ("gdp growth" in label or (
                "gross domestic product" in label and "percent change" in label
            )):
                return 0.0
            return 100.0 + 20.0 * (code == "NY.GDP.MKTP.KD.ZG")
        if concept == "investment_share":
            if not percent_of_gdp or not any(
                term in label for term in ("capital formation", "investment")
            ):
                return 0.0
            return (
                100.0
                + 20.0 * ("total" in label or ".TOTL." in code)
                - 10.0 * any(term in label for term in ("private", "fixed"))
            )
        if concept == "consumption_share":
            if not percent_of_gdp or "consumption" not in label:
                return 0.0
            return 100.0 + 20.0 * any(term in label for term in ("household", "npish"))
        return 0.0

    @staticmethod
    def _text_score(query: str, tokens: list[str], text: str) -> float:
        normalized = text.casefold()
        score = 5.0 * sum(token in normalized for token in tokens)
        if query.casefold().strip() in normalized:
            score += 30.0
        return score

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


@lru_cache(maxsize=1)
def default_planning_source_index() -> PlanningSourceIndex:
    return PlanningSourceIndex(Path(__file__).with_name("source_index_lite.sqlite3"))
