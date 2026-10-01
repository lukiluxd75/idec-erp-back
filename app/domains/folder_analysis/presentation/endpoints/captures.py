from typing import List

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.domains.folder_analysis.domain.entities import CaptureVariant

from app.domains.folder_analysis.application.use_cases import (
    ClearInboxUseCase,
    DeleteCaptureUseCase,
    GetCaptureImageUseCase,
    ListInboxUseCase,
    UploadCapturesUseCase,
)
from app.core.presence import CHANNEL_FOLDER_ANALYSIS, CHANNEL_SESSION, SqlPresenceStore
from app.domains.folder_analysis.presentation.deps import (
    get_capture_image_use_case,
    get_clear_inbox_use_case,
    get_delete_capture_use_case,
    get_list_inbox_use_case,
    get_presence_store,
    get_upload_captures_use_case,
    record_mobile_presence,
)
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import (
    CaptureOut,
    ClearedInboxOut,
    PhonePresenceOut,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/captures", tags=["Folder analysis · Captures"])


@router.post("", response_model=List[CaptureOut], status_code=status.HTTP_201_CREATED)
def upload_captures(
    files: List[UploadFile] = File(...),
    use_case: UploadCapturesUseCase = Depends(get_upload_captures_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
    _presence: None = Depends(record_mobile_presence),
):
    """Mobile app entry point: one or more photos (multipart field `files`) that
    land unsorted in the architect's inbox on the web.

    Also the main "phone connected" signal for this module: an upload arriving
    from a phone refreshes that account's presence (see record_mobile_presence)."""
    contents = [(f.file.read(), f.content_type or "", f.filename or "") for f in files]
    return [CaptureOut.from_entity(c) for c in use_case.execute(contents, user.sub)]


@router.get("", response_model=List[CaptureOut])
def list_inbox(
    use_case: ListInboxUseCase = Depends(get_list_inbox_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Photos not yet sorted into a document, newest first."""
    return [CaptureOut.from_entity(c) for c in use_case.execute(user.sub)]


# A photo never changes once it is uploaded, so the browser may keep any of its
# copies for as long as it likes: turning a page back, or coming back to the
# screen tomorrow, costs nothing.
IMMUTABLE_CACHE = "private, max-age=604800, immutable"


def _cached_image(request: Request, use_case: GetCaptureImageUseCase, capture_id: str, user_sub: str, variant: str):
    """The photo's copy, or 304 when the browser already has it. The tag is the
    capture and the copy asked for: neither ever changes."""
    etag = f'"{capture_id}-{variant}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE})
    content, mime = use_case.execute(capture_id, user_sub, variant)
    return Response(content=content, media_type=mime, headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE})


@router.get("/{capture_id}/image")
def get_image(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The photo as it was uploaded -- several megabytes. Only the viewer asks
    for it, and only when the architect zooms past what the preview shows."""
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.ORIGINAL)


@router.get("/{capture_id}/preview")
def get_preview(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Web-sized copy: what the review screen opens with."""
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.PREVIEW)


@router.get("/{capture_id}/thumbnail")
def get_thumbnail(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.THUMBNAIL)


@router.get("/presence", response_model=PhonePresenceOut)
def get_presence(
    presence: SqlPresenceStore = Depends(get_presence_store),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Whether this account has a phone connected right now, for the indicator
    on the web (PhoneConnectedBadge).

    Se enciende por cualquiera de dos motivos, y le basta uno:

      * CHANNEL_SESSION -- el arquitecto inicio sesion en la app movil y no la
        ha cerrado. Es el motivo principal: dura toda la sesion, asi que el
        indicador queda encendido tambien mientras no esta subiendo nada.
      * CHANNEL_FOLDER_ANALYSIS -- la app subio fotos hace poco. Respaldo para
        una app que todavia no llame a /api/presence/session.

    Answered from Postgres, so it does not matter which of the four workers
    takes the request -- the previous per-process design made the equivalent
    endpoints in geoextraction and resolutions answer True on one worker and
    False on the other three, and the badge flipped every few seconds.
    """
    return PhonePresenceOut(
        mobile_connected=presence.is_mobile_present_any(
            user.sub, (CHANNEL_SESSION, CHANNEL_FOLDER_ANALYSIS)
        )
    )


@router.post("/heartbeat", response_model=PhonePresenceOut)
def heartbeat(
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
    _presence: None = Depends(record_mobile_presence),
    presence: SqlPresenceStore = Depends(get_presence_store),
):
    """Optional for the mobile app: keeps "phone connected" lit while the
    architect has the module open but is not uploading yet.

    Without it the indicator still works -- every upload refreshes presence and
    it lasts ACTIVITY_TTL (3 min) -- but it goes grey during a long gap between
    batches. Calling this once a minute keeps it accurate. Costs one row
    update; from a desktop User-Agent it is a no-op (see record_mobile_presence).
    """
    return PhonePresenceOut(
        mobile_connected=presence.is_mobile_present_any(
            user.sub, (CHANNEL_SESSION, CHANNEL_FOLDER_ANALYSIS)
        )
    )


@router.delete("", response_model=ClearedInboxOut)
def clear_inbox(
    use_case: ClearInboxUseCase = Depends(get_clear_inbox_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Empties the bandeja: every photo still unsorted is deleted for good.
    The ones already classified in a document are left alone."""
    return ClearedInboxOut(deleted=use_case.execute(user.sub))


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(
    capture_id: str,
    use_case: DeleteCaptureUseCase = Depends(get_delete_capture_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    use_case.execute(capture_id, user.sub)
