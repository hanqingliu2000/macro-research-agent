from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from macro_research_agent.agent.contracts import AgentCommandV1, AgentRunV1
from macro_research_agent.agent.data_access import frame_rows, read_snapshot
from macro_research_agent.agent.observability import AgentContextCapture
from macro_research_agent.agent.recovery import recovery_advice
from macro_research_agent.agent.repository import (
    AgentBudgetExceeded,
    AgentConflict,
    AgentError,
    checksum,
)
from macro_research_agent.agent.runtime import AgentRuntime
from macro_research_agent.research_core.numerics import (
    evaluate_typed_model_frame,
    publication_columns,
)

agent_router = APIRouter(prefix="/agent", tags=["agent"])
admin_agent_router = APIRouter(prefix="/admin/agent", tags=["agent diagnostics"])


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: str = Field(min_length=1, max_length=20000)
    defer_clarification: bool = False


def runtime(request: Request) -> AgentRuntime:
    return request.app.state.agent_runtime  # type: ignore[no-any-return]


def wire(run: AgentRunV1, engine: AgentRuntime) -> dict[str, Any]:
    result = run.model_dump(mode="json")
    result["recovery"] = recovery_advice(run)
    phase = run.phase.split(":")[0]
    roles = {
        "clarification": "Planner",
        "route": "Planner",
        "data_assessment": "Data Steward",
        "analysis_assessment": "Analyst",
        "report": "Report Author",
        "report_revision": "Report Author",
        "chart": "Chart Author",
        "author_check": "Author self-check",
        "review": "Report / Visual Reviewer",
        "output_proposal": "Output Editor",
    }
    if phase in roles:
        model = engine.settings.deepseek_model
        if phase == "data_assessment":
            model = engine.settings.data_ai_model or model
        elif phase == "analysis_assessment":
            model = engine.settings.analysis_ai_model or model
        elif phase in {"report", "report_revision"}:
            model = engine.settings.report_author_model or model
        elif phase == "review":
            model = engine.settings.output_review_model or "codex-configured-default"
        result["active_role"] = {
            "label": roles[phase],
            "provider": "codex-local" if phase == "review" else "deepseek-development",
            "model": model,
            "state": run.status,
        }
    candidate = run.output.get("candidate", {})
    if candidate and run.analysis.get("final_snapshot"):
        frame = read_snapshot(
            engine.repo, run.session_id, run.run_id, run.analysis["final_snapshot"]
        )
        result["preview"] = {
            "columns": list(
                dict.fromkeys(
                    [column for column in ("period", "value", "unit") if column in frame.columns]
                    + publication_columns(frame)
                )
            ),
            "rows": frame_rows(frame.head(12)),
            "total_rows": len(frame),
        }
    return result


@agent_router.get("/sessions/{session_id}/runs/{run_id}/data-preview")
def data_preview(
    session_id: str, run_id: str, request: Request, offset: int = 0, limit: int = 12
) -> dict[str, Any]:
    engine = runtime(request)
    try:
        if offset < 0 or not 1 <= limit <= 500:
            raise AgentError("Preview page is outside its bounds.", "invalid_page")
        current = engine.repo.get_run(session_id, run_id)
        snapshot = (
            current.analysis.get("final_snapshot")
            or current.data.get("prepared_snapshot")
            or current.data.get("raw_snapshot")
        )
        if snapshot is None:
            raise AgentError("No acquired data snapshot is available yet.", "not_found")
        frame = read_snapshot(engine.repo, session_id, run_id, snapshot)
        return {
            "columns": list(
                dict.fromkeys(
                    [column for column in ("period", "value", "unit") if column in frame.columns]
                    + publication_columns(frame)
                )
            ),
            "rows": frame_rows(frame.iloc[offset : offset + limit]),
            "offset": offset,
            "total_rows": len(frame),
            "snapshot_ref": snapshot,
        }
    except AgentError as error:
        raise failure(error) from error


def failure(error: Exception) -> HTTPException:
    code = getattr(error, "code", "agent_error")
    return HTTPException(
        status_code=409
        if isinstance(error, AgentConflict)
        else 404
        if code == "not_found" or code == "invalid_identity"
        else 422,
        detail={"code": code, "message": str(error)},
    )


