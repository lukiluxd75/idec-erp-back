from fastapi import APIRouter
from app.domains.seguridad.presentation.endpoints.auth import router as auth_router
from app.domains.seguridad.presentation.endpoints.public import router as public_router
from app.domains.seguridad.presentation.endpoints.rbac_admin import router as rbac_admin_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(public_router)
router.include_router(rbac_admin_router, prefix="/seguridad")
