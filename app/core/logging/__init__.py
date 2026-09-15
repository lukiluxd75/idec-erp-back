"""
Structured logging shared across all domains.
Pending implementation — see ARQUITECTURA.md §11.
Today each module uses `logging.getLogger("uvicorn.error")` ad-hoc; this package
is where JSON format and context (domain/user/request-id) will be centralized when needed.
"""
