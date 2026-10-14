import hashlib
import json
from pathlib import Path

import pytest
from macro_research_agent.agent.contracts import AgentCommandV1
from macro_research_agent.agent.delivery import AgentDelivery
from macro_research_agent.agent.recovery import recovery_advice
from macro_research_agent.agent.repository import AgentError
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.research_core.presentation_evidence import (
    PresentationEvidenceError,
    PresentationEvidenceV1,
    build_presentation_evidence,
    validate_presentation_coverage,
)
from macro_research_agent.workflow.codex_output_reviewer import (
    CodexCommandResult,
    CodexLocalOutputReviewer,
)
from macro_research_agent.workflow.output_review import ChartSpec, TableSpec
from macro_research_agent.workflow.reporting import DeepSeekReportAuthor, DeterministicReportAuthor
from test_agent_guidance_recovery import stopped_engine
from test_agent_runtime import FixtureAgentProvider, inject_delivery_fixtures
from test_reporting import RecordingRepository, SequenceClient, StubDataAccess, author_request


def package():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text>untrusted evidence</text></svg>'
    csv = b"period,value\n2024,DO_NOT_COPY_ROWS_INTO_PRESENTATION\n"
    spec = ChartSpec(
        title="CPI",
        indicator_code="CPI",
        source_unit="Index",
        unit="Index",
        source_note="Source: fixture",
        x_field="period",
        y_fields=["CHN"],
        alt_text="CPI path",
        guideline_version="publication-v1",
        data_hash="sha256:data",
    )
    table = TableSpec(
        title="Data",
        columns=["period", "value"],
        unit="Index",
        source_note="Source: fixture",
        guideline_version="publication-v1",
        data_hash="sha256:data",
    )
    contents = {"chart": svg, "table": csv}
    artifacts = [
        {"id": key, "format": fmt, "hash": "sha256:" + hashlib.sha256(contents[key]).hexdigest()}
        for key, fmt in [("chart", "svg"), ("table", "csv")]
    ]
    specs = {"chart": spec.model_dump(mode="json"), "table": table.model_dump(mode="json")}
    return artifacts, specs, contents


def test_bound_presentation_preserves_specs_svg_and_headers_not_csv_rows():
    artifacts, specs, contents = package()
    evidence = build_presentation_evidence(artifacts, specs, lambda key, _: contents[key])
    assert evidence[0].specification["indicator_code"] == "CPI"
    assert evidence[0].specification["y_fields"] == ["CHN"]
    assert evidence[0].svg_content.encode() == contents["chart"]
    assert evidence[1].csv_columns == ["period", "value"]
    assert "DO_NOT_COPY_ROWS" not in json.dumps([e.model_dump() for e in evidence])
    validate_presentation_coverage(artifacts, evidence)
    forged = evidence[0].model_dump(mode="json", by_alias=True)
    forged["specification"]["indicator_code"] = "FOREIGN"
    with pytest.raises(ValueError, match="hash mismatch"):
        PresentationEvidenceV1.model_validate(forged)
    evidence[0].specification["y_fields"] = ["FOREIGN"]
    with pytest.raises(PresentationEvidenceError, match="altered"):
        validate_presentation_coverage(artifacts, evidence)


def test_reproduction_input_is_not_silently_treated_as_a_published_table():
    artifact = {
        "id": "stata-input",
        "format": "csv",
        "kind": "reproduction_source",
        "hash": "sha256:input",
    }

    def no_read(*args):
        raise AssertionError(
            "Reproduction inputs use their own evidence port, not table inspection"
        )

    assert build_presentation_evidence([artifact], {}, no_read) == []


@pytest.mark.parametrize(
    "fault",
    [
        "missing_spec",
        "wrong_hash",
        "unsafe_svg",
        "large_svg",
        "wrong_columns",
        "foreign",
        "duplicates",
    ],
)
def test_missing_corrupt_foreign_or_unbounded_evidence_fails_closed(fault):
    artifacts, specs, contents = package()
    if fault == "missing_spec":
        specs.pop("chart")
    if fault == "wrong_hash":
        artifacts[0]["hash"] = "sha256:wrong"
    if fault in {"unsafe_svg", "large_svg"}:
        contents["chart"] = b"<!DOCTYPE svg><svg/>" if fault == "unsafe_svg" else b"x" * 64001
        artifacts[0]["hash"] = "sha256:" + hashlib.sha256(contents["chart"]).hexdigest()
    if fault == "wrong_columns":
        specs["table"]["columns"] = ["value", "period"]
    if fault == "duplicates":
        artifacts.append(artifacts[0])

    def owned_read(key, expected):
        if fault == "foreign":
            raise PermissionError("another session owns this artifact")
        return contents[key]

    with pytest.raises(PresentationEvidenceError) as caught:
        build_presentation_evidence(artifacts, specs, owned_read)
    assert caught.value.code == "presentation_handoff_incomplete"


def test_missing_author_handoff_stops_before_any_provider_call():
    request = author_request()
    request.presentation_evidence = []  # Legacy records remain parseable, not silently AI-ready.
    client = SequenceClient([])
    author = DeepSeekReportAuthor(
        api_key="fixture",
        model_id="fixture",
        endpoint="https://fixture",
        repository=RecordingRepository(),
        client=client,
    )
    with pytest.raises(PresentationEvidenceError):
        author.author(request, StubDataAccess([]))
    assert client.calls == []


