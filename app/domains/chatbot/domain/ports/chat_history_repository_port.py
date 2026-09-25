from abc import ABC, abstractmethod
from typing import List, Optional

from app.domains.chatbot.domain.entities.conversation import ChatMessage


class ChatHistoryRepositoryPort(ABC):
    """Port for conversation persistence. Every method is scoped by `user_sub`
    (the Keycloak `sub`) so one person's conversation is never visible to, or
    replayable by, another — see AnswerQuestionUseCase for why this exists:
    unlike the ported prototype, the client never supplies its own transcript."""

    @abstractmethod
    def list_messages(self, conversation_id: str, user_sub: str) -> List[ChatMessage]:
        """Full turn-by-turn history of a conversation, oldest first."""

    @abstractmethod
    def end_read(self) -> None:
        """Close the transaction a read left open and hand the connection back.
        Reads start a transaction too, and one held open across a slow call to an
        external engine keeps its locks -- and a pooled connection -- for the whole
        wait, which is what once left this database unable to answer."""

    @abstractmethod
    def add_message(self, message: ChatMessage) -> ChatMessage:
        """Persists one turn and returns it with its assigned id."""

    @abstractmethod
    def get_last_detected_procedure_id(self, conversation_id: str, user_sub: str) -> Optional[str]:
        """Most recent non-null detected_procedure_id in the conversation — lets a
        follow-up question ('¿y cuánto cuesta?') resolve against the procedure
        already being discussed, same as the prototype's session-memory fallback."""

    @abstractmethod
    def set_feedback(self, message_id: str, feedback: str, comment: Optional[str]) -> bool:
        """True if a message with that id existed and was updated."""

    @abstractmethod
    def list_feedback(self) -> List[ChatMessage]:
        """Every message that has feedback set, newest first (admin dashboard)."""
