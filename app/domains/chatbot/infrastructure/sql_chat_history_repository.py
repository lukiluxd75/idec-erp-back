import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.domains.chatbot.domain.entities.conversation import ChatMessage
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort
from app.domains.chatbot.infrastructure.models import ChatMessageModel


def _to_entity(m: ChatMessageModel) -> ChatMessage:
    return ChatMessage(
        id=str(m.id),
        conversation_id=str(m.conversation_id),
        user_sub=m.user_sub,
        role=m.role,
        content=m.content,
        detected_procedure_id=str(m.detected_procedure_id) if m.detected_procedure_id else None,
        match_score=float(m.match_score) if m.match_score is not None else None,
        is_unanswered=m.is_unanswered,
        feedback=m.feedback,
        feedback_comment=m.feedback_comment,
        created_at=m.created_at,
    )


class SqlChatHistoryRepository(ChatHistoryRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def list_messages(self, conversation_id: str, user_sub: str) -> List[ChatMessage]:
        models = (
            self._db.query(ChatMessageModel)
            .filter(
                ChatMessageModel.conversation_id == uuid.UUID(conversation_id),
                ChatMessageModel.user_sub == user_sub,
            )
            .order_by(ChatMessageModel.created_at)
            .all()
        )
        return [_to_entity(m) for m in models]

    def add_message(self, message: ChatMessage) -> ChatMessage:
        m = ChatMessageModel(
            conversation_id=uuid.UUID(message.conversation_id),
            user_sub=message.user_sub,
            role=message.role,
            content=message.content,
            detected_procedure_id=uuid.UUID(message.detected_procedure_id)
            if message.detected_procedure_id
            else None,
            match_score=message.match_score,
            is_unanswered=message.is_unanswered,
        )
        self._db.add(m)
        self._db.commit()
        self._db.refresh(m)
        return _to_entity(m)

    def get_last_detected_procedure_id(self, conversation_id: str, user_sub: str) -> Optional[str]:
        m = (
            self._db.query(ChatMessageModel)
            .filter(
                ChatMessageModel.conversation_id == uuid.UUID(conversation_id),
                ChatMessageModel.user_sub == user_sub,
                ChatMessageModel.detected_procedure_id.isnot(None),
            )
            .order_by(ChatMessageModel.created_at.desc())
            .first()
        )
        return str(m.detected_procedure_id) if m else None

    def set_feedback(self, message_id: str, feedback: str, comment: Optional[str]) -> bool:
        try:
            mid = uuid.UUID(message_id)
        except (ValueError, TypeError):
            return False
        m = self._db.query(ChatMessageModel).filter(ChatMessageModel.id == mid).first()
        if m is None:
            return False
        m.feedback = feedback
        m.feedback_comment = comment
        self._db.commit()
        return True

    def list_feedback(self) -> List[ChatMessage]:
        models = (
            self._db.query(ChatMessageModel)
            .filter(ChatMessageModel.feedback.isnot(None))
            .order_by(ChatMessageModel.created_at.desc())
            .all()
        )
        return [_to_entity(m) for m in models]
