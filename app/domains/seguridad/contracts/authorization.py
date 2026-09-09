"""
Punto de entrada público del dominio `seguridad` para exigir un permiso RBAC concreto
desde otro dominio, sin importar nada de las capas internas de seguridad
(CLAUDE.md §2: "Dominio A -> contracts/ de Dominio B" es el único punto permitido).

Uso desde otro dominio, ej. catastro:

    from app.domains.seguridad.contracts import require_permission

    @router.post("/predios")
    def crear_predio(current_user = Depends(require_permission("catastro.predios.crear"))):
        ...
"""
from app.domains.seguridad.presentation.deps import require_permission

__all__ = ["require_permission"]
