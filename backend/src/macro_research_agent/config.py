from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "Macro Research Agent"
    environment: str = "development"
    runtime_dir: Path = Path("runtime")
    max_upload_mb: int = 100
    # Runtime planning is locked to DeepSeek. ``test`` is an internal-only
    # dependency-injection seam used by the offline test suite.
    llm_provider: str = "deepseek"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_endpoint: str = "https://api.openai.com/v1/responses"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    deepseek_endpoint: str = "https://api.deepseek.com/chat/completions"
    data_ai_model: str = ""
    analysis_ai_model: str = ""
    report_author_model: str = ""
    report_author_max_output_tokens: int = 12_000
    report_author_max_data_rows: int = 2_000
    stage_ai_max_attempts: int = 2
    stage_ai_timeout_seconds: float = 45
    stage_ai_max_prompt_chars: int = 250_000
    stage_ai_max_output_tokens: int = 4_000
    # Production Output review is locked to the locally authenticated Codex
    # runtime. Automated tests replace the port inside ``create_app`` rather
    # than selecting a production fallback through configuration.
    output_review_provider: str = "codex-local"
    output_review_model: str = ""
    output_review_codex_bin: str = "codex"
    output_review_timeout_seconds: float = 120
    planning_max_attempts: int = 2
    planning_timeout_seconds: float = 45
    planning_max_data_rows: int = 2_000
    planning_max_prompt_chars: int = 250_000
    planning_max_output_tokens: int = 4_000
    ai_data_access_enabled: bool = True
    ai_data_page_size: int = 200
    ai_remote_user_data_allowed: bool = True
    ai_remote_licensed_data_allowed: bool = False
    graph_orphan_timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if self.graph_orphan_timeout_seconds < 1:
            raise ValueError("Graph orphan timeout must be positive.")
        if self.planning_max_attempts < 1 or self.planning_max_attempts > 3:
            raise ValueError("Planning attempts must be between 1 and 3.")
        if self.planning_max_output_tokens < 1:
            raise ValueError("Planning output token budget must be positive.")
        if self.output_review_timeout_seconds < 1:
            raise ValueError("Output review timeout must be positive.")
        if self.stage_ai_max_attempts < 1 or self.stage_ai_max_attempts > 2:
            raise ValueError("Stage AI attempts must be between 1 and 2.")
        if self.stage_ai_timeout_seconds < 1:
            raise ValueError("Stage AI timeout must be positive.")
        if self.report_author_max_output_tokens < 1:
            raise ValueError("Report Author output token budget must be positive.")
        if self.report_author_max_data_rows < 1:
            raise ValueError("Report Author data row budget must be positive.")
        if self.output_review_provider != "codex-local":
            raise ValueError(
                "The Output review provider is locked to codex-local; "
                f"unsupported provider: {self.output_review_provider}."
            )

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            environment=os.getenv("MRA_ENVIRONMENT", "development"),
            runtime_dir=Path(os.getenv("MRA_RUNTIME_DIR", "runtime")),
            max_upload_mb=int(os.getenv("MRA_MAX_UPLOAD_MB", "100")),
            # Provider selection is no longer configurable at runtime. Keep
            # the field on Settings only so tests can inject their fake port.
            llm_provider="deepseek",
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", ""),
            openai_endpoint=os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_endpoint=os.getenv(
                "DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions"
            ),
            data_ai_model=os.getenv("MRA_DATA_AI_MODEL", ""),
            analysis_ai_model=os.getenv("MRA_ANALYSIS_AI_MODEL", ""),
            report_author_model=os.getenv("MRA_REPORT_AUTHOR_MODEL", ""),
            report_author_max_output_tokens=int(
                os.getenv("MRA_REPORT_AUTHOR_MAX_OUTPUT_TOKENS", "12000")
            ),
            report_author_max_data_rows=int(os.getenv("MRA_REPORT_AUTHOR_MAX_DATA_ROWS", "2000")),
            stage_ai_max_attempts=int(os.getenv("MRA_STAGE_AI_MAX_ATTEMPTS", "2")),
            stage_ai_timeout_seconds=float(os.getenv("MRA_STAGE_AI_TIMEOUT_SECONDS", "45")),
            stage_ai_max_prompt_chars=int(os.getenv("MRA_STAGE_AI_MAX_PROMPT_CHARS", "250000")),
            stage_ai_max_output_tokens=int(os.getenv("MRA_STAGE_AI_MAX_OUTPUT_TOKENS", "4000")),
            output_review_provider=(
                os.getenv("MRA_OUTPUT_REVIEW_PROVIDER", "codex-local").strip() or "codex-local"
            ),
            output_review_model=os.getenv("MRA_OUTPUT_REVIEW_MODEL", ""),
            output_review_codex_bin=os.getenv("MRA_OUTPUT_REVIEW_CODEX_BIN", "codex"),
            output_review_timeout_seconds=float(
                os.getenv("MRA_OUTPUT_REVIEW_TIMEOUT_SECONDS", "120")
            ),
            planning_max_attempts=int(os.getenv("MRA_PLANNING_MAX_ATTEMPTS", "2")),
            planning_timeout_seconds=float(os.getenv("MRA_PLANNING_TIMEOUT_SECONDS", "45")),
            planning_max_data_rows=int(os.getenv("MRA_PLANNING_MAX_DATA_ROWS", "2000")),
            planning_max_prompt_chars=int(os.getenv("MRA_PLANNING_MAX_PROMPT_CHARS", "250000")),
            planning_max_output_tokens=int(os.getenv("MRA_PLANNING_MAX_OUTPUT_TOKENS", "4000")),
            ai_data_access_enabled=os.getenv("MRA_AI_DATA_ACCESS", "true").lower()
            in {"1", "true", "yes"},
            ai_data_page_size=int(os.getenv("MRA_AI_DATA_PAGE_SIZE", "200")),
            ai_remote_user_data_allowed=os.getenv("MRA_AI_REMOTE_USER_DATA_ALLOWED", "true").lower()
            in {"1", "true", "yes"},
            ai_remote_licensed_data_allowed=os.getenv(
                "MRA_AI_REMOTE_LICENSED_DATA_ALLOWED", "false"
            ).lower()
            in {"1", "true", "yes"},
            graph_orphan_timeout_seconds=int(os.getenv("MRA_GRAPH_ORPHAN_TIMEOUT_SECONDS", "300")),
        )
