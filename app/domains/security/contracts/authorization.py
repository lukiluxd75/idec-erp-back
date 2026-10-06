"""
Public entry point of the `security` domain to require a concrete RBAC permission
from another domain, without importing anything from security internal layers
(CLAUDE.md §2: "Domain A -> Domain B contracts/" is the only allowed path).

Usage from another domain, e.g. cadastre:

    from app.domains.security.contracts import require_permission

    @router.post("/predios")
    def create_parcel(current_user = Depends(require_permission("catastro.predios.crear"))):
        ...
"""
from app.domains.security.presentation.deps import has_permission, require_permission

__all__ = ["has_permission", "require_permission"]
