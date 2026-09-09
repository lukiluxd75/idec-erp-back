import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors.exceptions import DomainException

logger = logging.getLogger("uvicorn.error")


def register_exception_handlers(app: FastAPI) -> None:


    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException):
        logger.warning(f"{request.method} {request.url.path} -> {exc.http_status}: {exc.message}")
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.message},
            headers=exc.headers,
        )
