"""
Dependency injection factories para el dominio CITE.
Siguen el mismo patrón que folios/presentation/deps.py:
  get_<repo> → get_<use_case>
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.cite.application.use_cases import (
    CrearConfiguracionCiteUseCase,
    GenerarCiteUseCase,
)
from app.domains.cite.domain.ports import CiteRepositoryPort
from app.domains.cite.infrastructure.sql_cite_repository import SqlCiteRepository


def get_cite_repository(db: Session = Depends(get_db)) -> CiteRepositoryPort:
    return SqlCiteRepository(db=db)


def get_crear_configuracion_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> CrearConfiguracionCiteUseCase:
    return CrearConfiguracionCiteUseCase(repository=repo)


def get_generar_cite_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> GenerarCiteUseCase:
    return GenerarCiteUseCase(repository=repo)
