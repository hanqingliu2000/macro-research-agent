from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from macro_research_agent.capabilities.contracts import (
    CapabilityAvailability,
    CapabilityDescriptor,
    InvocationMode,
    StageId,
)


class CapabilityRegistryError(ValueError):
    pass


CapabilityHandler = Callable[[BaseModel], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredHandler:
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: CapabilityHandler


class CapabilityRegistry:
    def __init__(self, descriptors: list[CapabilityDescriptor] | None = None) -> None:
        self._descriptors: dict[tuple[str, str], CapabilityDescriptor] = {}
        self._handlers: dict[tuple[str, str], RegisteredHandler] = {}
        for descriptor in descriptors or []:
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        key = (descriptor.capability_id, descriptor.version)
        if key in self._descriptors:
            raise CapabilityRegistryError(
                "Capability version is already registered: "
                f"{descriptor.capability_id}@{descriptor.version}"
            )
        self._descriptors[key] = descriptor

    def bind(
        self,
        capability_id: str,
        version: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler: CapabilityHandler,
    ) -> None:
        descriptor = self.resolve(capability_id, version)
        if descriptor.availability != CapabilityAvailability.AVAILABLE:
            raise CapabilityRegistryError("Only available capabilities may bind handlers.")
        if descriptor.invocation_mode != InvocationMode.DIRECT:
            raise CapabilityRegistryError("Only direct capabilities bind to CapabilityExecutor.")
        if descriptor.input_schema != input_model.model_json_schema():
            raise CapabilityRegistryError("Bound input model does not match descriptor schema.")
        if descriptor.output_schema != output_model.model_json_schema():
            raise CapabilityRegistryError("Bound output model does not match descriptor schema.")
        self._handlers[(capability_id, version)] = RegisteredHandler(
            input_model, output_model, handler
        )

    def resolve(self, capability_id: str, version: str) -> CapabilityDescriptor:
        try:
            return self._descriptors[(capability_id, version)]
        except KeyError as exc:
            raise CapabilityRegistryError(
                f"Capability is not registered: {capability_id}@{version}"
            ) from exc

    def handler(self, capability_id: str, version: str) -> RegisteredHandler:
        try:
            return self._handlers[(capability_id, version)]
        except KeyError as exc:
            raise CapabilityRegistryError(
                f"Capability has no direct executable handler: {capability_id}@{version}"
            ) from exc

    def list(
        self,
        *,
        stage: StageId | None = None,
        availability: CapabilityAvailability | None = None,
    ) -> list[CapabilityDescriptor]:
        return sorted(
            (
                descriptor
                for descriptor in self._descriptors.values()
                if (stage is None or stage in descriptor.stages)
                and (availability is None or descriptor.availability == availability)
            ),
            key=lambda item: (item.capability_id, item.version),
        )
