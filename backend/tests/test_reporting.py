from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessGrant,
    ModelDataPage,
    ModelDatasetContext,
)
from macro_research_agent.workflow.output_review import stable_hash
from macro_research_agent.workflow.reporting import (
    DeepSeekReportAuthor,
    DeterministicReportAuthor,
    ReportAuthorRequestV1,
    ReportCitationV1,
    ReportContractValidationError,
    ReportProviderError,
    ReportReviewResponseV1,
    ReportRevisionDirectiveV1,
    ReportRevisionRequestV1,
    constrain_revised_draft,
    model_safe_handoff,
    render_report_markdown,
    validate_report_draft,
    validate_revised_draft,
)
from macro_research_agent.workflow.states import WorkflowStage


class RecordingRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_trace_event(
        self, session_id: str, event_type: str, actor: Any, payload: Any
    ) -> None:
        self.events.append({"session_id": session_id, "event_type": event_type, "payload": payload})


class StubDataAccess:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def read_rows(
        self,
        access_id: str,
        *,
        session_id: str,
        stage: WorkflowStage,
        offset: int,
        limit: int | None = None,
    ) -> ModelDataPage:
        selected = self.rows[offset : offset + (limit or len(self.rows))]
        return ModelDataPage(
            access_id=access_id,
            offset=offset,
            limit=limit or len(self.rows),
            rows=selected,
            page_hash=f"sha256:page-{offset}",
        )


class StubResponse:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.content = content
        self.finish_reason = finish_reason

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "finish_reason": self.finish_reason,
                    "message": {"content": self.content},
                }
            ]
        }


