import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.concurrency import run_in_threadpool

from app.core.errors.exceptions import DomainException
from app.domains.folios.application.use_cases import (
    DeleteFolioUseCase,
    GetFolioDiagnosticsUseCase,
    GetFolioFillLogUseCase,
    GetFolioPageImageUseCase,
    GetFolioUseCase,
    ListFoliosUseCase,
    RequestReprocessUseCase,
    ReviewFolioUseCase,
    UploadFolioUseCase,
)
from app.domains.folios.domain.entities.folio import Folio
from app.domains.folios.infrastructure.ws_connection_manager import FoliosConnectionManager
from app.domains.folios.presentation.deps import (
    get_connection_manager,
    get_delete_folio_use_case,
    get_folio_diagnostics_use_case,
    get_folio_fill_log_use_case,
    get_folio_page_image_use_case,
    get_folio_use_case,
    get_list_folios_use_case,
    get_request_reprocess_use_case,
    get_review_folio_use_case,
    get_upload_folio_use_case,
    run_process_folio,
)
from app.domains.folios.presentation.schemas.folio_schema import (
    FolioDetail,
    FolioListItem,
    FolioPageItem,
    FolioReviewRequest,
)
from app.domains.security.contracts import UserProfile, get_current_user, verify_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/folios", tags=["Folios"])


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Timestamps are stored as UTC in `timestamp without time zone` columns and
    come back naive; without an explicit offset the browser would read them as
    local (Bolivia) time and show them 4 hours off."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _to_list_item(f: Folio) -> FolioListItem:
    return FolioListItem(
        id=f.id,
        status=f.status,
        matricula=f.matricula,
        page_count=len(f.pages),
        created_at=_utc(f.created_at),
        updated_at=_utc(f.updated_at),
        processed_at=_utc(f.processed_at),
        confirmed_at=_utc(f.confirmed_at),
        error_message=f.error_message,
    )


def _to_detail(f: Folio) -> FolioDetail:
    return FolioDetail(
        **_to_list_item(f).model_dump(),
        pages=[
            FolioPageItem(
                page_index=p.page_index, rotation_deg=p.rotation_deg, detected_page_number=p.detected_page_number
            )
            for p in f.pages
        ],
        extracted_data=f.extracted_data,
        reviewed_data=f.reviewed_data,
        data=f.current_data,
        confirmed_by_sub=f.confirmed_by_sub,
    )


async def _process_and_notify(folio_id: str, manager: FoliosConnectionManager) -> None:
    """Background task: the pipeline is blocking (HTTP calls to the OCR service,
    OpenCV), so it runs in the threadpool, not on the event loop."""
    await run_in_threadpool(run_process_folio, folio_id)
    await manager.notify_change()


@router.get("", response_model=List[FolioListItem])
def list_folios(
    use_case: ListFoliosUseCase = Depends(get_list_folios_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """The authenticated user's folios, newest first."""
    return [_to_list_item(f) for f in use_case.execute(user.sub)]


@router.post("", response_model=FolioDetail, status_code=status.HTTP_201_CREATED)
async def upload_folio(
    background: BackgroundTasks,
    pages: List[UploadFile] = File(...),
    use_case: UploadFolioUseCase = Depends(get_upload_folio_use_case),
    manager: FoliosConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Register a folio scanned from the phone (field `pages`, one photo per
    page, scan order) and start extraction in background. Returns right away
    with status `pending`; the list/WS tell when it is done."""
    contents = [((await p.read()), p.content_type or "image/jpeg") for p in pages]
    folio = use_case.execute(contents, user.sub)
    await manager.notify_change()
    background.add_task(_process_and_notify, folio.id, manager)
    return _to_detail(folio)


@router.get("/{folio_id}", response_model=FolioDetail)
def get_folio(
    folio_id: str,
    use_case: GetFolioUseCase = Depends(get_folio_use_case),
    user: UserProfile = Depends(get_current_user),
):
    return _to_detail(use_case.execute(folio_id, user.sub))


@router.get("/{folio_id}/pages/{page_index}")
def get_page_image(
    folio_id: str,
    page_index: int,
    upright: bool = Query(True, description="Copia enderezada por el pipeline (si existe) en vez del original"),
    use_case: GetFolioPageImageUseCase = Depends(get_folio_page_image_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Page image bytes. Requires Bearer -> the web downloads it as a Blob."""
    content, mime = use_case.execute(folio_id, page_index, user.sub, upright)
    return Response(content=content, media_type=mime)


@router.get("/{folio_id}/diagnostics", response_model=List[Dict[str, Any]])
def get_diagnostics(
    folio_id: str,
    use_case: GetFolioDiagnosticsUseCase = Depends(get_folio_diagnostics_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Raw OCR blocks, detected rotation, ruling lines and crop rectangles per
    page -- to understand why a field came out empty or wrong."""
    return use_case.execute(folio_id, user.sub)


@router.get("/{folio_id}/fill-log", response_model=Dict[str, Any])
def get_fill_log(
    folio_id: str,
    use_case: GetFolioFillLogUseCase = Depends(get_folio_fill_log_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """How each field was filled by the last extraction: OCR text behind every
    header value, how every column A line was classified, what the LLM
    proposed and what was kept. {} if the folio has no log yet."""
    return use_case.execute(folio_id, user.sub)


@router.put("/{folio_id}", response_model=FolioDetail)
async def review_folio(
    folio_id: str,
    body: FolioReviewRequest,
    use_case: ReviewFolioUseCase = Depends(get_review_folio_use_case),
    manager: FoliosConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Save the reviewer's corrected JSON; `confirm: true` also marks it confirmed."""
    folio = use_case.execute(folio_id, user.sub, body.data, body.confirm)
    await manager.notify_change()
    return _to_detail(folio)


@router.post("/{folio_id}/reprocess", response_model=FolioDetail, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_folio(
    folio_id: str,
    background: BackgroundTasks,
    use_case: RequestReprocessUseCase = Depends(get_request_reprocess_use_case),
    manager: FoliosConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Run extraction again (e.g. after a failure because the OCR service was down)."""
    folio = use_case.execute(folio_id, user.sub)
    await manager.notify_change()
    background.add_task(_process_and_notify, folio.id, manager)
    return _to_detail(folio)


@router.delete("/{folio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folio(
    folio_id: str,
    use_case: DeleteFolioUseCase = Depends(get_delete_folio_use_case),
    manager: FoliosConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    use_case.execute(folio_id, user.sub)
    await manager.notify_change()


@router.websocket("/ws")
async def folios_ws(
    websocket: WebSocket,
    manager: FoliosConnectionManager = Depends(get_connection_manager),
):
    """Change notifications (new folio, processing finished, review saved).
    Token via query string: the browser WebSocket API cannot send headers."""
    token = websocket.query_params.get("token")
    try:
        verify_token(token or "")
    except DomainException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception:
        logger.exception("Unexpected error validating the folios WS token.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
