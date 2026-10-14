import json
from pathlib import Path

import httpx
from macro_research_agent.agent.contracts import AgentRunEnvelopeV1
from macro_research_agent.agent.graph import AgentGraphService
from macro_research_agent.agent.observability import AgentAuditedHttpClient, AgentContextCapture
from macro_research_agent.agent.repository import AgentRepository


def test_complete_calls_repairs_unknown_usage_and_offline_context_reconstruction(
    tmp_path: Path,
) -> None:
    repo = AgentRepository(tmp_path)
    run = repo.create("Inspect data")

    def authorize(current):
        current.authorizations.append(
            AgentRunEnvelopeV1(
                request=run.request,
                answers={},
                allowed_connectors=[],
                allowed_models=["descriptive"],
                allowed_transforms=[],
            )
        )
        current.status = "queued"

    repo.mutate(run.session_id, run.run_id, "authorization", authorize)
    AgentGraphService(repo).claim(run.session_id, run.run_id, "route", [])

    def response(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "bad json sk-examplekey12345",
                            "reasoning_content": "private thought",
                        }
                    }
                ]
            },
        )

    client = AgentAuditedHttpClient(
        repo, run.session_id, run.run_id, "planner", transport=httpx.MockTransport(response)
    )
    body = {
        "model": "test",
        "max_tokens": 50,
        "messages": [
            {"role": "user", "content": json.dumps({"rows": [{"value": 1}], "request": "inspect"})}
        ],
    }
    client.post("https://test/chat", json=body)
    events = repo.events(run.session_id)
    assert "private thought" not in json.dumps(events)
    assert not any("rows" in event["payload"] for event in events)
    response_ref = next(
        blob for blob in repo.blobs(run.session_id, run.run_id) if blob["kind"] == "model_response"
    )
    stored = repo.read_blob(run.session_id, run.run_id, response_ref["id"]).decode()
    assert "bad json" in stored and "private thought" not in stored and "examplekey" not in stored
    request_ref = next(
        blob for blob in repo.blobs(run.session_id, run.run_id) if blob["kind"] == "model_request"
    )
    payload = json.loads(repo.read_blob(run.session_id, run.run_id, request_ref["id"]))
    restored = AgentContextCapture(repo, run.session_id, run.run_id).reconstruct(payload)
    assert json.loads(restored["messages"][0]["content"])["rows"] == [{"value": 1}]
    ledger = repo.get_run(run.session_id, run.run_id).ledger
    assert ledger.used["model_calls"] == 1 and ledger.reservations
    client.close()
