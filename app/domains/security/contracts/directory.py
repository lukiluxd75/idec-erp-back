"""
Public entry point of the `security` domain to put a name to a `sub`, for a
domain that stores its rows by the Keycloak subject and has to say on screen
whose they are (CLAUDE.md §2: "Domain A -> Domain B contracts/" is the only
allowed path -- never a join against the `users` table from another domain).

Usage from another domain, e.g. folder_analysis:

    from app.domains.security.contracts import UsernameLookup, get_username_lookup

    @router.get("/folders")
    def list_folders(owners: UsernameLookup = Depends(get_username_lookup)):
        names = owners(folder.user_sub for folder in folders)   # sub -> username

Only for naming what is already being shown. It is not an authorization check
and it is not a user directory: who may see a row is decided before this, with
require_permission / has_permission.
"""
from typing import Callable, Dict, Iterable, Optional

from fastapi import Depends

from app.domains.security.domain.ports import UserRepositoryPort
from app.domains.security.presentation.deps import get_user_repository

# subs -> {sub: username}.
UsernameLookup = Callable[[Iterable[Optional[str]]], Dict[str, str]]


def get_username_lookup(
    users: UserRepositoryPort = Depends(get_user_repository),
) -> UsernameLookup:
    """One lookup per distinct sub, so a list of rows that belong to two people
    costs two queries and not one per row. Meant for the handful of rows a
    search answers with, not for a listing of the whole table."""

    def lookup(subs: Iterable[Optional[str]]) -> Dict[str, str]:
        found: Dict[str, str] = {}
        for sub in dict.fromkeys(sub for sub in subs if sub):
            user = users.get_by_keycloak_sub(sub)
            if user and user.username:
                found[sub] = user.username
        return found

    return lookup
