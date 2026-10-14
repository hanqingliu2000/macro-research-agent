"""Deterministic classification of user-facing Plan blockers and cautions."""

from __future__ import annotations

from collections.abc import Iterable


def normalize_plan_guidance(
    unresolved_items: Iterable[str], warnings: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Keep only actionable blockers and material research cautions."""

    blockers: list[str] = []
    cautions = [
        text
        for item in warnings
        if (text := item.strip()) and not is_acquisition_dependent_claim(text.casefold())
    ]
    for item in unresolved_items:
        text = item.strip()
        if not text:
            continue
        lowered = text.casefold()
        if is_acquisition_dependent_claim(lowered):
            continue
        if _explicitly_non_blocking(lowered):
            if not _internal_discovery_note(lowered):
                cautions.append(text)
            continue
        blockers.append(text)

    material_cautions = [
        item
        for item in cautions
        if not _internal_discovery_note(item.casefold())
        and not item.casefold().startswith("the previous ")
    ]
    return _unique(blockers), _unique(material_cautions)


def _explicitly_non_blocking(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "does not block",
            "doesn't block",
            "will not block",
            "non-blocking",
            "not a blocker",
            "不阻塞",
            "非阻塞",
            "不是阻塞项",
        )
    )


def _internal_discovery_note(value: str) -> bool:
    if "discovery index" in value and any(
        marker in value for marker in ("cannot prove", "low-frequency", "bounded retrieval")
    ):
        return True
    return "discovery-only" in value and any(
        marker in value
        for marker in (
            "executable=false",
            "future connector admission",
            "not proposed",
            "not placed in data_sources",
            "blocked/alternative source",
        )
    )


def is_acquisition_dependent_claim(value: str) -> bool:
    """Discard claims that only a connector response can establish."""

    if any(
        marker in value
        for marker in (
            "credential",
            "api key",
            "api token",
            "authentication",
            "requires login",
            "not configured",
            "not executable",
            "not registered",
            "disabled connector",
            "connector is unavailable",
            "attach a local file",
            "discovery-only",
            "凭据",
            "连接器不可用",
        )
    ):
        return False
    if any(
        marker in value
        for marker in (
            "choose ",
            "select ",
            "user must decide",
            "user must confirm",
            "confirm whether",
            "whether to include",
            "whether to allow",
            "which vintage",
            "请选择",
            "是否采用",
            "用户决定",
        )
    ):
        return False
    metadata = any(
        marker in value
        for marker in (
            "metadata",
            "estimate/status/vintage",
            "status/vintage",
            "vintage labels",
            "observation status",
            "元数据",
            "版本信息",
            "观测状态",
        )
    )
    unknown_exposure = any(
        marker in value
        for marker in (
            "whether",
            "exposes",
            "supplies",
            "not exposed",
            "if it does not",
            "if none",
            "if unavailable",
            "if not provided",
            "availability",
            "是否提供",
            "若未提供",
            "如缺失",
        )
    )
    if metadata and unknown_exposure:
        return True

    # Explicit post-acquisition coverage checks are not human prerequisites. Keep
    # credential/admission failures actionable rather than broadly suppressing blockers.
    if any(
        marker in value
        for marker in ("confirmed only after acquisition", "confirmed only at acquisition")
    ) and not any(
        marker in value
        for marker in (
            "credential",
            "api key",
            "api token",
            "authentication",
            "requires login",
            "not configured",
            "unsupported",
            "disabled",
            "not executable",
            "not registered",
            "attach a local file",
        )
    ):
        return True

    if any(
        marker in value
        for marker in (
            "connector",
            "attach a local file",
            "enable an executable",
            "api key",
            "credential",
            "连接器",
            "上传本地文件",
            "凭据",
        )
    ):
        return False
    return any(
        marker in value
        for marker in (
            "no reported values",
            "no observations",
            "missing years",
            "data gap",
            "estimation gap",
            "does not contain",
            "doesn't contain",
            "not available in",
            "unavailable in",
            "availability must be validated",
            "availability should be validated",
            "must be validated at acquisition",
            "must be validated during acquisition",
            "validate at acquisition",
            "validated at acquisition",
            "verify at acquisition",
            "confirmed at acquisition",
            "established at acquisition",
            "determined at acquisition",
            "checked after acquisition",
            "checked at acquisition",
            "cannot be confirmed before acquisition",
            "exact codes must be validated",
            "coverage must be validated",
            "没有数据",
            "无数据",
            "缺少观测",
            "数据缺口",
            "缺失年份",
            "无法确认可用性",
            "获取时验证",
            "采集时验证",
        )
    )


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
