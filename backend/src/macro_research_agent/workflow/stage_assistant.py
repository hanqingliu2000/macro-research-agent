from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from macro_research_agent.workflow.model_data_access import (
    ModelDataAccessPort,
    ModelDatasetContext,
)
from macro_research_agent.workflow.pipeline_draft import default_model_parameters


class StrictAssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataOperationProposal(StrictAssistantModel):
    proposal_item_id: str = Field(min_length=1)
    operation: Literal[
        "filter_missing",
        "keep_columns",
        "drop_columns",
        "rename_columns",
        "map_codes",
        "cast_types",
        "missing_value_rule",
        "deduplicate",
        "sort",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1)


class SourceMappingProposal(StrictAssistantModel):
    proposal_item_id: str = Field(min_length=1)
    source_column: str = Field(min_length=1)
    role: Literal[
        "series_id",
        "entity_code",
        "indicator_code",
        "frequency",
        "period",
        "value",
        "attribute",
        "ignore",
    ]
    rationale: str = Field(min_length=1)


class DataDiagnostic(StrictAssistantModel):
    kind: Literal["missing_observations", "limitation"]
    summary: str = Field(min_length=1)
    details: list[str] = Field(default_factory=list, max_length=50)


class DataAssistantProposal(StrictAssistantModel):
    summary: str = Field(min_length=1)
    operations: list[DataOperationProposal] = Field(default_factory=list)
    source_mappings: list[SourceMappingProposal] = Field(default_factory=list)
    diagnostics: list[DataDiagnostic] = Field(default_factory=list)


class AnalysisOperationProposal(StrictAssistantModel):
    proposal_item_id: str = Field(min_length=1)
    operation: Literal[
        "lag",
        "lead",
        "difference",
        "yoy_growth",
        "period_growth",
        "log",
        "rebase_index",
        "unit_conversion",
        "deflate",
        "per_capita",
        "frequency_conversion",
        "merge",
        "rolling_mean",
        "seasonal_rule",
        "group_aggregation",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    indicators: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=lambda: ["value"])
    rationale: str = Field(min_length=1)


class AnalysisModelProposal(StrictAssistantModel):
    proposal_item_id: str = Field(min_length=1)
    model: Literal["descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"]
    variables: list[str] = Field(default_factory=list)
    dependent_variables: list[str] = Field(default_factory=list)
    independent_variables: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1)


class AnalysisModelRemovalProposal(StrictAssistantModel):
    proposal_item_id: str = Field(min_length=1)
    model_job_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class AnalysisAssistantProposal(StrictAssistantModel):
    summary: str = Field(min_length=1)
    operations: list[AnalysisOperationProposal] = Field(default_factory=list)
    models: list[AnalysisModelProposal] = Field(default_factory=list)
    model_removals: list[AnalysisModelRemovalProposal] = Field(default_factory=list)

    def item_ids(self) -> set[str]:
        return {
            *[item.proposal_item_id for item in self.operations],
            *[item.proposal_item_id for item in self.models],
            *[item.proposal_item_id for item in self.model_removals],
        }


class DataAssistantContext(StrictAssistantModel):
    request: str
    plan: dict[str, Any]
    diagnostics: dict[str, Any]
    source_mapping_draft: dict[str, Any] = Field(default_factory=dict)
    dataset: ModelDatasetContext
    capability_catalog: list[dict[str, Any]] = Field(default_factory=list)
    handoff: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisAssistantContext(StrictAssistantModel):
    request: str
    plan: dict[str, Any]
    pipeline: dict[str, Any]
    dataset: ModelDatasetContext
    capability_catalog: list[dict[str, Any]] = Field(default_factory=list)
    handoff: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)


class StageAssistantPort(ABC):
    provider_profile = "unconfigured"
    model_id = "unconfigured"
    remote_data_disclosure = True

    @abstractmethod
    def propose_data(
        self,
        request: str,
        context: DataAssistantContext,
        data_access: ModelDataAccessPort,
    ) -> DataAssistantProposal: ...

    @abstractmethod
    def propose_analysis(
        self,
        request: str,
        context: AnalysisAssistantContext,
        data_access: ModelDataAccessPort,
    ) -> AnalysisAssistantProposal: ...


DataAssistantPort = StageAssistantPort
AnalysisAssistantPort = StageAssistantPort


