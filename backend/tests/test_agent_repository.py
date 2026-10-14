import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from macro_research_agent.agent.contracts import AgentRunEnvelopeV1
from macro_research_agent.agent.graph import AgentGraphService, AgentStopped
from macro_research_agent.agent.repository import (
    AgentBudgetExceeded,
    AgentConflict,
    AgentError,
    AgentRepository,
)


def test_transactional_budget_idempotency_and_redacted_trace(tmp_path: Path) -> None:
    repo = AgentRepository(tmp_path)
    run = repo.create("Research")
    key = repo.reserve(run.session_id, run.run_id, {"model_calls": 1, "tokens": 100})
    repo.settle(run.session_id, run.run_id, key, {"model_calls": 1}, unknown=["tokens"])
    latest = repo.get_run(run.session_id, run.run_id)
    assert latest.ledger.used["model_calls"] == 1
    assert latest.ledger.reservations[key] == {"tokens": 100}

    def answer(current):
        current.status = "queued"
        return {"message": "Bearer secret123", "command_id": "answer"}

    first = repo.mutate(
        run.session_id,
        run.run_id,
        "answered",
        answer,
        key="same",
        command_hash="hash",
        expected_version=latest.version,
    )
    replay = repo.mutate(
        run.session_id,
        run.run_id,
        "answered",
        answer,
        key="same",
        command_hash="hash",
        expected_version=1,
    )
    assert first == replay
    assert "secret123" not in json.dumps(repo.events(run.session_id))
    with pytest.raises(AgentConflict):
        repo.mutate(
            run.session_id, run.run_id, "answered", answer, key="same", command_hash="other"
        )
    with pytest.raises(AgentBudgetExceeded):
        repo.reserve(run.session_id, run.run_id, {"model_calls": 41})


def test_graph_lease_freeze_restart_and_cross_mode_isolation(tmp_path: Path) -> None:
    repo = AgentRepository(tmp_path)
    run = repo.create("Research")

    def authorize(current):
        current.authorizations.append(
            AgentRunEnvelopeV1(
                request="Research",
                answers={},
                allowed_connectors=[],
                allowed_models=["descriptive"],
                allowed_transforms=[],
            )
        )
        current.status = "queued"

    repo.mutate(run.session_id, run.run_id, "authorized", authorize)
    graph = AgentGraphService(repo)
    node, reused = graph.claim(run.session_id, run.run_id, "acquisition", ["request"])
    assert not reused
    with pytest.raises(AgentStopped, match="lease"):
        graph.claim(run.session_id, run.run_id, "acquisition", ["request"])
    graph.finish(run.session_id, run.run_id, node, ["snapshot"])
    _, reused = graph.claim(run.session_id, run.run_id, "acquisition", ["request"])
    assert reused
    with pytest.raises(AgentError, match="immutable"):
        repo.mutate(
            run.session_id, run.run_id, "bad", lambda r: r.nodes[0].output_refs.append("wrong")
        )
    second, _ = graph.claim(run.session_id, run.run_id, "analysis", ["snapshot"])
    AgentRepository(tmp_path).recover()
    assert repo.get_run(run.session_id, run.run_id).status == "paused"
    assert not graph.finish(run.session_id, run.run_id, second, ["late"])
    with pytest.raises(AgentError):
        repo.current_run("workflow-session-123")


def test_payload_integrity_jsonl_recovery_and_concurrent_reservations(tmp_path: Path) -> None:
    repo = AgentRepository(tmp_path)
    run = repo.create("Research")
    blob = repo.payload(run.session_id, run.run_id, {"output": "invalid json", "api_key": "secret"})
    assert "secret" not in repo.read_blob(run.session_id, run.run_id, blob["id"]).decode()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: repo.reserve(run.session_id, run.run_id, {"model_calls": 1}), range(8)
            )
        )
    assert len(repo.get_run(run.session_id, run.run_id).ledger.reservations) == 8
    trace = tmp_path / "sessions" / run.session_id / "trace.jsonl"
    trace.write_text("torn")
    repo.recover()
    assert len(trace.read_text().splitlines()) == len(repo.events(run.session_id))
    assert not repo.diagnostics(run.session_id, run.run_id)["integrity_issues"]
