from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.connection import get_db
from app.domains.chatbot.application.use_cases import (
    AnalyzeImageUseCase,
    AnswerQuestionUseCase,
    IngestJsonProceduresUseCase,
    IngestProcedureUseCase,
    LearnFromFeedbackUseCase,
    ListFeedbackUseCase,
    ListProceduresUseCase,
    ReindexEmbeddingsUseCase,
    SubmitFeedbackUseCase,
    UpdateProcedureUseCase,
)
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.chat_history_repository_port import ChatHistoryRepositoryPort
from app.domains.chatbot.domain.ports.document_reader_port import DocumentReaderPort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.infrastructure.ocr.tesseract_document_reader import TesseractDocumentReader
from app.domains.chatbot.infrastructure.ollama.ollama_chat_engine import OllamaChatEngine
from app.domains.chatbot.infrastructure.sql_chat_history_repository import SqlChatHistoryRepository
from app.domains.chatbot.infrastructure.sql_procedure_repository import SqlProcedureRepository
from app.domains.digitization.contracts import get_borrow_host


def get_procedure_repository(db: Session = Depends(get_db)) -> ProcedureRepositoryPort:
    return SqlProcedureRepository(db=db)


def get_chat_history_repository(db: Session = Depends(get_db)) -> ChatHistoryRepositoryPort:
    return SqlChatHistoryRepository(db=db)


@lru_cache()
def get_chat_engine() -> ChatEnginePort:
    """Reports its calls to digitization (public contract) so the PCs monitor
    shows this host as working while the assistant is answering."""
    return OllamaChatEngine(borrow=get_borrow_host("chatbot").execute)


@lru_cache()
def get_document_reader() -> DocumentReaderPort:
    return TesseractDocumentReader()


def get_answer_question_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
    history: ChatHistoryRepositoryPort = Depends(get_chat_history_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> AnswerQuestionUseCase:
    return AnswerQuestionUseCase(
        procedure_repository=procedures,
        chat_history_repository=history,
        chat_engine=engine,
        match_threshold=settings.CHATBOT_MATCH_THRESHOLD,
    )


def get_analyze_image_use_case(
    history: ChatHistoryRepositoryPort = Depends(get_chat_history_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> AnalyzeImageUseCase:
    return AnalyzeImageUseCase(chat_history_repository=history, chat_engine=engine)


def get_submit_feedback_use_case(
    history: ChatHistoryRepositoryPort = Depends(get_chat_history_repository),
) -> SubmitFeedbackUseCase:
    return SubmitFeedbackUseCase(chat_history_repository=history)


def get_list_procedures_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
) -> ListProceduresUseCase:
    return ListProceduresUseCase(procedure_repository=procedures)


def get_update_procedure_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> UpdateProcedureUseCase:
    return UpdateProcedureUseCase(
        procedure_repository=procedures, chat_engine=engine, embedding_model=settings.CHATBOT_EMBEDDING_MODEL
    )


def get_ingest_procedure_use_case(
    reader: DocumentReaderPort = Depends(get_document_reader),
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> IngestProcedureUseCase:
    return IngestProcedureUseCase(
        document_reader=reader,
        procedure_repository=procedures,
        chat_engine=engine,
        embedding_model=settings.CHATBOT_EMBEDDING_MODEL,
    )


def get_ingest_json_procedures_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> IngestJsonProceduresUseCase:
    return IngestJsonProceduresUseCase(
        procedure_repository=procedures,
        chat_engine=engine,
        embedding_model=settings.CHATBOT_EMBEDDING_MODEL,
    )


def get_list_feedback_use_case(
    history: ChatHistoryRepositoryPort = Depends(get_chat_history_repository),
) -> ListFeedbackUseCase:
    return ListFeedbackUseCase(chat_history_repository=history)


def get_reindex_embeddings_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
    engine: ChatEnginePort = Depends(get_chat_engine),
) -> ReindexEmbeddingsUseCase:
    return ReindexEmbeddingsUseCase(
        procedure_repository=procedures, chat_engine=engine, embedding_model=settings.CHATBOT_EMBEDDING_MODEL
    )


def get_learn_from_feedback_use_case(
    procedures: ProcedureRepositoryPort = Depends(get_procedure_repository),
) -> LearnFromFeedbackUseCase:
    return LearnFromFeedbackUseCase(procedure_repository=procedures)
