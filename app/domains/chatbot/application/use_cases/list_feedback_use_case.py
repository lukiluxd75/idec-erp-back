from typing import List

from app.domains.chatbot.domain.entities.conversation import ChatMessage
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort


class ListFeedbackUseCase:
    """Use case: every message that has feedback set, for the admin dashboard."""

    def __init__(self, chat_history_repository: ChatHistoryRepositoryPort):
        self._history = chat_history_repository

    def execute(self) -> List[ChatMessage]:
        return self._history.list_feedback()
