"""
Punto de entrada público del dominio `seguridad` para el resto de dominios del ERP.
Cualquier otro dominio que necesite saber "quién es el usuario autenticado" importa
desde aquí — nunca desde `domains.seguridad.presentation.deps` ni de sus capas internas
(ver CLAUDE.md §2: "Dominio A -> contracts/ de Dominio B" es el único punto permitido).
"""
from app.domains.seguridad.domain.entities.user import UserProfile
from app.domains.seguridad.presentation.deps import get_current_user

__all__ = ["UserProfile", "get_current_user"]
