from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database.connection import init_db_tables
from app.core.errors.handlers import register_exception_handlers
from app.registry import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):

    init_db_tables()
    yield


def create_application() -> FastAPI:

    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Backend con Arquitectura Limpia e Integración OpenID Connect / Keycloak",
        lifespan=lifespan,
    )

    # Configuración de CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registro de manejadores de excepciones del Dominio
    register_exception_handlers(application)

    # Inclusión de routers de la capa de presentación
    application.include_router(api_router, prefix=settings.API_V1_STR)

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8061, reload=True)