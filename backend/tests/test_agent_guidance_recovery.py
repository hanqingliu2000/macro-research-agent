import httpx
import pytest
from macro_research_agent.agent.contracts import AgentCommandV1, AgentInterventionV1, AgentNodeV1
from macro_research_agent.agent.providers import normalize_agent_route_guidance
from macro_research_agent.agent.recovery import recovery_advice
from macro_research_agent.agent.repository import AgentError
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from macro_research_agent.llm.failures import classify_provider_error
from macro_research_agent.workflow.plan_guidance import normalize_plan_guidance
from test_agent_runtime import FixtureAgentProvider, inject_delivery_fixtures


@pytest.mark.parametrize(
    "message",
    [
        "Whether the IMF WEO connector exposes estimate/status/vintage labels for 2020–2024; "
        "disclose absence if none is provided.",
        "Whether the IMF WEO extract supplies estimate/status/vintage metadata; "
        "if it does not, the report states absence.",
        "Source metadata availability is inspected after acquisition, including observation status",
        "IMF 接口是否提供元数据、版本信息和观测状态；如缺失则披露。",
    ],
)
def test_source_metadata_checks_are_preserved_after_acquisition_not_human_blockers(message):
    route = FixtureAgentProvider().route(None)
    route.plan.unresolved_items = [
        message,
        "Confirm the intended general-government debt definition.",
    ]
    route.plan.warnings = ["SDMX WEO vintages can revise historical observations."]
    normalize_agent_route_guidance(route)
    assert route.acquisition_checks == [message]
    assert route.plan.unresolved_items == [
        "Confirm the intended general-government debt definition."
    ]
    assert route.plan.warnings == ["SDMX WEO vintages can revise historical observations."]
    normalize_agent_route_guidance(route)
    assert route.acquisition_checks == [message]


@pytest.mark.parametrize(
    "message",
    [
        "Choose which vintage should define the sample.",
        "Confirm whether to include estimates or final actuals, given unknown observation status.",
        "IMF connector is unavailable; whether metadata exists cannot be checked.",
        "Missing API key; check metadata availability after acquisition.",
        "Discovery-only dataset is not executable, even if metadata supplies country coverage.",
    ],
)
def test_true_human_or_access_prerequisites_are_not_suppressed(message):
    assert normalize_plan_guidance([message], [])[0] == [message]


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (402, "provider_payment_required", False),
        (401, "provider_authentication_failed", False),
        (403, "provider_authentication_failed", False),
        (429, "provider_rate_limited", True),
        (500, "provider_server_error", True),
        (503, "provider_server_error", True),
        (400, "provider_request_rejected", False),
    ],
)
def test_provider_failure_classes_do_not_echo_sensitive_provider_body(status, code, retryable):
    request = httpx.Request("POST", "https://fixture")
    response = httpx.Response(status, request=request, json={"secret": "private-key"})
    error = httpx.HTTPStatusError("private-key", request=request, response=response)
    result = classify_provider_error(error)
    assert result.code == code and result.retryable is retryable
    assert "private-key" not in result.message


def stopped_engine(
    tmp_path, code="provider_payment_required", calls=2, phase="analysis_assessment"
):
    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False
    run = engine.create("Same research", defer_clarification=True)

    def stop(current):
        current.status = "waiting_for_user"
        current.phase = phase
        current.nodes.append(
            AgentNodeV1(
                kind=phase,
                status="failed",
                physical_calls={"analyst": calls},
                attempt_ids=["attempt-1"],
            )
        )
        current.ledger.used["model_calls"] = calls
        current.error = {"code": code, "message": "Safe failure"}
        current.intervention = AgentInterventionV1(reason=code, message="Safe failure")

    run = engine.repo.mutate(run.session_id, run.run_id, "fixture.failure", stop)
    return engine, run


def test_retry_requires_provider_confirmation_and_keeps_answers_inputs_and_counters(tmp_path):
    engine, run = stopped_engine(tmp_path)
    advice = recovery_advice(run)
    assert advice["remaining"]["task_calls"] == 1
    assert advice["requires_provider_confirmation"]

    def command(arguments):
        return AgentCommandV1(
            command_id="retry",
            idempotency_key="retry",
            expected_version=run.version,
            type="retry_failed_task",
            arguments=arguments,
        )

    with pytest.raises(AgentError) as caught:
        engine.command(run.session_id, run.run_id, command({}))
    assert caught.value.code == "provider_action_required"
    recovered = engine.command(
        run.session_id, run.run_id, command({"confirm_provider_ready": True})
    )
    assert (
        recovered.answers == run.answers
        and recovered.nodes[0].input_refs == run.nodes[0].input_refs
    )
    assert recovered.nodes[0].physical_calls["analyst"] == 2
    assert recovered.ledger.used["model_calls"] == 2
    replay = engine.command(run.session_id, run.run_id, command({"confirm_provider_ready": True}))
    assert replay.version == recovered.version
    engine.close()


@pytest.mark.parametrize(
    "limit", ["physical", "clarification", "attempts", "tokens", "active_seconds"]
)
def test_advice_and_command_respect_all_actual_retry_limits(tmp_path, limit):
    engine, run = stopped_engine(
        tmp_path,
        code="provider_timeout",
        calls=3 if limit == "physical" else 1,
        phase="clarification" if limit == "clarification" else "analysis_assessment",
    )

    def cap(current):
        if limit == "clarification":
            current.ledger.used["clarification_batches"] = 2
        if limit == "attempts":
            current.nodes[0].attempt_ids = ["a", "b", "c"]
        if limit == "tokens":
            current.ledger.reservations["unknown"] = {"tokens": current.ledger.limits.tokens}
        if limit == "active_seconds":
            current.ledger.used["active_seconds"] = current.ledger.limits.active_seconds

    run = engine.repo.mutate(run.session_id, run.run_id, "fixture.cap", cap)
    advice = recovery_advice(run)
    assert advice["action"] == (
        "extend_budget" if limit in {"tokens", "active_seconds"} else "start_linked_run"
    )
    with pytest.raises(AgentError, match="cannot be retried"):
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="retry",
                idempotency_key="retry",
                expected_version=run.version,
                type="retry_failed_task",
            ),
        )
    assert engine.repo.get_run(run.session_id, run.run_id).ledger == run.ledger
    engine.close()


