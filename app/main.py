import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database.connection import init_db_tables
from app.core.errors.handlers import register_exception_handlers
from app.core.middleware.request_id import RequestIdMiddleware
from app.core.middleware.pagination import PaginationMiddleware
from app.registry import api_router, check_unregistered_domains

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):

    init_db_tables()

    unregistered = check_unregistered_domains()
    if unregistered:
        logger.warning(
            "Dominios presentes en app/domains/ pero NO registrados en registry.py "
            "(sus endpoints no existen): %s",
            ", ".join(unregistered),
        )

    yield


def create_application() -> FastAPI:

    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Backend con Arquitectura Limpia e Integración OpenID Connect / Keycloak",
        lifespan=lifespan,
    )

    # CORS configuration (FRONTEND_ORIGIN may be a comma-separated list)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(PaginationMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Expose Content-Disposition so the browser can read download filenames.
        expose_headers=["Content-Disposition", "X-Request-ID", "X-Total-Count", "X-Page-Limit", "X-Page-Offset"],
    )

    # Register domain exception handlers
    register_exception_handlers(application)

    # Include presentation-layer routers
    application.include_router(api_router, prefix=settings.API_V1_STR)

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8061, reload=True)