@dataclass(frozen=True)
class AnalysisRequestIntent:
    operation: str | None
    target_indicators: tuple[str, ...]
    protected_indicators: tuple[str, ...]
    output_unit: str | None
    has_explicit_operation: bool
    has_explicit_target: bool
    forbid_transformations: bool
    model_kind: str | None
    model_variables: tuple[str, ...]
    forecast_steps: int | None
    replace_models: bool
    preserve_model_kinds: tuple[str, ...]


@dataclass(frozen=True)
class DataRequestIntent:
    preserve_missing: bool
    sort_only: bool
    diagnose_missing: bool


def parse_data_request_intent(request: str) -> DataRequestIntent:
    lowered = " ".join(request.casefold().replace("_", " ").split())
    # "preserve all non-missing observations" protects valid rows; it does
    # not ask to retain the missing rows themselves.
    missing_scope = re.sub(r"\bnon[- ]missing\b", "complete", lowered)
    preserve_missing = bool(
        re.search(r"\b(?:keep|preserve|retain)\b[^.;\n]*\bmissing\b", missing_scope)
        or re.search(
            r"\b(?:do not|don't|never|without)\b[^.;\n]*"
            r"\b(?:filter|delete|drop|remove|impute)\b",
            missing_scope,
        )
        or re.search(r"(?:保留|保持)[^。；\n]*缺失", request)
        or re.search(r"(?:不要|不得|勿)[^。；\n]*(?:过滤|删除|丢弃|填补)", request)
    )
    sort_only = bool(
        re.search(
            r"\b(?:only|solely)\b[^.;\n]*\b(?:deterministic\s+)?sort(?:ing)?\b",
            lowered,
        )
        or re.search(r"(?:仅|只)[^。；\n]*(?:确定性)?排序", request)
        or "non-destructive only" in lowered
    )
    diagnose_missing = (
        "missing" in lowered
        and bool(re.search(r"\b(?:where|identify|locate|review|diagnos|tell me)\b", lowered))
        or bool(re.search(r"(?:缺失).*(?:哪里|位置|识别|检查|诊断)", request))
    )
    return DataRequestIntent(
        preserve_missing=preserve_missing,
        sort_only=sort_only,
        diagnose_missing=diagnose_missing,
    )


def validate_data_proposal_constraints(
    request: str,
    proposal: DataAssistantProposal,
) -> None:
    """Fail closed when a Data provider contradicts explicit preservation constraints."""

    intent = parse_data_request_intent(request)
    destructive_missing = {
        item.operation
        for item in proposal.operations
        if item.operation in {"filter_missing", "missing_value_rule"}
    }
    if intent.preserve_missing and destructive_missing:
        raise ValueError(
            "The Data proposal contradicts the request to preserve missing observations."
        )
    if intent.sort_only and any(item.operation != "sort" for item in proposal.operations):
        raise ValueError(
            "The Data proposal added a mutation beyond the requested deterministic sort."
        )
    if intent.diagnose_missing and not any(
        item.kind in {"missing_observations", "limitation"} for item in proposal.diagnostics
    ):
        raise ValueError(
            "The Data proposal omitted the requested missing-observation diagnostic or limitation."
        )


_ANALYSIS_OPERATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bfirst[- ]differences?\b|\bdifferences?\b", "difference"),
    (r"\byear[- ]on[- ]year\b|\byoy\b", "yoy_growth"),
    (r"\bperiod[- ]on[- ]period\b|\bperiod growth\b", "period_growth"),
    (r"\brolling (?:mean|average)\b|\bmoving average\b", "rolling_mean"),
    (r"\bnatural log(?:arithm)?\b|\blog transform", "log"),
    (r"\brebase(?:d| the)? index\b", "rebase_index"),
    (r"\blag(?:ged)?\b", "lag"),
    (r"\blead\b", "lead"),
    (r"\bgrowth\b", "yoy_growth"),
)
_PROTECTED_PATTERN = re.compile(
    r"\b(?:unchanged|as is|untransformed|exclude(?:d)?|do not transform|don't transform)\b"
)
_FORBID_TRANSFORMATIONS_PATTERN = re.compile(
    r"\b(?:do not|don't|without|no)\s+(?:add(?:ing)?\s+)?(?:new\s+)?"
    r"(?:transformations?|operations?|data transforms?)\b",
    re.IGNORECASE,
)
_MODEL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bdescriptive(?: statistics)?\b", "descriptive"),
    (r"\bcorrelations?\b", "correlation"),
    (r"\bols\b|\bordinary least squares\b", "ols"),
    (r"\badf\b|\baugmented dickey[- ]fuller\b", "adf"),
    (r"\bsarimax\b", "sarimax"),
    (r"\barima\b", "arima"),
    (r"\bvar\b|\bvector autoregress(?:ion|ive)\b", "var"),
)
_NUMBER_WORD_VALUES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "twenty-four": 24,
}


