from fastapi import APIRouter

from app.domains.templates.presentation.endpoints.cites import router as cites_router
from app.domains.templates.presentation.endpoints.documents import router as documents_router
from app.domains.templates.presentation.endpoints.templates import router as templates_router
from app.domains.templates.presentation.endpoints.variables import router as variables_router

router = APIRouter()
router.include_router(variables_router, prefix="/templates/variables")
router.include_router(cites_router, prefix="/templates/cites")
router.include_router(documents_router, prefix="/templates/documents")
router.include_router(templates_router, prefix="/templates")
