#!/usr/bin/env python3
"""
Bootstrap templates.view / templates.edit for development.

Grants those permission codes to every active internal role so existing admins
are not locked out after the templates endpoints start requiring
require_permission (see app/domains/templates/presentation/endpoints/).
Idempotent — safe to run on each deploy to 172.16.65.40.

Run AFTER database/plantillas_dinamicas_postgresql.sql has been applied — this
script only touches the RBAC tables (permission/role), not the plantillas_dinamicas
schema itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database.connection import SessionLocal
from app.domains.security.infrastructure.models import InternalRoleModel, PermissionModel
from app.domains.security.infrastructure.sql_rbac_admin_repository import SqlRbacAdminRepository

CODES = ("templates.view", "templates.edit")


def main() -> None:
    db: Session = SessionLocal()
    try:
        repo = SqlRbacAdminRepository(db)
        for code in CODES:
            permission = repo._get_or_create_permission(code)
            print(f"permission OK {code} -> {permission.id}")
        db.commit()

        roles = (
            db.query(InternalRoleModel)
            .options(joinedload(InternalRoleModel.permissions).joinedload(PermissionModel.resource))
            .filter(InternalRoleModel.is_active.is_(True))
            .all()
        )
        if not roles:
            print("No active roles found — create a role via UI after first login.")
            return

        for role in roles:
            current_codes = []
            for permission in role.permissions or []:
                resource = permission.resource.name if permission.resource else None
                if resource:
                    current_codes.append(f"{resource}.{permission.action}")
            merged = sorted(set(current_codes) | set(CODES))
            if set(merged) == set(current_codes):
                print(f"role already has templates.*: {role.name}")
                continue
            repo.set_role_permissions(str(role.id), merged, actor_user_id=None)
            print(f"role updated: {role.name} -> +templates.view/edit")

        print("bootstrap_templates_permissions done")
    finally:
        db.close()


if __name__ == "__main__":
    main()
