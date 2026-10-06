import importlib.util
import logging
import pkgutil
import app.domains as domains_pkg

logger = logging.getLogger(__name__)

# --- Registro de routers (ambos dominios integrados) ---
try:
    from app.domains.folder_analysis.presentation.router import router as folder_analysis_router
    api_router.include_router(folder_analysis_router, prefix="/folder-analysis")
except Exception as exc:
    logger.warning("Could not load domain 'folder_analysis': %s", exc)

try:
    from app.domains.cite.presentation.router import router as cite_router
    api_router.include_router(cite_router)
except Exception as exc:
    logger.warning("Could not load domain 'cite': %s", exc)


# --- Función de descubrimiento automático de dominios ---
def discover_domains():
    known = set(registered_domains())
    found = []
    for module in pkgutil.iter_modules(domains_pkg.__path__):
        if not module.ispkg or module.name in known:
            continue
        router_path = f"app.domains.{module.name}.presentation.router"
        try:
            spec = importlib.util.find_spec(router_path)
        except (ImportError, AttributeError, ValueError):
            # find_spec imports parent packages, so a domain whose __init__ is broken raises here.
            continue
        if spec is not None:
            found.append(module.name)
    return tuple(found)