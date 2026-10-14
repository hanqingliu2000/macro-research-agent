from pathlib import Path
from typing import Any

import pytest
from macro_research_agent.agent.contracts import AgentCommandV1
from macro_research_agent.agent.delivery import AgentDelivery
from macro_research_agent.agent.providers import AgentOutputCorrection, response_schema
from macro_research_agent.agent.repository import AgentError
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.research_core.authoring import DeterministicReportAuthor
from test_agent_runtime import FixtureAgentProvider, inject_delivery_fixtures


def test_output_schema_exposes_only_current_editable_ids_and_fixed_source_note():
    wire = response_schema(
        AgentOutputCorrection,
        {
            "editable_chart_table_ids": ["chart", "table"],
            "sourceNoteVerbatim": "Source: IMF, World Bank",
            "reportDrafts": {"report": {}},
        },
    )
    patch = wire["$defs"]["ArtifactPatch"]["properties"]
    assert patch["artifact_id"]["enum"] == ["chart", "table"]
    assert patch["changes"]["additionalProperties"] is False
    assert patch["changes"]["properties"]["source_note"]["const"] == "Source: IMF, World Bank"
    assert patch["changes"]["properties"]["alt_text"]["maxLength"] == 500
    assert wire["$defs"]["ReportRevisionDirectiveV1"]["properties"]["artifactId"]["enum"] == [
        "report"
    ]


def test_reproduction_evidence_is_owned_hash_verified_read_only_and_unfrozen(tmp_path):
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    run = engine.create("Reproduction evidence", defer_clarification=True)
    delivery = AgentDelivery(engine.repo, engine.settings, None, run.session_id, run.run_id)
    artifact = delivery.artifact(
        "reproduce.py", "code", "python", b"# controlled recipe\n", "Template"
    )
    evidence = delivery.reproduction_evidence(run, [artifact])
    assert evidence["scripts"] == [
        {
            "id": artifact["id"],
            "hash": artifact["hash"],
            "name": "reproduce.py",
            "content": "# controlled recipe\n",
        }
    ]
    assert evidence["inspectionOnly"] is True
    assert "not_frozen" in evidence["manifestState"]
    with pytest.raises(AgentError, match="checksum"):
        delivery.reproduction_evidence(run, [{**artifact, "hash": "sha256:wrong"}])
    other = engine.create("Other run", defer_clarification=True)
    foreign = AgentDelivery(engine.repo, engine.settings, None, other.session_id, other.run_id)
    with pytest.raises(AgentError, match="not found"):
        foreign.reproduction_evidence(other, [artifact])
    large = delivery.artifact("large.py", "code", "python", b"x" * 40001, "Large template")
    with pytest.raises(AgentError, match="context budget"):
        delivery.reproduction_evidence(run, [large])
    assert engine.repo.get_run(run.session_id, run.run_id).ledger.used.get("model_calls", 0) == 0
    engine.close()


def test_no_progress_at_delivery_ceiling_rejects_intervention_without_reset(tmp_path):
    from macro_research_agent.agent.contracts import AgentInterventionV1

    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    run = engine.create("Exhausted delivery", defer_clarification=True)

    def stop(current):
        current.status = "waiting_for_user"
        current.error = {"code": "no_progress", "message": "Title unchanged"}
        current.ledger.used["output_candidates"] = 3
        current.intervention = AgentInterventionV1(reason="no_progress", message="Stopped")

    run = engine.repo.mutate(run.session_id, run.run_id, "test.stop", stop)
    with pytest.raises(AgentError) as caught:
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="answer",
                idempotency_key="answer",
                expected_version=run.version,
                type="resolve_intervention",
                arguments={"answer": "Try again", "allow_scope_change": True},
            ),
        )
    assert caught.value.code == "delivery_round_limit"
    retained = engine.repo.get_run(run.session_id, run.run_id)
    assert retained.ledger.used["output_candidates"] == 3
    assert retained.answers == run.answers
    engine.close()


