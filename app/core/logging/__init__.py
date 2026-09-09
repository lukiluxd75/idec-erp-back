"""
Logging estructurado transversal a todos los dominios.
Pendiente de implementación — ver ARQUITECTURA.md §11.
Hoy cada módulo usa `logging.getLogger("uvicorn.error")` de forma ad-hoc; este paquete
es donde centralizar formato JSON y contexto (dominio/usuario/request-id) cuando se justifique.
"""
