from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.resoluciones.application.use_cases import (
    CrearResolucionUseCase,
    EliminarResolucionUseCase,
    GuardarTablaUseCase,
    ListarResolucionesUseCase,
    ObtenerPaginaUseCase,
    ObtenerResolucionUseCase,
)
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort
from app.domains.resoluciones.infrastructure.sql_resolucion_repository import SqlResolucionRepository
from app.domains.resoluciones.infrastructure.ws_connection_manager import ResolucionesConnectionManager


def get_resolucion_repository(db: Session = Depends(get_db)) -> ResolucionRepositoryPort:
    return SqlResolucionRepository(db=db)


def get_listar_resoluciones_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> ListarResolucionesUseCase:
    return ListarResolucionesUseCase(repository=repo)


def get_obtener_resolucion_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> ObtenerResolucionUseCase:
    return ObtenerResolucionUseCase(repository=repo)


def get_obtener_pagina_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> ObtenerPaginaUseCase:
    return ObtenerPaginaUseCase(repository=repo)


def get_guardar_tabla_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> GuardarTablaUseCase:
    return GuardarTablaUseCase(repository=repo)


def get_eliminar_resolucion_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> EliminarResolucionUseCase:
    return EliminarResolucionUseCase(repository=repo)


def get_crear_resolucion_use_case(
    repo: ResolucionRepositoryPort = Depends(get_resolucion_repository),
) -> CrearResolucionUseCase:
    return CrearResolucionUseCase(repository=repo)


@lru_cache()
def get_connection_manager() -> ResolucionesConnectionManager:
    """Instancia única (singleton cacheado): todos los requests/sockets del mismo
    proceso uvicorn tienen que compartir el mismo registro de conexiones."""
    return ResolucionesConnectionManager()