def test_joint_chart_report_revision_rebinds_directive_and_report_to_same_version(
    tmp_path, monkeypatch
):
    class BoundReportAuthor(DeterministicReportAuthor):
        def author(self, request, access):
            draft = super().author(request, access)
            chart_id = next(a["id"] for a in request.artifacts if a["format"] == "svg")
            section = next(s for s in draft.sections if s.heading == "Diagnostics and limitations")
            section.evidence_refs.append(chart_id)
            return draft

    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.provider = FixtureAgentProvider()
    inject_delivery_fixtures(engine)
    engine.delivery_ports["report_author"] = BoundReportAuthor()
    original = AgentDelivery.review
    old_ids = []

    def directing(self, run, candidate, snapshot, results, iteration):
        result = original(self, run, candidate, snapshot, results, iteration)
        if iteration == 1:
            chart_id = next(a["id"] for a in candidate["artifacts"] if a["format"] == "svg")
            old_ids.append(chart_id)
            report_id = next(a["id"] for a in candidate["artifacts"] if a["format"] == "report")
            section = next(
                s
                for s in candidate["drafts"][report_id]["sections"]
                if s["heading"] == "Diagnostics and limitations"
            )
            result.update(status="fail", semantic_report_status="fail")
            result["findings"] = [
                {
                    "rule_id": "JOINT-WORDING",
                    "severity": "fail",
                    "message": "Clarify chart wording in figure and narrative",
                    "blocking": True,
                }
            ]
            result["patches"] = [
                {
                    "patch_id": "chart-title",
                    "artifact_id": chart_id,
                    "rationale": "Clarify title",
                    "changes": {"title": "Annual CPI"},
                }
            ]
            result["report_directives"] = [
                {
                    "directiveId": "joint",
                    "artifactId": report_id,
                    "targetSectionIds": [section["sectionId"]],
                    "issue": "Clarify chart wording",
                    "preserveEvidenceRefs": section["evidenceRefs"],
                    "acceptanceCriteria": ["Explain the revised figure"],
                }
            ]
        return result

    monkeypatch.setattr(AgentDelivery, "review", directing)
    run = engine.create("Summarize CPI", defer_clarification=True)
    content = "country,period,indicator,value,unit\n" + "".join(
        f"USA,{year},CPI,{100 + year - 2010},Index\n" for year in range(2010, 2031)
    )
    run = engine.upload(run, "input.csv", content.encode())
    for kind, args in [("start", {}), ("answer_clarification", {"answers": {"scope": "USA"}})]:
        run = engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id=kind,
                idempotency_key=kind,
                expected_version=run.version,
                type=kind,
                arguments=args,
            ),
        )
        engine.execute(run.session_id, run.run_id)
        run = engine.repo.get_run(run.session_id, run.run_id)
    assert run.status == "awaiting_final_confirmation", run.error
    assert run.ledger.used["output_candidates"] == run.ledger.used["formal_reviews"] == 2
    current = run.output["candidate"]
    chart = next(a for a in current["artifacts"] if a["format"] == "svg")
    assert chart["id"] != old_ids[0]
    section = next(
        s
        for d in current["drafts"].values()
        for s in d["sections"]
        if s["heading"] == "Diagnostics and limitations"
    )
    assert chart["id"] in section["evidenceRefs"]
    assert old_ids[0] not in section["evidenceRefs"]
    request = next(iter(current["author_requests"].values()))
    presentation = next(e for e in request["presentationEvidence"] if e["format"] == "svg")
    assert presentation["artifactId"] == chart["id"]
    assert presentation["artifactHash"] == chart["hash"]
    assert presentation["specification"] == current["specifications"][chart["id"]]
    assert (
        run.output["history"][0]["review"]["report_directives"][0]["preserveEvidenceRefs"][-1]
        == old_ids[0]
    )
    engine.close()


