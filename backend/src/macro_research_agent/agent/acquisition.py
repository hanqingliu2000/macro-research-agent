from __future__ import annotations

import io
import json
import time
from typing import Any

import httpx
import pandas as pd  # type: ignore[import-untyped]

from macro_research_agent.agent.contracts import AgentRunV1
from macro_research_agent.agent.data_access import write_snapshot
from macro_research_agent.agent.graph import AgentGraphService, AgentStopped
from macro_research_agent.agent.repository import AgentError, AgentRepository, checksum
from macro_research_agent.connectors.adb import AdbConnector
from macro_research_agent.connectors.base import DataConnector, DataQuery
from macro_research_agent.connectors.bis import BisConnector
from macro_research_agent.connectors.ecb import EcbConnector
from macro_research_agent.connectors.eurostat import EurostatConnector
from macro_research_agent.connectors.imf import ImfDataConnector
from macro_research_agent.connectors.oecd import OecdConnector
from macro_research_agent.connectors.registry import connector_catalog
from macro_research_agent.connectors.un_sdg import UnSdgConnector
from macro_research_agent.connectors.world_bank import WorldBankConnector
from macro_research_agent.research_core.numerics import CANONICAL_KEYS, normalize_frame

CONNECTOR_CLASSES: dict[str, type[DataConnector]] = {
    "imf_data": ImfDataConnector,
    "world_bank": WorldBankConnector,
    "oecd": OecdConnector,
    "eurostat": EurostatConnector,
    "adb": AdbConnector,
    "ecb": EcbConnector,
    "bis": BisConnector,
    "un_sdg": UnSdgConnector,
}


def canonical_indicator(run: AgentRunV1, code: str) -> str:
    if run.task_plan and any(
        source.connector_id == "imf_data" and source.dataset == "CPI" and code in source.indicators
        for source in run.task_plan.plan.data_sources
    ):
        return code if code.startswith("CPI.") else f"CPI.{code}.IX"
    return code


def local_frame(filename: str, content: bytes) -> pd.DataFrame:
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "csv":
        return pd.read_csv(io.BytesIO(content))
    if extension == "json":
        parsed = json.loads(content)
        return pd.DataFrame(parsed if isinstance(parsed, list) else parsed.get("data", parsed))
    if extension == "xlsx":
        return pd.read_excel(io.BytesIO(content))
    raise AgentError("Only CSV, JSON and XLSX are supported.", "unsupported_attachment")


