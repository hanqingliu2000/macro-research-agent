"""Shared, stateless capability contracts and registries."""

from macro_research_agent.capabilities.contracts import (
    CapabilityDescriptor,
    CapabilityInvocationIntent,
    CapabilityInvocationResult,
)
from macro_research_agent.capabilities.registry import CapabilityRegistry

__all__ = [
    "CapabilityDescriptor",
    "CapabilityInvocationIntent",
    "CapabilityInvocationResult",
    "CapabilityRegistry",
]
