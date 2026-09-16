from typing import Optional

from app.domains.chatbot.domain.exceptions import ChatMessageNotFoundException
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort


class SubmitFeedbackUseCase:
    """Use case: record a thumbs up/down (with an optional comment) on a bot reply."""

    def __init__(self, chat_history_repository: ChatHistoryRepositoryPort):
        self._history = chat_history_repository

    def execute(self, message_id: str, feedback: str, comment: Optional[str]) -> None:
        updated = self._history.set_feedback(message_id, feedback, comment)
        if not updated:
            raise ChatMessageNotFoundException("El mensaje indicado no existe.")
