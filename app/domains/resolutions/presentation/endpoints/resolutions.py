import logging
from typing import List

from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.concurrency import run_in_threadpool

from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.core.errors.exceptions import DomainException
from app.core.presence import CHANNEL_RESOLUTIONS, SqlPresenceStore
from app.core.presence.socket import SocketPresence
from app.core.utils.user_agent import is_mobile_user_agent
from app.domains.resolutions.application.use_cases import (
    AddPlanPagesUseCase,
    CreateResolutionUseCase,
    DeletePlanPageUseCase,
    DeleteResolutionUseCase,
    RequestPlantaDetectionUseCase,
    SaveTableUseCase,
    SetPlanPagePlantasUseCase,
    GetPlanPageUseCase,
    ListResolutionsUseCase,
    GetPageUseCase,
    GetResolutionUseCase,
)
from app.domains.resolutions.domain.entities.resolution import PlanPage, Resolution
from app.domains.resolutions.infrastructure.ws_connection_manager import ResolutionsConnectionManager
from app.domains.resolutions.presentation.deps import (
    get_add_plan_pages_use_case,
    get_connection_manager,
    get_create_resolution_use_case,
    get_delete_plan_page_use_case,
    get_delete_resolution_use_case,
    get_save_table_use_case,
    get_get_plan_page_use_case,
    get_list_resolutions_use_case,
    get_page_use_case,
    get_request_planta_detection_use_case,
    get_resolution_use_case,
    get_set_plan_page_plantas_use_case,
    run_detect_plan_page_planta,
)
from app.domains.resolutions.presentation.schemas.resolution_schema import (
    SaveTableRequest,
    PageOut,
    PlanPageOut,
    ResolutionDetail,
    ResolutionListItem,
    SetPlanPagePlantasRequest,
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


def _to_plan_page_out(p: PlanPage) -> PlanPageOut:
    return PlanPageOut(
        order_index=p.order_index,
        planta=p.planta,
        plantas=p.plantas,
        planta_status=p.planta_status,
        planta_title=p.planta_title,
        planta_detection=p.planta_detection,
        source=p.source,
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
        plan_pages=[_to_plan_page_out(p) for p in r.plan_pages],
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


@router.get("/presence")
def get_presence(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    """Polled every few seconds by useResolutionsUpdates.js to keep
    PhoneConnectedBadge accurate.

    Se enciende tanto si la app movil tiene sesion abierta (CHANNEL_SESSION,
    que dura toda la sesion) como si hay un socket vivo de este modulo -- ver
    SqlPresenceStore.is_phone_connected.

    Answered from the shared presence store (app/core/presence), not from this
    worker's socket registry. That was the bug: the phone's socket lives on ONE
    of the four workers while this endpoint is load-balanced per request, so
    three polls out of four used to answer "not connected" and the badge
    alternated every 3 seconds forever.

    Declared before GET /{resolution_id} on purpose: routes are matched in
    registration order, so "presence" would otherwise be swallowed as a
    resolution_id by that path-param route instead of reaching this one.
    """
    return {"mobile_connected": SqlPresenceStore(db).is_phone_connected(user.sub, CHANNEL_RESOLUTIONS)}


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


# Separa varias plantas de una misma foto en el campo `plantas` ("PLANTA 2º PISO|PLANTA 3º PISO|PLANTA 4º PISO").
SEPARADOR_PLANTAS = "|"


async def _detect_and_notify(resolution_id: str, order_index: int, manager: ResolutionsConnectionManager) -> None:
    """Background task: read the plan title (OCR, blocking I/O -> threadpool)
    and tell the open screens that the page changed."""
    try:
        await run_in_threadpool(run_detect_plan_page_planta, resolution_id, order_index)
    except Exception:
        logger.exception("resolutions: falló la detección de planta de %s/%s", resolution_id, order_index)
    await manager.notify_change()


@router.post("/{resolution_id}/plan-pages", response_model=ResolutionDetail, status_code=status.HTTP_201_CREATED)
async def add_plan_pages(
    resolution_id: str,
    background: BackgroundTasks,
    pages: List[UploadFile] = File(...),
    plantas: Optional[List[str]] = Form(None),
    source: str = Form("app"),
    use_case: AddPlanPagesUseCase = Depends(get_add_plan_pages_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Attach floor-plan photos to a resolution. `plantas` (optional) goes one
    per photo, in order: one planta, several separated by "|" (a sheet valid
    for several floors), or "" -- and then the planta is read in background
    from the plan title ("PLANTA TIPO 2° - 4° PISO"); the page shows up with
    planta_status "detectando" and the WS tells when it is done.
    Same endpoint for the mobile app and the web upload (see `source`) — no
    separate code path per channel, just metadata about who called it."""
    plantas = plantas or [""] * len(pages)
    if len(pages) != len(plantas):
        raise DomainException(f"Se recibieron {len(pages)} fotos pero {len(plantas)} plantas.")
    contents = [
        (
            (await page.read()),
            page.content_type or "image/jpeg",
            [p.strip() for p in (planta or "").split(SEPARADOR_PLANTAS) if p.strip()],
        )
        for page, planta in zip(pages, plantas)
    ]
    resolution, pendientes = use_case.execute(
        resolution_id=resolution_id, pages=contents, source=source, user_sub=user.sub
    )
    await manager.notify_change()
    for order_index in pendientes:
        background.add_task(_detect_and_notify, resolution_id, order_index, manager)
    return _to_detail(resolution)


@router.put("/{resolution_id}/plan-pages/{order_index}/plantas", response_model=PlanPageOut)
async def set_plan_page_plantas(
    resolution_id: str,
    order_index: int,
    payload: SetPlanPagePlantasRequest,
    use_case: SetPlanPagePlantasUseCase = Depends(get_set_plan_page_plantas_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Assign by hand the planta(s) of a plan page (web correction)."""
    page = use_case.execute(resolution_id, order_index, payload.plantas, user.sub)
    await manager.notify_change()
    return _to_plan_page_out(page)


@router.post(
    "/{resolution_id}/plan-pages/{order_index}/detect-planta",
    response_model=PlanPageOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def detect_plan_page_planta(
    resolution_id: str,
    order_index: int,
    background: BackgroundTasks,
    use_case: RequestPlantaDetectionUseCase = Depends(get_request_planta_detection_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Read again the planta of a plan page from its title (e.g. after an OCR error)."""
    page = use_case.execute(resolution_id, order_index, user.sub)
    await manager.notify_change()
    background.add_task(_detect_and_notify, resolution_id, order_index, manager)
    return _to_plan_page_out(page)


@router.get("/{resolution_id}/plan-pages/{order_index}")
def get_plan_page(
    resolution_id: str,
    order_index: int,
    use_case: GetPlanPageUseCase = Depends(get_get_plan_page_use_case),
    user: UserProfile = Depends(get_current_user),
):
    """Image bytes of a floor-plan page — same Bearer-blob pattern as get_page."""
    content, content_type = use_case.execute(resolution_id, order_index, user.sub)
    return Response(content=content, media_type=content_type)


@router.delete("/{resolution_id}/plan-pages/{order_index}", response_model=ResolutionDetail)
async def delete_plan_page(
    resolution_id: str,
    order_index: int,
    use_case: DeletePlanPageUseCase = Depends(get_delete_plan_page_use_case),
    manager: ResolutionsConnectionManager = Depends(get_connection_manager),
    user: UserProfile = Depends(get_current_user),
):
    """Remove one floor-plan page (e.g. wrong planta, bad photo) — mainly for the web."""
    resolution = use_case.execute(resolution_id, order_index, user.sub)
    await manager.notify_change()
    return _to_detail(resolution)


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
        user = verify_token(token or "")
    except DomainException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception:
        logger.exception("Error inesperado validando el token del WS de resoluciones.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    is_mobile = is_mobile_user_agent(websocket.headers.get("user-agent", ""))

    presence = SocketPresence(user.sub, CHANNEL_RESOLUTIONS, is_mobile)
    await presence.start()
    await manager.connect(websocket, user.sub, is_mobile)
    try:
        while True:
            # The client sends nothing on this socket: it is only used for server -> browser notifications.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await presence.stop()
        await manager.disconnect(websocket)
