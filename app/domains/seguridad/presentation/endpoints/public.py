from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.application.use_cases.sync_user_rbac_use_case import SyncUserRbacUseCase
from app.domains.seguridad.presentation.deps import (
    get_current_user,
    get_sync_user_rbac_use_case,
    get_db,
)
from app.domains.seguridad.presentation.schemas.auth_schema import (
    PublicMessageResponse,
    PrivateProfileResponse,
    DatabaseHealthResponse,
)
from app.core.config import settings

router = APIRouter(tags=["Rutas Públicas y Protegidas"])


@router.get("/public", response_model=PublicMessageResponse)
def public_route():
    """Endpoint sin protección, accesible públicamente para pruebas de conectividad."""
    return PublicMessageResponse(
        message="Este endpoint es publico, no requiere login"
    )


@router.get("/health/db", response_model=DatabaseHealthResponse)
def health_database(db: Session = Depends(get_db)):
    """Verifica el estado de conexión con el motor de base de datos PostgreSQL."""
    try:
        db.execute(text("SELECT 1"))
        return DatabaseHealthResponse(
            status="online",
            database=settings.DB_NAME,
            message="Conexión exitosa con el servidor PostgreSQL",
        )
    except Exception as exc:
        return DatabaseHealthResponse(
            status="error",
            database=settings.DB_NAME,
            message=f"Error al conectar con PostgreSQL: {exc}",
        )


@router.get("/private", response_model=PrivateProfileResponse)
def private_route(
    current_user: UserProfile = Depends(get_current_user),
    sync_rbac: SyncUserRbacUseCase = Depends(get_sync_user_rbac_use_case),
):
    """
    Endpoint protegido: Requiere un token Bearer válido emitido por Keycloak.
    Valida el token, garantiza que el usuario exista en PostgreSQL (tabla 'usuario') y
    retorna datos de identidad, roles de Keycloak y permisos locales RBAC ya asignados.
    """
    id_usuario = None
    permisos = []

    try:
        user_entity, permisos = sync_rbac.execute(
            keycloak_sub=current_user.sub,
            username=current_user.username,
            correo=current_user.email,
        )
        id_usuario = user_entity.id_usuario
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning(f"Aviso al sincronizar con la base de datos: {exc}")

    return PrivateProfileResponse(
        message="¡Accediste a un endpoint protegido de Keycloak!",
        usuario=current_user.username,
        email=current_user.email,
        roles=current_user.roles,
        client_id=current_user.client_id,
        id_usuario=id_usuario,
        permisos=permisos,
    )
