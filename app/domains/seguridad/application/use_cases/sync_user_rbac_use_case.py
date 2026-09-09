from typing import List, Optional, Tuple

from app.domains.seguridad.domain.entities.rbac import UserEntity
from app.domains.seguridad.domain.exceptions import UsuarioInactivoException
from app.domains.seguridad.domain.ports.user_repository_port import UserRepositoryPort


INSTITUTIONAL_SUB_SENTINEL = "institucional"


class SyncUserRbacUseCase:
    """
    Caso de uso: garantiza que el usuario autenticado por Keycloak tenga un registro en
    PostgreSQL (vinculado por keycloak_sub) y recupera los permisos que ya le fueron
    asignados en el modelo RBAC interno.

    No asigna roles a partir de los roles de Keycloak: CLAUDE.md §5 es explícito en que
    nunca se toma una decisión de autorización de negocio a partir del rol de Keycloak
    directamente. Lo que sí hace (delegado en SqlUserRepository.ensure_user_exists) es
    darle a todo usuario nuevo un punto de partida fijo — área "Catastro" + rol "Inicio",
    no elegido en base a nada de Keycloak — en vez de dejarlo sin ningún permiso hasta que
    un admin se lo asigne a mano desde PermisosPage.

    Caso "institucional": cuando el token no trae 'sub' (p. ej. un token de tipo
    client_credentials, o de una cuenta de Keycloak que no representa a una persona —
    como las credenciales de admin-cli/realm master usadas hoy para pruebas), no hay
    identidad individual real que vincular. En vez de descartar el intento de sync, se
    reutiliza siempre el mismo usuario 'Institucional' (vía INSTITUTIONAL_SUB_SENTINEL),
    igual que hacía la versión anterior del backend. OJO: esto significa que ninguna
    acción hecha bajo estas condiciones se puede auditar por persona — confirmar con el
    equipo si esto es aceptable a largo plazo o si hace falta un usuario Keycloak real
    por persona (ver CLAUDE.md §10).
    """

    def __init__(self, user_repository: UserRepositoryPort):
        self._user_repository = user_repository

    def execute(
        self, keycloak_sub: str, username: str, correo: Optional[str] = None
    ) -> Tuple[UserEntity, List[str]]:
        clean_sub = (keycloak_sub or "").strip()
        clean_username = (username or "").strip() or "usuario_anonimo"

        if not clean_sub:
            clean_sub = INSTITUTIONAL_SUB_SENTINEL
            clean_username = clean_username if clean_username != "usuario_anonimo" else "Institucional"

        usuario_existente = self._user_repository.get_by_keycloak_sub(clean_sub)
        if usuario_existente and not usuario_existente.activo:
            raise UsuarioInactivoException(
                "Tu usuario está inactivo. Contactá a un administrador."
            )

        user_entity = self._user_repository.ensure_user_exists(
            keycloak_sub=clean_sub, username=clean_username, correo=correo
        )
        permissions = self._user_repository.get_user_permissions(clean_sub)
        return user_entity, permissions
