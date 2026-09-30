"""Resolves a Keycloak `sub` (on UserProfile, every authenticated request) to
`public.users.id` -- the UUID `created_by`/`confirmed_by` columns in
`alignment_results` actually reference (see infrastructure/models.py).

Queried by raw SQL against the physical table rather than importing
`security.infrastructure.models`, to keep this domain from depending on
another domain's internals -- `public.users` itself is the documented
exception domains are expected to FK into directly. Duplicated from
`detection/infrastructure/user_lookup.py` rather than imported, since this
backend avoids cross-domain imports (see detection/infrastructure/models.py).
"""
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def resolve_user_id(db: Session, keycloak_sub: Optional[str]) -> Optional[str]:
    if not keycloak_sub:
        return None
    row = db.execute(
        text("SELECT id FROM public.users WHERE keycloak_sub = :sub"),
        {"sub": keycloak_sub},
    ).first()
    return str(row[0]) if row else None


def resolve_usernames(db: Session, user_ids: Iterable[Any]) -> dict[str, str]:
    """Batch reverse lookup (`public.users.id` -> `username`), one query for a
    whole page of results instead of one per row."""
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id, username FROM public.users WHERE id = ANY(:ids)"),
        {"ids": ids},
    ).all()
    return {str(r[0]): r[1] for r in rows}
