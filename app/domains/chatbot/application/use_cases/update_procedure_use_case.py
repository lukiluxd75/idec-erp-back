import logging
from typing import Optional

from app.domains.chatbot.domain.entities.procedure import Procedure
from app.domains.chatbot.domain.exceptions import ChatEngineUnavailableException, ProcedureNotFoundException
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.domain.services.embedding_indexer import reindex_procedure

logger = logging.getLogger("uvicorn.error")


class UpdateProcedureUseCase:
    """Use case: admin edit of a procedure's editable fields. Recomputes its
    embeddings in the same call -- the fix for the ported prototype's bug where
    renaming a procedure from the admin panel left its ChromaDB vector pointing
    at the old name (see the integration plan).

    Reindexing is best-effort: the field edit itself (name/description/amount/
    currency/is_active) has nothing to do with the LLM being reachable, and the
    external Ollama host is not wired up yet (see the integration plan) -- the
    admin catalog has to stay usable while that is true. If embedding fails, the
    edit is still saved and returned; only the vectors stay stale until the next
    successful reindex (manual retry, another edit once Ollama is back, or
    POST /embeddings/reindex)."""

    def __init__(
        self,
        procedure_repository: ProcedureRepositoryPort,
        chat_engine: ChatEnginePort,
        embedding_model: str,
    ):
        self._procedures = procedure_repository
        self._engine = chat_engine
        self._embedding_model = embedding_model

    def execute(
        self,
        code: str,
        name: str,
        description: Optional[str],
        amount: Optional[float],
        currency: Optional[str],
        is_active: bool,
        actor_user_sub: str,
    ) -> Procedure:
        procedure = self._procedures.update_admin_fields(
            code, name, description, amount, currency, is_active, actor_user_sub
        )
        if procedure is None:
            raise ProcedureNotFoundException(f"No existe un trámite con código '{code}'.")

        try:
            reindex_procedure(procedure, self._engine, self._procedures, self._embedding_model)
        except ChatEngineUnavailableException as exc:
            logger.warning(
                "No se pudo reindexar el trámite '%s' tras editarlo (motor de IA no disponible): %s",
                code,
                exc.message,
            )

        return procedure
