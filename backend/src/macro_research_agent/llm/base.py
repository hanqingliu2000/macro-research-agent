from __future__ import annotations

from pydantic import BaseModel


class ClarificationQuestion(BaseModel):
    question_id: str
    prompt: str
    reason: str
    required: bool = True
