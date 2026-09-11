import logging
from typing import List

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, WebSocket, WebSocketDisconnect, status

from app.core.errors.exceptions import DomainException
from app.domains.resoluciones.application.use_cases import (
    CrearResolucionUseCase,
    EliminarResolucionUseCase,
    GuardarTablaUseCase,
    ListarResolucionesUseCase,
    ObtenerPaginaUseCase,
    ObtenerResolucionUseCase,
)
from app.domains.resoluciones.domain.entities.resolucion import Resolucion
from app.domains.resoluciones.infrastructure.ws_connection_manager import ResolucionesConnectionManager
from app.domains.resoluciones.presentation.deps import (
    get_connection_manager,
    get_crear_resolucion_use_case,
    get_eliminar_resolucion_use_case,
    get_guardar_tabla_use_case,
    get_listar_resoluciones_use_case,
    get_obtener_pagina_use_case,
    get_obtener_resolucion_use_case,
)
from app.domains.resoluciones.presentation.schemas.resolucion_schema import (
    GuardarTablaRequest,
    PaginaOut,
    ResolucionDetalle,
    ResolucionListItem,
)
from app.domains.seguridad.contracts import UserProfile, get_current_user, verify_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Resoluciones"])


def _to_list_item(r: Resolucion) -> ResolucionListItem:
    return ResolucionListItem(
        id_resolucion=r.id_resolucion,
        nombre=r.nombre,
        nro_resolucion=r.nro_resolucion,
        estado=r.estado,
        total_paginas=r.total_paginas,
        fecha_creacion=r.fecha_creacion,
    )


def _to_detalle(r: Resolucion) -> ResolucionDetalle:
    return ResolucionDetalle(
        id_resolucion=r.id_resolucion,
        nombre=r.nombre,
        nro_resolucion=r.nro_resolucion,
        estado=r.estado,
        total_paginas=r.total_paginas,
        fecha_creacion=r.fecha_creacion,
        paginas=[PaginaOut(orden=p.orden) for p in r.paginas],
        tabla=r.tabla,
    )


@router.get("", response_model=List[ResolucionListItem])
def listar_resoluciones(
    use_case: ListarResolucionesUseCase = Depends(get_listar_resoluciones_use_case),
    usuario: UserProfile = Depends(get_current_user),
):
    """Lista las resoluciones del usuario autenticado, más nuevas primero."""
    return [_to_list_item(r) for r in use_case.execute(usuario.sub)]


@router.post("", response_model=ResolucionDetalle, status_code=status.HTTP_201_CREATED)
async def crear_resolucion(
    nombre: str = Form(...),
    nro_resolucion: str = Form(...),
    paginas: List[UploadFile] = File(...),
    use_case: CrearResolucionUseCase = Depends(get_crear_resolucion_use_case),
    manager: ResolucionesConnectionManager = Depends(get_connection_manager),
    usuario: UserProfile = Depends(get_current_user),
):
    """Registra una resolución recién escaneada (desde la app móvil) junto con las
    fotos de sus páginas, en el orden en que se suben."""
    contenidos = [((await pagina.read()), pagina.content_type or "image/jpeg") for pagina in paginas]
    resolucion = use_case.execute(
        nombre=nombre, nro_resolucion=nro_resolucion, paginas=contenidos, user_sub=usuario.sub
    )
    await manager.avisar_cambio()
    return _to_detalle(resolucion)


@router.get("/{id_resolucion}", response_model=ResolucionDetalle)
def obtener_resolucion(
    id_resolucion: str,
    use_case: ObtenerResolucionUseCase = Depends(get_obtener_resolucion_use_case),
    usuario: UserProfile = Depends(get_current_user),
):
    """Detalle de una resolución: páginas y la tabla de superficies guardada (si ya se
    corrió/guardó un OCR)."""
    return _to_detalle(use_case.execute(id_resolucion, usuario.sub))


@router.get("/{id_resolucion}/paginas/{orden}")
def obtener_pagina(
    id_resolucion: str,
    orden: int,
    use_case: ObtenerPaginaUseCase = Depends(get_obtener_pagina_use_case),
    usuario: UserProfile = Depends(get_current_user),
):
    """Bytes de la imagen de una página. Requiere Bearer -> no sirve como <img src>
    directo, el frontend la baja como Blob (ver resolucionesApi.paginaBlob)."""
    contenido, content_type = use_case.execute(id_resolucion, orden, usuario.sub)
    return Response(content=contenido, media_type=content_type)


@router.put("/{id_resolucion}/tabla", response_model=ResolucionDetalle)
async def guardar_tabla(
    id_resolucion: str,
    payload: GuardarTablaRequest,
    use_case: GuardarTablaUseCase = Depends(get_guardar_tabla_use_case),
    manager: ResolucionesConnectionManager = Depends(get_connection_manager),
    usuario: UserProfile = Depends(get_current_user),
):
    """Guarda la tabla de superficies (revisada/editada) y el estado del flujo —
    'Guardar borrador' o 'Generar Excel' desde ResolucionPage."""
    resolucion = use_case.execute(id_resolucion, payload.tabla, payload.estado, usuario.sub)
    await manager.avisar_cambio()
    return _to_detalle(resolucion)


@router.delete("/{id_resolucion}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_resolucion(
    id_resolucion: str,
    use_case: EliminarResolucionUseCase = Depends(get_eliminar_resolucion_use_case),
    manager: ResolucionesConnectionManager = Depends(get_connection_manager),
    usuario: UserProfile = Depends(get_current_user),
):
    use_case.execute(id_resolucion, usuario.sub)
    await manager.avisar_cambio()


@router.websocket("/ws")
async def resoluciones_ws(
    websocket: WebSocket,
    manager: ResolucionesConnectionManager = Depends(get_connection_manager),
):
    """
    Canal de novedades en tiempo real: cada vez que alguien crea/edita/borra una
    resolución (desde el celular o desde otra pestaña), se avisa a todos los sockets
    conectados para que refresquen (ver useResolucionesUpdates.js en el frontend).

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
        logger.exception("Error inesperado validando el token del WS de resoluciones.")
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
