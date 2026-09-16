import base64
import uuid
from typing import Optional

from app.domains.chatbot.domain.entities.conversation import ChatMessage
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort
from app.domains.chatbot.domain.services.prompt_builder import VISION_DEFAULT_USER_PROMPT, VISION_SYSTEM_PROMPT


class AnalyzeImageUseCase:
    """Use case: describe/orient on a document photo a citizen attaches to the
    chat (no retrieval, no document-audit JSON -- pure vision Q&A, same scope as
    the ported prototype's /api/vision)."""

    def __init__(self, chat_history_repository: ChatHistoryRepositoryPort, chat_engine: ChatEnginePort):
        self._history = chat_history_repository
        self._engine = chat_engine

    def execute(
        self, conversation_id: Optional[str], image_bytes: bytes, prompt: Optional[str], user_sub: str
    ) -> ChatMessage:
        conversation_id = conversation_id or str(uuid.uuid4())
        user_text = (prompt or "").strip() or VISION_DEFAULT_USER_PROMPT

        self._history.add_message(
            ChatMessage(
                id=None,
                conversation_id=conversation_id,
                user_sub=user_sub,
                role="user",
                content=f"[Imagen adjunta] {user_text}",
            )
        )

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        reply = self._engine.vision(VISION_SYSTEM_PROMPT, user_text, image_b64)

        return self._history.add_message(
            ChatMessage(
                id=None,
                conversation_id=conversation_id,
                user_sub=user_sub,
                role="assistant",
                content=reply,
            )
        )
