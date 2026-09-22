from typing import Any, Dict, List

from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.domain.services.embedding_indexer import reindex_procedure


class IngestJsonProceduresUseCase:
    """Bulk-load procedures from a structured tramites_data.json file.

    Each entry in the JSON array must follow the schema:
    {
        "id_tramite": str,          # used as the canonical procedure code
        "nombre_tramite": str,
        "descripcion_busqueda": str,
        "costo": str,
        "leyes_asociadas": [str],
        "requisitos": [{"nombre": str, "obligatorio": bool, "condicion"?: str}]
    }

    The operation is fully idempotent: re-running it with the same JSON
    produces the same DB state.  Requirements are fully replaced on each run,
    same as IngestProcedureUseCase does for OCR ingests.

    Follows the same port pattern as every other use case in this domain
    (application/ must not import from infrastructure/ — CLAUDE.md §3).
    """

    def __init__(
        self,
        procedure_repository: ProcedureRepositoryPort,
        chat_engine: ChatEnginePort,
        embedding_model: str,
    ) -> None:
        self._procedures = procedure_repository
        self._engine = chat_engine
        self._embedding_model = embedding_model

    def execute(self, entries: List[Dict[str, Any]], actor_user_sub: str) -> int:
        """Persist all entries and rebuild embeddings.

        Returns the number of procedures upserted.
        """
        count = 0
        for entry in entries:
            id_tramite = str(entry.get("id_tramite", "")).strip()
            nombre_tramite = str(entry.get("nombre_tramite", "")).strip()
            if not id_tramite or not nombre_tramite:
                continue  # skip malformed entries silently

            procedure = self._procedures.upsert_from_json(
                id_tramite=id_tramite,
                nombre_tramite=nombre_tramite,
                descripcion_busqueda=str(entry.get("descripcion_busqueda", "") or ""),
                costo=str(entry.get("costo", "") or ""),
                leyes_asociadas=list(entry.get("leyes_asociadas", []) or []),
                requisitos=list(entry.get("requisitos", []) or []),
                actor_user_sub=actor_user_sub,
            )
            reindex_procedure(procedure, self._engine, self._procedures, self._embedding_model)
            count += 1

        return count