def connector_query(run: AgentRunV1, source: Any) -> DataQuery:
    route = run.task_plan
    if route is None:
        raise AgentError("A validated task route is required.", "route_missing")
    period = route.source_periods.get(f"{source.connector_id}.{source.dataset}", route.plan.period)
    end = period.end
    if end == "latest":
        date = run.created_at[:10]
        end = (
            date[:4]
            if period.frequency == "annual"
            else date[:7]
            if period.frequency == "monthly"
            else date[:4] + "-Q" + str((int(date[5:7]) - 1) // 3 + 1)
        )
    codes = sorted({code for geo in route.plan.geography_resolutions for code in geo.member_codes})
    indicator = (
        "coicop" if source.connector_id == "imf_data" and source.dataset == "CPI" else "indicator"
    )
    return DataQuery(
        dataset=source.dataset,
        dimensions={
            "country": codes,
            indicator: [
                code[4:-3]
                if indicator == "coicop" and code.startswith("CPI.") and code.endswith(".IX")
                else code
                for code in source.indicators
            ],
        },
        frequency={"annual": "A", "quarterly": "Q", "monthly": "M"}[period.frequency],
        start_period=period.start,
        end_period=end,
    )


async def acquire_public(
    repository: AgentRepository, run: AgentRunV1, connector_id: str, query: DataQuery
) -> dict[str, Any]:
    if connector_id not in CONNECTOR_CLASSES:
        raise AgentError("Unregistered public connector.", "connector_unavailable")
    allowed_hosts = connector_catalog()[connector_id].provider_hosts
    graph = AgentGraphService(repository)
    counts: dict[str, int] = {}
    reservations: dict[int, str] = {}

    async def before(request: httpx.Request) -> None:
        graph.ensure_current(run.session_id, run.run_id)
        if request.method != "GET" or request.url.host not in allowed_hosts:
            raise AgentError("Connector left its provider allowlist.", "connector_policy")
        fingerprint = checksum({"url": str(request.url), "method": request.method})

        def count_call(current: AgentRunV1) -> dict[str, Any]:
            active = next(node for node in reversed(current.nodes) if node.status == "running")
            key = "connector:" + fingerprint
            consumed = active.physical_calls.get(key, 0)
            if consumed >= 3:
                raise AgentStopped(
                    "Physical connector request attempts exhausted.", "task_attempt_limit"
                )
            active.physical_calls[key] = consumed + 1
            counts[fingerprint] = consumed + 1
            return {
                "connector": connector_id,
                "request_fingerprint": fingerprint,
                "physical_attempt": consumed + 1,
            }

        repository.mutate(run.session_id, run.run_id, "connector.attempt_reserved", count_call)
        reservation = repository.reserve(run.session_id, run.run_id, {"connector_requests": 1})
        reservations[id(request)] = reservation
        request.extensions["agent_started"] = time.perf_counter()
        repository.event(
            run.session_id,
            run.run_id,
            "connector.request_started",
            {
                "connector": connector_id,
                "query_hash": checksum(query.model_dump()),
                "url": str(request.url),
                "physical_attempt": counts[fingerprint],
                "span_id": reservation,
            },
        )

    async def after(response: httpx.Response) -> None:
        reservation = reservations.pop(id(response.request))
        repository.settle(run.session_id, run.run_id, reservation, {"connector_requests": 1})
        repository.event(
            run.session_id,
            run.run_id,
            "connector.request_completed" if response.is_success else "connector.request_failed",
            {
                "connector": connector_id,
                "http_status": response.status_code,
                "retry_after": response.headers.get("retry-after"),
                "latency_ms": (time.perf_counter() - response.request.extensions["agent_started"])
                * 1000,
                "span_id": reservation,
            },
        )

    root = repository.root / "sessions" / run.session_id / run.run_id
    async with httpx.AsyncClient(event_hooks={"request": [before], "response": [after]}) as client:
        connector = CONNECTOR_CLASSES[connector_id](
            root / "raw" / connector_id,
            client=client,
            shared_cache_dir=repository.root / "connector_cache" / connector_id,
        )  # type: ignore[call-arg]
        try:
            result = await connector.fetch(query)
        finally:
            for reservation in reservations.values():
                repository.settle(
                    run.session_id, run.run_id, reservation, {"connector_requests": 1}
                )
            repository.event(
                run.session_id,
                run.run_id,
                "connector.attempts_recorded",
                {
                    "connector": connector_id,
                    "query": query.model_dump(),
                    "attempts": getattr(connector, "attempts", []),
                    "requested_period_end": query.end_period,
                },
            )
    rows = []
    for observation in result.dataset.observations:
        row = observation.model_dump(exclude={"attributes"})
        row["frequency"] = {"A": "annual", "Q": "quarterly", "M": "monthly"}.get(
            str(row["frequency"]), row["frequency"]
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise AgentError(
            "Connector returned no observations for the requested scope.", "coverage_missing"
        )
    if frame.duplicated(CANONICAL_KEYS).any():
        raise AgentError("Source contains ambiguous analytical keys.", "duplicate_keys")
    provenance = result.provenance.model_dump(mode="json")
    status_count = sum(item.status is not None for item in result.dataset.observations)
    attributes = [
        {
            "series_id": item.series_id,
            "period": item.period,
            "attributes": {
                key: {k: v for k, v in value.items() if k not in {"OBS_VALUE", "value"}}
                if isinstance(value, dict)
                else value
                for key, value in item.attributes.items()
            },
        }
        for item in result.dataset.observations
    ]
    metadata_ref = repository.payload(
        run.session_id,
        run.run_id,
        {
            "dataset_metadata": result.dataset.metadata,
            "attributes": attributes,
            "provenance": provenance,
        },
        "source_metadata",
    )

    def release_fields(value: Any) -> dict[str, str]:
        found: dict[str, str] = {}
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    str(key).casefold()
                    in {"vintage", "release", "release_id", "edition", "weo_vintage"}
                    and item is not None
                ):
                    found[str(key)] = str(item)
                found.update(release_fields(item))
        elif isinstance(value, list):
            for item in value:
                found.update(release_fields(item))
        return found

    releases = release_fields({"metadata": result.dataset.metadata, "attributes": attributes})
    metadata_receipt = {
        "source_snapshot_pending": True,
        "metadata_ref": metadata_ref["id"],
        "metadata_hash": metadata_ref["hash"],
        "observation_count": len(rows),
        "status_reported_count": status_count,
        "status_disclosure": "not reported by the acquired response"
        if status_count == 0
        else "partially reported"
        if status_count != len(rows)
        else "reported",
        "vintage_disclosure": (
            "reported in source-bound metadata"
            if releases
            else "not reported by this acquired response; retrieval time is not an economic vintage"
        ),
        "release_fields": releases,
        "retrieved_at": provenance["retrieved_at"],
        "source_identifier": provenance["source_identifier"],
        "raw_sha256": provenance["raw_sha256"],
    }
    ref = write_snapshot(repository, run.session_id, run.run_id, frame, provenance=provenance)
    metadata_receipt.pop("source_snapshot_pending")
    metadata_receipt["snapshot_ref"] = ref["id"]
    metadata_receipt["snapshot_hash"] = ref["hash"]
    return {
        "snapshot": ref,
        "provenance": provenance,
        "metadata_receipt": metadata_receipt,
        "warnings": result.warnings,
    }


def normalize_local(
    repository: AgentRepository, run: AgentRunV1, attachment: dict[str, Any]
) -> dict[str, Any]:
    raw = repository.read_blob(run.session_id, run.run_id, attachment["id"], attachment["hash"])
    frame = normalize_frame(local_frame(attachment["name"], raw))
    if frame.duplicated(CANONICAL_KEYS).any():
        identical = frame.duplicated().sum()
        frame = frame.drop_duplicates()
        if frame.duplicated(CANONICAL_KEYS).any():
            raise AgentError("Local duplicate keys have conflicting values.", "duplicate_keys")
        repository.event(
            run.session_id, run.run_id, "data.exact_duplicates_removed", {"count": int(identical)}
        )
    ref = write_snapshot(
        repository,
        run.session_id,
        run.run_id,
        frame,
        classification="user_supplied",
        provenance={"upload": attachment["id"]},
    )
    return {
        "snapshot": ref,
        "provenance": {"upload": attachment["id"], "hash": attachment["hash"]},
        "warnings": [],
    }