@agent_router.get("/sessions")
def sessions(request: Request) -> dict[str, Any]:
    engine = runtime(request)
    return {
        "sessions": [
            {**session, "run": wire(engine.repo.current_run(session["session_id"]), engine)}
            for session in engine.repo.list_sessions()
        ]
    }


@agent_router.post("/sessions", status_code=201)
def create_session(body: AgentCreateRequest, request: Request) -> dict[str, Any]:
    engine = runtime(request)
    try:
        run = engine.create(body.request, defer_clarification=body.defer_clarification)
        return {"run": wire(run, engine)}
    except AgentError as error:
        raise failure(error) from error


@agent_router.get("/sessions/{session_id}")
def session(session_id: str, request: Request) -> dict[str, Any]:
    engine = runtime(request)
    try:
        return {
            "run": wire(engine.repo.current_run(session_id), engine),
            "runs": [run.model_dump(mode="json") for run in engine.repo.list_runs(session_id)],
        }
    except AgentError as error:
        raise failure(error) from error


@agent_router.get("/sessions/{session_id}/runs/{run_id}")
def run(session_id: str, run_id: str, request: Request) -> dict[str, Any]:
    engine = runtime(request)
    try:
        return {"run": wire(engine.repo.get_run(session_id, run_id), engine)}
    except AgentError as error:
        raise failure(error) from error


@agent_router.post("/sessions/{session_id}/runs/{run_id}/attachments")
async def attach(
    session_id: str, run_id: str, request: Request, file: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    engine = runtime(request)
    try:
        limit = engine.settings.max_upload_mb * 1024 * 1024
        content = await file.read(limit + 1)
        if len(content) > limit:
            raise AgentError("Attachment exceeds the upload limit.", "upload_too_large")
        current = engine.repo.get_run(session_id, run_id)
        updated = engine.upload(current, file.filename or "input.csv", content)
        return {"run": wire(updated, engine)}
    except (AgentError, ValueError) as error:
        raise failure(error) from error


@agent_router.post("/sessions/{session_id}/runs/{run_id}/commands")
def command(session_id: str, run_id: str, body: AgentCommandV1, request: Request) -> dict[str, Any]:
    engine = runtime(request)
    try:
        return {"run": wire(engine.command(session_id, run_id, body), engine)}
    except (AgentError, AgentBudgetExceeded, ValueError) as error:
        raise failure(error) from error


@agent_router.get("/sessions/{session_id}/runs/{run_id}/artifacts/{artifact_id}")
def artifact(session_id: str, run_id: str, artifact_id: str, request: Request) -> Response:
    engine = runtime(request)
    try:
        meta = next(
            (
                blob
                for blob in engine.repo.blobs(session_id, run_id)
                if blob["id"] == artifact_id and blob["kind"] in {"artifact", "render", "manifest"}
            ),
            None,
        )
        if meta is None:
            raise AgentError("This artifact does not belong to the run.", "not_found")
        content = engine.repo.read_blob(session_id, run_id, artifact_id, meta["hash"])
        media = {
            "svg": "image/svg+xml",
            "png": "image/png",
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "report": "text/markdown",
        }.get(str(meta.get("format")), "application/octet-stream")
        return Response(
            content,
            media_type="application/json" if meta["kind"] == "manifest" else media,
            headers={"X-Artifact-Hash": meta["hash"]},
        )
    except AgentError as error:
        raise failure(error) from error


@agent_router.get("/sessions/{session_id}/runs/{run_id}/events")
async def stream(
    session_id: str, run_id: str, request: Request, after: int = 0
) -> StreamingResponse:
    engine = runtime(request)
    try:
        engine.repo.get_run(session_id, run_id)
    except AgentError as error:
        raise failure(error) from error

    async def events() -> AsyncIterator[str]:
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            cursor = max(0, after)
        while not await request.is_disconnected():
            batch = engine.repo.events(session_id, run_id, after=cursor)
            for event in batch:
                cursor = event["sequence"]
                projection = {
                    "sequence": cursor,
                    "event_type": event["event_type"],
                    "occurred_at": event["occurred_at"],
                }
                yield f"id: {cursor}\nevent: progress\ndata: {json.dumps(projection)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/trace")