class SequenceClient:
    def __init__(self, responses: list[str | tuple[str, str] | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, tuple):
            return StubResponse(*response)
        return StubResponse(response)


def author_request() -> ReportAuthorRequestV1:
    import hashlib

    from macro_research_agent.research_core.presentation_evidence import build_presentation_evidence
    from macro_research_agent.workflow.output_review import ChartSpec

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    artifact = {
        "id": "chart-1",
        "format": "svg",
        "hash": "sha256:" + hashlib.sha256(svg).hexdigest(),
    }
    spec = ChartSpec(
        title="Fixture chart",
        unit="Percent",
        source_note="Source: Official data",
        x_field="period",
        y_fields=["value"],
        alt_text="Fixture",
        data_hash="sha256:data",
        guideline_version="publication-v1",
    ).model_dump(mode="json")
    return ReportAuthorRequestV1(
        sessionId="session-1",
        handoff={"handoffId": "handoff-1", "decisions": []},
        approvedPlan={"objective": "Compare inflation and project the next two periods."},
        deliverables={"researchReport": True},
        dataset=ModelDatasetContext(
            grant=ModelDataAccessGrant(
                access_id="grant-1",
                session_id="session-1",
                stage=WorkflowStage.OUTPUT,
                source_kind="snapshot",
                source_ref="snapshot-1",
                content_hash="sha256:data",
                classification="public",
                provider_profile="deepseek-development",
                model_id="deepseek-test",
                columns=["period", "value"],
                row_count=2,
                page_size=2,
                page_count=1,
                remote_disclosure_allowed=True,
            )
        ),
        modelResults=[{"id": "result-1", "kind": "arima", "forecast": [1.0, 1.1]}],
        diagnostics=["Residual diagnostics are available."],
        forecasts=[{"step": 1, "mean": 1.0}, {"step": 2, "mean": 1.1}],
        resultHashes={
            "result-1": stable_hash({"id": "result-1", "kind": "arima", "forecast": [1.0, 1.1]})
        },
        artifacts=[artifact],
        presentationEvidence=build_presentation_evidence(
            [artifact], {"chart-1": spec}, lambda *_: svg
        ),
        citations=[
            ReportCitationV1(citationId="source-1", label="Official data", sourceRef="snapshot-1")
        ],
        publicationGuideline={"version": "publication-v1"},
        requiredSections=[
            "Scope",
            "Data and method",
            "Results",
            "Diagnostics and limitations",
            "Reproducibility",
        ],
        title="Inflation report",
        sourceNote="Source: Official data",
    )


def test_report_title_limit_is_a_pre_persistence_contract_not_a_late_review_warning() -> None:
    request = author_request()
    author = DeterministicReportAuthor()
    draft = author.author(request, StubDataAccess([{"period": "2024", "value": 1.0}]))  # type: ignore[arg-type]
    assert DeepSeekReportAuthor._contract_constraints(request)["titleMaximumCharacters"] == 120
    valid = draft.model_copy(update={"title": "T" * 120})
    validate_report_draft(request, valid)
    invalid = draft.model_copy(update={"title": "T" * 121})
    with pytest.raises(ReportContractValidationError) as caught:
        validate_report_draft(request, invalid)
    assert caught.value.path == "$.title"
    assert caught.value.code == "report_title_too_long"


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_report_title_is_repaired_once_without_fallback(repair_succeeds: bool) -> None:
    request = author_request()
    access = StubDataAccess([{"period": "2024", "value": 1.0}, {"period": "2025", "value": 1.1}])
    draft = DeterministicReportAuthor().author(request, access)  # type: ignore[arg-type]
    invalid = draft.model_copy(update={"title": "T" * 121})
    client = SequenceClient(
        [
            invalid.model_dump_json(by_alias=True),
            (draft if repair_succeeds else invalid).model_dump_json(by_alias=True),
        ]
    )
    author = DeepSeekReportAuthor(
        api_key="fixture",
        model_id="fixture",
        endpoint="https://fixture",
        repository=RecordingRepository(),
        client=client,
    )  # type: ignore[arg-type]
    if repair_succeeds:
        assert author.author(request, access).title == draft.title  # type: ignore[arg-type]
    else:
        with pytest.raises(ReportProviderError, match="after repair"):
            author.author(request, access)  # type: ignore[arg-type]
    assert len(client.calls) == 2
    repair_prompt = client.calls[1]["json"]["messages"][1]["content"]
    assert "$.title" in repair_prompt and "report_title_too_long" in repair_prompt


def test_report_draft_renders_an_evidence_ledger_and_rejects_unknown_refs() -> None:
    request = author_request()
    author = DeterministicReportAuthor()
    draft = author.author(
        request,
        StubDataAccess([{"period": "2024", "value": 1.0}, {"period": "2025", "value": 1.1}]),  # type: ignore[arg-type]
    )

    markdown = render_report_markdown(draft)

    assert "## Evidence ledger" in markdown
    assert "## Declared limitations" in markdown
    assert "`sha256:data`" in markdown
    invalid = draft.model_copy(deep=True)
    invalid.claims[0].evidence_refs = ["sha256:invented"]
    with pytest.raises(ValueError, match="outside the request grant"):
        validate_report_draft(request, invalid)

    changed_citation = draft.model_copy(deep=True)
    changed_citation.citations[0].source_ref = "snapshot-invented"
    with pytest.raises(ValueError, match="citation binding"):
        validate_report_draft(request, changed_citation)

    unsupported_causal = draft.model_copy(deep=True)
    unsupported_causal.claims[0].claim_type = "causal"
    with pytest.raises(ValueError, match="Causal claims"):
        validate_report_draft(request, unsupported_causal)

    missing_required_statement = draft.model_copy(deep=True)
    data_section = next(
        item for item in missing_required_statement.sections if item.heading == "Data and method"
    )
    data_section.body = data_section.body.replace(request.source_note, "Official data")
    with pytest.raises(ValueError, match="source note verbatim") as caught:
        validate_report_draft(request, missing_required_statement)
    assert caught.value.path == "$.sections[].body"
    assert caught.value.code == "missing_source_note"


def test_report_requests_reject_model_results_with_the_wrong_hash() -> None:
    wire = author_request().model_dump(mode="json", by_alias=True)
    wire["resultHashes"]["result-1"] = "sha256:wrong"

    with pytest.raises(ValueError, match="model-result hashes"):
        ReportAuthorRequestV1.model_validate(wire)


def test_report_revision_may_change_only_target_sections_and_preserves_evidence() -> None:
    request = author_request()
    author = DeterministicReportAuthor()
    data_access = StubDataAccess([{"period": "2024", "value": 1.0}])
    draft = author.author(request, data_access)  # type: ignore[arg-type]
    directive = ReportRevisionDirectiveV1(
        directiveId="directive-1",
        artifactId="report-1",
        targetSectionIds=["section-results"],
        issue="State the forecast coverage more clearly.",
        preserveEvidenceRefs=["sha256:data"],
        acceptanceCriteria=["Name the two-period horizon."],
    )
    revision = ReportRevisionRequestV1(
        authorRequest=request,
        currentDraft=draft,
        directive=directive,
    )

    revised = author.revise(revision, data_access)  # type: ignore[arg-type]
    validate_revised_draft(revision, revised)

    unchanged = {
        item.section_id: item for item in draft.sections if item.section_id != "section-results"
    }
    assert all(
        item == unchanged[item.section_id]
        for item in revised.sections
        if item.section_id != "section-results"
    )

    changed_citation = revised.model_copy(deep=True)
    changed_citation.citations[0].source_ref = "snapshot-invented"
    with pytest.raises(ValueError, match="citation"):
        validate_revised_draft(revision, changed_citation)

    changed_binding = revised.model_copy(deep=True)
    changed_binding.claims[0].evidence_refs = ["chart-1"]
    with pytest.raises(ValueError, match="evidence bindings"):
        validate_revised_draft(revision, changed_binding)


def test_report_revision_projects_model_output_onto_text_only_authority() -> None:
    request = author_request()
    author = DeterministicReportAuthor()
    data_access = StubDataAccess([{"period": "2024", "value": 1.0}])
    current = author.author(request, data_access)  # type: ignore[arg-type]
    directive = ReportRevisionDirectiveV1(
        directiveId="directive-1",
        artifactId="report-1",
        targetSectionIds=["section-results"],
        issue="Correct the reported result.",
        preserveEvidenceRefs=["sha256:data"],
        acceptanceCriteria=["Use the verified value."],
    )
    revision = ReportRevisionRequestV1(
        authorRequest=request,
        currentDraft=current,
        directive=directive,
    )
    proposed = current.model_copy(deep=True)
    proposed.title = "Unauthorized title"
    proposed.citations[0].source_ref = "snapshot-invented"
    proposed.artifact_references = []
    target = next(item for item in proposed.sections if item.section_id == "section-results")
    target.body = "The verified result is one observation; causal inference is not supported."
    target.heading = "Unauthorized heading"
    target.evidence_refs = ["artifact-invented"]
    proposed.claims[0].statement = "The verified analytical snapshot contains one observation."
    proposed.claims[0].evidence_refs = ["artifact-invented"]
    proposed.claims[0].citation_refs = ["citation-wdi"]

    constrained = constrain_revised_draft(revision, proposed)

    constrained_target = next(
        item for item in constrained.sections if item.section_id == "section-results"
    )
    current_target = next(item for item in current.sections if item.section_id == "section-results")
    assert constrained.title == current.title
    assert constrained.citations == current.citations
    assert constrained.artifact_references == current.artifact_references
    assert constrained_target.heading == current_target.heading
    assert constrained_target.evidence_refs == current_target.evidence_refs
    assert constrained_target.body == target.body
    assert constrained.claims[0].statement == proposed.claims[0].statement
    assert constrained.claims[0].evidence_refs == current.claims[0].evidence_refs


def test_model_context_removes_embedded_results_from_handoff_copy() -> None:
    handoff = {
        "handoffId": "handoff-1",
        "analysisSpec": {"modelResults": [{"id": "result-1", "value": 12}], "models": []},
    }

    safe = model_safe_handoff(handoff)

    assert "modelResults" not in safe["analysisSpec"]
    assert handoff["analysisSpec"]["modelResults"][0]["value"] == 12


def test_deepseek_report_author_repairs_once_without_deterministic_fallback() -> None:
    request = author_request()
    valid = DeterministicReportAuthor().author(
        request,
        StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
    )
    client = SequenceClient(["{}", valid.model_dump_json(by_alias=True)])
    repository = RecordingRepository()
    author = DeepSeekReportAuthor(
        api_key="secret",
        model_id="deepseek-test",
        endpoint="https://example.test/chat",
        repository=repository,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )

    result = author.author(
        request,
        StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
    )

    assert result == valid
    assert len(client.calls) == 2
    assert "Repair these validation errors" in client.calls[1]["json"]["messages"][1]["content"]
    assert "$.sections" in client.calls[1]["json"]["messages"][1]["content"]
    first_payload = json.loads(client.calls[0]["json"]["messages"][1]["content"])
    constraints = first_payload["contractConstraints"]
    assert constraints["requiredSectionHeadings"] == request.required_sections
    assert constraints["citationBindings"] == [
        item.model_dump(mode="json", by_alias=True) for item in request.citations
    ]
    assert constraints["requiredStatements"] == {
        "sourceNoteVerbatim": request.source_note,
        "causalBoundaryMustContain": "causal inference",
        "reproductionBindingMustContain": "reproduction manifest",
        "artifactLifecycleNoteVerbatim": (
            "Artifact references identify generated candidates; selection and frozen "
            "reproduction-manifest membership are established only at Finish."
        ),
        "modelResultHashNoteVerbatim": (
            "Request-level resultHashes bind complete typed model-result records; each "
            "model-result resultHash binds only its nested numerical result payload, so those "
            "hashes are expected to differ."
        ),
    }
    assert constraints["artifactLifecycle"]["listedArtifactsAreFrozen"] is False
    assert set(constraints["allowedEvidenceRefs"]) >= {
        "sha256:data",
        "snapshot-1",
        "result-1",
        "chart-1",
    }
    assert repository.events[0]["event_type"] == "ai.model_results_accessed"
    assert "model_results" not in repository.events[0]["payload"]
    rejected = next(
        item
        for item in repository.events
        if item["event_type"] == "ai.report_author_contract_rejected"
    )
    assert any(issue["path"] == "$.sections" for issue in rejected["payload"]["issues"])
    assert all("input" not in issue for issue in rejected["payload"]["issues"])


def test_deepseek_report_author_expands_budget_after_truncated_json() -> None:
    request = author_request()
    valid = DeterministicReportAuthor().author(
        request,
        StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
    )
    client = SequenceClient([("{", "length"), valid.model_dump_json(by_alias=True)])
    author = DeepSeekReportAuthor(
        api_key="secret",
        model_id="deepseek-test",
        endpoint="https://example.test/chat",
        repository=RecordingRepository(),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        max_output_tokens=50,
    )

    assert (
        author.author(
            request,
            StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
        )
        == valid
    )
    assert [call["json"]["max_tokens"] for call in client.calls] == [50, 100]
    repair_prompt = client.calls[1]["json"]["messages"][1]["content"]
    assert "output_truncated" in repair_prompt


def test_deepseek_report_author_fails_closed_on_provider_timeout() -> None:
    request = author_request()
    author = DeepSeekReportAuthor(
        api_key="secret",
        model_id="deepseek-test",
        endpoint="https://example.test/chat",
        repository=RecordingRepository(),  # type: ignore[arg-type]
        client=SequenceClient([httpx.ReadTimeout("timeout")]),  # type: ignore[arg-type]
    )

    with pytest.raises(ReportProviderError) as caught:
        author.author(
            request,
            StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
        )
    assert caught.value.code == "provider_timeout"


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_deepseek_report_author_fails_closed_on_provider_http_errors(
    status_code: int,
) -> None:
    request = author_request()
    provider_response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://example.test/chat"),
    )
    error = httpx.HTTPStatusError(
        "provider error",
        request=provider_response.request,
        response=provider_response,
    )
    author = DeepSeekReportAuthor(
        api_key="secret",
        model_id="deepseek-test",
        endpoint="https://example.test/chat",
        repository=RecordingRepository(),  # type: ignore[arg-type]
        client=SequenceClient([error]),  # type: ignore[arg-type]
    )

    with pytest.raises(ReportProviderError) as caught:
        author.author(
            request,
            StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
        )
    assert caught.value.code == (
        "provider_rate_limited" if status_code == 429 else "provider_server_error"
    )


