import json
import uuid
from typing import Optional

from app.domains.chatbot.domain.entities.conversation import ChatMessage, ProcedureMatch
from app.domains.chatbot.domain.exceptions import EmptyUserMessageException
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.domain.services.prompt_builder import build_system_prompt
from app.domains.chatbot.domain.services.similarity import find_best_match

_AUDIT_REQUIRED_KEYS = {"estado", "documentos_presentes", "documentos_faltantes", "observaciones"}


def _normalize_if_audit_json(reply: str) -> str:
    """If the model answered with the document-audit JSON shape the system
    prompt asks for, re-serialize it (drops stray whitespace/formatting); any
    other reply -- including malformed JSON -- passes through untouched as
    Markdown, same fallback behavior as the ported prototype."""
    stripped = reply.strip()
    if not stripped.startswith("{"):
        return reply
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return reply
    if not isinstance(data, dict) or not _AUDIT_REQUIRED_KEYS.issubset(data.keys()):
        return reply
    return json.dumps(data, ensure_ascii=False)


class AnswerQuestionUseCase:
    """Use case: answer one chat turn. Deliberate deviation from the ported
    prototype (see the integration plan): the client sends only the new
    message, never a transcript -- the server reconstructs history from
    chat_messages by conversation_id + user_sub, so a citizen cannot forge past
    turns or inject arbitrary context into the prompt."""

    def __init__(
        self,
        procedure_repository: ProcedureRepositoryPort,
        chat_history_repository: ChatHistoryRepositoryPort,
        chat_engine: ChatEnginePort,
        match_threshold: float,
    ):
        self._procedures = procedure_repository
        self._history = chat_history_repository
        self._engine = chat_engine
        self._threshold = match_threshold

    def execute(self, conversation_id: Optional[str], message: str, user_sub: str) -> ChatMessage:
        message = (message or "").strip()
        if not message:
            raise EmptyUserMessageException("El mensaje no puede estar vacío.")

        conversation_id = conversation_id or str(uuid.uuid4())

        query_vector = self._engine.embed(message)
        embeddings = self._procedures.list_all_embeddings()
        match = find_best_match(query_vector, embeddings, self._threshold)

        # Session-memory fallback: a vague follow-up ("¿y cuánto cuesta?") with no
        # match of its own resolves against whatever procedure this conversation
        # was already discussing -- same fallback the prototype used.
        if not match.is_found:
            last_id = self._history.get_last_detected_procedure_id(conversation_id, user_sub)
            if last_id:
                match = ProcedureMatch(is_found=True, score=1.0, procedure_id=last_id)

        self._history.add_message(
            ChatMessage(
                id=None,
                conversation_id=conversation_id,
                user_sub=user_sub,
                role="user",
                content=message,
                detected_procedure_id=match.procedure_id if match.is_found else None,
                match_score=match.score,
                is_unanswered=not match.is_found,
            )
        )

        procedure = self._procedures.get_by_id(match.procedure_id) if match.is_found else None
        institutional_context = self._procedures.get_institutional_context()
        system_prompt = build_system_prompt(institutional_context, procedure)

        history = self._history.list_messages(conversation_id, user_sub)
        engine_messages = [{"role": m.role, "content": m.content} for m in history]
        reply = self._engine.chat(system_prompt, engine_messages)
        reply = _normalize_if_audit_json(reply)

        return self._history.add_message(
            ChatMessage(
                id=None,
                conversation_id=conversation_id,
                user_sub=user_sub,
                role="assistant",
                content=reply,
                detected_procedure_id=match.procedure_id if match.is_found else None,
            )
        )
