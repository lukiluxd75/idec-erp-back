"""
Endpoints HTTP del módulo CITE.

POST /cite/configuraciones  → CrearConfiguracionCiteUseCase
POST /cite/generar          → GenerarCiteUseCase (core transaccional)

Ambos requieren un usuario autenticado (Bearer JWT vía Keycloak).
La sesión de BD tiene autocommit=False (definida en connection.py), por lo que el
commit ocurre al salir del bloque `with db.begin()` dentro del repositorio, o en el
cierre limpio del generador get_db(). Si el use_case lanza una DomainException el
handler global hace rollback implícito al no haberse commiteado nada.
"""
import logging

from fastapi import APIRouter, Depends, status

from app.domains.cite.application.use_cases import (
    CrearConfiguracionCiteUseCase,
    GenerarCiteUseCase,
)
from app.domains.cite.presentation.deps import (
    get_crear_configuracion_use_case,
    get_generar_cite_use_case,
)
from app.domains.cite.presentation.schemas import (
    ConfiguracionCiteResponse,
    CrearConfiguracionCiteRequest,
    DocumentoCiteResponse,
    GenerarCiteRequest,
)
from app.domains.security.contracts import UserProfile, get_current_user

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/cite", tags=["CITE - Motor de Generación"])


# ── Configurador ──────────────────────────────────────────────────────────────

@router.post(
    "/configuraciones",
    response_model=ConfiguracionCiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ConfiguracionCite",
    description=(
        "Registra un nuevo prefijo CITE para un área en una gestión determinada. "
        "La gestión debe estar activa y el prefijo debe ser único para ese año."
    ),
)
def crear_configuracion(
    body: CrearConfiguracionCiteRequest,
    use_case: CrearConfiguracionCiteUseCase = Depends(get_crear_configuracion_use_case),
    user: UserProfile = Depends(get_current_user),
) -> ConfiguracionCiteResponse:
    configuracion = use_case.execute(
        id_area=body.id_area,
        id_gestion=body.id_gestion,
        prefijo=body.prefijo,
    )
    logger.info(
        "CITE config creada: prefijo=%s gestion=%s area=%s by=%s",
        configuracion.prefijo,
        configuracion.id_gestion,
        configuracion.id_area,
        user.sub,
    )
    return ConfiguracionCiteResponse(
        id_configuracion=configuracion.id_configuracion,
        id_area=configuracion.id_area,
        id_gestion=configuracion.id_gestion,
        prefijo=configuracion.prefijo,
        activo=configuracion.activo,
    )


# ── Generador Transaccional ───────────────────────────────────────────────────

@router.post(
    "/generar",
    response_model=DocumentoCiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generar CITE",
    description=(
        "Genera un nuevo CITE de forma atómica y concurrentemente segura. "
        "Usa SELECT ... FOR UPDATE para serializar el correlativo; "
        "el UNIQUE constraint (id_configuracion, correlativo) actúa como red de seguridad."
    ),
)
def generar_cite(
    body: GenerarCiteRequest,
    use_case: GenerarCiteUseCase = Depends(get_generar_cite_use_case),
    user: UserProfile = Depends(get_current_user),
) -> DocumentoCiteResponse:
    documento = use_case.execute(
        id_configuracion=body.id_configuracion,
        referencia=body.referencia,
        id_funcionario_remitente=body.id_funcionario_remitente,
    )
    logger.info(
        "CITE generado: %s (id=%s) por funcionario=%s user=%s",
        documento.codigo_cite_completo,
        documento.id_documento,
        documento.id_funcionario_remitente,
        user.sub,
    )
    return DocumentoCiteResponse(
        id_documento=documento.id_documento,
        id_configuracion=documento.id_configuracion,
        prefijo=documento.prefijo,
        correlativo=documento.correlativo,
        codigo_cite_completo=documento.codigo_cite_completo,
        fecha_generacion=documento.fecha_generacion,
        referencia=documento.referencia,
        id_funcionario_remitente=documento.id_funcionario_remitente,
    )
