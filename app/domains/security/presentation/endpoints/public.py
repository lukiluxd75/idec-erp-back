from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.application.use_cases.sync_user_rbac_use_case import SyncUserRbacUseCase
from app.domains.security.presentation.deps import (
    get_current_user,
    get_sync_user_rbac_use_case,
    get_db,
)
from app.domains.security.presentation.schemas.auth_schema import (
    PublicMessageResponse,
    PrivateProfileResponse,
    DatabaseHealthResponse,
)
from app.core.config import settings

router = APIRouter(tags=["Rutas Públicas y Protegidas"])


@router.get("/public", response_model=PublicMessageResponse)
def public_route():
    """Unprotected endpoint, publicly reachable for connectivity checks."""
    return PublicMessageResponse(
        message="Este endpoint es publico, no requiere login"
    )


@router.get("/health/db", response_model=DatabaseHealthResponse)
def health_database(db: Session = Depends(get_db)):
    """Check connectivity with the PostgreSQL database engine."""
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
    Protected endpoint: requires a valid Bearer token issued by Keycloak.
    Validates the token, ensures the user exists in PostgreSQL (table 'usuario'),
    and returns identity data, Keycloak roles, and local RBAC permissions already
    assigned.
    """
    user_id = None
    permissions = []

    try:
        user_entity, permissions = sync_rbac.execute(
            keycloak_sub=current_user.sub,
            username=current_user.username,
            email=current_user.email,
        )
        user_id = user_entity.user_id
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning(f"Aviso al sincronizar con la base de datos: {exc}")

    return PrivateProfileResponse(
        message="Ha accedido a un endpoint protegido de Keycloak.",
        usuario=current_user.username,
        email=current_user.email,
        roles=current_user.roles,
        client_id=current_user.client_id,
        user_id=user_id,
        permisos=permissions,
    )
