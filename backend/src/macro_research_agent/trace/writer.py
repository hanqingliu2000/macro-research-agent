from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from macro_research_agent.trace.events import TraceEvent

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "reasoning_content",
    "chain_of_thought",
}


def redact_trace_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if str(key).lower() in SENSITIVE_KEYS
            else redact_trace_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_trace_value(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:api[_-]?key|password|access[_-]?token|secret)\s*[=:]\s*)[^\s&\"']+",
            r"\1[REDACTED]",
            value,
        )
        value = re.sub(r"(?is)<think>.*?</think>", "[REDACTED]", value)
        return value
    return value


class JsonlTraceWriter:
    """Materialize durable trace events as append-only, redacted JSON Lines."""

    def __init__(
        self,
        path_for_session: Callable[[str], Path],
        redactor: Callable[[Any], Any] = redact_trace_value,
    ) -> None:
        self._path_for_session = path_for_session
        self._redactor = redactor
        self._lock = threading.Lock()

    def append(self, event: TraceEvent) -> None:
        path = self._path_for_session(event.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            self._redactor(event.model_dump(mode="json")),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._lock, path.open("a", encoding="utf-8") as stream:
            stream.write(f"{line}\n")
            stream.flush()

    def recover(self, session_id: str, events: list[TraceEvent]) -> None:
        path = self._path_for_session(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_sequences: set[int] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    existing_sequences.add(int(json.loads(line)["sequence"]))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        missing = [event for event in events if event.sequence not in existing_sequences]
        for event in sorted(missing, key=lambda item: item.sequence):
            self.append(event)
