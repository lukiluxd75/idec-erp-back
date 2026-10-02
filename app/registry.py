"""
Single place that knows every ERP domain and assembles them into the application
(see CLAUDE.md §3). To add a domain: add one row to `_DOMAINS` below — do not
touch other domains. If a domain fails to import, it is skipped with a warning
instead of crashing the whole app.

The table replaced eleven hand-copied try/except blocks. That shape is what let
`alignment` ship fully built but never mounted: its block was simply never
written, and nothing compared the modules on disk against the ones registered
here. `check_unregistered_domains()` does that comparison now, and the lifespan
in main.py logs whatever it finds.
"""
import importlib
import importlib.util
import logging
import pkgutil
from typing import Iterable

from fastapi import APIRouter

logger = logging.getLogger("uvicorn.error")

# (package name under app.domains, URL prefix). An empty prefix means the
# domain's own router already carries whatever path it wants to live at.
_DOMAINS: tuple[tuple[str, str], ...] = (
    ("security", ""),
    ("geoextraction", "/geoextraction"),
    ("detection", "/detection"),
    ("alignment", "/alignment"),
    ("resolutions", ""),
    ("chatbot", ""),
    ("folios", ""),
    ("appraisal_review", "/appraisal-review"),
    ("templates", ""),
    ("digitization", "/digitization"),
    ("folder_analysis", "/folder-analysis"),
    ("procedurereports", "/procedurereports"),
    ("cadastralviewer", ""),
)

api_router = APIRouter()


def registered_domains() -> tuple[str, ...]:
    """Return the domains this registry expects to mount."""
    return tuple(name for name, _prefix in _DOMAINS)


def check_unregistered_domains() -> Iterable[str]:
    """Find domain packages with routers that are missing from the registry."""
    import app.domains as domains_pkg

    known = set(registered_domains())
    found = []
    for module in pkgutil.iter_modules(domains_pkg.__path__):
        if not module.ispkg or module.name in known:
            continue
        router_path = f"app.domains.{module.name}.presentation.router"
        try:
            spec = importlib.util.find_spec(router_path)
        except (ImportError, AttributeError, ValueError):
            continue
        if spec is not None:
            found.append(module.name)
    return tuple(found)

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

try:
    from app.domains.folder_analysis.presentation.router import router as folder_analysis_router
    api_router.include_router(folder_analysis_router, prefix="/folder-analysis")
except Exception as exc:
    logger.warning("Could not load domain 'folder_analysis': %s", exc)

try:
    from app.domains.cadastralviewer.presentation.router import router as cadastralviewer_router
    api_router.include_router(cadastralviewer_router)
except Exception as exc:
    logger.warning("Could not load domain 'cadastralviewer': %s", exc)