import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from macro_research_agent.agent.contracts import AgentTaskPlanV1
from macro_research_agent.agent.providers import AgentAssessment
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.research_core.authoring import (
    DeterministicArtifactAuthor,
    DeterministicOutputReviewer,
    DeterministicReportAuthor,
)
from macro_research_agent.research_core.planning import ClarificationBatch


def inject_delivery_fixtures(engine):
    engine.delivery_ports = {
        "artifact_author": DeterministicArtifactAuthor(),
        "report_author": DeterministicReportAuthor(),
        "reviewer": DeterministicOutputReviewer(),
    }


class FixtureAgentProvider:
    def clarify(self, run: Any, attachments: Any) -> ClarificationBatch:
        return ClarificationBatch.model_validate(
            {
                "questions": [
                    {"question_id": "scope", "prompt": "Which scope?", "options": ["USA", "Other"]}
                ]
            }
        )

    def route(self, run: Any) -> AgentTaskPlanV1:
        return AgentTaskPlanV1.model_validate(
            {
                "plan": {
                    "objective": "Summarize CPI",
                    "geography_intent": "USA",
                    "period": {"start": "2010", "end": "2030", "frequency": "annual"},
                    "geography_resolutions": [],
                    "data_sources": [
                        {
                            "connector_id": "local_file",
                            "dataset": "uploaded",
                            "indicators": ["CPI"],
                            "query_intent": "Use input",
                        }
                    ],
                    "model_intents": [
                        {
                            "capability_id": "descriptive",
                            "purpose": "Summarize",
                            "variables": [
                                {"indicator_code": "CPI", "role": "descriptive", "order": 1}
                            ],
                        }
                    ],
                    "deliverables": {
                        "charts": True,
                        "tables": True,
                        "clean_data": True,
                        "python": True,
                        "stata": False,
                        "research_report": True,
                    },
                },
                "analyses": [
                    {
                        "task_id": "summary",
                        "model": "descriptive",
                        "variables": ["CPI"],
                        "purpose": "Describe observed annual CPI",
                    }
                ],
                "rationale": "Fixture route",
            }
        )

    def call(self, *args: Any, **kwargs: Any) -> AgentAssessment:
        return AgentAssessment(status="pass", summary="Values are usable", cleaning="none")


@pytest.mark.asyncio
async def test_real_agent_http_commands_freeze_reload_diagnostics_and_mode_isolation(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.provider = FixtureAgentProvider()
    inject_delivery_fixtures(engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/agent/sessions", json={"request": "Summarize CPI", "defer_clarification": True}
        )
        assert created.status_code == 201, created.text
        run = created.json()["run"]
        session_id, run_id = run["session_id"], run["run_id"]
        root = f"/api/v1/agent/sessions/{session_id}/runs/{run_id}"
        content = "country,period,indicator,value,unit\n" + "".join(
            f"USA,{year},CPI,{100 + year - 2010},Index\n" for year in range(2010, 2031)
        )
        uploaded = await client.post(
            root + "/attachments", files={"file": ("data.csv", content.encode())}
        )
        assert uploaded.status_code == 200, uploaded.text

        async def command(kind: str, arguments: dict[str, Any] | None = None):
            current = (await client.get(root)).json()["run"]
            return await client.post(
                root + "/commands",
                json={
                    "command_id": kind,
                    "idempotency_key": kind,
                    "expected_version": current["version"],
                    "type": kind,
                    "arguments": arguments or {},
                },
            )

        assert (await command("start")).status_code == 200
        engine.execute(session_id, run_id)
        current = (await client.get(root)).json()["run"]
        assert current["status"] == "clarifying", current.get("error")
        response = await command("answer_clarification", {"answers": {"scope": "USA"}})
        assert response.status_code == 200, response.text
        engine.execute(session_id, run_id)
        current = (await client.get(root)).json()["run"]
        assert current["status"] == "awaiting_final_confirmation", json.dumps(
            (current["output"].get("candidate", {}).get("review") or {}).get("findings"), indent=2
        )
        assert current["ledger"]["used"]["formal_reviews"] == 1
        assert current["ledger"]["used"]["model_fits"] == 1
        assert current["output"]["candidate"]["review"]["semantic_report_status"] == "pass"
        preview = (await client.get(root + "/data-preview?offset=12&limit=12")).json()
        assert preview["columns"][:3] == ["period", "value", "unit"]
        assert preview["offset"] == 12 and len(preview["rows"]) == 9
        assert (await client.get(root + "/data-preview?offset=-1")).status_code == 422
        finished = await command("finalize", {"accept_warnings": True})
        assert finished.status_code == 200, finished.text
        assert finished.json()["run"]["status"] == "completed"
        manifest = finished.json()["run"]["output"]["manifest"]
        downloaded = await client.get(root + f"/artifacts/{manifest['id']}")
        assert downloaded.status_code == 200 and downloaded.json()["finalized_by"] == "user"
        assert (await client.get(f"/api/v1/workflow/sessions/{session_id}")).status_code == 404
        linked_request = {
            "command_id": "linked",
            "idempotency_key": "linked",
            "expected_version": finished.json()["run"]["version"],
            "type": "new_run",
            "arguments": {"request": "Explain another CPI comparison"},
        }
        linked = await client.post(root + "/commands", json=linked_request)
        replayed = await client.post(root + "/commands", json=linked_request)
        assert linked.status_code == 200 and replayed.status_code == 200
        assert linked.json()["run"]["run_id"] == replayed.json()["run"]["run_id"]
        diagnostics = await client.get(
            f"/api/v1/admin/agent/sessions/{session_id}/runs/{run_id}/diagnostics"
        )
        assert diagnostics.status_code == 200 and not diagnostics.json()["integrity_issues"]
        assert diagnostics.json()["events"]
        replay = await client.get(
            f"/api/v1/admin/agent/sessions/{session_id}/runs/{run_id}/replay?verify_numerics=true"
        )
        assert replay.status_code == 200 and replay.json()["external_calls"] == 0
        assert all(item["matches"] for item in replay.json()["numerical_checks"])
        recreated = create_app(
            Settings(environment="test", llm_provider="test", runtime_dir=tmp_path)
        )
        assert recreated.state.agent_runtime.repo.get_run(session_id, run_id).status == "completed"
        recreated.state.agent_runtime.close()
    engine.close()