def _forecast_steps(request: str) -> int | None:
    match = re.search(
        r"\bforecast(?:ing|s|ed)?(?:\s+(?:for|exactly))?\s+"
        r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty-four)"
        r"\s+(?:annual\s+|quarterly\s+|monthly\s+)?(?:periods?|years?|quarters?|months?)\b",
        request,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"\b(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty-four)"
            r"\s+(?:annual\s+|quarterly\s+|monthly\s+)?(?:periods?|years?|quarters?|months?)"
            r"\s+(?:ahead|forecast)\b",
            request,
            flags=re.IGNORECASE,
        )
    if match is None:
        match = re.search(
            r"\b(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty-four)"
            r"\s+(?:annual\s+|quarterly\s+|monthly\s+)?forecast\s+"
            r"(?:periods?|years?|quarters?|months?)\b",
            request,
            flags=re.IGNORECASE,
        )
    if match is None:
        return None
    token = match.group("count").casefold()
    return int(token) if token.isdigit() else _NUMBER_WORD_VALUES[token]


def _dataset_indicator_profile(
    rows: list[dict[str, Any]],
) -> tuple[list[str], dict[str, set[str]], dict[str, set[str]]]:
    labels: dict[str, set[str]] = {}
    units: dict[str, set[str]] = {}
    for row in rows:
        code = str(row.get("indicator_code") or "").strip()
        if not code:
            continue
        labels.setdefault(code, set())
        units.setdefault(code, set())
        for key in ("indicator_name", "indicator", "series_name"):
            value = str(row.get(key) or "").strip()
            if value:
                labels[code].add(value)
        unit = str(row.get("unit") or "").strip()
        if unit:
            units[code].add(unit)
    return sorted(labels), labels, units


def _request_fragments(
    request: str,
    indicators: list[str],
    labels: dict[str, set[str]],
) -> list[tuple[str, set[str]]]:
    rewritten = request.casefold()
    tokens: dict[str, str] = {}
    aliases: list[tuple[str, str]] = []
    for index, code in enumerate(indicators):
        token = f"indicatorref_{index}_end"
        tokens[token] = code
        aliases.append((code.casefold(), token))
        aliases.extend((label.casefold(), token) for label in labels.get(code, set()))
    for alias, token in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        if len(alias) >= 3:
            rewritten = rewritten.replace(alias, f" {token} ")
    fragments = re.split(r"[;\n]+|\.\s+|[!?]+", rewritten)
    return [
        (fragment, {code for token, code in tokens.items() if token in fragment})
        for fragment in fragments
        if fragment.strip()
    ]


