from fastapi import APIRouter

from app.domains.templates.presentation.endpoints.cites import router as cites_router
from app.domains.templates.presentation.endpoints.templates import router as templates_router
from app.domains.templates.presentation.endpoints.variables import router as variables_router

router = APIRouter()
# Registered before templates_router: "/templates/variables" and "/templates/cites"
# are static paths, but keeping the more specific routes first mirrors the caution
# in resolutions/presentation/endpoints/resolutions.py ("/presence" before "/{id}").
router.include_router(variables_router, prefix="/templates/variables")
router.include_router(cites_router, prefix="/templates/cites")
router.include_router(templates_router, prefix="/templates")
