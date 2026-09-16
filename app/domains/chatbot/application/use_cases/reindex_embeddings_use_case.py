from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.domain.services.embedding_indexer import reindex_procedure


class ReindexEmbeddingsUseCase:
    """Use case: recompute embeddings for every active procedure. Manual escape
    hatch for bulk fixes (e.g. after changing the embedding model) -- normal
    edits already reindex themselves via UpdateProcedureUseCase/
    IngestProcedureUseCase, this is not required for those to be consistent."""

    def __init__(
        self,
        procedure_repository: ProcedureRepositoryPort,
        chat_engine: ChatEnginePort,
        embedding_model: str,
    ):
        self._procedures = procedure_repository
        self._engine = chat_engine
        self._embedding_model = embedding_model

    def execute(self) -> int:
        # list_active() already loads aliases + search_description, which is all
        # reindexing needs -- no need for a per-procedure get_by_id() round trip.
        procedures = self._procedures.list_active()
        for procedure in procedures:
            reindex_procedure(procedure, self._engine, self._procedures, self._embedding_model)
        return len(procedures)
