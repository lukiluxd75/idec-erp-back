from typing import Optional, Dict


class DomainException(Exception):
    """
    Excepción base para todas las excepciones de dominio del ERP (cualquier dominio).
    Cada subclase declara `http_status` y, opcionalmente, `headers` para que el manejador
    genérico de core/errors/handlers.py sepa cómo traducirla a HTTP sin conocer el tipo concreto.
    """
    http_status: int = 400
    headers: Optional[Dict[str, str]] = None

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnauthorizedException(DomainException):
    """Se lanza cuando el usuario está autenticado pero no tiene permiso para la acción solicitada."""
    http_status = 403
