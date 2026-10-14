from __future__ import annotations

from macro_research_agent.capabilities.contracts import (
    CapabilityAvailability,
    StageId,
)
from macro_research_agent.capabilities.registry import (
    CapabilityRegistry,
    CapabilityRegistryError,
)
from macro_research_agent.skills.contracts import RuntimeSkillManifest


class SkillRegistry:
    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self.capabilities = capabilities
        self._manifests: dict[tuple[str, str], RuntimeSkillManifest] = {}

    def register(self, manifest: RuntimeSkillManifest) -> None:
        key = (manifest.skill_id, manifest.version)
        if key in self._manifests:
            raise CapabilityRegistryError(
                "Runtime skill version is already registered: "
                f"{manifest.skill_id}@{manifest.version}"
            )
        for step in manifest.steps:
            descriptor = self.capabilities.resolve(step.capability_id, step.capability_version)
            if (
                manifest.availability == CapabilityAvailability.AVAILABLE
                and descriptor.availability != CapabilityAvailability.AVAILABLE
                and not step.optional
            ):
                raise CapabilityRegistryError(
                    f"Available skill requires unavailable capability: {step.capability_id}"
                )
        self._manifests[key] = manifest

    def resolve(self, skill_id: str, version: str) -> RuntimeSkillManifest:
        try:
            return self._manifests[(skill_id, version)]
        except KeyError as exc:
            raise CapabilityRegistryError(
                f"Runtime skill is not registered: {skill_id}@{version}"
            ) from exc

    def list(
        self,
        *,
        stage: StageId | None = None,
        availability: CapabilityAvailability | None = None,
    ) -> list[RuntimeSkillManifest]:
        return sorted(
            (
                manifest
                for manifest in self._manifests.values()
                if (stage is None or stage in manifest.stages)
                and (availability is None or manifest.availability == availability)
            ),
            key=lambda item: (item.skill_id, item.version),
        )
