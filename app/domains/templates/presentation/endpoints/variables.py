from typing import List

from fastapi import APIRouter, Depends, status

from app.domains.security.contracts import UserProfile, require_permission
from app.domains.templates.application.use_cases import CreateVariableUseCase, ListVariablesUseCase
from app.domains.templates.domain.entities.variable import Variable
from app.domains.templates.presentation.deps import (
    get_create_variable_use_case,
    get_list_variables_use_case,
)
from app.domains.templates.presentation.schemas.variable_schema import (
    CreateVariableRequest,
    VariableOut,
)

router = APIRouter(tags=["Variables"])


def _to_out(v: Variable) -> VariableOut:
    return VariableOut(
        id=v.id,
        nombre=v.nombre,
        clave=v.clave,
        tipo_dato=v.tipo_dato,
        descripcion=v.descripcion,
        valor_predeterminado=v.valor_predeterminado,
        activa=v.activa,
        creado_en=v.creado_en,
    )


@router.get("", response_model=List[VariableOut])
def list_variables(
    use_case: ListVariablesUseCase = Depends(get_list_variables_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """Todas las variables reutilizables registradas."""
    return [_to_out(v) for v in use_case.execute()]


@router.post("", response_model=VariableOut, status_code=status.HTTP_201_CREATED)
def create_variable(
    payload: CreateVariableRequest,
    use_case: CreateVariableUseCase = Depends(get_create_variable_use_case),
    _user: UserProfile = Depends(require_permission("templates.edit")),
):
    """Registra una nueva variable reutilizable."""
    variable = use_case.execute(
        nombre=payload.nombre,
        clave=payload.clave,
        tipo_dato=payload.tipo_dato,
        descripcion=payload.descripcion,
        valor_predeterminado=payload.valor_predeterminado,
    )
    return _to_out(variable)