def parse_analysis_request_intent(
    request: str,
    rows: list[dict[str, Any]],
) -> AnalysisRequestIntent:
    indicators, labels, _ = _dataset_indicator_profile(rows)
    fragments = _request_fragments(request, indicators, labels)
    protected: set[str] = set()
    targeted: set[str] = set()
    operation: str | None = None
    explicit_operation = False
    for fragment, mentioned in fragments:
        is_protected = bool(_PROTECTED_PATTERN.search(fragment))
        if is_protected:
            protected.update(mentioned)
            continue
        # Model clauses commonly describe lag-order parameters. They are not
        # requests to add a data-lag transformation.
        if any(re.search(pattern, fragment) for pattern, _ in _MODEL_PATTERNS):
            continue
        fragment_operation = next(
            (
                kind
                for pattern, kind in _ANALYSIS_OPERATION_PATTERNS
                if re.search(pattern, fragment)
            ),
            None,
        )
        if fragment_operation is not None and operation is None:
            operation = fragment_operation
            explicit_operation = True
        if fragment_operation is not None:
            targeted.update(mentioned)
    output_unit = (
        "percentage points"
        if re.search(r"\bpercentage[- ]points?\b", request, flags=re.IGNORECASE)
        else None
    )
    mentioned_indicators = {code for _, mentioned in fragments for code in mentioned}
    replacement_clause = re.search(
        r"\breplac(?:e|ing)\b[^.;\n]*?\bwith\b(?P<target>[^.;\n]+)",
        request,
        flags=re.IGNORECASE,
    )
    model_search_text = replacement_clause.group("target") if replacement_clause else request
    model_matches = [
        (match.start(), kind)
        for pattern, kind in _MODEL_PATTERNS
        if (match := re.search(pattern, model_search_text, flags=re.IGNORECASE)) is not None
    ]
    model_kind = min(model_matches)[1] if model_matches else None
    model_variables = tuple(
        sorted(
            {
                code
                for fragment, mentioned in fragments
                if model_kind is not None
                and any(
                    kind == model_kind and re.search(pattern, fragment)
                    for pattern, kind in _MODEL_PATTERNS
                )
                for code in mentioned
            }
        )
    )
    preserve_model_kinds = tuple(
        kind
        for pattern, kind in _MODEL_PATTERNS
        if re.search(
            rf"\b(?:keep|preserve|retain)\b[^.;\n]*{pattern}",
            request,
            flags=re.IGNORECASE,
        )
    )
    return AnalysisRequestIntent(
        operation=operation,
        target_indicators=tuple(sorted(targeted - protected)),
        protected_indicators=tuple(sorted(protected)),
        output_unit=output_unit,
        has_explicit_operation=explicit_operation,
        has_explicit_target=bool(targeted),
        forbid_transformations=bool(_FORBID_TRANSFORMATIONS_PATTERN.search(request)),
        model_kind=model_kind,
        model_variables=model_variables or tuple(sorted(mentioned_indicators)),
        forecast_steps=_forecast_steps(request),
        replace_models=bool(
            re.search(
                r"\b(?:replac(?:e|ing)|revis(?:e|ing)|updat(?:e|ing)|modif(?:y|ying))\b"
                r"[^.;\n]*(?:models?|jobs?|forecasts?|var|arima|sarimax)\b",
                request,
                flags=re.IGNORECASE,
            )
        ),
        preserve_model_kinds=preserve_model_kinds,
    )


def read_all_dataset_rows(
    context: ModelDatasetContext,
    data_access: ModelDataAccessPort,
) -> list[dict[str, Any]]:
    grant = context.grant
    rows = list(context.initial_page.rows if context.initial_page else [])
    offset = len(rows)
    while offset < grant.row_count:
        page = data_access.read_page(
            grant.access_id,
            session_id=grant.session_id,
            stage=grant.stage,
            offset=offset,
            limit=min(grant.page_size, grant.row_count - offset),
        )
        rows.extend(page.rows)
        offset += len(page.rows)
        if not page.rows:
            break
    return rows


def validate_analysis_proposal_constraints(
    request: str,
    rows: list[dict[str, Any]],
    proposal: AnalysisAssistantProposal,
    pipeline: dict[str, Any] | None = None,
) -> None:
    """Fail closed when a provider contradicts explicit transformation instructions."""

    indicators, _, _ = _dataset_indicator_profile(rows)
    available = set(indicators)
    intent = parse_analysis_request_intent(request, rows)
    if intent.forbid_transformations and proposal.operations:
        raise ValueError("The Analysis proposal added a forbidden transformation.")
    if intent.model_kind is not None:
        matching_models = [item for item in proposal.models if item.model == intent.model_kind]
        if len(matching_models) != 1 or len(proposal.models) != 1:
            raise ValueError(
                "The Analysis proposal did not preserve the requested "
                f"{intent.model_kind.upper()} model."
            )
        model = matching_models[0]
        if intent.model_variables and set(model.variables) != set(intent.model_variables):
            raise ValueError(
                "The Analysis proposal did not preserve the requested model variables."
            )
        if (
            intent.forecast_steps is not None
            and int(model.parameters.get("forecastSteps", -1)) != intent.forecast_steps
        ):
            raise ValueError(
                "The Analysis proposal did not preserve the requested forecast horizon."
            )
    if intent.replace_models and pipeline is not None:
        existing = {str(item.get("id")): item for item in pipeline.get("models") or []}
        removed = {item.model_job_id for item in proposal.model_removals}
        if not removed or not removed.issubset(existing):
            raise ValueError(
                "The Analysis replacement did not identify valid model jobs to remove."
            )
        if any(str(existing[item].get("kind")) in intent.preserve_model_kinds for item in removed):
            raise ValueError("The Analysis replacement removed a model the request preserves.")
    if not intent.has_explicit_operation:
        return
    if not proposal.operations:
        if proposal.models:
            raise ValueError(
                "An Analysis transformation refusal cannot substitute an unrelated model job."
            )
        return
    expected = intent.operation
    matching = [item for item in proposal.operations if item.operation == expected]
    if not matching:
        raise ValueError(
            f"The Analysis proposal did not preserve the requested {expected} operation."
        )
    protected = set(intent.protected_indicators)
    expected_targets = set(intent.target_indicators)
    for item in proposal.operations:
        if item.operation != expected:
            raise ValueError(
                "The Analysis proposal substituted a materially different transformation."
            )
        actual_targets = set(item.indicators) if item.indicators else available
        if actual_targets & protected:
            raise ValueError(
                "The Analysis proposal targeted an indicator that the request keeps unchanged."
            )
        if intent.has_explicit_target and actual_targets != expected_targets:
            raise ValueError(
                "The Analysis proposal did not preserve the requested indicator subset."
            )
        if expected == "difference" and int(item.parameters.get("periods", 1)) != 1:
            raise ValueError("The Analysis proposal did not preserve a one-period difference.")
        if intent.output_unit and (
            str(item.parameters.get("outputUnit") or "").casefold() != intent.output_unit.casefold()
        ):
            raise ValueError("The Analysis proposal did not preserve the requested output unit.")