def trace(
    session_id: str,
    run_id: str,
    request: Request,
    after: int = 0,
    limit: int = 200,
    event_type: str | None = None,
    role: str | None = None,
    task_id: str | None = None,
    attempt_id: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    engine = runtime(request)
    try:
        events = engine.repo.events(
            session_id,
            run_id,
            after=after,
            limit=limit,
            event_type=event_type,
            role=role,
            task_id=task_id,
            attempt_id=attempt_id,
            error_code=error_code,
        )
        return {"events": events, "next_cursor": events[-1]["sequence"] if events else after}
    except AgentError as error:
        raise failure(error) from error


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/attempts/{attempt_id}")
def attempt_details(
    session_id: str, run_id: str, attempt_id: str, request: Request
) -> dict[str, Any]:
    try:
        return runtime(request).repo.attempt(session_id, run_id, attempt_id)
    except AgentError as error:
        raise failure(error) from error


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/diagnostics")
def diagnostics(session_id: str, run_id: str, request: Request) -> dict[str, Any]:
    try:
        return runtime(request).repo.diagnostics(session_id, run_id)
    except AgentError as error:
        raise failure(error) from error


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/payloads/{payload_id}")
def payload(session_id: str, run_id: str, payload_id: str, request: Request) -> Response:
    engine = runtime(request)
    try:
        return Response(
            engine.repo.read_blob(session_id, run_id, payload_id), media_type="application/json"
        )
    except AgentError as error:
        raise failure(error) from error


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/debug-bundle")
def bundle(session_id: str, run_id: str, request: Request) -> Response:
    try:
        return Response(
            runtime(request).repo.debug_bundle(session_id, run_id),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="agent-diagnostics.zip"'},
        )
    except AgentError as error:
        raise failure(error) from error


@admin_agent_router.get("/sessions/{session_id}/runs/{run_id}/replay")
def replay(
    session_id: str, run_id: str, request: Request, verify_numerics: bool = False
) -> dict[str, Any]:
    engine = runtime(request)
    try:
        diagnostics = engine.repo.diagnostics(session_id, run_id)
        capture = AgentContextCapture(engine.repo, session_id, run_id)
        requests = []
        responses = []
        for blob in diagnostics["payloads"]:
            if blob["kind"] == "model_request":
                requests.append(
                    {
                        "ref": blob["id"],
                        "request": capture.reconstruct(
                            json.loads(engine.repo.read_blob(session_id, run_id, blob["id"]))
                        ),
                    }
                )
            if blob["kind"] == "model_response":
                responses.append(
                    {
                        "ref": blob["id"],
                        "response": json.loads(
                            engine.repo.read_blob(session_id, run_id, blob["id"])
                        ),
                    }
                )
        numerical_checks = []
        if verify_numerics:
            current = engine.repo.get_run(session_id, run_id)
            for result in current.analysis.get("results", [])[:32]:
                job = next(
                    (
                        job
                        for job in current.analysis.get("model_jobs", [])
                        if job["id"] == result["jobId"]
                        and job.get("entityCodes") == [result["entity"]]
                    ),
                    None,
                )
                if job is None:
                    numerical_checks.append(
                        {"result_id": result["id"], "status": "missing_specification"}
                    )
                    continue
                if checksum(job) != result["specificationHash"]:
                    raise AgentError(
                        "Numerical replay specification hash changed.", "evidence_corrupt"
                    )
                recomputed, sample, _ = evaluate_typed_model_frame(
                    read_snapshot(engine.repo, session_id, run_id, result["inputSnapshotRef"]), job
                )
                numerical_checks.append(
                    {
                        "result_id": result["id"],
                        "recorded_hash": result["resultHash"],
                        "recomputed_hash": checksum(recomputed),
                        "matches": checksum(recomputed) == result["resultHash"],
                        "sample_matches": sample == result["sample"],
                    }
                )
        return {
            "mode": "offline",
            "external_calls": 0,
            "responses": responses,
            "requests": requests,
            "numerical_checks": numerical_checks,
            "integrity_issues": diagnostics["integrity_issues"],
            "reconstructable_requests": sum(
                blob["kind"] == "model_request" for blob in diagnostics["payloads"]
            ),
        }
    except AgentError as error:
        raise failure(error) from error
