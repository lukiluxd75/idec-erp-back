from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Only the new message travels from the client -- never a transcript (see
    AnswerQuestionUseCase for why: the server reconstructs history itself)."""
    conversation_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    response: str


class VisionResponse(BaseModel):
    conversation_id: str
    message_id: str
    response: str


class FeedbackRequest(BaseModel):
    message_id: str
    feedback: Literal["positive", "negative"]
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    success: bool = True
    message: str = "Retroalimentación registrada correctamente."


class LearnRuleRequest(BaseModel):
    rule_text: str

class FeedbackListItem(BaseModel):
    id: str
    conversation_id: str
    content: str
    created_at: Optional[datetime] = None
    detected_procedure_id: Optional[str] = None
    match_score: Optional[float] = None
    feedback: Optional[str] = None
    feedback_comment: Optional[str] = None
    user_message: Optional[str] = None
