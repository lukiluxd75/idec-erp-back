from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ChatMessage:
    id: Optional[str]
    conversation_id: str
    user_sub: str
    role: str  # "user" | "assistant" | "system"
    content: str
    detected_procedure_id: Optional[str] = None
    match_score: Optional[float] = None
    is_unanswered: bool = False
    feedback: Optional[str] = None
    feedback_comment: Optional[str] = None
    user_message: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ProcedureMatch:
    """Result of the retrieval step — equivalent of the prototype's SearchResult.
    `is_found` is False both when nothing cleared the similarity threshold and
    when the vector store has nothing indexed yet."""

    is_found: bool
    score: float
    procedure_id: Optional[str] = None
