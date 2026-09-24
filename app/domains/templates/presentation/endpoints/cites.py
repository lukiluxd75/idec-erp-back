from typing import List

from fastapi import APIRouter, Depends, status

from app.domains.security.contracts import UserProfile, require_permission
from app.domains.templates.application.use_cases import (
    CreateCiteConfiguracionUseCase,
    GenerateCiteUseCase,
    ListCiteConfiguracionesUseCase,
    ListCitesUseCase,
)
from app.domains.templates.domain.entities.cite import CiteConfiguracion, CiteGenerado
from app.domains.templates.presentation.deps import (
    get_create_cite_configuracion_use_case,
    get_generate_cite_use_case,
    get_list_cite_configuraciones_use_case,
    get_list_cites_use_case,
)
from app.domains.templates.presentation.schemas.cite_schema import (
    CiteConfiguracionOut,
    CiteGeneradoOut,
    CreateCiteConfiguracionRequest,
    GenerateCiteRequest,
)

router = APIRouter(tags=["CITES"])


def _configuracion_to_out(c: CiteConfiguracion) -> CiteConfiguracionOut:
    return CiteConfiguracionOut(
        id=c.id,
        area_codigo=c.area_codigo,
        tipo_documento_codigo=c.tipo_documento_codigo,
        nombre=c.nombre,
        formato=c.formato,
        longitud_numero=c.longitud_numero,
        reinicia_por_gestion=c.reinicia_por_gestion,
        activa=c.activa,
    )


def _generado_to_out(g: CiteGenerado) -> CiteGeneradoOut:
    return CiteGeneradoOut(
        id=g.id,
        cite_configuracion_id=g.cite_configuracion_id,
        gestion=g.gestion,
        numero_correlativo=g.numero_correlativo,
        codigo=g.codigo,
        documento_id=g.documento_id,
        tramite_id=g.tramite_id,
        estado=g.estado,
        motivo_anulacion=g.motivo_anulacion,
        generado_en=g.generado_en,
        generado_por=g.generado_por,
    )


@router.get("/configuraciones", response_model=List[CiteConfiguracionOut])
def list_configuraciones(
    use_case: ListCiteConfiguracionesUseCase = Depends(get_list_cite_configuraciones_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """Siglas (área + tipo de documento) registradas, cada una con su propio contador."""
    return [_configuracion_to_out(c) for c in use_case.execute()]


@router.post("/configuraciones", response_model=CiteConfiguracionOut, status_code=status.HTTP_201_CREATED)
def create_configuracion(
    payload: CreateCiteConfiguracionRequest,
    use_case: CreateCiteConfiguracionUseCase = Depends(get_create_cite_configuracion_use_case),
    _user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Registra una nueva sigla."""
    configuracion = use_case.execute(
        area_codigo=payload.area_codigo,
        tipo_documento_codigo=payload.tipo_documento_codigo,
        nombre=payload.nombre,
        formato=payload.formato,
        longitud_numero=payload.longitud_numero,
        reinicia_por_gestion=payload.reinicia_por_gestion,
    )
    return _configuracion_to_out(configuracion)


@router.post("/generar", response_model=CiteGeneradoOut, status_code=status.HTTP_201_CREATED)
def generate_cite(
    payload: GenerateCiteRequest,
    use_case: GenerateCiteUseCase = Depends(get_generate_cite_use_case),
    user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Emite el siguiente CITE correlativo para una sigla. Cambiar de sigla usa
    un contador distinto -- empieza en 01 la primera vez que se use esa
    combinación de área + tipo de documento."""
    cite = use_case.execute(
        area_codigo=payload.area_codigo,
        tipo_documento_codigo=payload.tipo_documento_codigo,
        documento_id=payload.documento_id,
        tramite_id=payload.tramite_id,
        user_sub=user.sub,
        gestion=payload.gestion,
    )
    return _generado_to_out(cite)


@router.get("", response_model=List[CiteGeneradoOut])
def list_cites(
    use_case: ListCitesUseCase = Depends(get_list_cites_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """Historial de CITES emitidos, más recientes primero."""
    return [_generado_to_out(g) for g in use_case.execute()]
