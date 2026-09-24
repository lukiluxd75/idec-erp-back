"""
Single place that knows every ERP domain and assembles them into the application
(see CLAUDE.md §3). To add a domain: register its router here — do not touch other
domains. If a domain fails to import, it is skipped with a warning instead of
crashing the whole app.
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger("uvicorn.error")

api_router = APIRouter()

try:
    from app.domains.security.presentation.router import router as security_router
    api_router.include_router(security_router)
except Exception as exc:
    logger.warning("Could not load domain 'security': %s", exc)

try:
    from app.domains.geoextraction.presentation.router import router as geoextraction_router
    api_router.include_router(geoextraction_router, prefix="/geoextraction")
except Exception as exc:
    logger.warning("Could not load domain 'geoextraction': %s", exc)

try:
    from app.domains.detection.presentation.router import router as detection_router
    api_router.include_router(detection_router, prefix="/detection")
except Exception as exc:
    logger.warning("Could not load domain 'detection': %s", exc)

try:
    from app.domains.resolutions.presentation.router import router as resolutions_router
    api_router.include_router(resolutions_router)
except Exception as exc:
    logger.warning("Could not load domain 'resolutions': %s", exc)

try:
    from app.domains.chatbot.presentation.router import router as chatbot_router
    api_router.include_router(chatbot_router)
except Exception as exc:
    logger.warning("Could not load domain 'chatbot': %s", exc)

try:
    from app.domains.folios.presentation.router import router as folios_router
    api_router.include_router(folios_router)
except Exception as exc:
    logger.warning("Could not load domain 'folios': %s", exc)

try:
    from app.domains.appraisal_review.presentation.router import router as appraisal_review_router
    api_router.include_router(appraisal_review_router, prefix="/appraisal-review")
except Exception as exc:
    logger.warning("Could not load domain 'appraisal_review': %s", exc)

try:
    from app.domains.templates.presentation.router import router as templates_router
    api_router.include_router(templates_router)
except Exception as exc:
    logger.warning("Could not load domain 'templates': %s", exc)

try:
    from app.domains.digitization.presentation.router import router as digitization_router
    api_router.include_router(digitization_router, prefix="/digitization")
except Exception as exc:
    logger.warning("Could not load domain 'digitization': %s", exc)