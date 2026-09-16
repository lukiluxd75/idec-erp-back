import logging
from typing import List

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, WebSocket, WebSocketDisconnect, status

from app.core.errors.exceptions import DomainException
from app.domains.resolutions.application.use_cases import (
    CreateResolutionUseCase,
    DeleteResolutionUseCase,
    SaveTableUseCase,
    ListResolutionsUseCase,
    GetPageUseCase,
    GetResolutionUseCase,
)
from app.domains.resolutions.domain.entities.resolution import Resolution
from app.domains.resolutions.infrastructure.ws_connection_manager import ResolutionsConnectionManager
from app.domains.resolutions.presentation.deps import (
    get_connection_manager,
    get_create_resolution_use_case,
    get_delete_resolution_use_case,
    get_save_table_use_case,
    get_list_resolutions_use_case,
    get_page_use_case,
    get_resolution_use_case,
)
from app.domains.resolutions.presentation.schemas.resolution_schema import (
    SaveTableRequest,
    PageOut,
    ResolutionDetail,
    ResolutionListItem,
)
from app.domains.security.contracts import UserProfile, get_current_user, verify_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Resoluciones"])


def _to_list_item(r: Resolution) -> ResolutionListItem:
    return ResolutionListItem(
        resolution_id=r.resolution_id,
        name=r.name,
        resolution_number=r.resolution_number,
        status=r.status,
        total_pages=r.total_pages,
        created_at=r.created_at,
    )


def _to_detail(r: Resolution) -> ResolutionDetail:
    return ResolutionDetail(
        resolution_id=r.resolution_id,
        name=r.name,
        resolution_number=r.resolution_number,
        status=r.status,
        total_pages=r.total_pages,
        created_at=r.created_at,
        pages=[PageOut(order_index=p.order_index) for p in r.pages],
        table_data=r.table_data,
    )


@router.get("", response_model=List[ResolutionListItem])
def list_resolutions(
    use_case: ListResolutionsUseCase = Depends(get_list_resolutions_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """List the authenticated user's resolutions, newest first."""
    return [_to_list_item(r) for r in use_case.execute(user.sub)]


@router.post("", response_model=ResolutionDetail, status_code=status.HTTP_201_CREATED)
async def create_resolution(
    name: str = Form(...),
    resolution_number: str = Form(...),
    pages: List[UploadFile] = File(...),
    use_case: CreateResolutionUseCase = Depends(get_create_resolution_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Register a newly scanned resolution together with its page photos, in
    upload order."""
    contents = [((await page.read()), page.content_type or "image/jpeg") for page in pages]
    resolution = use_case.execute(
        name=name, resolution_number=resolution_number, pages=contents, user_sub=user.sub
    )
    await manager.notify_change()
    return _to_detail(resolution)


@router.get("/{resolution_id}", response_model=ResolutionDetail)
def get_resolution(
    resolution_id: str,
    use_case: GetResolutionUseCase = Depends(get_resolution_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Resolution detail: pages and the saved surface table (if OCR already ran/saved)."""
    return _to_detail(use_case.execute(resolution_id, user.sub))


@router.get("/{resolution_id}/pages/{order_index}")
def get_page(
    resolution_id: str,
    order_index: int,
    use_case: GetPageUseCase = Depends(get_page_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Image bytes of a page. Requires Bearer -> cannot be used as a direct
    <img src>; the frontend downloads it as a Blob (see resolutionsApi.pageBlob)."""
    content, content_type = use_case.execute(resolution_id, order_index, user.sub)
    return Response(content=content, media_type=content_type)


@router.put("/{resolution_id}/table", response_model=ResolutionDetail)
async def save_table(
    resolution_id: str,
    payload: SaveTableRequest,
    use_case: SaveTableUseCase = Depends(get_save_table_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Save the surface table (reviewed/edited) and the flow status —
    'Guardar borrador' or 'Generar Excel' from ResolutionPage."""
    resolution = use_case.execute(resolution_id, payload.table_data, payload.status, user.sub)
    await manager.notify_change()
    return _to_detail(resolution)


@router.delete("/{resolution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resolution(
    resolution_id: str,
    use_case: DeleteResolutionUseCase = Depends(get_delete_resolution_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    use_case.execute(resolution_id, user.sub)
    await manager.notify_change()


@router.websocket("/ws")
async def resolutions_ws(
    websocket: WebSocket,
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
):
    """
    Real-time update channel: whenever someone creates/edits/deletes a
    resolution (from the phone or another tab), all connected sockets are
    notified so they can refresh (see useResolucionesUpdates.js on the frontend).

    The browser cannot send an Authorization header on a WebSocket, so the token
    travels as a query string and is validated here by hand (contracts.verify_token)
    instead of the Security(HTTPBearer()) dependency used by REST endpoints.
    """
    token = websocket.query_params.get("token")
    try:
        verify_token(token or "")
    except DomainException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception:
        logger.exception("Error inesperado validando el token del WS de resoluciones.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await manager.connect(websocket)
    try:
        while True:
            # The client sends nothing on this socket: it is only used for
            # server -> browser notifications. receive_text() detects disconnect
            # (WebSocketDisconnect) without busy-waiting.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