def test_deepseek_report_author_has_no_credential_or_contract_fallback() -> None:
    with pytest.raises(ReportProviderError) as credential_error:
        DeepSeekReportAuthor(
            api_key="",
            model_id="deepseek-test",
            endpoint="https://example.test/chat",
            repository=RecordingRepository(),  # type: ignore[arg-type]
        )
    assert credential_error.value.code == "provider_credentials_missing"

    author = DeepSeekReportAuthor(
        api_key="secret",
        model_id="deepseek-test",
        endpoint="https://example.test/chat",
        repository=RecordingRepository(),  # type: ignore[arg-type]
        client=SequenceClient(["{}", "{}"]),  # type: ignore[arg-type]
    )
    with pytest.raises(ReportProviderError) as contract_error:
        author.author(
            author_request(),
            StubDataAccess([{"period": "2024", "value": 1.0}]),  # type: ignore[arg-type]
        )
    assert contract_error.value.code == "invalid_report_contract"
    assert contract_error.value.attempts == 2
    assert any(issue["path"] == "$.sections" for issue in contract_error.value.issues)


def test_report_review_requires_explicit_upstream_stage() -> None:
    response = ReportReviewResponseV1.model_validate(
        {
            "status": "requires_upstream_stage",
            "findings": [
                {
                    "findingId": "finding-1",
                    "ruleId": "MISSING-FORECAST",
                    "severity": "fail",
                    "message": "The requested forecast result is absent.",
                    "requiresUpstreamStage": True,
                    "upstreamStage": "transformation",
                }
            ],
            "directives": [],
        }
    )
    assert response.status == "requires_upstream_stage"
    with pytest.raises(ValueError, match="needs an upstream finding"):
        ReportReviewResponseV1(status="requires_upstream_stage")