@pytest.mark.parametrize(
    "status,command", [("failed", "resume"), ("waiting_for_user", "resolve_intervention")]
)
def test_exhausted_task_cannot_be_resumed_or_reset_by_an_answer(tmp_path, status, command):
    from macro_research_agent.agent.contracts import AgentInterventionV1

    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    run = engine.create("Historical hard-stop", defer_clarification=True)

    def stop(current):
        current.status = status
        current.error = {"code": "task_attempt_limit", "message": "Three calls used"}
        current.intervention = AgentInterventionV1(reason="task_attempt_limit", message="Stopped")
        current.ledger.used["model_calls"] = 3

    run = engine.repo.mutate(run.session_id, run.run_id, "test.stop", stop)
    with pytest.raises(AgentError) as caught:
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="retry",
                idempotency_key="retry",
                expected_version=run.version,
                type=command,
                arguments={"answer": "Try again"},
            ),
        )
    assert caught.value.code == "task_attempt_limit"
    retained = engine.repo.get_run(run.session_id, run.run_id)
    assert retained.status == status
    assert retained.ledger.used["model_calls"] == 3
    assert retained.error == run.error
    engine.close()


@pytest.mark.parametrize("always_fail", [False, True])
def test_report_directives_are_automatic_bounded_and_keep_evidence(
    tmp_path: Path, monkeypatch: Any, always_fail: bool
) -> None:
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.provider = FixtureAgentProvider()
    inject_delivery_fixtures(engine)
    original = AgentDelivery.review

    def directing(self, run, candidate, snapshot, results, iteration):
        report = original(self, run, candidate, snapshot, results, iteration)
        if iteration == 1 or always_fail:
            artifact_id = next(a["id"] for a in candidate["artifacts"] if a["format"] == "report")
            draft = candidate["drafts"][artifact_id]
            section = next(s for s in draft["sections"] if s["heading"] == "Results")
            report["status"] = "fail"
            report["semantic_report_status"] = "fail"
            report["findings"] = [
                {
                    "finding_id": "needs-wording",
                    "rule_id": "REPORT-WORDING",
                    "severity": "fail",
                    "message": "State the scope clearly",
                    "blocking": True,
                    "artifact_ids": [artifact_id],
                }
            ]
            report["report_directives"] = [
                {
                    "directiveId": f"directive-{iteration}",
                    "artifactId": artifact_id,
                    "targetSectionIds": [section["sectionId"]],
                    "issue": "Clarify descriptive scope",
                    "preserveEvidenceRefs": section["evidenceRefs"],
                    "acceptanceCriteria": ["Explain that results are descriptive"],
                }
            ]
        return report

    monkeypatch.setattr(AgentDelivery, "review", directing)
    run = engine.create("Summarize CPI", defer_clarification=True)
    content = "country,period,indicator,value,unit\n" + "".join(
        f"USA,{year},CPI,{100 + year - 2010},Index\n" for year in range(2010, 2031)
    )
    run = engine.upload(run, "input.csv", content.encode())
    run = engine.command(
        run.session_id,
        run.run_id,
        AgentCommandV1(
            command_id="start", idempotency_key="start", expected_version=run.version, type="start"
        ),
    )
    engine.execute(run.session_id, run.run_id)
    run = engine.repo.get_run(run.session_id, run.run_id)
    run = engine.command(
        run.session_id,
        run.run_id,
        AgentCommandV1(
            command_id="answer",
            idempotency_key="answer",
            expected_version=run.version,
            type="answer_clarification",
            arguments={"answers": {"scope": "USA"}},
        ),
    )
    engine.execute(run.session_id, run.run_id)
    run = engine.repo.get_run(run.session_id, run.run_id)
    if always_fail:
        assert run.status in {"budget_exhausted", "waiting_for_user"}
        assert run.ledger.used["formal_reviews"] <= 3
        assert run.ledger.used["output_candidates"] == 3
    else:
        assert run.status == "awaiting_final_confirmation", run.error
        assert run.ledger.used["formal_reviews"] == 2
        assert run.ledger.used["output_candidates"] == 2
        assert run.output["history"]
    assert run.ledger.used["model_fits"] == 1
    engine.close()
