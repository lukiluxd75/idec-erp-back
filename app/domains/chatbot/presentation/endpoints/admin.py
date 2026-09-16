from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from app.domains.chatbot.application.use_cases import (
    IngestProcedureUseCase,
    ListFeedbackUseCase,
    ListProceduresUseCase,
    ReindexEmbeddingsUseCase,
    UpdateProcedureUseCase,
)
from app.domains.chatbot.domain.entities.procedure import Procedure
from app.domains.chatbot.presentation.deps import (
    get_ingest_procedure_use_case,
    get_list_feedback_use_case,
    get_list_procedures_use_case,
    get_reindex_embeddings_use_case,
    get_update_procedure_use_case,
)
from app.domains.chatbot.presentation.schemas.chat_schema import FeedbackListItem
from app.domains.chatbot.presentation.schemas.procedure_schema import (
    IngestResponse,
    ProcedureListItem,
    ProcedureUpdateRequest,
    ReindexResponse,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Chatbot · Admin"])


def _to_list_item(p: Procedure) -> ProcedureListItem:
    return ProcedureListItem(
        code=p.code,
        name=p.name,
        description=p.description,
        cost_note=p.cost_note,
        amount=p.amount,
        currency=p.currency,
        is_active=p.is_active,
    )


@router.get("/procedures", response_model=List[ProcedureListItem])
def list_procedures(
    use_case: ListProceduresUseCase = Depends(get_list_procedures_use_case),
    _user: UserProfile = Depends(require_permission("chatbot.edit")),
):
    return [_to_list_item(p) for p in use_case.execute()]


@router.put("/procedures/{code}", response_model=ProcedureListItem)
def update_procedure(
    code: str,
    payload: ProcedureUpdateRequest,
    use_case: UpdateProcedureUseCase = Depends(get_update_procedure_use_case),
    user: UserProfile = Depends(require_permission("chatbot.edit")),
):
    procedure = use_case.execute(
        code=code,
        name=payload.name,
        description=payload.description,
        amount=payload.amount,
        currency=payload.currency,
        is_active=payload.is_active,
        actor_user_sub=user.sub,
    )
    return _to_list_item(procedure)


@router.post("/ingests", response_model=IngestResponse)
async def ingest_procedure(
    file: UploadFile = File(...),
    use_case: IngestProcedureUseCase = Depends(get_ingest_procedure_use_case),
    user: UserProfile = Depends(require_permission("chatbot.edit")),
):
    """OCR-scans a normativa document and registers/updates the procedure it
    describes -- see IngestProcedureUseCase for the three-stage pipeline."""
    content = await file.read()
    procedure = use_case.execute(content, user.sub)
    return IngestResponse(
        message=f"Trámite '{procedure.name}' ingresado exitosamente vía OCR.",
        code=procedure.code,
        name=procedure.name,
        requirements=[r.description for r in procedure.requirements],
        cost_note=procedure.cost_note,
    )


@router.get("/feedback", response_model=List[FeedbackListItem])
def list_feedback(
    use_case: ListFeedbackUseCase = Depends(get_list_feedback_use_case),
    # Separado de chatbot.edit a propósito: gestionar el catálogo de trámites y
    # ver la retroalimentación de todos los usuarios son permisos distintos (un
    # rol puede tener uno sin el otro) -- ver seed_permisos_chatbot.sql.
    _user: UserProfile = Depends(require_permission("chatbot.feedback")),
):
    return [
        FeedbackListItem(
            id=m.id,
            conversation_id=m.conversation_id,
            content=m.content,
            created_at=m.created_at,
            detected_procedure_id=m.detected_procedure_id,
            match_score=m.match_score,
            feedback=m.feedback,
            feedback_comment=m.feedback_comment,
        )
        for m in use_case.execute()
    ]


@router.post("/embeddings/reindex", response_model=ReindexResponse)
def reindex_embeddings(
    use_case: ReindexEmbeddingsUseCase = Depends(get_reindex_embeddings_use_case),
    _user: UserProfile = Depends(require_permission("chatbot.edit")),
):
    count = use_case.execute()
    return ReindexResponse(reindexed_count=count)
