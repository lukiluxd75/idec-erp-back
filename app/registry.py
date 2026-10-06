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

# (package name under app.domains, URL prefix).
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
    ("cite", ""),
)

api_router = APIRouter()

for _name, _prefix in _DOMAINS:
    try:
        _module = importlib.import_module(f"app.domains.{_name}.presentation.router")
        api_router.include_router(_module.router, **({"prefix": _prefix} if _prefix else {}))
    except Exception as exc:
        # exc_info so the log carries the traceback: "No module named 'geoalchemy2'" alone does not say which import pulled it in.
        logger.warning("Could not load domain '%s': %s", _name, exc, exc_info=True)


def registered_domains() -> tuple[str, ...]:
    """Domain names this module tries to mount, in mount order."""
    return tuple(name for name, _ in _DOMAINS)


def check_unregistered_domains() -> Iterable[str]:
    """Names of domains that exist under app/domains/ with a presentation router
    but are absent from `_DOMAINS` — i.e. built but unreachable over HTTP.

    Returns names rather than raising: a half-finished domain sitting on disk is
    normal during development, and refusing to boot over it would be worse than
    saying so. main.py logs the result at startup.
    """
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
            # find_spec imports parent packages, so a domain whose __init__ is broken raises here.
            continue
        if spec is not None:
            found.append(module.name)
    return tuple(found)