@pytest.mark.parametrize(
    "phase,limit", [("review", "formal_reviews"), ("report_revision", "output_candidates")]
)
def test_delivery_failure_cannot_retry_exhausted_version_or_review_budget(tmp_path, phase, limit):
    engine, run = stopped_engine(tmp_path, code="provider_timeout", calls=1, phase=phase)

    def cap(current):
        current.ledger.used[limit] = current.ledger.limits.model_dump()[limit]

    run = engine.repo.mutate(run.session_id, run.run_id, "fixture.cap", cap)
    assert recovery_advice(run)["action"] == "start_linked_run"
    engine.close()


def test_new_call_errors_cannot_use_scope_reply_to_bypass_retry_guards(tmp_path):
    engine, run = stopped_engine(tmp_path)
    with pytest.raises(AgentError) as caught:
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="answer",
                idempotency_key="answer",
                expected_version=run.version,
                type="resolve_intervention",
                arguments={"answer": "Retry", "allow_scope_change": True},
            ),
        )
    assert caught.value.code == "provider_action_required"
    assert engine.repo.get_run(run.session_id, run.run_id).answers == run.answers
    engine.close()


def test_paused_provider_failure_cannot_bypass_explicit_retry_via_resume(tmp_path):
    engine, run = stopped_engine(tmp_path, code="provider_timeout", calls=3)
    run = engine.repo.mutate(
        run.session_id,
        run.run_id,
        "fixture.pause",
        lambda current: setattr(current, "status", "paused"),
    )
    with pytest.raises(AgentError, match="explicit retry"):
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="resume",
                idempotency_key="resume",
                expected_version=run.version,
                type="resume",
            ),
        )
    assert engine.repo.get_run(run.session_id, run.run_id).ledger == run.ledger
    engine.close()


def test_missing_credentials_cannot_be_confirmed_away(tmp_path):
    engine, run = stopped_engine(tmp_path, code="provider_credentials_missing", calls=0)
    assert not engine.settings.deepseek_api_key
    with pytest.raises(AgentError) as caught:
        engine.command(
            run.session_id,
            run.run_id,
            AgentCommandV1(
                command_id="retry",
                idempotency_key="retry",
                expected_version=run.version,
                type="retry_failed_task",
                arguments={"confirm_provider_ready": True},
            ),
        )
    assert caught.value.code == "provider_credentials_missing"
    assert engine.repo.get_run(run.session_id, run.run_id).ledger == run.ledger
    engine.close()


def test_real_agent_adapter_classifies_402_with_one_audited_call_no_fallback(tmp_path, monkeypatch):
    from macro_research_agent.agent import providers
    from macro_research_agent.agent.observability import AgentAuditedHttpClient
    from macro_research_agent.agent.providers import AgentAssessment

    app = create_app(
        Settings(
            environment="test",
            llm_provider="test",
            runtime_dir=tmp_path,
            deepseek_api_key="fixture-key",
        )
    )
    engine = app.state.agent_runtime
    engine.autorun = False
    run = engine.create("Summarize CPI", defer_clarification=True)
    engine.graph.claim(run.session_id, run.run_id, "clarification", [])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(402, json={"error": "Insufficient Balance"})

    def client(*args, **kwargs):
        return AgentAuditedHttpClient(*args, **kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(providers, "AgentAuditedHttpClient", client)
    with pytest.raises(AgentError) as caught:
        engine.provider.call(run, "planner", "Test", {}, AgentAssessment)
    assert caught.value.code == "provider_payment_required"
    saved = engine.repo.get_run(run.session_id, run.run_id)
    assert len(calls) == saved.ledger.used["model_calls"] == 1
    assert saved.nodes[-1].physical_calls["planner"] == 1
    assert engine.repo.events(run.session_id, event_type="ai.request_failed")
    assert saved.ledger.reservations  # Unknown tokens remain reserved, never silently zeroed.
    engine.close()


def test_deferred_check_reaches_actual_data_assessment_and_evidence_reference(
    tmp_path, monkeypatch
):
    from macro_research_agent.agent.providers import AgentAssessment

    app = create_app(Settings(environment="test", llm_provider="test", runtime_dir=tmp_path))
    engine = app.state.agent_runtime
    engine.autorun = False

    class Provider(FixtureAgentProvider):
        def route(self, run):
            route = super().route(run)
            route.acquisition_checks = [
                "Check metadata availability and disclose absence after retrieval."
            ]
            return route

        def call(self, run, role, task, evidence, *args):
            if role == "data_steward":
                assert evidence["acquisition_checks"] and evidence["rows"]
                assert "source_metadata_receipts" in evidence
            return AgentAssessment(status="pass", summary="Usable", cleaning="none")

    engine.provider = Provider()
    inject_delivery_fixtures(engine)
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
    assert run.status == "awaiting_final_confirmation", run.error
    checks = run.data["acquisition_checks"]
    assert checks["assessment_ref"] and checks["source_snapshot_refs"]
    assert checks["state"] == "assessed_against_acquired_evidence"
    engine.close()