class DeterministicStageAssistant(StageAssistantPort):
    provider_profile = "deterministic-local"
    model_id = "deterministic-stage-assistant-v1"
    remote_data_disclosure = False

    @staticmethod
    def _all_rows(
        context: ModelDatasetContext,
        data_access: ModelDataAccessPort,
    ) -> list[dict[str, Any]]:
        return read_all_dataset_rows(context, data_access)

    def propose_data(
        self,
        request: str,
        context: DataAssistantContext,
        data_access: ModelDataAccessPort,
    ) -> DataAssistantProposal:
        rows = self._all_rows(context.dataset, data_access)
        if context.source_mapping_draft:
            mappings = dict(context.source_mapping_draft.get("mappings") or {})
            return DataAssistantProposal(
                summary=f"Prepared a typed local-file schema mapping for: {request}",
                source_mappings=[
                    SourceMappingProposal(
                        proposal_item_id=f"mapping-{column}",
                        source_column=str(column),
                        role=cast(Any, role),
                        rationale="Use the controlled canonical-role inference for this column.",
                    )
                    for column, role in mappings.items()
                ],
            )
        operations: list[DataOperationProposal] = []
        intent = parse_data_request_intent(request)
        missing_rows = [row for row in rows if row.get("value") is None]
        diagnostics: list[DataDiagnostic] = []
        if intent.diagnose_missing:
            details = sorted(
                {
                    " · ".join(
                        str(row.get(key) or "unknown")
                        for key in ("entity_code", "indicator_code", "period")
                    )
                    for row in missing_rows
                }
            )
            diagnostics.append(
                DataDiagnostic(
                    kind="missing_observations",
                    summary=(f"Found {len(missing_rows)} row(s) with a missing analytical value."),
                    details=details[:50],
                )
            )
        if missing_rows and not intent.preserve_missing and not intent.sort_only:
            operations.append(
                DataOperationProposal(
                    proposal_item_id="data-filter-missing",
                    operation="filter_missing",
                    parameters={"column": "value"},
                    rationale="Remove observations whose analytical value is missing.",
                )
            )
        if int(context.diagnostics.get("duplicateKeys") or 0) > 0 and not intent.sort_only:
            operations.append(
                DataOperationProposal(
                    proposal_item_id="data-deduplicate",
                    operation="deduplicate",
                    parameters={"keep": "last"},
                    rationale="Keep one reviewed observation per canonical key.",
                )
            )
        operations.append(
            DataOperationProposal(
                proposal_item_id="data-sort",
                operation="sort",
                parameters={},
                rationale="Create a deterministic canonical row order.",
            )
        )
        mutation_summary = (
            f"Proposed {len(operations)} mutating operation(s) for separate approval."
        )
        diagnostic_summary = (
            f"Read-only diagnostic inspected {len(rows)} rows and found "
            f"{len(missing_rows)} missing analytical value(s)."
        )
        proposal = DataAssistantProposal(
            summary=f"{diagnostic_summary} {mutation_summary}",
            operations=operations,
            diagnostics=diagnostics,
        )
        validate_data_proposal_constraints(request, proposal)
        return proposal

    def propose_analysis(
        self,
        request: str,
        context: AnalysisAssistantContext,
        data_access: ModelDataAccessPort,
    ) -> AnalysisAssistantProposal:
        rows = self._all_rows(context.dataset, data_access)
        indicators, labels, units = _dataset_indicator_profile(rows)
        entities = sorted({str(row.get("entity_code")) for row in rows if row.get("entity_code")})
        intent = parse_analysis_request_intent(request, rows)
        if intent.model_kind is not None:
            model_parameters = default_model_parameters(intent.model_kind)
            if intent.forecast_steps is not None:
                model_parameters["forecastSteps"] = intent.forecast_steps
            removals = self._replacement_model_removals(context.pipeline, intent)
            proposal = AnalysisAssistantProposal(
                summary=self._model_revision_summary(intent, removals),
                operations=[],
                models=[
                    AnalysisModelProposal(
                        proposal_item_id=f"analysis-{intent.model_kind}",
                        model=cast(Any, intent.model_kind),
                        variables=list(intent.model_variables or tuple(indicators[:20])),
                        parameters=model_parameters,
                        rationale=(
                            f"Configure the requested {intent.model_kind.upper()} model with the "
                            "explicit variables and forecast horizon."
                        ),
                    )
                ],
                model_removals=removals,
            )
            validate_analysis_proposal_constraints(request, rows, proposal, context.pipeline)
            return proposal
        operation_kind = intent.operation or "yoy_growth"
        protected = set(intent.protected_indicators)
        if intent.has_explicit_target:
            operation_indicators = list(intent.target_indicators)
        else:
            operation_indicators = [code for code in indicators if code not in protected]
            if operation_kind in {"yoy_growth", "period_growth"}:
                operation_indicators = [
                    code
                    for code in operation_indicators
                    if not self._already_rate_indicator(code, labels.get(code, set()))
                ]
        output_unit = intent.output_unit or self._inferred_output_unit(
            operation_kind, operation_indicators, units
        )
        operation_parameters = self._analysis_parameters(operation_kind, output_unit)
        duplicate = self._has_equivalent_operation(
            context.pipeline,
            operation_kind,
            operation_indicators,
            operation_parameters,
        )
        operations = (
            []
            if intent.forbid_transformations or duplicate or not operation_indicators
            else [
                AnalysisOperationProposal(
                    proposal_item_id=f"analysis-{operation_kind.replace('_', '-')}",
                    operation=cast(Any, operation_kind),
                    parameters=operation_parameters,
                    indicators=operation_indicators[:20],
                    entities=entities[:50],
                    rationale=self._analysis_rationale(
                        operation_kind,
                        operation_indicators,
                        protected,
                    ),
                )
            ]
        )
        model = AnalysisModelProposal(
            proposal_item_id="analysis-descriptive",
            model="descriptive",
            variables=indicators[:20],
            parameters={
                "missing": "drop",
                "addConstant": True,
                "covariance": "nonrobust",
                "maxLags": 1,
            },
            rationale="Summarize the reviewed transformed series without causal claims.",
        )
        models = (
            []
            if intent.has_explicit_target
            or protected
            or (intent.has_explicit_operation and not operations)
            else [model]
        )
        proposal = AnalysisAssistantProposal(
            summary=self._analysis_summary(
                context,
                operation_kind,
                operation_indicators,
                protected,
                units,
                output_unit,
                duplicate,
            ),
            operations=operations,
            models=models,
        )
        validate_analysis_proposal_constraints(request, rows, proposal, context.pipeline)
        return proposal

    @staticmethod
    def _replacement_model_removals(
        pipeline: dict[str, Any],
        intent: AnalysisRequestIntent,
    ) -> list[AnalysisModelRemovalProposal]:
        if not intent.replace_models:
            return []
        preserve = set(intent.preserve_model_kinds)
        candidates = []
        for model in pipeline.get("models") or []:
            kind = str(model.get("kind") or "")
            parameters = dict(model.get("parameters") or {})
            is_forecast = (
                kind in {"arima", "sarimax"} or int(parameters.get("forecastSteps") or 0) > 0
            )
            if kind in preserve or not is_forecast:
                continue
            model_id = str(model.get("id") or "")
            if not model_id:
                continue
            candidates.append(
                AnalysisModelRemovalProposal(
                    proposal_item_id=f"analysis-remove-{model_id}",
                    model_job_id=model_id,
                    label=str(model.get("label") or f"{kind.upper()} model"),
                    rationale=(
                        "Remove this existing forecast job as part of the requested replacement."
                    ),
                )
            )
        return candidates

    @staticmethod
    def _model_revision_summary(
        intent: AnalysisRequestIntent,
        removals: list[AnalysisModelRemovalProposal],
    ) -> str:
        variables = ", ".join(intent.model_variables) or "the available series"
        horizon = (
            f" forecasting exactly {intent.forecast_steps} periods"
            if intent.forecast_steps is not None
            else ""
        )
        replacement = (
            f" Replace {len(removals)} existing forecast job(s)." if intent.replace_models else ""
        )
        transform_note = " No transformation is proposed." if intent.forbid_transformations else ""
        return (
            f"Configure one {str(intent.model_kind).upper()} model for {variables}{horizon}."
            f"{replacement}{transform_note}"
        )

    @staticmethod
    def _already_rate_indicator(code: str, labels: set[str]) -> bool:
        description = " ".join([code, *sorted(labels)]).casefold()
        return bool(
            code.upper().endswith(".ZG") or re.search(r"\b(?:growth|rate|change)\b", description)
        )

    @staticmethod
    def _analysis_parameters(kind: str, output_unit: str | None) -> dict[str, Any]:
        parameters: dict[str, Any] = {}
        if kind in {"lag", "lead", "difference", "period_growth"}:
            parameters["periods"] = 1
        if kind == "rolling_mean":
            parameters.update({"window": 4, "minimumPeriods": 1})
        if output_unit and kind == "difference":
            parameters["outputUnit"] = output_unit
        return parameters

    @staticmethod
    def _inferred_output_unit(
        kind: str,
        indicators: list[str],
        units: dict[str, set[str]],
    ) -> str | None:
        input_units = {unit for code in indicators for unit in units.get(code, set())}
        if (
            kind == "difference"
            and input_units
            and all(unit.casefold().startswith("percent") for unit in input_units)
        ):
            return "percentage points"
        return None

    @staticmethod
    def _has_equivalent_operation(
        pipeline: dict[str, Any],
        kind: str,
        indicators: list[str],
        parameters: dict[str, Any],
    ) -> bool:
        expected_indicators = set(indicators)
        for item in pipeline.get("operations") or []:
            if not item.get("enabled", True) or item.get("kind") != kind:
                continue
            target = dict(item.get("target") or {})
            actual_indicators = set(target.get("indicators") or [])
            actual_parameters = dict(item.get("parameters") or {})
            if actual_indicators == expected_indicators and all(
                actual_parameters.get(key) == value for key, value in parameters.items()
            ):
                return True
        return False

    @staticmethod
    def _analysis_rationale(
        kind: str,
        indicators: list[str],
        protected: set[str],
    ) -> str:
        rationale = (
            f"Apply the registered {kind.replace('_', ' ')} operation only to "
            f"{', '.join(indicators)}."
        )
        if protected:
            rationale += f" Preserve {', '.join(sorted(protected))} unchanged."
        return rationale

    @staticmethod
    def _analysis_summary(
        context: AnalysisAssistantContext,
        kind: str,
        indicators: list[str],
        protected: set[str],
        units: dict[str, set[str]],
        output_unit: str | None,
        duplicate: bool,
    ) -> str:
        input_units = sorted({unit for code in indicators for unit in units.get(code, set())})
        dataset = context.dataset.grant.source_ref
        target_text = ", ".join(indicators) or "no eligible indicators"
        summary = (
            f"{kind.replace('_', ' ').title()} for {target_text}; input dataset: {dataset}; "
            f"output dataset: proposed {kind.replace('_', ' ')} step; "
            f"input units: {', '.join(input_units) or 'not specified'}; "
            f"output unit: {output_unit or 'same as input'}."
        )
        if protected:
            summary += f" Kept {', '.join(sorted(protected))} unchanged."
        if duplicate:
            summary += " No duplicate operation was proposed because the same step already exists."
        return summary


def assistant_state_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
