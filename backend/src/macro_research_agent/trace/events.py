from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Actor(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    CONNECTOR = "connector"


class TraceEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str
    sequence: int = Field(ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str
    actor: Actor
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_event_id: UUID | None = None
