from typing import Any, Dict

from app.domains.chatbot.domain.entities.procedure import Procedure
from app.domains.chatbot.domain.exceptions import DocumentIngestFailedException, InvalidUploadException
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.document_reader_port import DocumentReaderPort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.domain.services.embedding_indexer import reindex_procedure
from app.domains.chatbot.domain.services.prompt_builder import INGEST_SYSTEM_PROMPT


def _validate_extracted_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Loose validation of what the LLM structured the OCR text into -- mirrors
    the ported prototype's NuevoTramiteSchema, but as a plain dict check instead
    of a Pydantic model, since application/ does not depend on the presentation
    layer's schemas (CLAUDE.md §3)."""
    name = str(data.get("nombre_tramite", "")).strip()
    if not name:
        raise DocumentIngestFailedException(
            "El modelo no pudo identificar un nombre de trámite en el documento.", stage="structuring"
        )

    raw_requirements = data.get("requisitos") or []
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise DocumentIngestFailedException(
            "El modelo no pudo identificar requisitos en el documento.", stage="structuring"
        )
    requirements = [r if isinstance(r, str) else str(r) for r in raw_requirements]

    cost_note = str(data.get("costo", "") or "")

    return {"name": name, "requirements": requirements, "cost_note": cost_note}


class IngestProcedureUseCase:
    """Use case: OCR-scan a normativa document and register/update the procedure
    it describes. Three stages (OCR -> LLM structuring -> persist + re-embed),
    each raising a distinct DocumentIngestFailedException.stage on failure --
    same intent as the prototype's per-stage [ETAPA n ...] error messages."""

    def __init__(
        self,
        document_reader: DocumentReaderPort,
        procedure_repository: ProcedureRepositoryPort,
        chat_engine: ChatEnginePort,
        embedding_model: str,
    ):
        self._reader = document_reader
        self._procedures = procedure_repository
        self._engine = chat_engine
        self._embedding_model = embedding_model

    def execute(self, file_bytes: bytes, actor_user_sub: str) -> Procedure:
        if not file_bytes:
            raise InvalidUploadException("El archivo está vacío.")

        raw_text = self._reader.extract_text(file_bytes)
        if not raw_text.strip():
            raise DocumentIngestFailedException(
                "No se pudo extraer texto legible del documento (OCR vacío).", stage="ocr"
            )

        structured = self._engine.extract_json(INGEST_SYSTEM_PROMPT, raw_text)
        fields = _validate_extracted_fields(structured)

        procedure = self._procedures.upsert_from_ingest(
            name=fields["name"],
            requirements=fields["requirements"],
            cost_note=fields["cost_note"],
            actor_user_sub=actor_user_sub,
        )
        reindex_procedure(procedure, self._engine, self._procedures, self._embedding_model)
        return procedure
