from typing import Optional, Dict


class DomainException(Exception):
    """
    Base exception for all ERP domain exceptions (any domain).
    Each subclass declares `http_status` and optionally `headers` so the generic
    handler in core/errors/handlers.py can map it to HTTP without knowing the concrete type.
    """
    http_status: int = 400
    headers: Optional[Dict[str, str]] = None

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnauthorizedException(DomainException):
    """Raised when the user is authenticated but lacks permission for the requested action."""
    http_status = 403
