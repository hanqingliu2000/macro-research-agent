from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from macro_research_agent.agent.schemas import AgentRouteDecision, AgentRoutingContext


class AgentPolicyViolation(ValueError):
    """A route attempted to leave the registered capability boundary."""


class AgentRouter(ABC):
    @abstractmethod
    async def route(self, context: AgentRoutingContext) -> AgentRouteDecision:
        raise NotImplementedError


class AgentPolicyValidator:
    def __init__(self, allowed_connector_ids: set[str]) -> None:
        self._allowed_connector_ids = set(allowed_connector_ids)

    def validate(self, context: AgentRoutingContext, decision: AgentRouteDecision) -> None:
        available = set(context.available_connector_ids) & self._allowed_connector_ids
        requested = {query.connector_id for query in decision.connector_queries}
        unknown = requested - available
        if unknown:
            raise AgentPolicyViolation("Unregistered connector IDs: " + ", ".join(sorted(unknown)))

        attachment_ids = {attachment.attachment_id for attachment in context.attachments}
        unknown_attachments = set(decision.attachment_ids) - attachment_ids
        if unknown_attachments:
            raise AgentPolicyViolation(
                "Unknown attachment IDs: " + ", ".join(sorted(unknown_attachments))
            )

        if _contains_url(decision.model_dump(mode="json")):
            raise AgentPolicyViolation("Agent route decisions cannot contain arbitrary URLs")


def _contains_url(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered.startswith(("http://", "https://"))
    if isinstance(value, Mapping):
        return any(_contains_url(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_url(item) for item in value)
    return False
