"""
Public entry point of the `security` domain for the rest of the ERP domains.
Any other domain that needs to know "who is the authenticated user" imports
from here — never from `domains.security.presentation.deps` or its internal layers
(see CLAUDE.md §2: "Domain A -> Domain B contracts/" is the only allowed path).
"""
from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.presentation.deps import get_auth_provider, get_current_user
from app.domains.security.application.use_cases import VerifyTokenUseCase


def verify_token(raw_token: str) -> UserProfile:
    """
    Variant of `get_current_user` for transports that cannot send an
    `Authorization` header (e.g. the `resolutions` domain WebSocket, which receives
    the token via query string — the browser WebSocket API does not allow custom headers).
    Validates the token the same way as `get_current_user`, but from a raw string
    instead of FastAPI's `Security(HTTPBearer())` dependency.
    """
    return VerifyTokenUseCase(auth_provider=get_auth_provider()).execute(raw_token)


__all__ = ["UserProfile", "get_current_user", "verify_token"]
