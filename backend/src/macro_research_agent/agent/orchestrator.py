from __future__ import annotations

from abc import ABC, abstractmethod

from macro_research_agent.agent.schemas import (
    AgentRouteDecision,
    AgentRoutingContext,
    AgentRunResult,
)
from macro_research_agent.llm.base import ClarificationQuestion


class AgentOrchestrator(ABC):
    """Mode-specific orchestration over shared, stateless capabilities."""

    @abstractmethod
    async def clarification_questions(
        self, context: AgentRoutingContext
    ) -> list[ClarificationQuestion]:
        raise NotImplementedError

    @abstractmethod
    async def build_route(self, context: AgentRoutingContext) -> AgentRouteDecision:
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self, context: AgentRoutingContext, route: AgentRouteDecision
    ) -> AgentRunResult:
        raise NotImplementedError
