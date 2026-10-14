import json

import pytest
from macro_research_agent.workflow.reporting import (
    DeepSeekReportAuthor,
    DeterministicReportAuthor,
    ReportProviderError,
    ReportRevisionDirectiveV1,
    ReportRevisionRequestV1,
    ReportSectionEditsV1,
    apply_report_section_edits,
)
from test_reporting import RecordingRepository, SequenceClient, StubDataAccess, author_request


def fixture():
    request = author_request()
    access = StubDataAccess([{"period": "2024", "value": 1.0}, {"period": "2025", "value": 1.1}])
    draft = DeterministicReportAuthor().author(request, access)
    revision = ReportRevisionRequestV1(
        authorRequest=request,
        currentDraft=draft,
        directive=ReportRevisionDirectiveV1(
            directiveId="d",
            artifactId="report",
            targetSectionIds=["section-results"],
            issue="Clarify the existing forecast coverage",
            preserveEvidenceRefs=["sha256:data"],
            acceptanceCriteria=["Name the two periods without new evidence or analysis"],
        ),
    )
    section = next(s for s in draft.sections if s.section_id == "section-results")
    edits = {
        "directiveId": "d",
        "sectionEdits": [
            {
                "sectionId": section.section_id,
                "body": section.body + "\nThe supplied forecast covers two periods.",
            }
        ],
        "claimEdits": [
            {
                "claimId": c.claim_id,
                "statement": c.statement + " Two periods are supplied.",
                "uncertainty": c.uncertainty,
                "limitation": c.limitation,
            }
            for c in draft.claims
            if c.claim_id in section.claim_ids
        ],
    }
    return revision, access, edits


def test_partial_edits_preserve_all_binding_and_untargeted_fields_by_construction():
    revision, _, edits = fixture()
    updated = apply_report_section_edits(revision, ReportSectionEditsV1.model_validate(edits))
    original = revision.current_draft
    assert updated.title == original.title and updated.citations == original.citations
    assert updated.artifact_references == original.artifact_references
    for new, old in zip(updated.sections, original.sections, strict=True):
        assert new.evidence_refs == old.evidence_refs and new.claim_ids == old.claim_ids
        if old.section_id != "section-results":
            assert new == old
    for new, old in zip(updated.claims, original.claims, strict=True):
        assert new.evidence_refs == old.evidence_refs and new.citation_refs == old.citation_refs
    assert original.sections != updated.sections


@pytest.mark.parametrize(
    "corruption",
    ["title", "evidence", "new_section", "new_claim", "wrong_directive", "limitations"],
)
def test_partial_edits_reject_unauthorized_mutations(corruption):
    revision, _, edits = fixture()
    if corruption == "title":
        edits["title"] = "Changed"
    elif corruption == "evidence":
        edits["sectionEdits"][0]["evidenceRefs"] = ["invented"]
    elif corruption == "new_section":
        edits["sectionEdits"][0]["sectionId"] = "invented"
    elif corruption == "new_claim":
        edits["claimEdits"].append(
            {"claimId": "invented", "statement": "x", "uncertainty": "x", "limitation": "x"}
        )
    elif corruption == "wrong_directive":
        edits["directiveId"] = "other"
    else:
        edits["limitations"] = ["Hide a limitation"]
    with pytest.raises(ValueError):
        apply_report_section_edits(revision, ReportSectionEditsV1.model_validate(edits))


@pytest.mark.parametrize("recovers", [True, False])
def test_real_adapter_partial_contract_repair_is_bounded_and_audited(recovers):
    revision, access, edits = fixture()
    client = SequenceClient(
        [
            json.dumps({**edits, "title": "protected"}),
            json.dumps(edits if recovers else {**edits, "title": "protected"}),
        ]
    )
    repo = RecordingRepository()
    author = DeepSeekReportAuthor(
        api_key="fixture",
        model_id="fixture",
        endpoint="https://fixture",
        repository=repo,
        client=client,
    )
    if recovers:
        updated = author.revise_sections(revision, access)
        assert updated.title == revision.current_draft.title
        assert any(
            e["payload"].get("output_contract") == "report-section-edits-v1" for e in repo.events
        )
    else:
        with pytest.raises(ReportProviderError, match="after repair"):
            author.revise_sections(revision, access)
    assert len(client.calls) == 2
    assert client.calls[0]["json"]["messages"][0]["content"].count("sectionEdits") > 0
    assert "protected" not in json.dumps(revision.current_draft.model_dump())
