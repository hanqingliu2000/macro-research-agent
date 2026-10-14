from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class SessionPaths:
    root: Path

    @classmethod
    def for_session(cls, runtime_root: Path, session_id: UUID) -> SessionPaths:
        return cls(root=runtime_root / "sessions" / str(session_id))

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def normalized(self) -> Path:
        return self.root / "normalized"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def trace_file(self) -> Path:
        return self.root / "trace.jsonl"
