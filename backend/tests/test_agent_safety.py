import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from macro_research_agent.agent.contracts import AgentRunEnvelopeV1
from macro_research_agent.agent.graph import AgentGraphService, AgentStopped
from macro_research_agent.agent.observability import AgentAuditedHttpClient, AgentContextCapture
from macro_research_agent.agent.repository import AgentError, AgentRepository


def authorized(tmp_path: Path):
    repo = AgentRepository(tmp_path)
    run = repo.create("Bounded research")

    def apply(current):
        current.authorizations.append(
            AgentRunEnvelopeV1(
                request=current.request,
                answers={},
                allowed_connectors=[],
                allowed_models=["descriptive"],
                allowed_transforms=[],
            )
        )
        current.status = "queued"

    repo.mutate(run.session_id, run.run_id, "authorization", apply)
    return repo, run, AgentGraphService(repo)


def test_task_attempt_details_pause_cancel_lease_and_concurrency(tmp_path: Path):
    repo, run, graph = authorized(tmp_path)
    node, _ = graph.claim(run.session_id, run.run_id, "analysis", ["input"])
    other, _ = graph.claim(run.session_id, run.run_id, "other", ["input"])
    with pytest.raises(AgentStopped, match="concurrency"):
        graph.claim(run.session_id, run.run_id, "third", [])
    repo.mutate(
        run.session_id,
        run.run_id,
        "pause",
        lambda current: setattr(current, "pause_requested", True),
    )
    assert graph.finish(run.session_id, run.run_id, node, ["accepted"])
    assert repo.get_run(run.session_id, run.run_id).status == "paused"
    detail = repo.attempt(run.session_id, run.run_id, node.active_attempt_id)
    assert detail["attempt"]["status"] == "completed"
    assert {event["event_type"] for event in detail["events"]} >= {"task.started", "task.completed"}

    def cancel(current):
        current.status = "cancelled"
        current.epoch += 1

    repo.mutate(run.session_id, run.run_id, "cancel", cancel)
    assert not graph.finish(run.session_id, run.run_id, other, ["late"])
    assert (
        repo.attempt(run.session_id, run.run_id, other.active_attempt_id)["attempt"]["status"]
        == "late_result"
    )


def test_expired_lease_cannot_accept_result(tmp_path: Path):
    repo, run, graph = authorized(tmp_path)
    node, _ = graph.claim(run.session_id, run.run_id, "fit", [])
    repo.mutate(
        run.session_id,
        run.run_id,
        "lease_expired",
        lambda current: setattr(
            current.nodes[0],
            "lease_until",
            (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        ),
    )
    assert not graph.finish(run.session_id, run.run_id, node, ["untrusted-late-result"])
    assert repo.get_run(run.session_id, run.run_id).nodes[0].status == "failed"


def test_produced_snapshot_dependency_invalidation_preserves_unaffected_sibling(tmp_path: Path):
    repo, run, graph = authorized(tmp_path)
    first, _ = graph.claim(run.session_id, run.run_id, "acquire-a", [])
    graph.finish(run.session_id, run.run_id, first, ["result-a"], produced_refs=["snapshot-a"])
    sibling, _ = graph.claim(run.session_id, run.run_id, "acquire-b", [])
    graph.finish(run.session_id, run.run_id, sibling, ["result-b"], produced_refs=["snapshot-b"])
    dependent, _ = graph.claim(run.session_id, run.run_id, "fit-a", ["snapshot-a"])
    assert dependent.depends_on == [first.node_id]
    graph.finish(run.session_id, run.run_id, dependent, ["fit-result"])
    repo.mutate(
        run.session_id,
        run.run_id,
        "invalidate-a",
        lambda current: {"affected": graph.invalidate_descendants(current, {first.node_id})},
    )
    nodes = {node.node_id: node for node in repo.get_run(run.session_id, run.run_id).nodes}
    assert nodes[first.node_id].status == nodes[dependent.node_id].status == "stale"
    assert nodes[sibling.node_id].status == "completed"


def test_transport_retries_and_repairs_share_persisted_physical_budget(tmp_path: Path):
    repo, run, graph = authorized(tmp_path)
    graph.claim(run.session_id, run.run_id, "route", [])
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "busy"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "malformed"}}], "usage": {"total_tokens": 2}},
        )

    for _ in range(2):
        client = AgentAuditedHttpClient(
            repo, run.session_id, run.run_id, "planner", transport=httpx.MockTransport(respond)
        )
        if not calls:
            client.post("https://test/chat", json={"model": "fixture", "max_tokens": 20})
        else:
            with pytest.raises(AgentStopped, match="physical-call"):
                client.post("https://test/chat", json={"model": "fixture"})
        client.close()
    assert len(calls) == 3
    assert repo.get_run(run.session_id, run.run_id).ledger.used["model_calls"] == 3
    assert len(repo.events(run.session_id, event_type="ai.request_started")) == 3


