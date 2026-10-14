"""Source-backed interim visual rules, not a journal submission certification."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict


class VisualRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    requirement: str
    source_ids: tuple[str, ...]


class AcademicVisualRubric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal["academic-publication-placeholder-v1"] = "academic-publication-placeholder-v1"
    status: Literal["placeholder"] = "placeholder"
    researched_on: str = "2026-09-28"
    scope: str = (
        "One fixed Nature-inspired interim research-chart standard, not Nature submission "
        "certification or final project creative direction. Review at the native 900x500-or-larger "
        "canvas. Use readable editable text, white background, color plus line encoding, "
        "visible units/source, faithful values and gaps. Final print sizing/font points and "
        "journal packaging are outside this browser acceptance standard."
    )
    severity_policy: str = (
        "Fail only for evidenced loss or distortion of meaning: clipped required labels/data, "
        "unreadable essential text, ambiguous series, wrong units/scale/values, hidden missing "
        "observations, or mislabeled uncertainty. Warn for minor non-obscuring readability "
        "issues. A conditional rule is not applicable when its element is absent: a historical "
        "chart need not contain forecasts if the approved deliverable supplies them elsewhere. "
        "Do not infer exact font points or print DPI from a PNG. Never invent data or patches."
    )
    sources: tuple[tuple[str, str], ...] = (
        (
            "NATURE",
            "https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/",
        ),
        ("MRA", "guidelines/academic-publication-placeholder-v1.md"),
    )
    rules: tuple[VisualRule, ...] = (
        VisualRule(
            rule_id="VISUAL-CLIPPING",
            requirement="Required titles, labels, notes, legend and marks stay inside the canvas.",
            source_ids=("NATURE",),
        ),
        VisualRule(
            rule_id="VISUAL-OVERLAP",
            requirement="Text, legend and panels must not obscure data or each other.",
            source_ids=("NATURE",),
        ),
        VisualRule(
            rule_id="VISUAL-LEGIBILITY",
            requirement=(
                "Essential labels and glyphs must be readable; use consistent typography, "
                "plain background and strong text contrast. Report actual defects, not taste."
            ),
            source_ids=("NATURE",),
        ),
        VisualRule(
            rule_id="VISUAL-LEGEND",
            requirement=(
                "Identify plotted entities/series using a key or direct labels. Multiple series "
                "must remain distinguishable without hue alone (line styles, marks or labels)."
            ),
            source_ids=("NATURE", "MRA"),
        ),
        VisualRule(
            rule_id="VISUAL-RENDER-SPEC-MISMATCH",
            requirement=(
                "Compare marks with the bound spec and rows: indicators, order, time span, "
                "units, magnitude and gaps must agree. Never hide missing observations by "
                "joining a line across them. Do not combine incompatible units on one axis."
            ),
            source_ids=("MRA",),
        ),
        VisualRule(
            rule_id="VISUAL-AXIS-UNIT",
            requirement=(
                "Expose period and units/scaling. Show non-zero ranges honestly; a line chart "
                "need not start at zero. Any log scale must be labeled. Do not confuse percent "
                "with percentage points or a GDP share with a growth rate."
            ),
            source_ids=("MRA",),
        ),
        VisualRule(
            rule_id="VISUAL-UNCERTAINTY",
            requirement=(
                "When estimates, error bars or forecasts are shown, name their meaning and "
                "interval level, distinguish observations from projections and do not draw "
                "unavailable intervals. Check these claims against supplied model evidence."
            ),
            source_ids=("MRA",),
        ),
        VisualRule(
            rule_id="VISUAL-CAPTION-SOURCE",
            requirement=(
                "A title/description and source must identify the content. Define opaque "
                "indicator/entity codes in the figure, caption or bound spec. Accessible "
                "descriptions must not contradict the data. Linked companion metadata is "
                "acceptable; do not demand the full report inside every figure."
            ),
            source_ids=("MRA",),
        ),
    )


ACADEMIC_VISUAL_RUBRIC = AcademicVisualRubric()
ACADEMIC_VISUAL_RUBRIC_HASH = (
    "sha256:"
    + hashlib.sha256(
        json.dumps(
            ACADEMIC_VISUAL_RUBRIC.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
)