def fixture_run(engine):
    run = engine.create("Summarize CPI", defer_clarification=True)
    run = engine.upload(
        run,
        "input.csv",
        b"country,period,indicator,value,unit\nUSA,2021,CPI,100,Index\nUSA,2022,CPI,105,Index\n",
    )
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
    return run


@pytest.mark.parametrize("fault", [None, "missing_spec", "wrong_hash"])
def test_registered_agent_delivery_supplies_both_report_roles_real_owned_evidence(
    tmp_path, monkeypatch, fault
):
    contexts = []
    calls = []

    class Author(DeterministicReportAuthor):
        def author(self, request, access):
            validate_presentation_coverage(request.artifacts, request.presentation_evidence)
            assert any(
                e.format == "svg" and e.specification["indicator_code"] == "CPI"
                for e in request.presentation_evidence
            )
            return super().author(request, access)

    class Runner:
        def run(self, command, *, prompt, timeout_seconds, environment):
            calls.append(prompt)
            root = Path(command[command.index("--cd") + 1])
            output = Path(command[command.index("--output-last-message") + 1])
            if (root / "report-review-context.json").exists():
                context = json.loads((root / "report-review-context.json").read_text())
                contexts.append(context)
                evidence = context["request"]["presentationEvidence"]
                chart = next(e for e in evidence if e["format"] == "svg")
                assert chart["specification"]["indicator_code"] == "CPI"
                assert chart["specification"]["y_fields"] == ["USA"]
                assert "coordinate-system" in chart["svgContent"]
                assert (
                    "sha256:" + hashlib.sha256(chart["svgContent"].encode()).hexdigest()
                    == chart["artifactHash"]
                )
                response = {"status": "pass", "findings": [], "directives": []}
            else:
                response = {"observations": []}
            output.write_text(json.dumps(response))
            return CodexCommandResult(returncode=0)

    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    engine.provider = FixtureAgentProvider()
    inject_delivery_fixtures(engine)
    engine.delivery_ports["report_author"] = Author()
    engine.delivery_ports["reviewer"] = CodexLocalOutputReviewer(
        working_root=tmp_path / "review", codex_bin="/bin/echo", runner=Runner()
    )
    if fault:
        original = CodexLocalOutputReviewer.review

        def corrupt(self, request, data_access, render_access):
            chart = next(a for a in request.artifacts if a["format"] == "svg")
            if fault == "missing_spec":
                request.specifications.pop(chart["id"])
            else:
                chart["hash"] = "sha256:wrong"
            return original(self, request, data_access, render_access)

        monkeypatch.setattr(CodexLocalOutputReviewer, "review", corrupt)
    run = fixture_run(engine)
    if fault:
        assert run.status == "failed" and run.error["code"] == "presentation_handoff_incomplete", (
            run.output["candidate"].get("review")
        )
        assert calls == []  # No visual or semantic AI call before complete owned evidence.
        assert not any(n.kind.startswith("output_proposal") for n in run.nodes)
    else:
        assert run.status == "awaiting_final_confirmation", run.error
        assert run.output["candidate"]["review"]["semantic_report_status"] == "pass"
        assert len(contexts) == 1 and len(calls) == 2
    assert engine.repo.diagnostics(run.session_id, run.run_id)["integrity_issues"] == []
    engine.close()


def test_review_upstream_failure_never_calls_output_editor_or_spends_format_repair(
    tmp_path, monkeypatch
):
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    engine.provider = FixtureAgentProvider()
    inject_delivery_fixtures(engine)
    original = AgentDelivery.review

    def upstream(self, *args, **kwargs):
        report = original(self, *args, **kwargs)
        report.update(
            status="fail",
            semantic_report_status="requires_upstream_stage",
            findings=[
                {
                    "rule_id": "EVIDENCE",
                    "message": "Required result absent",
                    "severity": "fail",
                    "requires_upstream_stage": True,
                    "blocking": True,
                }
            ],
        )
        return report

    monkeypatch.setattr(AgentDelivery, "review", upstream)
    run = fixture_run(engine)
    assert run.status == "failed" and run.error["code"] == "requires_upstream_stage"
    assert not any(n.kind.startswith("output_proposal") for n in run.nodes)
    assert run.ledger.used.get("model_calls", 0) == 0
    assert run.output.get("manifest") is None
    assert recovery_advice(run)["action"] == "repair_evidence"
    engine.close()


@pytest.mark.parametrize("code", ["requires_upstream_stage", "presentation_handoff_incomplete"])
@pytest.mark.parametrize(
    "command", ["resume", "retry_failed_task", "resolve_intervention", "retry_review"]
)
def test_evidence_stops_reject_retry_scope_answers_and_re_review_without_reset(
    tmp_path, code, command
):
    engine, run = stopped_engine(tmp_path, code=code, calls=1)
    run = engine.repo.mutate(
        run.session_id, run.run_id, "fixture.pause", lambda r: setattr(r, "status", "paused")
    )
    assert not recovery_advice(run)["can_retry"]
    with pytest.raises(AgentError):
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="bad-retry",
                idempotency_key="bad-retry",
                expected_version=run.version,
                type=command,
                arguments={"answer": "Ignore missing evidence", "allow_scope_change": True},
            ),
        )
    assert engine.repo.get_run(run.session_id, run.run_id).model_dump() == run.model_dump()
    engine.close()