def test_audit_failure_stops_before_external_call_and_exact_context_replay(
    tmp_path: Path, monkeypatch: Any
):
    repo, run, graph = authorized(tmp_path)
    graph.claim(run.session_id, run.run_id, "route", [])
    calls = []
    original = repo.mutate

    def fail_before_call(session, run_id, event, change, **kwargs):
        if event == "ai.request_started":
            raise OSError("audit write unavailable")
        return original(session, run_id, event, change, **kwargs)

    monkeypatch.setattr(repo, "mutate", fail_before_call)
    with (
        AgentAuditedHttpClient(
            repo,
            run.session_id,
            run.run_id,
            "planner",
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        ) as client,
        pytest.raises(OSError, match="audit"),
    ):
        client.post("https://test/chat", json={"model": "fixture"})
    assert calls == []
    capture = AgentContextCapture(repo, run.session_id, run.run_id)
    for ascii_mode in (True, False):
        text = (
            json.dumps({"question": "中国", "rows": [{"value": 5}]}, ensure_ascii=ascii_mode)
            + "\nRepair this field."
        )
        assert capture.reconstruct(capture.capture(text)) == text


def test_codex_remote_review_obeys_the_same_public_disclosure_grant(tmp_path: Path):
    import pandas as pd
    from macro_research_agent.agent.data_access import AgentModelDataAccess, write_snapshot
    from macro_research_agent.research_core.data_access import ResearchStage

    repo, run, _ = authorized(tmp_path)
    snapshot = write_snapshot(repo, run.session_id, run.run_id, pd.DataFrame({"value": [1]}))
    context = AgentModelDataAccess(repo, run.session_id, run.run_id).context(
        snapshot["id"],
        ResearchStage.OUTPUT,
        provider="codex-local",
        model="configured-default",
        remote=True,
    )
    assert context.grant.provider_profile == "codex-local" and context.grant.mode == "agent"


def test_frozen_results_and_broken_payload_reference_fail_closed(tmp_path: Path):
    repo, run, _ = authorized(tmp_path)
    repo.mutate(
        run.session_id,
        run.run_id,
        "complete_fixture",
        lambda current: setattr(current, "status", "completed"),
    )
    with pytest.raises(AgentError, match="Frozen"):
        repo.mutate(
            run.session_id,
            run.run_id,
            "tamper",
            lambda current: current.output.update({"fake": True}),
        )
    repo.event(run.session_id, run.run_id, "audit", {"ref": "agent-blob-absent"})
    # Broken references in scientific state are reported, not silently accepted as success.
    other = repo.create("Incomplete evidence")
    repo.mutate(
        other.session_id,
        other.run_id,
        "broken",
        lambda current: current.analysis.update({"ref": "agent-blob-absent"}),
    )
    assert (
        repo.diagnostics(other.session_id, other.run_id)["integrity_issues"][0]["code"]
        == "broken_reference"
    )
