from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.templates.application.use_cases import (
    CreateCiteConfiguracionUseCase,
    CreateTemplateUseCase,
    CreateVariableUseCase,
    DeleteTemplateUseCase,
    GenerateCiteUseCase,
    GetTemplateUseCase,
    ListCiteConfiguracionesUseCase,
    ListCitesUseCase,
    ListTemplatesUseCase,
    ListVariablesUseCase,
    UpdateTemplateUseCase,
)
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort
from app.domains.templates.domain.ports.variable_repository_port import VariableRepositoryPort
from app.domains.templates.infrastructure.sql_cite_repository import SqlCiteRepository
from app.domains.templates.infrastructure.sql_template_repository import SqlTemplateRepository
from app.domains.templates.infrastructure.sql_variable_repository import SqlVariableRepository


def get_template_repository(db: Session = Depends(get_db)) -> TemplateRepositoryPort:
    return SqlTemplateRepository(db=db)


def get_variable_repository(db: Session = Depends(get_db)) -> VariableRepositoryPort:
    return SqlVariableRepository(db=db)


def get_list_templates_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
) -> ListTemplatesUseCase:
    return ListTemplatesUseCase(repository=repo)


def get_template_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
) -> GetTemplateUseCase:
    return GetTemplateUseCase(repository=repo)


def get_create_template_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
) -> CreateTemplateUseCase:
    return CreateTemplateUseCase(repository=repo)


def get_update_template_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
) -> UpdateTemplateUseCase:
    return UpdateTemplateUseCase(repository=repo)


def get_delete_template_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
) -> DeleteTemplateUseCase:
    return DeleteTemplateUseCase(repository=repo)


def get_list_variables_use_case(
    repo: VariableRepositoryPort = Depends(get_variable_repository),
) -> ListVariablesUseCase:
    return ListVariablesUseCase(repository=repo)


def get_create_variable_use_case(
    repo: VariableRepositoryPort = Depends(get_variable_repository),
) -> CreateVariableUseCase:
    return CreateVariableUseCase(repository=repo)


def get_cite_repository(db: Session = Depends(get_db)) -> CiteRepositoryPort:
    return SqlCiteRepository(db=db)


def get_list_cite_configuraciones_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> ListCiteConfiguracionesUseCase:
    return ListCiteConfiguracionesUseCase(repository=repo)


def get_create_cite_configuracion_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> CreateCiteConfiguracionUseCase:
    return CreateCiteConfiguracionUseCase(repository=repo)


def get_generate_cite_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> GenerateCiteUseCase:
    return GenerateCiteUseCase(repository=repo)


def get_list_cites_use_case(
    repo: CiteRepositoryPort = Depends(get_cite_repository),
) -> ListCitesUseCase:
    return ListCitesUseCase(repository=repo)

from app.domains.templates.infrastructure.template_engine_client import HttpTemplateEngineClient
from app.domains.templates.application.use_cases.preview_document_use_case import PreviewDocumentUseCase
from app.domains.templates.domain.ports.template_engine_port import TemplateEnginePort

def get_template_engine_client() -> TemplateEnginePort:
    return HttpTemplateEngineClient()

def get_preview_document_use_case(
    repo: TemplateRepositoryPort = Depends(get_template_repository),
    engine_client: TemplateEnginePort = Depends(get_template_engine_client)
) -> PreviewDocumentUseCase:
    return PreviewDocumentUseCase(repository=repo, engine_client=engine_client)
