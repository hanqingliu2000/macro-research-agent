import pytest
from macro_research_agent.agent.router import AgentPolicyValidator, AgentPolicyViolation
from macro_research_agent.agent.schemas import (
    AgentAttachmentMetadata,
    AgentConnectorQuery,
    AgentRouteDecision,
    AgentRoutingContext,
)
from macro_research_agent.agent.states import AgentSessionState
from pydantic import ValidationError


def test_agent_state_is_independent_and_experimental() -> None:
    assert AgentSessionState.CLARIFYING.value == "clarifying"
    assert AgentSessionState.ROUTING.value == "routing"
    assert AgentSessionState.COMPLETED.value == "completed"


def test_agent_policy_accepts_only_context_capabilities() -> None:
    context = AgentRoutingContext(
        research_request="Compare inflation.",
        available_connector_ids=["imf_data"],
        attachments=[
            AgentAttachmentMetadata(
                attachment_id="file-1",
                filename="input.csv",
                media_type="text/csv",
                size_bytes=24,
            )
        ],
    )
    decision = AgentRouteDecision(
        attachment_ids=["file-1"],
        connector_queries=[
            AgentConnectorQuery(connector_id="imf_data", dataset="CPI")
        ],
    )

    AgentPolicyValidator({"imf_data"}).validate(context, decision)


def test_agent_policy_rejects_unregistered_connectors() -> None:
    context = AgentRoutingContext(
        research_request="Compare inflation.",
        available_connector_ids=["imf_data"],
    )
    decision = AgentRouteDecision(
        connector_queries=[
            AgentConnectorQuery(connector_id="arbitrary_web", dataset="CPI")
        ]
    )

    with pytest.raises(AgentPolicyViolation, match="Unregistered connector"):
        AgentPolicyValidator({"imf_data"}).validate(context, decision)


def test_attachment_media_type_is_allowlisted() -> None:
    with pytest.raises(ValidationError):
        AgentAttachmentMetadata(
            attachment_id="file-1",
            filename="notes.pdf",
            media_type="application/pdf",
            size_bytes=10,
        )
