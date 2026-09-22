from typing import List

from fastapi import APIRouter, Depends, status

from app.domains.security.contracts import UserProfile, require_permission
from app.domains.templates.application.use_cases import (
    CreateTemplateUseCase,
    DeleteTemplateUseCase,
    GetTemplateUseCase,
    ListTemplatesUseCase,
    UpdateTemplateUseCase,
)
from app.domains.templates.domain.entities.template import Template
from app.domains.templates.presentation.deps import (
    get_create_template_use_case,
    get_delete_template_use_case,
    get_list_templates_use_case,
    get_template_use_case,
    get_update_template_use_case,
)
from app.domains.templates.presentation.schemas.template_schema import (
    CreateTemplateRequest,
    TemplateDetail,
    TemplateListItem,
    UpdateTemplateRequest,
)

router = APIRouter(tags=["Plantillas"])


def _to_list_item(t: Template) -> TemplateListItem:
    return TemplateListItem(
        id=t.id,
        nombre=t.nombre,
        codigo=t.codigo,
        area=t.area,
        tipo_documento=t.tipo_documento,
        version=t.version,
        activa=t.activa,
        creado_en=t.creado_en,
    )


def _to_detail(t: Template) -> TemplateDetail:
    return TemplateDetail(
        id=t.id,
        nombre=t.nombre,
        codigo=t.codigo,
        area=t.area,
        tipo_documento=t.tipo_documento,
        version=t.version,
        activa=t.activa,
        creado_en=t.creado_en,
        descripcion=t.descripcion,
        contenido_html=t.contenido_html,
        actualizado_en=t.actualizado_en,
        creado_por=t.creado_por,
        actualizado_por=t.actualizado_por,
    )


@router.get("", response_model=List[TemplateListItem])
def list_templates(
    use_case: ListTemplatesUseCase = Depends(get_list_templates_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """Catálogo de plantillas registradas, más recientes primero."""
    return [_to_list_item(t) for t in use_case.execute()]


@router.post("", response_model=TemplateDetail, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: CreateTemplateRequest,
    use_case: CreateTemplateUseCase = Depends(get_create_template_use_case),
    user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Registra una nueva plantilla dinámica."""
    template = use_case.execute(
        nombre=payload.nombre,
        codigo=payload.codigo,
        area=payload.area,
        tipo_documento=payload.tipo_documento,
        contenido_html=payload.contenido_html,
        descripcion=payload.descripcion,
        user_sub=user.sub,
    )
    return _to_detail(template)


@router.get("/{template_id}", response_model=TemplateDetail)
def get_template(
    template_id: int,
    use_case: GetTemplateUseCase = Depends(get_template_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """Detalle de una plantilla, incluido su contenido HTML."""
    return _to_detail(use_case.execute(template_id))


@router.put("/{template_id}", response_model=TemplateDetail)
def update_template(
    template_id: int,
    payload: UpdateTemplateRequest,
    use_case: UpdateTemplateUseCase = Depends(get_update_template_use_case),
    user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Edita los campos enviados de una plantilla (actualización parcial)."""
    changes = payload.model_dump(exclude_unset=True)
    template = use_case.execute(template_id, changes, user_sub=user.sub)
    return _to_detail(template)


@router.delete("/{template_id}", response_model=TemplateDetail)
def delete_template(
    template_id: int,
    use_case: DeleteTemplateUseCase = Depends(get_delete_template_use_case),
    user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Desactiva una plantilla (soft delete -- ver DeleteTemplateUseCase)."""
    return _to_detail(use_case.execute(template_id, user_sub=user.sub))
