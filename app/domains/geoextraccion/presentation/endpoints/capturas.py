import logging
from typing import List

from fastapi import APIRouter, Depends, File, Response, UploadFile, WebSocket, WebSocketDisconnect, status

from app.core.errors.exceptions import DomainException
from app.domains.geoextraccion.application.use_cases import (
    CrearCapturaUseCase,
    DescartarCapturaUseCase,
    ListarCapturasPendientesUseCase,
    ObtenerImagenCapturaUseCase,
)
from app.domains.geoextraccion.domain.entities.captura import Captura
from app.domains.geoextraccion.infrastructure.ws_connection_manager import CapturasConnectionManager
from app.domains.geoextraccion.presentation.deps import (
    get_connection_manager,
    get_crear_captura_use_case,
    get_descartar_captura_use_case,
    get_listar_capturas_pendientes_use_case,
    get_obtener_imagen_captura_use_case,
)
from app.domains.geoextraccion.presentation.schemas.captura_schema import CapturaListItem
from app.domains.seguridad.contracts import UserProfile, get_current_user, verify_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/capturas", tags=["Geoextracción · Capturas"])


def _to_list_item(c: Captura) -> CapturaListItem:
    return CapturaListItem(id_captura=c.id_captura, mime=c.mime, fecha_creacion=c.fecha_creacion)


@router.get("", response_model=List[CapturaListItem])
def listar_capturas(
    use_case: ListarCapturasPendientesUseCase = Depends(get_listar_capturas_pendientes_use_case),
    usuario: UserProfile = Depends(get_current_user),
):
    """Capturas que el usuario mandó desde el celular y todavía no cargó en el visor."""
    return [_to_list_item(c) for c in use_case.execute(usuario.sub)]


@router.post("", response_model=CapturaListItem, status_code=status.HTTP_201_CREATED)
async def crear_captura(
    archivo: UploadFile = File(...),
    use_case: CrearCapturaUseCase = Depends(get_crear_captura_use_case),
    manager: CapturasConnectionManager = Depends(get_connection_manager),
    usuario: UserProfile = Depends(get_current_user),
):
    """Registra una foto recién sacada desde la app móvil (geoextract móvil: solo saca
    la foto y la manda acá — el recorte, el OCR y todo lo demás se hacen en la web)."""
    contenido = await archivo.read()
    captura = use_case.execute(
        contenido=contenido, mime=archivo.content_type or "image/jpeg", user_sub=usuario.sub
    )
    await manager.avisar_cambio()
    return _to_list_item(captura)


@router.get("/{id_captura}/imagen")
def obtener_imagen(
    id_captura: str,
    use_case: ObtenerImagenCapturaUseCase = Depends(get_obtener_imagen_captura_use_case),
    usuario: UserProfile = Depends(get_current_user),
):
    """Bytes de la imagen de una captura. Requiere Bearer -> no sirve como <img src>
    directo, el frontend la baja como Blob (ver geoextraccionApi.capturaBlob)."""
    contenido, mime = use_case.execute(id_captura, usuario.sub)
    return Response(content=contenido, media_type=mime)


@router.delete("/{id_captura}", status_code=status.HTTP_204_NO_CONTENT)
async def descartar_captura(
    id_captura: str,
    use_case: DescartarCapturaUseCase = Depends(get_descartar_captura_use_case),
    manager: CapturasConnectionManager = Depends(get_connection_manager),
    usuario: UserProfile = Depends(get_current_user),
):
    """Saca la captura del store: la web la llama apenas terminó de cargarla en el
    visor, para que no vuelva a aparecer en la lista de pendientes."""
    use_case.execute(id_captura, usuario.sub)
    await manager.avisar_cambio()


@router.websocket("/ws")
async def capturas_ws(
    websocket: WebSocket,
    manager: CapturasConnectionManager = Depends(get_connection_manager),
):
    """
    Canal de novedades en tiempo real: cada vez que llega una foto nueva desde el
    celular (o se descarta una), se avisa a todos los sockets conectados para que
    refresquen la lista (ver useCapturasUpdates.js en el frontend).

    El navegador no puede mandar el header Authorization en un WebSocket, así que el
    token viaja por query string y se valida acá a mano (contracts.verify_token) en vez
    de con la dependencia Security(HTTPBearer()) que usan los endpoints REST.
    """
    token = websocket.query_params.get("token")
    try:
        verify_token(token or "")
    except DomainException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception:
        logger.exception("Error inesperado validando el token del WS de capturas.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await manager.conectar(websocket)
    try:
        while True:
            # El cliente no manda nada por este socket: solo se usa para notificar en
            # el sentido servidor -> browser. receive_text() sirve para detectar el
            # cierre de conexión (WebSocketDisconnect) sin busy-waiting.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.desconectar(websocket)
