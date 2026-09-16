import logging
from typing import List

from fastapi import APIRouter, Depends, File, Response, UploadFile, WebSocket, WebSocketDisconnect, status

from app.core.errors.exceptions import DomainException
from app.domains.geoextraction.application.use_cases import (
    CreateCaptureUseCase,
    DiscardCaptureUseCase,
    ListPendingCapturesUseCase,
    GetCaptureImageUseCase,
)
from app.domains.geoextraction.domain.entities.capture import Capture
from app.domains.geoextraction.infrastructure.ws_connection_manager import CapturesConnectionManager
from app.domains.geoextraction.presentation.deps import (
    get_connection_manager,
    get_create_capture_use_case,
    get_discard_capture_use_case,
    get_list_pending_captures_use_case,
    get_capture_image_use_case,
)
from app.domains.geoextraction.presentation.schemas.capture_schema import CaptureListItem
from app.domains.security.contracts import UserProfile, get_current_user, verify_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/captures", tags=["Geoextraction · Captures"])


def _to_list_item(c: Capture) -> CaptureListItem:
    return CaptureListItem(capture_id=c.capture_id, mime=c.mime, created_at=c.created_at)


@router.get("", response_model=List[CaptureListItem])
def list_captures(
    use_case: ListPendingCapturesUseCase = Depends(get_list_pending_captures_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Captures the user sent from the phone that are not yet loaded in the viewer."""
    return [_to_list_item(c) for c in use_case.execute(user.sub)]


@router.post("", response_model=CaptureListItem, status_code=status.HTTP_201_CREATED)
async def create_capture(
    file: UploadFile = File(...),
    use_case: CreateCaptureUseCase = Depends(get_create_capture_use_case),
    manager: CapturesConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Register a photo just taken from the mobile app (mobile geoextract: only
    takes the photo and sends it here — crop, OCR and the rest happen on the web)."""
    content = await file.read()
    capture = use_case.execute(
        content=content, mime=file.content_type or "image/jpeg", user_sub=user.sub
    )
    await manager.notify_change()
    return _to_list_item(capture)


@router.get("/{id_captura}/image")
def get_image(
    id_captura: str,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Image bytes for a capture. Requires Bearer -> cannot be used as a direct
    <img src>; the frontend downloads it as a Blob."""
    content, mime = use_case.execute(id_captura, user.sub)
    return Response(content=content, media_type=mime)


@router.delete("/{id_captura}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_capture(
    id_captura: str,
    use_case: DiscardCaptureUseCase = Depends(get_discard_capture_use_case),
    manager: CapturesConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Remove the capture from the store: the web calls this as soon as it finished
    loading it in the viewer, so it does not reappear in the pending list."""
    use_case.execute(id_captura, user.sub)
    await manager.notify_change()


@router.websocket("/ws")
async def captures_ws(
    websocket: WebSocket,
    manager: CapturesConnectionManager = Depends(get_connection_manager),
):
    """
    Real-time update channel: whenever a new photo arrives from the phone (or one
    is discarded), all connected sockets are notified so they refresh the list
    (see useCapturasUpdates.js on the frontend).

    The browser cannot send the Authorization header on a WebSocket, so the token
    travels via query string and is validated here by hand (contracts.verify_token)
    instead of the Security(HTTPBearer()) dependency used by REST endpoints.
    """
    token = websocket.query_params.get("token")
    try:
        verify_token(token or "")
    except DomainException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception:
        logger.exception("Unexpected error validating the captures WS token.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Client sends nothing on this socket: only used for server -> browser
            # notify. receive_text() detects disconnect (WebSocketDisconnect)
            # without busy-waiting.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
